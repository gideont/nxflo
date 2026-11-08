"""Persistent document identity is distinct from version labels and execution retries."""
import json,os,uuid
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
from test_portal_auth import make_test_app,sign_in,ORIGIN
from portal_api import db
from portal_api.generator import BASE,DEFAULTS
from portal_api.generator_library import migrate

class DocumentLibraryTests(TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.path=Path(self.temp.name)/'library.sqlite3'
        self.key=patch.dict(os.environ,{'OPENROUTER_API_KEY':'synthetic-library-key'});self.key.start()
        self.app=make_test_app(self.path);self.owner=self.app.test_client();sign_in(self.owner)
        self.headers={'Origin':ORIGIN,'X-CSRF-Token':self.owner.get('/bms_integration_hub/api/me').json['csrf_token']}
    def tearDown(self):self.key.stop();self.temp.cleanup()
    def create(self,title='Identical title',parent=None,status='ready'):
        response=self.owner.post(BASE+'/jobs',json={'config':{**DEFAULTS,'title':title,'topic':'Author concept','revision_parent':parent or ''}},headers=self.headers)
        self.assertEqual(response.status_code,202,response.json);job=response.json
        self.status(job['id'],status);return job
    def status(self,job,status):
        with db.connect(self.path) as c:
            state=json.loads(c.execute('SELECT state FROM generator_jobs WHERE id=?',(job,)).fetchone()[0]);state['document']={'chapters':[{'title':'Original','paragraphs':['Author vision']} ]}
            c.execute('UPDATE generator_jobs SET status=?,state=?,updated_at=? WHERE id=?',(status,json.dumps(state),db.now(),job))
        directory=self.path.parent/'generated'/job;directory.mkdir(parents=True,exist_ok=True)
        (directory/'document.html').write_text('<html><head><title>Author vision</title></head><body>Author vision</body></html>');(directory/'document.pdf').write_bytes(b'%PDF-original')
    def documents(self):return self.owner.get(BASE).json['documents']
    def test_identical_titles_remain_separate_but_a_renamed_revision_keeps_identity(self):
        first=self.create();second=self.create();revision=self.create('New title',first['id'])
        self.assertNotEqual(first['document_id'],second['document_id'])
        self.assertEqual(revision['document_id'],first['document_id']);self.assertNotEqual(revision['version_id'],first['version_id']);self.assertEqual(revision['version'],'1.1')
        docs=self.documents();self.assertEqual(len(docs),2)
        doc=next(d for d in docs if d['id']==first['document_id']);self.assertEqual(doc['title'],'New title');self.assertEqual([v['version'] for v in doc['versions']],['1.1','1.0'])
        restarted=make_test_app(self.path).test_client();sign_in(restarted)
        self.assertEqual(restarted.get(BASE).json['documents'],docs)
        for job in (first,revision):
            for kind in ('html','pdf'):
                response=self.owner.get(BASE+'/jobs/'+job['id']+'/download/'+kind);self.assertEqual(response.status_code,200);response.close()
    def test_database_rejects_a_job_pointing_to_another_documents_version(self):
        import sqlite3
        first=self.create('First');second=self.create('Second')
        with db.connect(self.path) as c:
            with self.assertRaises(sqlite3.IntegrityError):c.execute('UPDATE generator_jobs SET version_id=? WHERE id=?',(first['version_id'],second['id']))
            self.assertEqual(c.execute('SELECT version_id FROM generator_jobs WHERE id=?',(second['id'],)).fetchone()[0],second['version_id'])
    def test_resume_retains_both_identities_and_unknown_billing_remains_blocked(self):
        job=self.create(status='failed');before=self.owner.get(BASE+'/jobs/'+job['id']).json
        response=self.owner.post(BASE+'/jobs/'+job['id']+'/resume',json={},headers=self.headers);self.assertEqual(response.status_code,202,response.json)
        after=self.owner.get(BASE+'/jobs/'+job['id']).json
        self.assertEqual((before['document_id'],before['version_id'],before['config']['version']),(after['document_id'],after['version_id'],after['config']['version']))
        self.status(job['id'],'failed')
        with db.connect(self.path) as c:c.execute("INSERT INTO generator_calls(job_id,call_key,status,stage) VALUES(?,?,'submitting','draft:0')",(job['id'],'uncertain'))
        self.assertEqual(self.owner.post(BASE+'/jobs/'+job['id']+'/resume',json={},headers=self.headers).status_code,409)
        doc=self.documents()[0];self.assertEqual(doc['versions'],[]);self.assertFalse(doc['current_work']['can_resume']);self.assertTrue(doc['current_work']['recovery_blocked'])
        with db.connect(self.path) as c:self.assertEqual(c.execute('SELECT count(*) FROM generator_versions').fetchone()[0],1);self.assertEqual(c.execute('SELECT count(*) FROM generator_calls').fetchone()[0],1)
    def test_continuation_waits_for_an_existing_generation_without_changing_the_version(self):
        waiting=self.create(status='awaiting_html_review');active=self.create('Another document',status='queued')
        response=self.owner.post(BASE+'/jobs/'+waiting['id']+'/approve-html',json={},headers=self.headers)
        self.assertEqual(response.status_code,409);self.assertIn('Another document is generating',response.json['error'])
        self.assertEqual(self.owner.get(BASE+'/jobs/'+waiting['id']).json['status'],'awaiting_html_review')
    def test_unsaved_revision_is_current_work_not_a_saved_version(self):
        original=self.create();revision=self.create(parent=original['id'],status='failed')
        doc=self.documents()[0];self.assertEqual(doc['latest']['version'],'1.1');self.assertEqual(doc['latest_downloadable']['version'],'1.0');self.assertEqual([v['version'] for v in doc['versions']],['1.0']);self.assertTrue(doc['current_work']['can_resume'])
        self.status(revision['id'],'awaiting_html_review');doc=self.documents()[0]
        self.assertEqual([v['version'] for v in doc['versions']],['1.1','1.0']);self.assertTrue(doc['versions'][0]['is_current']);self.assertEqual(doc['versions'][0]['status_label'],'Awaiting HTML review');self.assertEqual(doc['latest_downloadable']['version'],'1.0')
    def test_historical_lineage_multiple_attempts_and_orphans_are_migrated_without_loss(self):
        root=self.create('Historic');old=uuid.uuid4().hex;orphan=uuid.uuid4().hex
        with db.connect(self.path) as c:
            row=c.execute('SELECT * FROM generator_jobs WHERE id=?',(root['id'],)).fetchone();config=row['config']
            for job,parent in ((old,root['id']),(orphan,'missing-parent')):
                c.execute("INSERT INTO generator_jobs(id,config,status,step,state,events,error,created_at,updated_at,parent_id) VALUES(?,?,'failed','draft','{}','[]','Internal diagnostic retained',?,?,?)",(job,config,db.now(),db.now(),parent))
            c.execute("INSERT INTO generator_calls(job_id,call_key,status,stage,result,cost) VALUES(?,?,'complete','draft:0','raw provider receipt',0.12)",(old,'receipt'))
            migrate(c);migrate(c)
            self.assertEqual(c.execute('SELECT count(*) FROM generator_jobs').fetchone()[0],3)
            ids=c.execute('SELECT document_id,version_id FROM generator_jobs WHERE id=?',(old,)).fetchone();self.assertEqual(ids['document_id'],root['document_id']);self.assertEqual(ids['version_id'],root['version_id'])
            self.assertNotEqual(c.execute('SELECT document_id FROM generator_jobs WHERE id=?',(orphan,)).fetchone()[0],root['document_id'])
            self.assertEqual(c.execute('SELECT result FROM generator_calls WHERE job_id=?',(old,)).fetchone()[0],'raw provider receipt')
            self.assertEqual(c.execute('SELECT error FROM generator_jobs WHERE id=?',(old,)).fetchone()[0],'Internal diagnostic retained')
        doc=next(d for d in self.documents() if d['id']==root['document_id']);self.assertEqual(len(doc['versions']),1);self.assertEqual(doc['versions'][0]['status'],'ready');self.assertEqual(doc['versions'][0]['pdf_job_id'],root['id']);self.assertEqual(doc['current_work']['job_id'],old)
        with db.connect(self.path) as c:c.execute("UPDATE generator_jobs SET updated_at='2099-01-01T00:00:00Z' WHERE id=?",(root['id'],))
        recovered=next(d for d in self.documents() if d['id']==root['document_id']);self.assertIsNone(recovered['current_work']);self.assertEqual(len(recovered['versions']),1)
        self.assertEqual(self.owner.get(BASE+'/jobs/'+old).json['error'],'Internal diagnostic retained')
    def test_library_is_not_limited_to_the_last_fifty_execution_records(self):
        with db.connect(self.path) as c:
            for i in range(55):
                c.execute("INSERT INTO generator_jobs(id,config,status,step,created_at,updated_at) VALUES(?,?,'preview','collect',?,?)",(uuid.uuid4().hex,json.dumps({**DEFAULTS,'title':'Draft '+str(i)}),db.now(),db.now()))
        self.assertEqual(len(self.documents()),55)
        self.assertEqual(self.app.test_client().get(BASE).status_code,401)
