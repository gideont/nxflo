"""Google-authenticated customer portal API. No development authentication endpoints."""
from functools import wraps
from hashlib import sha256
import hmac
import json
import os
from pathlib import Path
import secrets
import tempfile
import sqlite3

from flask import Flask, g, jsonify, request
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from . import db

PREFIX = '/bms_integration_hub/api'
COOKIE_PATH = '/bms_integration_hub'
DEFAULT_CLIENT_ID = '658474600728-2rikqi8fb8r0qk5l4ir10a1goe42ohof.apps.googleusercontent.com'


class APIError(Exception):
    def __init__(self, message, status=400):
        self.message, self.status = message, status


def google_verifier(credential, audience):
    from google.auth.transport.requests import Request
    from google.oauth2 import id_token
    class TimedRequest(Request):
        def __call__(self, *args, **kwargs):
            kwargs['timeout'] = 10
            return super().__call__(*args, **kwargs)
    return id_token.verify_oauth2_token(credential, TimedRequest(), audience)


def persistent_secret(path):
    secret_path = Path(path).parent / '.auth-signing-key'
    if secret_path.exists():
        value = secret_path.read_bytes()
        if len(value) != 32:
            raise RuntimeError('The persistent signing key is invalid')
        return value
    # Link a completely written file so concurrent starts cannot read an empty key.
    fd, temporary = tempfile.mkstemp(dir=secret_path.parent, prefix='.auth-key-')
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(secrets.token_bytes(32))
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, secret_path)
        except FileExistsError:
            pass
    finally:
        os.unlink(temporary)
    return persistent_secret(path)


def create_app(config=None, verifier=None):
    app = Flask(__name__)
    app.config.update(
        DATABASE=os.environ.get('BMS_DATABASE_PATH', '/data/bms_hub.sqlite3'),
        GOOGLE_CLIENT_ID=os.environ.get('BMS_GOOGLE_CLIENT_ID', DEFAULT_CLIENT_ID),
        OWNER_EMAIL=os.environ.get('BMS_OWNER_EMAIL', 'gideont@gmail.com'),
        PUBLIC_ORIGIN=os.environ.get('BMS_PUBLIC_ORIGIN', 'https://www.nxflo.com'),
        COOKIE_SECURE=True,
        MAX_CONTENT_LENGTH=16384,
    )
    if config:
        app.config.update(config)
    if verifier and not app.testing:
        raise RuntimeError('Injected identity verifiers are allowed only in isolated tests')
    verify = verifier or google_verifier
    db.migrate(app.config['DATABASE'])
    os.chmod(app.config['DATABASE'], 0o600)
    secret = app.config.get('SIGNING_KEY') or persistent_secret(app.config['DATABASE'])
    signer = URLSafeTimedSerializer(secret, salt='bms-google-login')
    cookie_name = '__Secure-bms_session' if app.config['COOKIE_SECURE'] else 'bms_session'
    challenge_cookie = '__Secure-bms_login' if app.config['COOKIE_SECURE'] else 'bms_login'

    def conn():
        if 'db' not in g:
            g.db = db.connect(app.config['DATABASE'])
        return g.db

    def csrf_for(token):
        return hmac.new(secret, token.encode(), sha256).hexdigest()

    def payload(allowed):
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or set(data) - set(allowed):
            raise APIError('Invalid request fields')
        return data

    def text(data, key, limit, required=False):
        value = data.get(key, '')
        if not isinstance(value, str) or len(value.strip()) > limit or (required and not value.strip()):
            raise APIError(f'Enter a valid {key.replace("_", " ")}')
        return value.strip()

    def integer(value, label='ID'):
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise APIError(f'Invalid {label}')
        return value

    def permission_keys(value):
        if not isinstance(value, list) or any(not isinstance(v, str) for v in value) or set(value) - db.PERMISSIONS.keys():
            raise APIError('Select valid permissions from the permission catalog')
        keys = set(value)
        if any(key.rsplit('.', 1)[0] + '.view' not in keys for key in keys):
            raise APIError('Create, edit, and delete permissions require view access')
        return sorted(keys)

    def login_required(owner=False, approved=True):
        def decorate(fn):
            @wraps(fn)
            def wrapped(*args, **kwargs):
                token = request.cookies.get(cookie_name, '')
                user = conn().execute('''SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id
                                         WHERE s.token_hash=? AND s.revoked_at IS NULL AND s.expires_at>?''',
                                      (db.token_hash(token), db.now())).fetchone() if token else None
                if user is None:
                    raise APIError('Please sign in to continue', 401)
                if user['status'] in ('rejected', 'revoked'):
                    raise APIError('Your access is no longer active', 401)
                if approved and user['status'] != 'approved':
                    raise APIError('Your account is awaiting administrator approval', 403)
                if owner and not user['is_owner']:
                    raise APIError('Portal owner access is required', 403)
                if request.method not in ('GET', 'HEAD', 'OPTIONS'):
                    if not hmac.compare_digest(request.headers.get('X-CSRF-Token', ''), csrf_for(token)):
                        raise APIError('Your session could not be verified. Reload and try again.', 403)
                g.user = user
                g.session_token = token
                return fn(*args, **kwargs)
            return wrapped
        return decorate

    @app.before_request
    def generator_upload_limit():
        if request.path.startswith('/bms_integration_hub/api/admin/generator'):
            request.max_content_length = 32 * 1024 * 1024

    @app.before_request
    def protect_origin():
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            if request.headers.get('Origin') != app.config['PUBLIC_ORIGIN']:
                raise APIError('Request origin is not allowed', 403)

    @app.after_request
    def privacy_headers(response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Robots-Tag'] = 'noindex, nofollow, noarchive, nosnippet'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    @app.teardown_appcontext
    def close_db(_error):
        connection = g.pop('db', None)
        if connection:
            connection.close()

    @app.errorhandler(APIError)
    def api_error(error):
        return jsonify(error=error.message), error.status

    @app.errorhandler(sqlite3.IntegrityError)
    def integrity_error(_error):
        return jsonify(error='This change conflicts with an existing or protected record.'), 409

    @app.errorhandler(sqlite3.OperationalError)
    def database_error(error):
        app.logger.error('Database operation failed: %s', type(error).__name__)
        return jsonify(error='The workspace is temporarily busy. Please try again.'), 503

    @app.errorhandler(404)
    def not_found(_error):
        return jsonify(error='Not found'), 404

    @app.errorhandler(413)
    def too_large(_error):
        return jsonify(error='Request is too large'), 413

    @app.errorhandler(500)
    def internal_error(_error):
        return jsonify(error='The request could not be completed. Please try again.'), 500

    @app.get(PREFIX + '/health')
    def health():
        version = conn().execute('SELECT max(version) FROM schema_migrations').fetchone()[0]
        return jsonify(status='ok', schema_version=version)

    @app.get(PREFIX + '/auth/config')
    def auth_config():
        challenge = {'csrf': secrets.token_urlsafe(32), 'nonce': secrets.token_urlsafe(32)}
        response = jsonify(client_id=app.config['GOOGLE_CLIENT_ID'], csrf_token=challenge['csrf'], nonce=challenge['nonce'])
        response.set_cookie(challenge_cookie, signer.dumps(challenge), max_age=600, secure=app.config['COOKIE_SECURE'],
                            httponly=True, samesite='Lax', path=COOKIE_PATH)
        return response

    @app.post(PREFIX + '/auth/google')
    def google_login():
        data = payload(('credential',))
        try:
            challenge = signer.loads(request.cookies.get(challenge_cookie, ''), max_age=600)
        except (BadSignature, SignatureExpired):
            raise APIError('Your sign-in request expired. Reload and try again.', 403)
        if not hmac.compare_digest(request.headers.get('X-CSRF-Token', ''), challenge['csrf']):
            raise APIError('Your sign-in request could not be verified', 403)
        credential = data.get('credential')
        if not isinstance(credential, str) or not 1 <= len(credential) <= 12000:
            raise APIError('A Google credential is required')
        try:
            claims = verify(credential, app.config['GOOGLE_CLIENT_ID'])
        except ValueError:
            raise APIError('Google sign-in could not be verified', 401)
        except Exception:
            app.logger.warning('Google verification service unavailable')
            raise APIError('Google sign-in is temporarily unavailable. Please try again.', 503)
        if not isinstance(claims.get('nonce'), str) or not hmac.compare_digest(claims['nonce'], challenge['nonce']):
            raise APIError('Google sign-in request does not match this browser session', 401)
        try:
            user, token = db.login_identity(conn(), claims, app.config['OWNER_EMAIL'])
        except ValueError as error:
            raise APIError(str(error), 401)
        response = jsonify(user=user, status=user['status'])
        response.delete_cookie(challenge_cookie, path=COOKIE_PATH, secure=app.config['COOKIE_SECURE'], httponly=True, samesite='Lax')
        # A fresh verified sign-in replaces any previous browser session.
        old_token = request.cookies.get(cookie_name)
        if old_token:
            with db.transaction(conn()):
                conn().execute('UPDATE sessions SET revoked_at=? WHERE token_hash=?', (db.now(), db.token_hash(old_token)))
        if token:
            response.set_cookie(cookie_name, token, max_age=db.session_seconds(user['is_owner']), secure=app.config['COOKIE_SECURE'],
                                httponly=True, samesite='Lax', path=COOKIE_PATH)
        else:
            response.delete_cookie(cookie_name, path=COOKIE_PATH, secure=app.config['COOKIE_SECURE'], httponly=True, samesite='Lax')
        return response

    @app.get(PREFIX + '/me')
    @login_required(approved=False)
    def me():
        response = jsonify(user=db.user_data(conn(), g.user), permissions=db.permissions_for(conn(), g.user),
                           csrf_token=csrf_for(g.session_token))
        if g.user['is_owner']:
            # Renew only an active authenticated owner session; never revive revoked/expired sessions.
            changed = conn().execute('UPDATE sessions SET expires_at=? WHERE token_hash=? AND revoked_at IS NULL AND expires_at>?',
                (db.session_expiry(True), db.token_hash(g.session_token), db.now())).rowcount
            if not changed:
                raise APIError('Please sign in to continue', 401)
            response.set_cookie(cookie_name, g.session_token, max_age=db.session_seconds(True),
                                httponly=True, secure=app.config['COOKIE_SECURE'], samesite='Lax', path=COOKIE_PATH)
        return response

    @app.post(PREFIX + '/auth/logout')
    @login_required(approved=False)
    def logout():
        with db.transaction(conn()):
            conn().execute('UPDATE sessions SET revoked_at=? WHERE token_hash=?', (db.now(), db.token_hash(g.session_token)))
        response = jsonify(ok=True)
        response.delete_cookie(cookie_name, path=COOKIE_PATH, secure=app.config['COOKIE_SECURE'], httponly=True, samesite='Lax')
        return response

    @app.get(PREFIX + '/projects')
    @login_required()
    def projects():
        if not g.user['is_owner'] and 'projects.view' not in db.permissions_for(conn(), g.user):
            raise APIError('Your role does not permit project access', 403)
        if g.user['is_owner']:
            rows = conn().execute('SELECT * FROM projects ORDER BY name COLLATE NOCASE')
        else:
            rows = conn().execute('''SELECT p.* FROM projects p JOIN user_project_access a ON a.project_id=p.id
                                     WHERE a.user_id=? ORDER BY p.name COLLATE NOCASE''', (g.user['id'],))
        return jsonify(projects=[dict(row) for row in rows])

    @app.get(PREFIX + '/projects/<int:project_id>')
    @login_required()
    def project(project_id):
        if not db.can_access(conn(), g.user, project_id, 'projects.view'):
            raise APIError('Project not found', 404)
        return jsonify(project=dict(conn().execute('SELECT * FROM projects WHERE id=?', (project_id,)).fetchone()),
                       permissions=db.permissions_for(conn(), g.user))

    @app.get(PREFIX + '/admin/users')
    @login_required(owner=True)
    def users():
        query = request.args.get('q', '')[:200].lower()
        status = request.args.get('status', '')
        if status and status not in ('pending', 'approved', 'rejected', 'revoked'):
            raise APIError('Invalid account status')
        rows = conn().execute('''SELECT * FROM users WHERE (?='' OR status=?)
                                AND (?='' OR instr(lower(email),?)>0 OR instr(lower(display_name),?)>0)
                                ORDER BY is_owner DESC,created_at DESC,id DESC''', (status, status, query, query, query))
        return jsonify(users=[db.user_data(conn(), row) for row in rows])

    @app.patch(PREFIX + '/admin/users/<int:user_id>')
    @login_required(owner=True)
    def update_user(user_id):
        data = payload(('status', 'role_id', 'project_ids', 'reason'))
        reason = text(data, 'reason', 1000)
        with db.transaction(conn()):
            target = conn().execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone()
            if not target:
                raise APIError('User not found', 404)
            if target['is_owner']:
                raise APIError('The portal owner account is protected', 403)
            before = db.user_data(conn(), target)
            status = data.get('status', target['status'])
            transitions = {'pending': {'pending', 'approved', 'rejected'}, 'approved': {'approved', 'revoked'},
                           'rejected': {'rejected', 'approved'}, 'revoked': {'revoked', 'approved'}}
            if not isinstance(status, str) or status not in transitions[target['status']]:
                raise APIError('This status transition is not allowed')
            role_id = data.get('role_id', target['role_id'])
            if role_id is not None:
                integer(role_id, 'role')
                if not conn().execute('SELECT 1 FROM roles WHERE id=?', (role_id,)).fetchone():
                    raise APIError('Role not found')
            if status == 'approved' and role_id is None:
                raise APIError('Choose a role before approving this account')
            if 'project_ids' in data:
                project_ids = data['project_ids']
                if not isinstance(project_ids, list) or len(project_ids) > 1000:
                    raise APIError('Invalid project assignments')
                project_ids = sorted({integer(value, 'project') for value in project_ids})
                for project_id in project_ids:
                    if not conn().execute('SELECT 1 FROM projects WHERE id=?', (project_id,)).fetchone():
                        raise APIError('An assigned project does not exist')
                current = set(before['project_ids'])
                for project_id in current - set(project_ids):
                    conn().execute('DELETE FROM user_project_access WHERE user_id=? AND project_id=?', (user_id, project_id))
                for project_id in set(project_ids) - current:
                    conn().execute('INSERT INTO user_project_access VALUES(?,?,?,?)', (user_id, project_id, g.user['id'], db.now()))
            changed_status = status != target['status']
            conn().execute('''UPDATE users SET status=?,role_id=?,updated_at=?,status_changed_at=?,status_changed_by=? WHERE id=?''',
                           (status, role_id, db.now(), db.now() if changed_status else target['status_changed_at'],
                            g.user['id'] if changed_status else target['status_changed_by'], user_id))
            if changed_status and status in ('rejected', 'revoked'):
                conn().execute('UPDATE sessions SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL', (db.now(), user_id))
            after = db.user_data(conn(), conn().execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone())
            action = ('user.restored' if status == 'approved' and target['status'] in ('rejected', 'revoked') else
                      'user.' + status if changed_status else 'user.access_updated')
            audit_before = {key: before[key] for key in ('email', 'status', 'role_id', 'role_name', 'project_ids')}
            audit_after = {key: after[key] for key in ('email', 'status', 'role_id', 'role_name', 'project_ids')}
            db.audit(conn(), g.user['id'], action, 'users', user_id, audit_before, audit_after, user_id, reason)
        return jsonify(user=after)

    @app.get(PREFIX + '/admin/permissions')
    @login_required(owner=True)
    def permission_catalog():
        return jsonify(permissions=[{'key': key, 'module': module, 'action': action, 'label': label}
                                    for key, (module, action, label) in db.PERMISSIONS.items()])

    @app.get(PREFIX + '/admin/roles')
    @login_required(owner=True)
    def roles():
        return jsonify(roles=[db.role_data(conn(), row) for row in conn().execute('SELECT * FROM roles ORDER BY id')])

    @app.post(PREFIX + '/admin/roles')
    @login_required(owner=True)
    def create_role():
        data = payload(('name', 'description', 'permissions'))
        name, description = text(data, 'name', 80, True), text(data, 'description', 500)
        keys = permission_keys(data.get('permissions', []))
        with db.transaction(conn()):
            timestamp = db.now()
            role_id = conn().execute('INSERT INTO roles(name,description,created_at,updated_at) VALUES(?,?,?,?)',
                                     (name, description, timestamp, timestamp)).lastrowid
            conn().executemany('INSERT INTO role_permissions VALUES(?,?)', [(role_id, key) for key in keys])
            role = db.role_data(conn(), conn().execute('SELECT * FROM roles WHERE id=?', (role_id,)).fetchone())
            db.audit(conn(), g.user['id'], 'role.created', 'roles', role_id, after=role)
        return jsonify(role=role), 201

    @app.patch(PREFIX + '/admin/roles/<int:role_id>')
    @login_required(owner=True)
    def update_role(role_id):
        data = payload(('name', 'description', 'permissions', 'version', 'confirm_affected_count'))
        name, description = text(data, 'name', 80, True), text(data, 'description', 500)
        keys = permission_keys(data.get('permissions', []))
        with db.transaction(conn()):
            row = conn().execute('SELECT * FROM roles WHERE id=?', (role_id,)).fetchone()
            if not row:
                raise APIError('Role not found', 404)
            before = db.role_data(conn(), row)
            if type(data.get('version')) is not int or data['version'] != before['version']:
                raise APIError('This role changed. Reload it before saving.', 409)
            if type(data.get('confirm_affected_count')) is not int or data['confirm_affected_count'] != before['user_count']:
                raise APIError('The number of affected users changed. Reload and review before saving.', 409)
            conn().execute('UPDATE roles SET name=?,description=?,version=version+1,updated_at=? WHERE id=?',
                           (name, description, db.now(), role_id))
            conn().execute('DELETE FROM role_permissions WHERE role_id=?', (role_id,))
            conn().executemany('INSERT INTO role_permissions VALUES(?,?)', [(role_id, key) for key in keys])
            after = db.role_data(conn(), conn().execute('SELECT * FROM roles WHERE id=?', (role_id,)).fetchone())
            db.audit(conn(), g.user['id'], 'role.updated', 'roles', role_id, before, after)
        return jsonify(role=after)

    @app.delete(PREFIX + '/admin/roles/<int:role_id>')
    @login_required(owner=True)
    def delete_role(role_id):
        payload(())
        with db.transaction(conn()):
            row = conn().execute('SELECT * FROM roles WHERE id=?', (role_id,)).fetchone()
            if not row:
                raise APIError('Role not found', 404)
            before = db.role_data(conn(), row)
            if before['user_count']:
                raise APIError('Reassign every user before deleting this role', 409)
            db.audit(conn(), g.user['id'], 'role.deleted', 'roles', role_id, before=before)
            conn().execute('DELETE FROM roles WHERE id=?', (role_id,))
        return jsonify(ok=True)

    @app.get(PREFIX + '/admin/projects')
    @login_required(owner=True)
    def admin_projects():
        return jsonify(projects=[dict(row) for row in conn().execute('SELECT * FROM projects ORDER BY name COLLATE NOCASE')])

    @app.post(PREFIX + '/admin/projects')
    @login_required(owner=True)
    def create_project():
        data = payload(('name',))
        name = text(data, 'name', 120, True)
        with db.transaction(conn()):
            project_id = conn().execute('INSERT INTO projects(name,created_at) VALUES(?,?)', (name, db.now())).lastrowid
            project = dict(conn().execute('SELECT * FROM projects WHERE id=?', (project_id,)).fetchone())
            db.audit(conn(), g.user['id'], 'project.created', 'projects', project_id, after=project)
        return jsonify(project=project), 201

    @app.get(PREFIX + '/admin/audit')
    @login_required(owner=True)
    def access_history():
        before = request.args.get('before', '')
        if before and (not before.isascii() or not before.isdecimal() or len(before) > 16 or int(before) < 1):
            raise APIError('Invalid history cursor')
        rows = conn().execute('''SELECT a.*,actor.email actor_email,subject.email subject_email FROM audit_log a
                                LEFT JOIN users actor ON actor.id=a.actor_user_id LEFT JOIN users subject ON subject.id=a.subject_user_id
                                WHERE (?='' OR a.id<?) ORDER BY a.id DESC LIMIT 51''', (before, int(before) if before else 0)).fetchall()
        entries = [dict(row) for row in rows[:50]]
        for entry in entries:
            before_json, after_json = entry.pop('before_json'), entry.pop('after_json')
            entry['before'] = json.loads(before_json) if before_json is not None else None
            entry['after'] = json.loads(after_json) if after_json is not None else None
        return jsonify(entries=entries, next_cursor=entries[-1]['id'] if len(rows) > 50 else None)

    from .workspace import register_workspace
    register_workspace(app, conn, login_required, payload, APIError)
    from .admin_preferences import register_admin_preferences
    register_admin_preferences(app, conn, login_required)

    from .analytics import register_analytics
    register_analytics(app, conn, login_required, secret)
    from .generator import register_generator
    register_generator(app, conn, login_required, APIError)
    return app
