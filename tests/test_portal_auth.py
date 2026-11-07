from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from portal_api import create_app, PREFIX, google_verifier
from portal_api import db
from portal_api.backup import backup

ORIGIN = 'http://localhost'


def fake_verifier(credential, audience):
    claims = json.loads(credential)
    if claims.pop('invalid', False):
        raise ValueError('Invalid Google token')
    return claims


def make_test_app(path):
    return create_app({'TESTING': True, 'DATABASE': str(path), 'PUBLIC_ORIGIN': ORIGIN,
                       'COOKIE_SECURE': False, 'SIGNING_KEY': b'test-signing-key-not-used-in-production'}, verifier=fake_verifier)


def sign_in(client, subject='owner', email='gideont@gmail.com', **overrides):
    config = client.get(PREFIX + '/auth/config').get_json()
    claims = {'sub': subject, 'email': email, 'email_verified': True, 'name': subject.title(), 'nonce': config['nonce']}
    claims.update(overrides)
    return client.post(PREFIX + '/auth/google', json={'credential': json.dumps(claims)},
                       headers={'Origin': ORIGIN, 'X-CSRF-Token': config['csrf_token']})


class PortalAccessTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.path = Path(self.temp.name) / 'bms_hub.sqlite3'
        self.app = make_test_app(self.path)
        self.owner = self.app.test_client()
        self.assertEqual(sign_in(self.owner).status_code, 200)
        self.owner_id = self.owner.get(PREFIX + '/me').get_json()['user']['id']
        self.member = self.app.test_client()
        self.assertEqual(sign_in(self.member, 'member', 'member@example.com').status_code, 200)
        self.member_id = self.member.get(PREFIX + '/me').get_json()['user']['id']
        self.viewer = self.role('Viewer')
        self.engineer = self.role('Engineer')

    def tearDown(self):
        self.temp.cleanup()

    def connection(self):
        return db.connect(self.path)

    def role(self, name):
        return next(r for r in self.owner.get(PREFIX + '/admin/roles').get_json()['roles'] if r['name'] == name)

    def mutate(self, path, data, client=None, method='PATCH'):
        client = client or self.owner
        csrf = client.get(PREFIX + '/me').get_json().get('csrf_token', '')
        return client.open(PREFIX + path, method=method, json=data, headers={'Origin': ORIGIN, 'X-CSRF-Token': csrf})

    def approve(self, projects=None, role=None):
        return self.mutate('/admin/users/' + str(self.member_id), {'status':'approved', 'role_id':(role or self.viewer)['id'], 'project_ids':projects or []})

    def project(self, name):
        response = self.mutate('/admin/projects', {'name':name}, method='POST')
        self.assertEqual(response.status_code, 201)
        return response.get_json()['project']

    def test_schema_defaults_foreign_keys_and_wal(self):
        with self.connection() as conn:
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertTrue({'users','roles','permissions','role_permissions','projects','user_project_access','sessions','audit_log','schema_migrations'} <= tables)
            self.assertEqual(conn.execute('PRAGMA journal_mode').fetchone()[0], 'wal')
            self.assertEqual(conn.execute('PRAGMA foreign_keys').fetchone()[0], 1)
            self.assertEqual(conn.execute('PRAGMA busy_timeout').fetchone()[0], 5000)
            self.assertEqual(conn.execute('PRAGMA foreign_key_check').fetchall(), [])
        for name in ('Viewer','Engineer','Project Manager'):
            self.assertFalse(any(key.endswith('.delete') for key in self.role(name)['permissions']))
        self.assertIn('tasks.edit', self.engineer['permissions'])
        self.assertNotIn('planning.edit', self.engineer['permissions'])
        self.assertTrue(all(key.endswith('.view') for key in self.viewer['permissions']))

    def test_google_subject_deduplicates_and_refreshes_profile(self):
        before = self.member.get(PREFIX + '/me').get_json()['user']
        self.assertEqual(sign_in(self.member, 'member', 'changed@example.com', name='Updated Name').status_code, 200)
        after = self.member.get(PREFIX + '/me').get_json()['user']
        self.assertEqual(after['id'], before['id'])
        self.assertEqual(after['created_at'], before['created_at'])
        self.assertEqual(after['display_name'], 'Updated Name')
        self.assertEqual(after['email'], 'changed@example.com')
        self.assertGreaterEqual(after['last_login_at'], before['last_login_at'])
        self.assertEqual(after['status'], 'pending')
        other = self.app.test_client()
        self.assertEqual(sign_in(other, 'different-subject', 'CHANGED@example.com').status_code, 409)
        with self.connection() as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM users').fetchone()[0], 2)

    def test_pending_user_cannot_read_projects_or_admin(self):
        self.assertEqual(self.member.get(PREFIX + '/me').get_json()['user']['status'], 'pending')
        for route in ('/projects','/admin/users','/admin/roles','/admin/permissions','/admin/projects','/admin/audit'):
            self.assertEqual(self.member.get(PREFIX + route).status_code, 403, route)
        self.assertEqual(self.approve().status_code, 200)
        self.assertEqual(self.member.get(PREFIX + '/projects').get_json()['projects'], [])
        self.assertEqual(self.member.get(PREFIX + '/admin/users').status_code, 403)

    def test_approval_requires_role_and_rejects_ownership_injection(self):
        self.assertEqual(self.mutate('/admin/users/' + str(self.member_id), {'status':'approved'}).status_code, 400)
        self.assertEqual(self.mutate('/admin/users/' + str(self.member_id), {'is_owner':1}).status_code, 400)
        self.assertEqual(self.mutate('/admin/users/' + str(self.member_id), {'role_id':True}).status_code, 400)
        self.assertEqual(self.approve().status_code, 200)
        self.assertEqual(self.mutate('/admin/users/' + str(self.member_id), {'role_id':None}).status_code, 400)

    def test_project_assignments_and_permissions_are_both_required(self):
        first, second = self.project('First project'), self.project('Second project')
        self.assertEqual(self.approve([first['id']], self.engineer).status_code, 200)
        self.assertEqual([p['id'] for p in self.member.get(PREFIX + '/projects').get_json()['projects']], [first['id']])
        self.assertEqual(self.member.get(PREFIX + '/projects/' + str(first['id'])).status_code, 200)
        self.assertEqual(self.member.get(PREFIX + '/projects/' + str(second['id'])).status_code, 404)
        with self.connection() as conn:
            user = conn.execute('SELECT * FROM users WHERE id=?', (self.member_id,)).fetchone()
            self.assertTrue(db.can_access(conn, user, first['id'], 'requirements.edit'))
            self.assertFalse(db.can_access(conn, user, second['id'], 'requirements.edit'))
            self.assertFalse(db.can_access(conn, user, first['id'], 'requirements.delete'))
        self.assertEqual(self.mutate('/admin/users/' + str(self.member_id), {'project_ids':[]}).status_code, 200)
        self.assertEqual(self.member.get(PREFIX + '/projects/' + str(first['id'])).status_code, 404)

    def test_role_edit_takes_effect_without_relogin(self):
        project = self.project('Permission test')
        self.approve([project['id']], self.engineer)
        role = self.role('Engineer')
        keys = [key for key in role['permissions'] if not key.startswith('requirements.')]
        data = {'name':role['name'],'description':role['description'],'permissions':keys,'version':role['version'],'confirm_affected_count':1}
        self.assertEqual(self.mutate('/admin/roles/' + str(role['id']), data).status_code, 200)
        with self.connection() as conn:
            user = conn.execute('SELECT * FROM users WHERE id=?', (self.member_id,)).fetchone()
            self.assertFalse(db.can_access(conn, user, project['id'], 'requirements.edit'))
        self.assertEqual(self.member.get(PREFIX + '/projects/' + str(project['id'])).status_code, 200)
        # Restarting the application must not restore the seed permissions.
        make_test_app(self.path)
        self.assertNotIn('requirements.edit', self.role('Engineer')['permissions'])

    def test_permission_dependencies_and_admin_escalation_are_rejected(self):
        for keys in (['requirements.edit'], ['users.approve'], ['roles.edit'], ['made-up.view']):
            response = self.mutate('/admin/roles', {'name':'Invalid', 'permissions':keys}, method='POST')
            self.assertEqual(response.status_code, 400)
        self.approve()
        response = self.mutate('/admin/roles', {'name':'Escalate','permissions':[]}, client=self.member, method='POST')
        self.assertEqual(response.status_code, 403)

    def test_custom_role_lifecycle_conflicts_and_affected_count(self):
        role = self.mutate('/admin/roles', {'name':'Custom reader','permissions':['projects.view']}, method='POST').get_json()['role']
        self.assertEqual(self.approve(role=role).status_code, 200)
        self.assertEqual(self.mutate('/admin/roles/' + str(role['id']), {}, method='DELETE').status_code, 409)
        data = {'name':'Custom reader','description':'Updated','permissions':['projects.view'],'version':role['version'],'confirm_affected_count':0}
        self.assertEqual(self.mutate('/admin/roles/' + str(role['id']), data).status_code, 409)
        data['confirm_affected_count'] = 1
        self.assertEqual(self.mutate('/admin/roles/' + str(role['id']), data).status_code, 200)
        self.assertEqual(self.mutate('/admin/roles/' + str(role['id']), data).status_code, 409)
        self.mutate('/admin/users/' + str(self.member_id), {'role_id':self.viewer['id']})
        self.assertEqual(self.mutate('/admin/roles/' + str(role['id']), {}, method='DELETE').status_code, 200)
        self.assertEqual(self.mutate('/admin/roles', {'name':'viewer','permissions':[]}, method='POST').status_code, 409)

    def test_rejected_and_revoked_accounts_stay_blocked_until_restored(self):
        self.assertEqual(self.mutate('/admin/users/' + str(self.member_id), {'status':'rejected'}).status_code, 200)
        self.assertEqual(self.member.get(PREFIX + '/me').status_code, 401)
        response = sign_in(self.member, 'member', 'member@example.com')
        self.assertEqual(response.get_json()['status'], 'rejected')
        self.assertEqual(self.member.get(PREFIX + '/me').status_code, 401)
        self.approve()
        sign_in(self.member, 'member', 'member@example.com')
        self.assertEqual(self.member.get(PREFIX + '/projects').status_code, 200)
        self.assertEqual(self.mutate('/admin/users/' + str(self.member_id), {'status':'revoked','reason':'Contract ended'}).status_code, 200)
        self.assertEqual(self.member.get(PREFIX + '/projects').status_code, 401)
        self.assertEqual(sign_in(self.member, 'member', 'member@example.com').get_json()['status'], 'revoked')
        self.assertEqual(self.member.get(PREFIX + '/me').status_code, 401)
        self.approve()
        self.assertEqual(self.member.get(PREFIX + '/me').status_code, 401)
        sign_in(self.member, 'member', 'member@example.com')
        self.assertEqual(self.member.get(PREFIX + '/projects').status_code, 200)

    def test_owner_is_bound_to_subject_and_protected(self):
        self.assertEqual(self.mutate('/admin/users/' + str(self.owner_id), {'status':'revoked'}).status_code, 403)
        with self.connection() as conn:
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute('UPDATE users SET is_owner=0 WHERE id=?', (self.owner_id,))
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute('DELETE FROM users WHERE id=?', (self.owner_id,))
        self.assertEqual(sign_in(self.owner, 'owner', 'new-owner@example.com').status_code, 200)
        self.assertTrue(self.owner.get(PREFIX + '/me').get_json()['user']['is_owner'])
        other = self.app.test_client()
        self.assertEqual(sign_in(other, 'second-owner-sub', 'gideont@gmail.com').status_code, 200)
        self.assertFalse(other.get(PREFIX + '/me').get_json()['user']['is_owner'])

    def test_csrf_and_origin_are_required(self):
        route = PREFIX + '/admin/projects'
        csrf = self.owner.get(PREFIX + '/me').get_json()['csrf_token']
        self.assertEqual(self.owner.post(route,json={'name':'Bad'},headers={'Origin':ORIGIN}).status_code,403)
        self.assertEqual(self.owner.post(route,json={'name':'Bad'},headers={'Origin':'https://evil.example','X-CSRF-Token':csrf}).status_code,403)
        self.assertEqual(self.owner.post(route,json={'name':'Bad'},headers={'X-CSRF-Token':csrf}).status_code,403)
        stranger = self.app.test_client()
        self.assertEqual(stranger.post(PREFIX + '/auth/google', json={'credential':'anything'}, headers={'Origin':ORIGIN}).status_code,403)
        self.assertEqual(stranger.get(PREFIX + '/admin/users').status_code,401)

    def test_nonce_unverified_email_and_invalid_credentials_fail(self):
        stranger = self.app.test_client()
        for kwargs in ({'nonce':'wrong'}, {'email_verified':False}, {'invalid':True}, {'sub':123}):
            self.assertEqual(sign_in(stranger, 'bad-user','bad@example.com',**kwargs).status_code,401)
        with self.connection() as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM users').fetchone()[0],2)

    def test_session_expiry_logout_and_hashed_storage(self):
        raw = self.member.get_cookie('bms_session',path='/bms_integration_hub').value
        with self.connection() as conn:
            row = conn.execute('SELECT * FROM sessions WHERE token_hash=?',(db.token_hash(raw),)).fetchone()
            self.assertIsNotNone(row)
            self.assertNotIn(raw, json.dumps(dict(row)))
            conn.execute("UPDATE sessions SET expires_at='2000-01-01T00:00:00.000Z' WHERE user_id=?",(self.member_id,))
        self.assertEqual(self.member.get(PREFIX + '/me').status_code,401)
        sign_in(self.member,'member','member@example.com')
        self.assertEqual(self.mutate('/auth/logout',{},client=self.member,method='POST').status_code,200)
        self.assertEqual(self.member.get(PREFIX + '/me').status_code,401)
        production = create_app({'TESTING':True,'DATABASE':str(self.path),'PUBLIC_ORIGIN':ORIGIN,'SIGNING_KEY':b'key'},verifier=fake_verifier)
        secure_client=production.test_client()
        response=sign_in(secure_client,'secure-user','secure@example.com')
        cookies=' '.join(response.headers.getlist('Set-Cookie'))
        self.assertIn('Secure',cookies)
        self.assertIn('HttpOnly',cookies)
        self.assertIn('SameSite=Lax',cookies)
        self.assertIn('Path=/bms_integration_hub',cookies)

    def test_owner_login_persists_30_days_renews_and_stays_revocable(self):
        raw=self.owner.get_cookie('bms_session',path='/bms_integration_hub').value
        with self.connection() as conn:
            # An active session issued under the former short lifetime is renewed on return.
            soon=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(timespec='milliseconds').replace('+00:00','Z')
            conn.execute('UPDATE sessions SET expires_at=? WHERE token_hash=?',(soon,db.token_hash(raw)))
        response=self.owner.get(PREFIX+'/me')
        self.assertEqual(response.status_code,200)
        self.assertIn('Max-Age=2592000',' '.join(response.headers.getlist('Set-Cookie')))
        with self.connection() as conn:
            expires=conn.execute('SELECT expires_at FROM sessions WHERE token_hash=?',(db.token_hash(raw),)).fetchone()[0]
        self.assertGreater(datetime.fromisoformat(expires.replace('Z','+00:00')),datetime.now(timezone.utc)+timedelta(days=29))
        # Reusing a persisted browser cookie still authenticates without another Google exchange.
        restored=self.app.test_client();restored.set_cookie('bms_session',raw,path='/bms_integration_hub')
        self.assertEqual(restored.get(PREFIX+'/me').status_code,200)
        self.assertEqual(self.mutate('/auth/logout',{},client=self.owner,method='POST').status_code,200)
        self.assertEqual(restored.get(PREFIX+'/me').status_code,401)
        # Customer sessions retain their existing eight-hour lifetime and are not renewed.
        login=sign_in(self.member,'member','member@example.com')
        self.assertIn('Max-Age=28800',' '.join(login.headers.getlist('Set-Cookie')))
        self.assertNotIn('Set-Cookie',self.member.get(PREFIX+'/me').headers)

    def test_audit_history_transaction_rollback_and_sql_injection(self):
        before = self.owner.get(PREFIX + '/admin/audit').get_json()['entries']
        response = self.mutate('/admin/users/' + str(self.member_id), {'status':'approved','role_id':self.viewer['id'],'project_ids':[99999]})
        self.assertEqual(response.status_code,400)
        self.assertEqual(self.member.get(PREFIX + '/me').get_json()['user']['status'],'pending')
        self.assertEqual(len(self.owner.get(PREFIX + '/admin/audit').get_json()['entries']),len(before))
        self.approve()
        self.mutate('/admin/users/' + str(self.member_id), {'status':'revoked','reason':'Review complete'})
        entries=self.owner.get(PREFIX + '/admin/audit').get_json()['entries']
        event=next(e for e in entries if e['action']=='user.revoked')
        self.assertEqual(event['actor_user_id'],self.owner_id)
        self.assertEqual(event['subject_user_id'],self.member_id)
        self.assertEqual(event['before']['status'],'approved')
        self.assertEqual(event['after']['status'],'revoked')
        self.assertEqual(event['reason'],'Review complete')
        data=self.owner.get(PREFIX + '/admin/users',query_string={'q':"' OR 1=1 --"}).get_json()
        self.assertEqual(data['users'],[])

    def test_persistence_backup_and_migration_version_guard(self):
        project=self.project('Persistent project')
        self.approve([project['id']])
        new_app=make_test_app(self.path)
        restored_client=new_app.test_client()
        raw=self.member.get_cookie('bms_session',path='/bms_integration_hub').value
        restored_client.set_cookie('bms_session',raw,path='/bms_integration_hub')
        self.assertEqual(restored_client.get(PREFIX + '/projects').get_json()['projects'][0]['id'],project['id'])
        target=Path(self.temp.name)/'backup.sqlite3'
        self.assertTrue(backup(self.path,target))
        with sqlite3.connect(target) as conn:
            self.assertEqual(conn.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            self.assertEqual(conn.execute('SELECT count(*) FROM users').fetchone()[0],2)
        with self.connection() as conn:
            conn.execute('INSERT INTO schema_migrations VALUES(999,?)',(db.now(),))
        with self.assertRaises(RuntimeError):
            make_test_app(self.path)

    def test_noindex_applies_to_errors_and_no_test_backdoor(self):
        stranger=self.app.test_client()
        for route in ('/admin/users','/not-found','/health'):
            response=stranger.get(PREFIX+route)
            self.assertIn('noindex',response.headers['X-Robots-Tag'])
            self.assertEqual(response.headers['Cache-Control'],'no-store')
        self.assertEqual(stranger.post(PREFIX+'/auth/test',headers={'Origin':ORIGIN}).status_code,404)
        with self.assertRaises(RuntimeError):
            create_app({'DATABASE':str(self.path)},verifier=fake_verifier)

    def test_google_library_receives_configured_audience(self):
        with patch('google.oauth2.id_token.verify_oauth2_token',return_value={'sub':'verified'}) as verify:
            self.assertEqual(google_verifier('credential','expected-client')['sub'],'verified')
            self.assertEqual(verify.call_args.args[0],'credential')
            self.assertEqual(verify.call_args.args[2],'expected-client')
        with patch('google.oauth2.id_token.verify_oauth2_token',side_effect=ValueError('invalid')):
            with self.assertRaises(ValueError):
                google_verifier('forged-or-expired','expected-client')
