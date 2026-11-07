"""SIGTERM must preserve the response, cache and checkpoint before worker exit."""
import json
import multiprocessing
import os
import signal
import time
import unittest
from unittest.mock import patch
import test_databricks_generator as databricks_fixture
from portal_api import db, generation_shutdown as shutdown
from portal_api.generation_models import Models
from portal_api.generator_worker import Engine, main
from portal_api.generation_tasks import run_task


def response_after_signal(parent_pid):
    os.kill(parent_pid,signal.SIGTERM)
    time.sleep(.2)
    return {'choices':[{'message':{'content':'{"notes":"saved evidence"}'}}]}


class ShutdownTests(unittest.TestCase):
    start=databricks_fixture.DatabricksTests.start
    def setUp(self):
        databricks_fixture.DatabricksTests.setUp(self)
        self.stopping=patch.object(shutdown,'_requested',False)
        self.stopping.start()
    def tearDown(self):
        self.stopping.stop()
        databricks_fixture.DatabricksTests.tearDown(self)

    def test_signal_during_request_saves_response_before_pausing_between_requests(self):
        job=self.start()
        connection=db.connect(self.path)
        models=Models(connection,job,self.config,lambda text:None)
        response={'choices':[{'message':{'content':'{"notes":"saved evidence"}'}}]}
        prior=signal.getsignal(signal.SIGTERM)
        prior_int=signal.getsignal(signal.SIGINT)
        shutdown.install_handlers()
        try:
            def finish(*args,**kwargs):
                return run_task(response_after_signal,(os.getpid(),),timeout=5,check=models.check)
            with patch('portal_api.generation_models.monitored_call',side_effect=finish) as transport:
                with self.assertRaises(shutdown.WorkerDraining):models.many('summary',['part one','part two'],'summarize')
                self.assertEqual(transport.call_count,1)
            rows=connection.execute('SELECT status,stage,result FROM generator_calls WHERE job_id=?',(job,)).fetchall()
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]['status'],'complete')
            self.assertIn('saved evidence',rows[0]['result'])
            shutdown._requested=False
            with patch('portal_api.generation_models.monitored_call',return_value=response) as transport:
                self.assertEqual(len(models.many('summary',['part one','part two'],'summarize')),2)
                self.assertEqual(transport.call_count,1,'The saved first request was submitted twice')
        finally:
            signal.signal(signal.SIGTERM,prior)
            signal.signal(signal.SIGINT,prior_int)
            connection.close()

    def test_explicit_retry_authorization_repeats_only_the_lost_request_once(self):
        from portal_api.generation_errors import TransientGenerationError
        job=self.start()
        with db.connect(self.path) as connection:
            models=Models(connection,job,self.config,lambda text:None)
            with patch.object(models,'request',side_effect=TransientGenerationError('Response lost')):
                with self.assertRaises(TransientGenerationError):models.many('summary',['source'],'review-2')
            connection.execute("UPDATE generator_calls SET status='retry_authorized',billing=? WHERE job_id=?",(json.dumps({'original_outcome_unknown':True,'retry_authorized_by':'owner'}),job))
            shutdown._requested=True
            with self.assertRaises(shutdown.WorkerDraining):models.many('summary',['source'],'review-2')
            shutdown._requested=False
            response={'choices':[{'message':{'content':'{"major_issues":[]}'}}]}
            with patch.object(models,'request',return_value=response) as transport:
                for _ in range(2):self.assertEqual(models.many('summary',['source'],'review-2'),[{'major_issues':[]}])
                self.assertEqual(transport.call_count,1)
            row=connection.execute('SELECT * FROM generator_calls WHERE job_id=?',(job,)).fetchone()
            self.assertEqual(row['status'],'complete')
            self.assertTrue(json.loads(row['billing'])['original_outcome_unknown'])

    def test_idle_worker_exits_cleanly_on_sigterm(self):
        with patch.dict(os.environ,{'BMS_DATABASE_PATH':str(self.path)}):
            process=multiprocessing.get_context('spawn').Process(target=main)
            process.start()
            try:
                deadline=time.monotonic()+8
                with db.connect(self.path) as connection:
                    while not connection.execute("SELECT 1 FROM generator_meta WHERE key='heartbeat'").fetchone():
                        self.assertTrue(process.is_alive())
                        self.assertLess(time.monotonic(),deadline)
                        time.sleep(.05)
                os.kill(process.pid,signal.SIGTERM)
                process.join(timeout=5)
                self.assertEqual(process.exitcode,0)
            finally:
                if process.is_alive():process.kill();process.join()
                process.close()

    def test_graph_requeues_at_checkpoint_and_resumes_without_rebilling(self):
        job=self.start()
        with db.connect(self.path) as connection:
            connection.execute("UPDATE generator_jobs SET status='running' WHERE id=?",(job,))
        response={'choices':[{'message':{'content':'{"notes":"saved evidence"}'}}]}
        def finish(*args,**kwargs):
            shutdown.request_stop()
            return response
        with patch('portal_api.generation_models.monitored_call',side_effect=finish) as transport:
            Engine(self.path,job).run()
            self.assertEqual(transport.call_count,1)
        with db.connect(self.path) as connection:
            row=connection.execute('SELECT * FROM generator_jobs WHERE id=?',(job,)).fetchone()
            self.assertEqual(row['status'],'queued')
            self.assertEqual(json.loads(row['state'])['next_step'],'outline')
            self.assertFalse(row['error'])
            self.assertEqual(connection.execute("SELECT count(*) FROM generator_calls WHERE status='submitting'").fetchone()[0],0)
        shutdown._requested=False
        # A resumed graph starts at outline rather than summarizing the source again.
        with patch.object(Engine,'outline',side_effect=shutdown.WorkerDraining) as outline,patch.object(Engine,'summarize',side_effect=AssertionError('Saved work repeated')):
            Engine(self.path,job).run()
            self.assertEqual(outline.call_count,1)


if __name__=='__main__':unittest.main()
