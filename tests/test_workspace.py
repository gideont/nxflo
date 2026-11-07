"""Workspace authorization, validation, real-data aggregation and upgrade preservation."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from portal_api import db, PREFIX
import test_portal_auth as auth
from test_portal_auth import make_test_app


class WorkspaceTests(unittest.TestCase):
    for _name in ('setUp','tearDown','connection','role','mutate','approve','project'):
        locals()[_name] = getattr(auth.PortalAccessTests, _name)

    def test_assigned_data_and_task_permissions_change_immediately(self):
        a = self.mutate('/workspace/projects', {'name':'Visible','site_code':'SEA1','customer':'Test customer',
                        'start_date':'2026-10-01','rfs_date':'2027-01-01'}, method='POST').get_json()['project']
        b = self.project('Restricted')
        task = self.mutate(f"/workspace/projects/{a['id']}/tasks", {'title':'Map points','start_date':'2026-10-02',
                           'end_date':'2026-10-10','effort_md':2.5}, method='POST').get_json()['task']
        self.mutate(f"/workspace/projects/{b['id']}/tasks", {'title':'Hidden task'}, method='POST')
        self.assertEqual(self.member.get(PREFIX+'/workspace').status_code,403)
        self.approve([a['id']],self.engineer)
        data = self.member.get(PREFIX+'/workspace').get_json()
        self.assertEqual([p['id'] for p in data['projects']],[a['id']])
        self.assertEqual([t['id'] for t in data['tasks']],[task['id']])
        self.assertEqual(self.mutate(f"/workspace/tasks/{task['id']}",{'status':'completed'},self.member).status_code,200)
        self.assertEqual(self.mutate(f"/workspace/projects/{b['id']}/tasks",{'title':'Forbidden'},self.member,'POST').status_code,404)
        self.assertEqual(self.mutate(f"/workspace/projects/{a['id']}",{'rfs_date':'2027-02-01'},self.member).status_code,404)
        with self.connection() as conn:
            conn.execute('DELETE FROM role_permissions WHERE role_id=? AND permission_key=?',(self.engineer['id'],'tasks.view'))
            conn.execute('DELETE FROM role_permissions WHERE role_id=? AND permission_key=?',(self.engineer['id'],'tasks.edit'))
        self.assertEqual(self.member.get(PREFIX+'/workspace').get_json()['tasks'],[])
        self.assertEqual(self.mutate(f"/workspace/tasks/{task['id']}",{'status':'planned'},self.member).status_code,404)
        self.assertEqual(self.mutate('/workspace/projects',{'name':'Escalation'},self.member,'POST').status_code,403)

    def test_dates_validation_audit_and_empty_real_workspace(self):
        self.assertEqual(self.owner.get(PREFIX+'/workspace').get_json()['projects'],[])
        for data in ({'name':'Bad date','rfs_date':'2026-02-30'}, {'name':'Inverted','start_date':'2027-01-01','rfs_date':'2026-01-01'}, {'name':'Bad status','health':'fake'}):
            self.assertEqual(self.mutate('/workspace/projects',data,method='POST').status_code,400)
        project=self.mutate('/workspace/projects',{'name':'RFS project','site_code':'ABC1'},method='POST').get_json()['project']
        self.assertEqual(self.mutate(f"/workspace/projects/{project['id']}",{'rfs_date':'2027-01-20','health':'watch'}).status_code,200)
        for effort in (-1,True,'NaN',float('inf')):
            self.assertEqual(self.mutate(f"/workspace/projects/{project['id']}/tasks",{'title':'Invalid','effort_md':effort},method='POST').status_code,400)
        with self.connection() as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM audit_log WHERE action='project.updated'").fetchone()[0],1)
            self.assertEqual(conn.execute('PRAGMA foreign_key_check').fetchall(),[])

    def test_schema_one_upgrade_preserves_accounts_roles_and_project_access(self):
        with TemporaryDirectory() as directory:
            path=Path(directory)/'upgrade.sqlite3'
            with patch('portal_api.db.apply_workspace_migration'):
                make_test_app(path)
            with db.connect(path) as conn:
                owner,_=db.login_identity(conn,{'sub':'stable','email':'gideont@gmail.com','name':'Owner','email_verified':True},'gideont@gmail.com')
                conn.execute("DELETE FROM role_permissions WHERE permission_key='tasks.edit'")
                conn.execute('INSERT INTO projects(name,created_at) VALUES(?,?)',('Existing project',db.now()))
                before=conn.execute('SELECT count(*) FROM role_permissions').fetchone()[0]
            app=make_test_app(path)
            with db.connect(path) as conn:
                self.assertEqual(conn.execute('SELECT google_subject FROM users WHERE is_owner=1').fetchone()[0],'stable')
                self.assertEqual(conn.execute('SELECT count(*) FROM sessions').fetchone()[0],1)
                self.assertEqual(conn.execute('SELECT count(*) FROM role_permissions').fetchone()[0],before)
                self.assertEqual(conn.execute('SELECT max(version) FROM schema_migrations').fetchone()[0],2)
                self.assertEqual(conn.execute('SELECT status FROM projects').fetchone()[0],'planned')
                self.assertEqual(conn.execute('SELECT count(*) FROM tasks').fetchone()[0],0)
            make_test_app(path)
