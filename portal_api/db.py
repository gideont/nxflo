"""SQLite storage and transactional authorization primitives for the customer portal."""
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from hashlib import sha256
import json
from pathlib import Path
import secrets
import sqlite3

MODULES = {
    'projects': 'Project directory',
    'requirements': 'Requirements',
    'planning': 'Project planning',
    'tasks': 'Task lists',
    'architecture': 'Architecture',
    'monitoring': 'Monitoring',
}
PERMISSIONS = {
    f'{module}.{action}': (module, action, label)
    for module, label in MODULES.items()
    for action in (('view',) if module in ('projects', 'monitoring') else ('view', 'create', 'edit', 'delete'))
}


OWNER_SESSION_SECONDS = 30 * 24 * 3600
MEMBER_SESSION_SECONDS = 8 * 3600


def session_seconds(owner):
    return OWNER_SESSION_SECONDS if owner else MEMBER_SESSION_SECONDS


def session_expiry(owner):
    return (datetime.now(timezone.utc) + timedelta(seconds=session_seconds(owner))).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def now():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def token_hash(value):
    return sha256(value.encode()).hexdigest()


def connect(path):
    conn = sqlite3.connect(str(path), timeout=5, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    conn.execute('PRAGMA busy_timeout=5000')
    conn.execute('PRAGMA synchronous=FULL')
    return conn


@contextmanager
def transaction(conn):
    conn.execute('BEGIN IMMEDIATE')
    try:
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise


def migrate(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = connect(path)
    try:
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)')
        with transaction(conn):
            versions = {r[0] for r in conn.execute('SELECT version FROM schema_migrations')}
            if versions - {1, 2}:
                raise RuntimeError('Database schema is newer than this application')
            if 1 in versions:
                apply_workspace_migration(conn, versions)
                return
            statement = ''
            for line in (Path(__file__).parent / 'migrations/001_initial.sql').read_text().splitlines():
                statement += line + '\n'
                if sqlite3.complete_statement(statement):
                    conn.execute(statement)
                    statement = ''
            conn.executemany('INSERT INTO permissions(key,module,action,label) VALUES(?,?,?,?)',
                             [(key, *values) for key, values in PERMISSIONS.items()])
            timestamp = now()
            for name, description in (
                ('Viewer', 'Read access to assigned projects.'),
                ('Engineer', 'Create and edit requirements, tasks, and architecture in assigned projects.'),
                ('Project Manager', 'Create and edit content across assigned project workspaces.'),
            ):
                role_id = conn.execute('INSERT INTO roles(name,description,is_builtin,created_at,updated_at) VALUES(?,?,1,?,?)',
                                       (name, description, timestamp, timestamp)).lastrowid
                keys = [key for key, (module, action, _) in PERMISSIONS.items()
                        if action == 'view' or (action in ('create', 'edit') and
                           (name == 'Project Manager' or (name == 'Engineer' and module in ('requirements', 'tasks', 'architecture'))))]
                conn.executemany('INSERT INTO role_permissions VALUES(?,?)', [(role_id, key) for key in keys])
            conn.execute('INSERT INTO schema_migrations VALUES(1,?)', (timestamp,))
            apply_workspace_migration(conn, versions)
    finally:
        conn.close()


def apply_workspace_migration(conn, versions):
    if 2 in versions:
        return
    statement = ''
    for line in (Path(__file__).parent / 'migrations/002_workspace.sql').read_text().splitlines():
        statement += line + '\n'
        if sqlite3.complete_statement(statement):
            conn.execute(statement)
            statement = ''
    conn.execute('INSERT INTO schema_migrations VALUES(2,?)', (now(),))


def audit(conn, actor, action, entity_type, entity_id, before=None, after=None, subject=None, reason=''):
    conn.execute('''INSERT INTO audit_log(actor_user_id,subject_user_id,entity_type,entity_id,action,before_json,after_json,reason,created_at)
                    VALUES(?,?,?,?,?,?,?,?,?)''',
                 (actor, subject, entity_type, entity_id, action,
                  json.dumps(before, ensure_ascii=False) if before is not None else None,
                  json.dumps(after, ensure_ascii=False) if after is not None else None, reason, now()))


def user_data(conn, row):
    result = dict(row)
    result['project_ids'] = [r[0] for r in conn.execute('SELECT project_id FROM user_project_access WHERE user_id=? ORDER BY project_id', (row['id'],))]
    role = conn.execute('SELECT name FROM roles WHERE id=?', (row['role_id'],)).fetchone()
    result['role_name'] = role[0] if role else None
    return result


def role_data(conn, row):
    result = dict(row)
    result['permissions'] = [r[0] for r in conn.execute('SELECT permission_key FROM role_permissions WHERE role_id=? ORDER BY permission_key', (row['id'],))]
    result['user_count'] = conn.execute('SELECT count(*) FROM users WHERE role_id=?', (row['id'],)).fetchone()[0]
    return result


def permissions_for(conn, user):
    if user['is_owner']:
        return sorted(PERMISSIONS)
    return [r[0] for r in conn.execute('SELECT permission_key FROM role_permissions WHERE role_id=? ORDER BY permission_key', (user['role_id'],))]


def can_access(conn, user, project_id, permission):
    if user['status'] != 'approved' or permission not in PERMISSIONS:
        return False
    if not conn.execute('SELECT 1 FROM projects WHERE id=?', (project_id,)).fetchone():
        return False
    if user['is_owner']:
        return True
    return bool(conn.execute('''SELECT 1 FROM user_project_access a JOIN role_permissions p ON p.role_id=?
                                WHERE a.user_id=? AND a.project_id=? AND p.permission_key=?''',
                             (user['role_id'], user['id'], project_id, permission)).fetchone())


def login_identity(conn, claims, owner_email):
    """Called only after server-side Google signature/audience/issuer/expiry/nonce verification."""
    if not isinstance(claims.get('sub'), str) or not claims['sub'] or claims.get('email_verified') is not True:
        raise ValueError('A verified Google account is required')
    email = str(claims.get('email', '')).strip().lower()
    if '@' not in email or len(email) > 320:
        raise ValueError('Google did not return a valid email')
    name = str(claims.get('name') or email)[:200]
    timestamp = now()
    with transaction(conn):
        user = conn.execute('SELECT * FROM users WHERE google_subject=?', (claims['sub'],)).fetchone()
        if user is None:
            owner_exists = conn.execute('SELECT 1 FROM users WHERE is_owner=1').fetchone()
            is_owner = email == owner_email.lower() and not owner_exists
            user_id = conn.execute('''INSERT INTO users(google_subject,email,display_name,email_verified,status,is_owner,created_at,updated_at,last_login_at,status_changed_at)
                                      VALUES(?,?,?,1,?,?,?,?,?,?)''',
                                   (claims['sub'], email, name, 'approved' if is_owner else 'pending', int(is_owner),
                                    timestamp, timestamp, timestamp, timestamp)).lastrowid
            if is_owner:
                conn.execute('UPDATE users SET status_changed_by=? WHERE id=?', (user_id, user_id))
            audit(conn, user_id if is_owner else None, 'owner.bootstrapped' if is_owner else 'user.registered',
                  'users', user_id, after={'email': email, 'status': 'approved' if is_owner else 'pending'}, subject=user_id)
        else:
            user_id = user['id']
            if email != user['email'] or name != user['display_name']:
                audit(conn, user_id, 'user.profile_updated', 'users', user_id,
                      before={'email': user['email'], 'display_name': user['display_name']},
                      after={'email': email, 'display_name': name}, subject=user_id)
            # Identity refresh cannot modify ownership, approval, role, or project assignments.
            conn.execute('UPDATE users SET email=?,display_name=?,email_verified=1,updated_at=?,last_login_at=? WHERE id=?',
                         (email, name, timestamp, timestamp, user_id))
        user = conn.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone()
        if user['status'] in ('rejected', 'revoked'):
            return dict(user), None
        raw_token = secrets.token_urlsafe(32)
        expiry = session_expiry(user['is_owner'])
        conn.execute('INSERT INTO sessions(token_hash,user_id,created_at,expires_at) VALUES(?,?,?,?)',
                     (token_hash(raw_token), user_id, timestamp, expiry))
        conn.execute('DELETE FROM sessions WHERE expires_at < ?',
                     ((datetime.now(timezone.utc) - timedelta(days=7)).isoformat(timespec='milliseconds').replace('+00:00', 'Z'),))
        return dict(user), raw_token
