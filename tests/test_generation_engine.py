"""Real LangGraph and PDF pipeline; deterministic models, no provider spending."""
import json
import os
from pathlib import Path
import socket
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_portal_auth import make_test_app,sign_in,ORIGIN
from portal_api import db
from portal_api.generator import BASE,DEFAULTS
from portal_api.generator_worker import Engine
from portal_api.generation_models import Models,GenerationError,PendingBatch,Cancelled
from portal_api.generation_errors import TransientGenerationError
from portal_api.generation_sources import public_addresses,fetch_reference
from portal_api.generation_document import chart_svg,assemble

CH={'title':'Operating findings','paragraphs':['User-provided figures show a reduction from 42 to 25 units [B1].','Validate the baseline before making investment decisions [B1].'],'takeaway':'Confirm the evidence and measure the result.','charts':[{'kind':'bar','title':'Reported units','labels':['Before','After'],'values':[42,25],'unit':'units','source_id':'B1','evidence':['before 42 units','after 25 units']}]}
class FakeModels:
    calls=[]
    def __init__(self,connection,job_id,config,message):self.real=Models(connection,job_id,config,message)
    def check(self):self.real.check()
    def many(self,role,prompts,stage,**kwargs):
        self.calls.append(stage)
        if stage.startswith('summarize'):return [{'notes':'B1: before 42 units; after 25 units. User-provided claims.'} for _ in prompts]
        if stage=='outline':return [{'title':'Evidence report','chapters':[{'title':'Findings','brief':'Assess results'},{'title':'Actions','brief':'Recommend checks'}]}]
        if stage.startswith('review'):return [{'major_issues':['Improve explanation'] if stage=='review-1' else []} for _ in prompts]
        return [json.loads(json.dumps(CH)) for _ in prompts]

class EngineTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.path=Path(self.temp.name)/'test.sqlite3';self.app=make_test_app(self.path)
        self.owner=self.app.test_client();sign_in(self.owner);csrf=self.owner.get('/bms_integration_hub/api/me').json['csrf_token'];self.headers={'Origin':ORIGIN,'X-CSRF-Token':csrf}
        self.cfg={**DEFAULTS,'topic':'The pilot reported before 42 units and after 25 units.','title':'A real document','web_search':False,'review_passes':2,'length_mode':'target','pages':2}
        with patch.dict(os.environ,{'OPENROUTER_API_KEY':'synthetic'}):self.id=self.owner.post(BASE+'/jobs',json={'config':self.cfg},headers=self.headers).json['id']
        FakeModels.calls=[]
    def tearDown(self):self.temp.cleanup()
    def row(self):
        with db.connect(self.path) as connection:return dict(connection.execute('SELECT * FROM generator_jobs WHERE id=?',(self.id,)).fetchone())
    def run_reviewed(self,job_id=None,factory=FakeModels):
        job_id=job_id or self.id
        Engine(self.path,job_id,factory).run()
        if self.owner.get(BASE+'/jobs/'+job_id).json['status']=='awaiting_html_review':
            response=self.owner.post(BASE+'/jobs/'+job_id+'/approve-html',json={},headers=self.headers)
            self.assertEqual(response.status_code,202,response.json)
            Engine(self.path,job_id,factory).run()

    def test_html_review_is_durable_and_blocks_pdf_until_explicit_approval(self):
        route=BASE+'/jobs/'+self.id
        self.assertEqual(self.owner.post(route+'/approve-html',json={},headers=self.headers).status_code,409)
        Engine(self.path,self.id,FakeModels).run()
        self.assertEqual(self.row()['status'],'awaiting_html_review')
        directory=self.path.parent/'generated'/self.id
        self.assertTrue((directory/'document.html').is_file())
        self.assertFalse((directory/'document.pdf').exists())
        self.assertEqual(self.owner.get(route+'/download/pdf').status_code,409)
        preview=self.owner.get(route+'/download/html?view=1')
        self.assertEqual(preview.status_code,200)
        self.assertIn(b'Operating findings',preview.data)
        self.assertIn("default-src 'none'",preview.headers['Content-Security-Policy'])
        preview.close()
        self.assertEqual(self.app.test_client().get(route+'/download/html?view=1').status_code,401)
        self.assertEqual(self.app.test_client().post(route+'/approve-html',json={},headers={'Origin':ORIGIN}).status_code,401)
        self.assertEqual(self.owner.post(route+'/approve-html',json={},headers={'Origin':ORIGIN}).status_code,403)
        before=list(FakeModels.calls)
        # Restarting the worker cannot bypass review or repeat model calls.
        Engine(self.path,self.id,FakeModels).run()
        self.assertEqual(self.row()['status'],'awaiting_html_review')
        self.assertEqual(FakeModels.calls,before)
        self.assertFalse((directory/'document.pdf').exists())
        self.assertEqual(self.owner.post(route+'/resume',json={},headers=self.headers).status_code,409)
        self.assertEqual(self.owner.post(route+'/approve-html',json={},headers=self.headers).status_code,202)
        self.assertEqual(self.owner.post(route+'/approve-html',json={},headers=self.headers).status_code,409)
        Engine(self.path,self.id,FakeModels).run()
        self.assertEqual(self.row()['status'],'ready')
        self.assertTrue((directory/'document.pdf').read_bytes().startswith(b'%PDF'))
        self.assertEqual(FakeModels.calls,before)

    def test_real_graph_review_loop_and_pdf(self):
        self.run_reviewed();row=self.row()
        self.assertEqual(row['status'],'ready',row['error'])
        self.assertEqual(FakeModels.calls.count('review-2'),1)
        self.assertIn('rewrite-1',FakeModels.calls)
        self.assertNotIn('rewrite-2',FakeModels.calls)
        events=json.loads(row['events']);self.assertEqual(events[-1]['step'],'deliver')
        directory=self.path.parent/'generated'/self.id
        self.assertTrue((directory/'document.pdf').read_bytes().startswith(b'%PDF'))
        from pypdf import PdfReader
        reader=PdfReader(directory/'document.pdf');self.assertGreaterEqual(len(reader.pages),2)
        self.assertIn('Operating findings',' '.join(p.extract_text() for p in reader.pages))
        html=(directory/'document.html').read_text();self.assertIn('<svg',html);self.assertIn('source-B1',html)
        # A restart after a completed checkpoint performs no more model calls.
        FakeModels.calls=[];self.run_reviewed();self.assertEqual(FakeModels.calls,[])

    def test_editorial_notes_never_precede_the_cover_and_contents_has_page_numbers(self):
        from portal_api.generation_document import export_pdf
        from pypdf import PdfReader
        state={'sources':[{'id':'B1','label':'Brief','text':'Source text'}],'document':{'chapters':[CH]},'warnings':['Source verification pending: '+('unavailable reference details '*30) for _ in range(6)]}
        html=assemble(self.cfg,state);path=self.path.parent/'layout.pdf';export_pdf(html,path);reader=PdfReader(path)
        cover=reader.pages[0].extract_text();self.assertIn('A real document',cover);self.assertNotIn('Source verification pending',cover);self.assertNotIn('Review required',cover)
        contents=reader.pages[1].extract_text();self.assertIn('Contents',contents);self.assertIn('Operating findings',contents);self.assertRegex(contents,r'Operating findings\s*[.\s]*3')
        later=' '.join(page.extract_text() or '' for page in reader.pages[2:]);self.assertIn('Source verification pending',later);self.assertIn('Source and editorial notes',later);self.assertIn('Page 3 of',later)

    def test_transient_failures_retry_automatically_from_checkpoint_with_a_limit(self):
        with patch.object(Engine,'summarize',side_effect=TransientGenerationError('Temporary local interruption')):
            for attempt in range(1,5):
                self.run_reviewed();row=self.row()
                self.assertEqual(json.loads(row['state'])['next_step'],'summarize')
                self.assertEqual(row['status'],'queued' if attempt<=3 else 'failed')
                self.assertEqual(json.loads(row['recovery'])['attempts'],min(attempt,3))
        with patch.dict(os.environ,{'OPENROUTER_API_KEY':'synthetic'}):self.assertEqual(self.owner.post(BASE+'/jobs/'+self.id+'/resume',json={},headers=self.headers).status_code,202)
        with patch.object(Engine,'collect',side_effect=AssertionError('Completed collection repeated')),patch.object(Engine,'pdf',return_value={}):self.run_reviewed()
        row=self.row();self.assertEqual(row['status'],'ready',row['error']);self.assertEqual(row['recovery'],'{}')

    def test_unknown_paid_submission_and_user_cancel_are_never_auto_retried(self):
        with db.connect(self.path) as connection:connection.execute("INSERT INTO generator_calls(job_id,call_key,status,stage) VALUES(?,?,'submitting','summarize')",(self.id,'ambiguous'))
        with patch.object(Engine,'summarize',side_effect=TransientGenerationError('POST connection lost')):self.run_reviewed()
        row=self.row();self.assertEqual(row['status'],'failed');self.assertIn('prevent duplicate charges',row['error']);self.assertEqual(row['recovery'],'{}')
        with db.connect(self.path) as connection:connection.execute("UPDATE generator_jobs SET status='cancelled' WHERE id=?",(self.id,))
        self.run_reviewed();self.assertEqual(self.row()['status'],'cancelled')
    def test_feedback_uses_previous_document_and_renders_formal_history(self):
        self.run_reviewed()
        original=(self.path.parent/'generated'/self.id/'document.pdf').read_bytes()
        cfg={**self.cfg,'revision_parent':self.id,'feedback':'Add a specific measurement recommendation.','change_summary':'Expanded the measurement recommendations.'}
        with patch.dict(os.environ,{'OPENROUTER_API_KEY':'synthetic'}):result=self.owner.post(BASE+'/jobs',json={'config':cfg},headers=self.headers)
        self.assertEqual(result.status_code,202,result.json);revision=result.json['id'];self.assertEqual(result.json['version'],'1.1')
        captured=[]
        class RevisionModels(FakeModels):
            def many(self,role,prompts,stage,**kwargs):
                if stage=='draft':captured.extend(prompts)
                return super().many(role,prompts,stage,**kwargs)
        self.run_reviewed(revision,RevisionModels)
        job=self.owner.get(BASE+'/jobs/'+revision).json;self.assertEqual(job['status'],'ready',job['error'])
        self.assertTrue(all('Add a specific measurement recommendation.' in prompt and 'Operating findings' in prompt for prompt in captured))
        html=(self.path.parent/'generated'/revision/'document.html').read_text()
        self.assertIn('Document control and revision history',html)
        if 'id="document-contact"' in html:self.assertLess(html.index('id="document-contact"'),html.index('id="document-control"'))
        self.assertIn('Expanded the measurement recommendations.',html)
        self.assertNotIn('Add a specific measurement recommendation.',html)
        self.assertIn('mailto:research@nxflo.com',html);self.assertIn('https://www.nxflo.com',html)
        self.assertLess(html.index('<section id="sources"'),html.index('<section id="document-control"'))
        self.assertEqual((self.path.parent/'generated'/self.id/'document.pdf').read_bytes(),original)
        from pypdf import PdfReader
        pdf=PdfReader(self.path.parent/'generated'/revision/'document.pdf');text=' '.join(page.extract_text() for page in pdf.pages)
        self.assertIn('research@nxflo.com',text);self.assertIn('1.1',text);self.assertIn('Expanded the measurement recommendations.',' '.join(text.split()))
    def test_optional_team_omits_attribution_and_contact(self):
        text=assemble({**self.cfg,'prepared_team':'','website':''},{'sources':[{'id':'B1','text':'evidence','label':'Brief'}],'document':{'chapters':[CH]}})
        self.assertNotIn('mailto:research@nxflo.com',text);self.assertNotIn('class="prepared-by"',text)

    def test_optional_web_timeout_keeps_supplied_research_and_finishes(self):
        with db.connect(self.path) as connection:connection.execute('UPDATE generator_jobs SET config=? WHERE id=?',(json.dumps({**self.cfg,'web_search':True}),self.id))
        class WebUnavailable(FakeModels):
            def many(self,role,prompts,stage,**kwargs):
                if stage=='web-research':raise GenerationError('Web request exceeded its deadline; no automatic retry.')
                return super().many(role,prompts,stage,**kwargs)
        self.run_reviewed(factory=WebUnavailable);row=self.row()
        self.assertEqual(row['status'],'needs_review',row['error'])
        state=json.loads(row['state']);self.assertTrue(any('Optional web research was unavailable' in warning for warning in state['warnings']))
        self.assertEqual(state['sources'][0]['text'],self.cfg['topic'])
        self.assertEqual(row['wait_state'],'{}')

    def test_one_pass_finishes_with_review_warning(self):
        with db.connect(self.path) as connection:connection.execute('UPDATE generator_jobs SET config=? WHERE id=?',(json.dumps({**self.cfg,'review_passes':1}),self.id))
        self.run_reviewed()
        self.assertEqual(self.row()['status'],'needs_review');self.assertNotIn('review-2',FakeModels.calls)
    def test_unavailable_source_warns_and_continues(self):
        with db.connect(self.path) as connection:connection.execute('UPDATE generator_jobs SET config=? WHERE id=?',(json.dumps({**self.cfg,'topic':self.cfg['topic']+' https://example.com/paper'}),self.id))
        from portal_api.generation_tasks import monitored_call
        def unavailable(connection,job,label,timeout,function,args,**kwargs):
            if label.startswith('reference '):raise GenerationError('Reference unavailable.')
            return monitored_call(connection,job,label,timeout,function,args,**kwargs)
        with patch('portal_api.generator_worker.monitored_call',side_effect=unavailable):self.run_reviewed()
        row=self.row();self.assertEqual(row['status'],'needs_review',row['error'])
        self.assertIn('Reference unavailable',json.loads(row['state'])['warnings'][0])
    def test_chart_grounding_and_escaping(self):
        sources=[{'id':'B1','text':self.cfg['topic'],'label':'Brief'}]
        svg=chart_svg(CH['charts'][0],self.cfg,sources);self.assertIn('<svg',svg)
        bad={**CH['charts'][0],'values':[999,25]}
        with self.assertRaises(ValueError):chart_svg(bad,self.cfg,sources)
        text=assemble(self.cfg,{'sources':sources,'document':{'chapters':[{**CH,'paragraphs':['<script>alert(1)</script> [B1]']}]}})
        self.assertNotIn('<script>',text);self.assertIn('&lt;script&gt;',text)
    def test_public_source_dns_guards(self):
        for ip in ('127.0.0.1','10.0.0.1','169.254.169.254','::1','fd00::1','::ffff:127.0.0.1'):
            with patch('socket.getaddrinfo',return_value=[(socket.AF_INET,socket.SOCK_STREAM,6,'',(ip,0))]):
                with self.assertRaises(GenerationError):public_addresses('example.com')
        with self.assertRaises(GenerationError):fetch_reference('http://example.com:abc')
    def test_sync_calls_cached_and_flex_pinned(self):
        connection=db.connect(self.path);models=Models(connection,self.id,self.cfg,lambda text:None)
        answer={'choices':[{'message':{'content':'{"notes":"Evidence"}'},'finish_reason':'stop'}],'usage':{'cost':.001,'is_byok':False}}
        with patch.object(models,'request',return_value=answer) as call:
            self.assertEqual(models.many('summary',['notes'],'summarize'),[{'notes':'Evidence'}])
            models.many('summary',['notes'],'summarize');self.assertEqual(call.call_count,1)
            body=call.call_args.args[2];self.assertEqual(body['response_format']['type'],'json_schema');self.assertTrue(body['provider']['require_parameters']);self.assertEqual(body['service_tier'],'flex');self.assertFalse(body['provider']['allow_fallbacks'])
        self.assertEqual(connection.execute('SELECT sum(cost) FROM generator_calls').fetchone()[0],.001)
        connection.close()
    def test_missing_provider_cost_is_not_reported_as_free(self):
        connection=db.connect(self.path);models=Models(connection,self.id,self.cfg,lambda text:None)
        answer={'choices':[{'message':{'content':'{"notes":"Evidence"}'},'finish_reason':'stop'}]}
        with patch.object(models,'request',return_value=answer):models.many('summary',['notes'],'summarize')
        result=self.owner.get(BASE+'/jobs/'+self.id).json
        self.assertIsNone(result['cost']);self.assertEqual(result['unreported_calls'],1)
        connection.close()
    def test_batch_wait_resume_and_cache(self):
        connection=db.connect(self.path);cfg={**self.cfg,'summary_model':'anthropic/claude-haiku-5.5:batch','summary_service':'default'};models=Models(connection,self.id,cfg,lambda text:None)
        completed={'status':'completed','results':[{'custom_id':'0','response':{'status_code':200,'body':{'choices':[{'message':{'content':'{"notes":"Batch evidence"}'},'finish_reason':'stop'}]}}}],'usage':{'cost':.002,'is_byok':False}}
        with patch.object(models,'request',side_effect=[{'id':'batch_synthetic'},{'status':'in_progress'},completed]) as call:
            with self.assertRaises(PendingBatch):models.many('summary',['evidence'],'summarize')
            payload=call.call_args.args[2];self.assertEqual(payload['model'],'anthropic/claude-haiku-5.5');self.assertEqual(payload['endpoint'],'/v1/chat/completions')
            with self.assertRaises(PendingBatch):models.many('summary',['evidence'],'summarize')
            self.assertEqual(models.many('summary',['evidence'],'summarize'),[{'notes':'Batch evidence'}])
            models.many('summary',['evidence'],'summarize');self.assertEqual(call.call_count,3)
        connection.close()
    def test_ambiguous_submission_never_automatically_rebilled(self):
        connection=db.connect(self.path);models=Models(connection,self.id,self.cfg,lambda text:None)
        with patch.object(models,'request',side_effect=GenerationError('Timeout')) as call:
            with self.assertRaises(GenerationError):models.many('summary',['evidence'],'summarize')
            with self.assertRaisesRegex(GenerationError,'billing outcome is unknown'):models.many('summary',['evidence'],'summarize')
            self.assertEqual(call.call_count,1)
        connection.close()
    def test_cancel_before_work_makes_no_model_calls(self):
        self.owner.post(BASE+'/jobs/'+self.id+'/cancel',json={},headers=self.headers)
        self.run_reviewed();self.assertEqual(self.row()['status'],'cancelled');self.assertEqual(FakeModels.calls,[])

if __name__=='__main__':unittest.main()
