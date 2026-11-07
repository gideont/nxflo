"""Exercise wall-clock deadlines against a response that keeps sending bytes."""
import hashlib
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import multiprocessing
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import threading
import time
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_portal_auth import make_test_app
from portal_api import db
from portal_api.generator import DEFAULTS
from portal_api.generation_errors import Cancelled,GenerationError,TransientGenerationError,RejectedGenerationError,RateLimitedGenerationError
from portal_api.generation_models import Models,PendingBatch
from portal_api.generation_tasks import run_task,monitored_call
from portal_api.generation_transport import fetch_json

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_GET(self):
        self.send_response(503 if self.path=='/error' else 429 if self.path=='/rate-limit' else 401 if self.path=='/unauthorized' else 200);self.end_headers()
        try:
            if self.path=='/drip':
                self.server.drip_started.set()
                for _ in range(300):self.wfile.write(b' ');self.wfile.flush();self.server.drip_chunks+=1;time.sleep(.03)
            self.wfile.write(b'{"ok":true}')
        except (BrokenPipeError,ConnectionResetError):pass

class TaskTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);cls.server.drip_started=threading.Event();cls.server.drip_chunks=0;threading.Thread(target=cls.server.serve_forever,daemon=True).start();cls.url='http://127.0.0.1:'+str(cls.server.server_port)
    @classmethod
    def tearDownClass(cls):cls.server.shutdown();cls.server.server_close()
    def setUp(self):
        self.temp=TemporaryDirectory();self.path=Path(self.temp.name)/'tasks.sqlite3';make_test_app(self.path);self.db=db.connect(self.path);self.job='a'*32
        self.db.execute('INSERT INTO generator_jobs(id,config,status,step,created_at,updated_at) VALUES(?,?,?,?,?,?)',(self.job,json.dumps(DEFAULTS),'running','collect',db.now(),db.now()))
    def tearDown(self):self.db.close();self.temp.cleanup()
    def test_trickled_bytes_cannot_bypass_total_deadline(self):
        started=time.monotonic();pulses=[]
        with self.assertRaisesRegex(GenerationError,'deadline'):
            run_task(fetch_json,('GET',self.url+'/drip',None,{}),timeout=3,pulse=pulses.append,pulse_interval=.1)
        self.assertLess(time.monotonic()-started,5);self.assertGreaterEqual(len(pulses),2);self.assertTrue(self.server.drip_started.is_set());self.assertGreater(self.server.drip_chunks,2)
        self.assertEqual(multiprocessing.active_children(),[])
    def test_normal_json_response_and_http_failure(self):
        self.assertEqual(run_task(fetch_json,('GET',self.url+'/ok',None,{}),timeout=5),{'ok':True})
        with self.assertRaisesRegex(GenerationError,'HTTP 503'):run_task(fetch_json,('GET',self.url+'/error',None,{}),timeout=5)
        with self.assertRaises(RateLimitedGenerationError):run_task(fetch_json,('GET',self.url+'/rate-limit',None,{}),timeout=5)
        with self.assertRaises(RejectedGenerationError):run_task(fetch_json,('GET',self.url+'/unauthorized',None,{}),timeout=5)

    def test_rejected_request_can_retry_without_repeating_completed_calls(self):
        models=Models(self.db,self.job,DEFAULTS,lambda text:None)
        result={'choices':[{'message':{'content':'{"notes":"Saved evidence"}'}}]}
        with patch.object(models,'request',side_effect=[result,RateLimitedGenerationError('HTTP 429'),result]) as call:
            with self.assertRaises(RateLimitedGenerationError):models.many('summary',['first','second'],'summarize')
            progress=json.loads(self.db.execute('SELECT work_progress FROM generator_jobs').fetchone()[0]);self.assertEqual(progress['completed'],1);self.assertEqual(progress['total'],2)
            self.assertEqual([r[0] for r in self.db.execute('SELECT status FROM generator_calls ORDER BY stage')],['complete','rejected'])
            self.assertEqual(len(models.many('summary',['first','second'],'summarize')),2)
            self.assertEqual(call.call_count,3)

    def test_received_response_is_preserved_even_if_parsing_fails(self):
        models=Models(self.db,self.job,DEFAULTS,lambda text:None)
        result={'choices':[{'finish_reason':'length','message':{'content':'incomplete'}}],'usage':{'cost':.002,'is_byok':False}}
        with patch.object(models,'request',return_value=result) as call:
            for _ in range(2):
                with self.assertRaisesRegex(GenerationError,'cut short'):models.many('summary',['evidence'],'summarize')
            self.assertEqual(call.call_count,1)
            row=self.db.execute('SELECT * FROM generator_calls').fetchone();self.assertEqual(row['status'],'received');self.assertEqual(row['cost'],.002)
            self.assertEqual(json.loads(row['result']),result)
    def test_cancellation_kills_the_blocking_operation(self):
        started=time.monotonic()
        def check():
            if time.monotonic()-started>.35:raise Cancelled()
        with self.assertRaises(Cancelled):run_task(time.sleep,(20,),timeout=10,check=check)
        self.assertLess(time.monotonic()-started,2);self.assertEqual(multiprocessing.active_children(),[])
    def test_wait_metadata_and_heartbeat_are_written_and_cleared(self):
        seen=[]
        def message(text):
            waiting=json.loads(self.db.execute('SELECT wait_state FROM generator_jobs WHERE id=?',(self.job,)).fetchone()[0]);self.assertEqual(waiting['label'],'test operation');seen.append(text)
            self.db.execute("INSERT OR REPLACE INTO generator_meta VALUES('heartbeat',?)",(str(time.time()),))
        monitored_call(self.db,self.job,'test operation',3,time.sleep,(.2,),check=lambda:None,message=message)
        self.assertTrue(any('Waiting for' in text for text in seen));self.assertEqual(self.db.execute('SELECT wait_state FROM generator_jobs').fetchone()[0],'{}')
        self.assertLess(time.time()-float(self.db.execute("SELECT value FROM generator_meta WHERE key='heartbeat'").fetchone()[0]),2)
    def test_wait_metadata_clears_when_deadline_expires(self):
        with self.assertRaisesRegex(GenerationError,'deadline'):monitored_call(self.db,self.job,'test operation',.4,time.sleep,(10,),check=lambda:None,message=lambda text:None)
        self.assertEqual(self.db.execute('SELECT wait_state FROM generator_jobs').fetchone()[0],'{}')
    def test_web_request_has_shorter_deadline_and_no_hidden_retry(self):
        models=Models(self.db,self.job,DEFAULTS,lambda text:None)
        with patch('portal_api.generation_models.monitored_call',side_effect=GenerationError('deadline')) as call:
            with self.assertRaisesRegex(GenerationError,'will not be retried'):models.request('POST','/chat/completions',{'plugins':[{'id':'web','engine':'parallel','mode':'turbo','max_results':5}],'tool_choice':'none','max_tokens':1800})
            self.assertEqual(call.call_count,1);self.assertEqual(call.call_args.args[3],90)
    def test_web_response_from_before_upgrade_is_reused(self):
        self.db.execute('INSERT INTO generator_calls(job_id,call_key,status,stage,result) VALUES(?,?,?,?,?)',(self.job,'old-key','complete','web-research:0',json.dumps([{'content':'Existing research','annotations':[]}])) )
        models=Models(self.db,self.job,DEFAULTS,lambda text:None)
        with patch.object(models,'request') as call:
            value=models.many('summary',['research'],'web-research',web=True,structured=False)
            self.assertEqual(value[0]['content'],'Existing research');call.assert_not_called()
    def test_batch_poll_timeout_retries_status_without_resubmitting(self):
        cfg={**DEFAULTS,'summary_model':'openai/gpt-6-luna:batch','summary_service':'default'};models=Models(self.db,self.job,cfg,lambda text:None)
        with patch.object(models,'request',side_effect=[{'id':'batch-live'},TransientGenerationError('deadline')]) as call:
            with self.assertRaises(PendingBatch):models.many('summary',['evidence'],'summarize')
            with self.assertRaises(PendingBatch):models.many('summary',['evidence'],'summarize')
            self.assertEqual([args.args[0] for args in call.call_args_list],['POST','GET'])
            self.assertEqual(self.db.execute('SELECT remote_id FROM generator_calls').fetchone()[0],'batch-live')
    def test_opaque_batch_id_is_persisted_without_another_submission(self):
        cfg={**DEFAULTS,'summary_model':'openai/gpt-6-luna:batch','summary_service':'default'};models=Models(self.db,self.job,cfg,lambda text:None)
        for remote in ('batch_abc123','batch-1793943995-EaDTSxIah13LogtnKRGy'):
            with patch.object(models,'request',return_value={'id':remote,'status':'in_progress'}):
                with self.assertRaises(PendingBatch):models.many('summary',[remote],'batch-'+remote)
            self.assertTrue(self.db.execute('SELECT 1 FROM generator_calls WHERE job_id=? AND remote_id=?',(self.job,remote)).fetchone())

if __name__=='__main__':unittest.main()
