"""Provider isolation, credential privacy, and synchronous Databricks workflow routing."""
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_portal_auth import make_test_app,sign_in,ORIGIN
from portal_api import db
from portal_api.generator import DEFAULTS,BASE
from portal_api.generation_models import Models
from portal_api.generation_providers import databricks_chat,databricks_settings
from portal_api.generator_worker import Engine

ENV={'DATABRICKS_AI_KEY':'synthetic-private-databricks-token','DATABRICKS_BASE_URL':'https://workspace.example/ai-gateway/mlflow/v1','DATABRICKS_MODEL':'system.ai.claude-haiku-5-5','OPENROUTER_API_KEY':''}

class DatabricksTests(unittest.TestCase):
    def setUp(self):
        self.env=patch.dict(os.environ,ENV);self.env.start();self.temp=TemporaryDirectory();self.path=Path(self.temp.name)/'db.sqlite3';self.app=make_test_app(self.path)
        self.owner=self.app.test_client();sign_in(self.owner);token=self.owner.get('/bms_integration_hub/api/me').json['csrf_token'];self.headers={'Origin':ORIGIN,'X-CSRF-Token':token}
        self.config={**DEFAULTS,'provider':'databricks','databricks_model':ENV['DATABRICKS_MODEL'],'topic':'Synthetic source text','title':'Provider test'}
    def tearDown(self):self.temp.cleanup();self.env.stop()
    def start(self):
        response=self.owner.post(BASE+'/jobs',json={'config':self.config},headers=self.headers)
        self.assertEqual(response.status_code,202,response.json);return response.json['id']
    def test_databricks_can_start_without_openrouter_and_never_exposes_secret(self):
        job=self.start();saved=self.owner.get(BASE+'/jobs/'+job).json['config']
        self.assertEqual(saved['provider'],'databricks');self.assertTrue(saved['web_search']);self.assertEqual(saved['web_budget_usd'],5)
        data=self.owner.get(BASE).json;self.assertTrue(data['providers']['databricks']['configured']);self.assertFalse(data['providers']['openrouter']['configured'])
        self.assertNotIn(ENV['DATABRICKS_AI_KEY'],json.dumps(data));self.assertNotIn(ENV['DATABRICKS_BASE_URL'],json.dumps(data))
    def test_batch_and_arbitrary_databricks_models_are_rejected(self):
        for model in ('openai/gpt-6-luna:batch','anthropic/claude-haiku-5.5:batch'):
            response=self.owner.post(BASE+'/jobs',json={'config':{**self.config,'summary_model':model}},headers=self.headers)
            self.assertEqual(response.status_code,400)
        response=self.owner.post(BASE+'/jobs',json={'config':{**self.config,'databricks_model':'different-model'}},headers=self.headers)
        self.assertEqual(response.status_code,503)
    def test_payload_strips_openrouter_fields_and_uses_configured_endpoint(self):
        url,headers,body=databricks_chat(self.config,{'messages':[{'role':'user','content':'JSON please'}],'max_tokens':100,'provider':{'only':['openai/flex']},'plugins':[{'id':'web'}],'service_tier':'flex','response_format':{'type':'json_schema'},'reasoning':{'effort':'none'}})
        self.assertEqual(url,ENV['DATABRICKS_BASE_URL']+'/chat/completions');self.assertEqual(body['model'],ENV['DATABRICKS_MODEL']);self.assertFalse(body['stream']);self.assertEqual(body['thinking'],{'type':'disabled'})
        self.assertEqual(set(body),{'messages','max_tokens','model','stream','thinking'});self.assertIn('Authorization',headers)
        with patch.dict(os.environ,{'DATABRICKS_BASE_URL':'http://unsafe.example'}):
            with self.assertRaisesRegex(Exception,'Configure'):databricks_settings()

    def test_uncertain_databricks_submission_pauses_with_provider_specific_guidance(self):
        job=self.start()
        with db.connect(self.path) as connection:
            connection.execute("UPDATE generator_jobs SET status='failed' WHERE id=?",(job,))
            connection.execute("INSERT INTO generator_calls(job_id,call_key,status,stage) VALUES(?,?,'submitting','summarize')",(job,'uncertain'))
        recovery=self.owner.get(BASE+'/jobs/'+job).json['recovery']
        self.assertFalse(recovery['can_resume']);self.assertIn('Databricks workspace',recovery['blocked_reason']);self.assertNotIn('OpenRouter',recovery['blocked_reason'])
    def test_generation_uses_databricks_cache_and_never_queries_openrouter_billing(self):
        job=self.start();connection=db.connect(self.path);models=Models(connection,job,self.config,lambda text:None)
        result={'id':'db-test-response','model':ENV['DATABRICKS_MODEL'],'choices':[{'message':{'content':'{"notes":"Evidence from B1"}'}}],'usage':{'prompt_tokens':30,'completion_tokens':12}}
        with patch('portal_api.generation_models.monitored_call',return_value=result) as call:
            self.assertEqual(models.many('summary',['source'],'summarize'),[{'notes':'Evidence from B1'}])
            self.assertEqual(models.many('summary',['source'],'summarize'),[{'notes':'Evidence from B1'}]);self.assertEqual(call.call_count,1)
            args=call.call_args.args[5];self.assertEqual(args[1],ENV['DATABRICKS_BASE_URL']+'/chat/completions');self.assertNotIn('provider',args[2])
        row=connection.execute('SELECT * FROM generator_calls').fetchone();self.assertEqual(row['status'],'complete');self.assertFalse(row['cost_known']);self.assertEqual(json.loads(row['billing'])['input_tokens'],30);connection.close()
        progress=self.owner.get(BASE+'/jobs/'+job).json['step_progress'];self.assertEqual(progress['completed'],1);self.assertEqual(progress['total'],1)
    def test_autofill_uses_selected_provider_without_uploads(self):
        response=Mock(status_code=200);response.json.return_value={'choices':[{'message':{'content':'{"title":"Filled title","questions":"What is supported?"}'},'finish_reason':'stop'}]}
        config={**self.config,'title':'','questions':'','documents':[{'name':'private.txt','text':'PRIVATE_UPLOAD'}]}
        with patch('portal_api.generator_autofill.requests.post',return_value=response) as call:
            result=self.owner.post(BASE+'/autofill',json={'config':config},headers=self.headers)
        self.assertEqual(result.status_code,200,result.json);self.assertEqual(result.json['provider'],'databricks');self.assertEqual(call.call_args.args[0],ENV['DATABRICKS_BASE_URL']+'/chat/completions')
        self.assertNotIn('PRIVATE_UPLOAD',json.dumps(call.call_args.kwargs['json']));self.assertNotIn('service_tier',call.call_args.kwargs['json'])

    def test_complete_graph_uses_databricks_for_all_ai_stages_and_exports_pdf(self):
        self.config.update(charts=False,review_passes=1,web_search=False);job=self.start();calls=[]
        def transport(connection,job_id,label,timeout,function,args,**kwargs):
            method,url,body,headers,provider=args;self.assertEqual(provider,'Databricks');self.assertEqual(method,'POST');self.assertEqual(url,ENV['DATABRICKS_BASE_URL']+'/chat/completions');calls.append(body)
            prompt=body['messages'][-1]['content']
            if prompt.startswith('Summarize'):value={'notes':'B1: Synthetic source evidence.'}
            elif prompt.startswith('Create a useful chapter outline'):value={'title':'Provider test','chapters':[{'title':'Findings','brief':'Explain evidence'},{'title':'Actions','brief':'Suggest verification'}]}
            elif prompt.startswith('Review this chapter'):value={'major_issues':[],'minor_notes':[]}
            else:value={'title':'Evidence','paragraphs':['The supplied research should be verified before action [B1].'],'takeaway':'Check the evidence.','charts':[]}
            return {'id':'db-fixture-'+str(len(calls)),'choices':[{'message':{'content':json.dumps(value)},'finish_reason':'stop'}],'usage':{'prompt_tokens':100,'completion_tokens':40}}
        with patch('portal_api.generation_models.monitored_call',side_effect=transport):
            Engine(self.path,job).run()
            self.assertEqual(self.owner.get(BASE+'/jobs/'+job).json['status'],'awaiting_html_review')
            self.assertEqual(self.owner.post(BASE+'/jobs/'+job+'/approve-html',json={},headers=self.headers).status_code,202)
            Engine(self.path,job).run()
        result=self.owner.get(BASE+'/jobs/'+job).json;self.assertEqual(result['status'],'ready',result['error']);self.assertGreaterEqual(len(calls),6)
        pdf=self.path.parent/'generated'/job/'document.pdf';self.assertTrue(pdf.read_bytes().startswith(b'%PDF'))
        self.assertTrue(all('provider' not in body and 'plugins' not in body for body in calls))

if __name__=='__main__':unittest.main()
