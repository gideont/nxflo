"""Selected-model-only verification, shared budgets, and durable recovery."""
from copy import deepcopy
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier,Thread
import unittest
from unittest.mock import patch
from portal_api import db
from portal_api.generator import BASE,DEFAULTS
from portal_api.generator_worker import Engine
from portal_api.generation_models import Models
from portal_api.generation_errors import GenerationError
from portal_api.generation_intent import digest
from portal_api.research_client import ResearchClient,model_rates
from portal_api.research_store import Store,ResearchPaused,summary
from portal_api.research_workflow import validate_assessments,blocks,Verifier
from test_portal_auth import make_test_app,sign_in,ORIGIN
from regulatory_fixtures import BRIEF,saved_state,CLAIMS

MODEL='system.ai.claude-haiku-5-5'
ENV={'DATABRICKS_AI_KEY':'synthetic-databricks-secret','DATABRICKS_BASE_URL':'https://workspace.example/ai-gateway/mlflow/v1','DATABRICKS_MODEL':MODEL,'TAVILY_API_KEY':'synthetic-search-secret','TAVILY_REMOTE_MCP':'https://mcp.tavily.com/mcp/?tavilyApiKey=synthetic-search-secret'}
RATES={'input':.5,'output':2.5,'buffer':1.5,'assumed':True,'checked_at':'2026-11-08'}
RULE='https://example.gov/rules';GUIDE='https://example.gov/guidance'
CORRECT=CLAIMS[1].replace('around 2024','in 2019').replace('$100,000','$150,000')
SOURCE='\n\n'.join([CORRECT,CLAIMS[2],CLAIMS[3]])

class NoWriting(Models):
    def many(self,*a,**kw):raise AssertionError('Verification must not repeat chapter generation or ordinary writing calls')

class ResearchTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.path=Path(self.temp.name)/'test.sqlite3';self.app=make_test_app(self.path);self.app.config['GENERATOR_PIPELINE_VERSION']=2
        self.owner=self.app.test_client();sign_in(self.owner);csrf=self.owner.get('/bms_integration_hub/api/me').json['csrf_token'];self.headers={'Origin':ORIGIN,'X-CSRF-Token':csrf}
        self.env=patch.dict(os.environ,ENV);self.env.start()
        self.config={**DEFAULTS,'provider':'databricks','databricks_model':MODEL,'topic':BRIEF,'title':'Backyard Espresso','document_intent':'content_preserving_rewrite','web_search':False}
        response=self.owner.post(BASE+'/jobs',json={'config':self.config},headers=self.headers);self.assertEqual(response.status_code,202,response.json)
        self.id=response.json['id'];self.doc=response.json['document_id'];self.source_state=saved_state(self.config);self.source_state.pop('publication_review');self.source_state.pop('quality_errors')
        with db.connect(self.path) as c:c.execute("UPDATE generator_jobs SET status='needs_review',step='deliver',state=? WHERE id=?",(json.dumps(self.source_state),self.id))
        directory=self.path.parent/'generated'/self.id;directory.mkdir(parents=True);(directory/'document.html').write_text('Original saved document');(directory/'document.pdf').write_bytes(b'original-pdf')
        self.ai_calls=[];self.retrieval_calls=[];self.inconclusive=False;self.bad_quote=False;self.bad_recheck=False;self.anchor_warnings=False
    def tearDown(self):self.env.stop();self.temp.cleanup()
    def start(self):
        response=self.owner.post(BASE+'/jobs/'+self.id+'/verify',json={},headers=self.headers);self.assertEqual(response.status_code,202,response.json);return response.json
    def row(self,job_id):
        with db.connect(self.path) as c:return dict(c.execute('SELECT * FROM generator_jobs WHERE id=?',(job_id,)).fetchone())
    def provider(self,models,method,path,body=None):
        self.assertEqual(method,'POST');self.assertEqual(path,'/chat/completions');self.assertEqual(body['model'],MODEL);self.assertEqual(models.config['provider'],'databricks');self.assertNotIn('plugins',body)
        self.ai_calls.append(body);prompt=body['messages'][-1]['content']
        if 'Identify ALL checkable' in prompt:
            content=json.loads(prompt.split('Blocks: ',1)[1]);claims=[]
            for key,block in content.items():
                if key.startswith('P') and any(marker in block['text'] for marker in ('MEHKO permits','Food Premises Regulation','33.3%')):
                    claims.append({'text':block['text'],'excerpt':block['text'],'block':key,'kind':'regulatory','scope':'Mock jurisdictions and current period','group':'regulation','query':'official regulation rules and guidance'})
            result={'claims':claims}
        elif 'Independently verify EACH' in prompt:
            claims=json.JSONDecoder().raw_decode(prompt.split('\nClaims: ',1)[1])[0];result={'claims':[]}
            for claim in claims:
                text=claim['text'];old='2024' in text;quote=CORRECT if 'MEHKO' in text else CLAIMS[2] if 'Food Premises' in text else CLAIMS[3]
                result['claims'].append({'id':claim['id'],'status':'unresolved' if self.inconclusive or self.bad_recheck and 'independent recheck' in prompt else 'contradicted' if old else 'supported','reason':'The source establishes the applicable requirements.' if not old else 'The provided year and cap differ from the controlling rule.','suggested_correction':CORRECT if old else '',
                    'evidence':[{'url':url,'quote':'invented quote not in the page' if self.bad_quote else quote,'authority':authority,'scope_matches':True,'date_matches':True} for url,authority in ((RULE,'primary_rule'),(GUIDE,'official_guidance'))]})
        elif 'Apply ONE minimal' in prompt:
            content=json.JSONDecoder().raw_decode(prompt.split('\nBlocks: ',1)[1])[0];claims=json.JSONDecoder().raw_decode(prompt.split('\nClaims and assessments: ',1)[1])[0]
            result={'patches':[{'block':key,'before':block['text'],'after':block['text'].replace('around 2024','in 2019').replace('$100,000','$150,000'),'claim_ids':[c['id'] for c in claims if key in c['blocks']],'reason':'Corrected the factual date and threshold from official evidence.'} for key,block in content.items() if '2024' in block['text']]}
        elif 'Independently assess this manuscript' in prompt:
            keys=json.JSONDecoder().raw_decode(prompt.split('Evaluate each required criterion exactly once: ',1)[1])[0]
            result={'checks':[{'criterion':key,'passed':True,'evidence_blocks':['P1.0'],'reason':'The original intent, sourced corrections and required sections are preserved.','issue_type':'none'} for key in keys]}
            if self.anchor_warnings:
                for check in result['checks']:
                    if check['criterion'].startswith(('author:','section:')) or check['criterion']=='publication':check.update(passed=False,issue_type='unverified_claim',reason='The original message is preserved, but its regulatory assertion is unverified without external evidence.')
        else:raise AssertionError('Unexpected model task')
        return {'choices':[{'message':{'content':json.dumps(result)},'finish_reason':'stop'}],'usage':{'prompt_tokens':300,'completion_tokens':200}}
    def tavily(self,*args,**kwargs):
        method,url,body,headers,provider=args[5];self.assertEqual(method,'POST');self.assertEqual(headers['Authorization'],'Bearer '+ENV['TAVILY_API_KEY']);self.assertEqual(provider,'Tavily');self.retrieval_calls.append((url,body))
        if url.endswith('/search'):
            self.assertFalse(body['include_answer']);self.assertFalse(body['auto_parameters']);self.assertTrue(body['include_usage']);self.assertLessEqual(body['max_results'],5)
            return {'results':[{'url':RULE},{'url':GUIDE}],'usage':{'credits':2 if body['search_depth']=='advanced' else 1},'answer':'This generated answer must never be used.'}
        self.assertTrue(url.endswith('/extract'));return {'results':[{'url':url,'raw_content':SOURCE} for url in body['urls']],'usage':{'credits':1}}
    def run_job(self,job):
        fixture=self
        def model(models,*a,**kw):return fixture.provider(models,*a,**kw)
        with patch('portal_api.research_client.model_rates',return_value=RATES),patch.object(Models,'request',new=model),patch('portal_api.research_client.monitored_call',side_effect=self.tavily),patch('portal_api.generation_sources.public_addresses',return_value=['93.184.216.34']):Engine(self.path,job,NoWriting).run()
        return self.row(job)

    def test_verification_revision_corrects_facts_without_rewriting_or_destroying_previous_files(self):
        job=self.start();self.assertEqual(job['version'],'1.1');again=self.start();self.assertEqual(again['id'],job['id']);self.assertTrue(again['reused'])
        row=self.run_job(job['id']);self.assertEqual(row['status'],'awaiting_html_review',row['error']);state=json.loads(row['state'])
        self.assertEqual(state['publication_quality']['outcome'],'PASS');self.assertEqual(state['author_original'],BRIEF)
        self.assertEqual(state['document']['chapters'][1]['paragraphs'][0],CORRECT)
        self.assertEqual(state['document']['chapters'][0],self.source_state['document']['chapters'][0]);self.assertEqual(len(state['research_corrections']),1)
        self.assertEqual(state['research_corrections'][0]['before'],CLAIMS[1]);self.assertEqual(state['research_corrections'][0]['after'],CORRECT)
        response=self.owner.get(BASE+'/jobs/'+self.id+'/download/pdf');self.assertEqual(response.data,b'original-pdf');response.close()
        before=(len(self.ai_calls),len(self.retrieval_calls))
        self.assertEqual(self.owner.post(BASE+'/jobs/'+job['id']+'/approve-html',json={},headers=self.headers).status_code,202)
        self.run_job(job['id']);self.assertEqual(self.row(job['id'])['status'],'ready');self.assertEqual(before,(len(self.ai_calls),len(self.retrieval_calls)))
        data=self.owner.get(BASE+'/jobs/'+job['id']+'/verification').json;self.assertEqual(data['counts']['corrected'],1);self.assertGreater(data['budget']['estimated_spent'],0);self.assertLess(data['budget']['estimated_spent'],5)
        self.assertNotIn(ENV['TAVILY_API_KEY'],json.dumps(data));self.assertNotIn(ENV['DATABRICKS_AI_KEY'],json.dumps(data))
        with db.connect(self.path) as c:self.assertFalse(c.execute("SELECT 1 FROM generator_calls WHERE job_id=? AND stage IN ('draft:0','outline:0')",(job['id'],)).fetchone())
    def test_missing_evidence_produces_downloadable_warning_and_stops_after_two_searches(self):
        self.inconclusive=True;self.anchor_warnings=True;job=self.start();row=self.run_job(job['id']);self.assertEqual(row['status'],'needs_review',row['error'])
        state=json.loads(row['state']);self.assertEqual(state['publication_quality']['outcome'],'WARNING');self.assertEqual(state['document'],self.source_state['document'])
        self.assertEqual(sum(url.endswith('/search') for url,_ in self.retrieval_calls),2)
        before=(len(self.ai_calls),len(self.retrieval_calls));self.run_job(job['id']);self.assertEqual(before,(len(self.ai_calls),len(self.retrieval_calls)))
        response=self.owner.get(BASE+'/jobs/'+job['id']+'/download/pdf');self.assertEqual(response.status_code,200);response.close()
    def test_saved_inventory_wrong_block_rebinds_only_unique_exact_excerpt_without_rebilling(self):
        engine=Engine(self.path,self.id);verifier=Verifier(engine)
        content={'P0.0':{'text':'An unrelated introductory sentence.','kind':'paragraph'},'P1.0':{'text':'The ordinance limits daily customers to three.','kind':'paragraph'}}
        value={'claims':[{'text':'Daily customers are limited to three.','excerpt':content['P1.0']['text'],'block':'P0.0','kind':'regulatory','scope':'Vancouver present rules','group':'limits','query':'official daily customer limits'}]}
        response={'choices':[{'message':{'content':json.dumps(value)},'finish_reason':'stop'}],'usage':{'prompt_tokens':300,'completion_tokens':200}}
        with patch('portal_api.research_client.model_rates',return_value=RATES),patch.object(Models,'request',return_value=response) as paid:
            claims=verifier.inventory({},content);self.assertEqual(claims[0]['blocks'],['P1.0'])
            # A new validator re-parses saved raw output instead of re-paying.
            engine.db.execute('DELETE FROM generator_research_cache')
            self.assertEqual(verifier.inventory({},content),claims);self.assertEqual(paid.call_count,1)
            value['claims'][0]['excerpt']='An invented assertion that appears nowhere.'
            with patch.object(verifier.client,'ai',return_value=value):
                engine.db.execute('DELETE FROM generator_research_cache')
                with self.assertRaises(ResearchPaused):verifier.inventory({},content)
        engine.db.close()
    def test_failed_corrective_recheck_cannot_loop_or_clear_warning(self):
        self.bad_recheck=True;job=self.start();row=self.run_job(job['id']);self.assertEqual(row['status'],'needs_review',row['error'])
        state=json.loads(row['state']);self.assertEqual(state['document'],self.source_state['document']);self.assertFalse(state.get('research_corrections'))
        self.assertEqual(sum('Apply ONE minimal' in body['messages'][-1]['content'] for body in self.ai_calls),1)
        self.assertEqual(sum('This is the independent recheck' in body['messages'][-1]['content'] for body in self.ai_calls),1)
    def test_shared_allowance_explicit_increase_authentication_and_no_reset(self):
        job=self.start();self.assertEqual(self.owner.post(BASE+'/documents/'+self.doc+'/research-budget',json={'limit_usd':4},headers=self.headers).status_code,400)
        response=self.owner.post(BASE+'/documents/'+self.doc+'/research-budget',json={'limit_usd':7},headers=self.headers);self.assertEqual(response.status_code,200,response.json)
        self.assertEqual(self.owner.post(BASE+'/documents/'+self.doc+'/research-budget',json={'limit_usd':7},headers=self.headers).status_code,200)
        self.assertEqual(self.app.test_client().get(BASE+'/jobs/'+job['id']+'/verification').status_code,401)
        self.assertEqual(self.owner.post(BASE+'/documents/'+self.doc+'/research-budget',json={'limit_usd':8}).status_code,403)
        with db.connect(self.path) as c:self.assertEqual(summary(c,self.doc)['limit'],7);self.assertEqual(c.execute('SELECT count(*) FROM generator_research_budget_log').fetchone()[0],1)
    def test_budget_reservation_is_atomic_across_connections(self):
        with db.connect(self.path) as c:c.execute('UPDATE generator_research_budgets SET limit_usd=.02 WHERE document_id=?',(self.doc,))
        barrier=Barrier(2);results=[]
        def reserve(index):
            with db.connect(self.path) as c:
                barrier.wait()
                try:Store(c,self.id).reserve('concurrent-'+str(index),'research-tavily:search',.016);results.append(True)
                except ResearchPaused:results.append(False)
        threads=[Thread(target=reserve,args=(i,)) for i in range(2)]
        for t in threads:t.start()
        for t in threads:t.join()
        self.assertEqual(sorted(results),[False,True])
    def test_same_reserved_request_can_be_claimed_only_once(self):
        with db.connect(self.path) as c:Store(c,self.id).reserve('one-request','research-tavily:search',.008)
        barrier=Barrier(2);results=[]
        def claim():
            with db.connect(self.path) as c:
                barrier.wait()
                try:Store(c,self.id).begin('one-request');results.append(True)
                except ResearchPaused:results.append(False)
        threads=[Thread(target=claim) for _ in range(2)]
        for t in threads:t.start()
        for t in threads:t.join()
        self.assertEqual(sorted(results),[False,True])

    def test_unknown_tavily_outcome_holds_allowance_and_never_repeats(self):
        engine=Engine(self.path,self.id);client=ResearchClient(engine)
        with patch('portal_api.research_client.model_rates',return_value=RATES),patch('portal_api.research_client.monitored_call',side_effect=GenerationError('Tavily connection interrupted')) as transport:
            with self.assertRaises(GenerationError):client.search('rules')
            with self.assertRaises(ResearchPaused):client.search('rules')
            self.assertEqual(transport.call_count,1)
        self.assertEqual(client.store.budget()['reserved'],.008);engine.db.close()
    def test_invalid_quotes_wrong_scope_and_wrong_dates_never_support_claim(self):
        from portal_api.research_workflow import official
        self.assertTrue(official('https://bylaws.vancouver.ca/zoning/zoning-by-law.pdf'))
        self.assertFalse(official('https://vancouver.ca.example.org/rules'))
        claim={'id':'c','text':'A factual legal claim','kind':'regulatory','blocks':['P0.0']};sources=[{'id':'V1','url':RULE,'text':SOURCE},{'id':'V2','url':GUIDE,'text':SOURCE}]
        good={'id':'c','status':'supported','reason':'Verified','evidence':[{'url':u,'quote':CORRECT,'authority':a,'scope_matches':True,'date_matches':True} for u,a in ((RULE,'primary_rule'),(GUIDE,'official_guidance'))]}
        self.assertEqual(validate_assessments({'claims':[good]},[claim],sources)[0]['status'],'supported')
        for change in ({'quote':'This quotation is fabricated.'},{'scope_matches':False},{'date_matches':False},{'url':'https://blog.example/unknown'}):
            value=deepcopy(good);value['evidence'][0].update(change)
            self.assertEqual(validate_assessments({'claims':[value]},[claim],sources)[0]['status'],'unresolved')
    def test_retrieval_cache_reuses_same_day_but_refreshes_a_later_date(self):
        engine=Engine(self.path,self.id);client=ResearchClient(engine)
        with patch('portal_api.research_client.model_rates',return_value=RATES),patch('portal_api.research_client.monitored_call',side_effect=self.tavily):
            with patch('portal_api.research_client.verification_date',return_value='2026-11-08'):
                client.search('official rules');client.search('official rules');self.assertEqual(len(self.retrieval_calls),1)
            with patch('portal_api.research_client.verification_date',return_value='2026-11-09'):
                client.search('official rules');self.assertEqual(len(self.retrieval_calls),2)
        engine.db.close()

    def test_oversized_packet_is_rejected_before_reservation_or_provider_call(self):
        engine=Engine(self.path,self.id);client=ResearchClient(engine)
        with patch.object(Models,'request') as transport,patch('portal_api.research_client.model_rates') as prices:
            with self.assertRaises(ResearchPaused):client.ai('assess','x'*210000)
            transport.assert_not_called();prices.assert_not_called()
        self.assertEqual(client.store.budget()['reserved'],0);engine.db.close()

    def test_missing_matching_model_price_and_tavily_research_are_blocked(self):
        with patch('portal_api.generator_pricing.read_prices',return_value={'models':{},'checked_at':'today'}):
            with self.assertRaises(ResearchPaused):model_rates(self.config)
        engine=Engine(self.path,self.id);client=ResearchClient(engine)
        with patch('portal_api.research_client.model_rates',return_value=RATES):
            with self.assertRaises(GenerationError):client.tavily('research',{'input':'Do deep research'})
        engine.db.close()

    def test_insufficient_allowance_stops_before_paid_requests_and_topup_reuses_saved_manuscript(self):
        with db.connect(self.path) as c:c.execute('UPDATE generator_research_budgets SET limit_usd=.000001 WHERE document_id=?',(self.doc,))
        first=self.start();row=self.run_job(first['id']);self.assertEqual(row['status'],'needs_review',row['error'])
        state=json.loads(row['state']);self.assertEqual(state['research']['pause_reason'],'budget_exhausted');self.assertEqual(self.ai_calls,[]);self.assertEqual(self.retrieval_calls,[])
        data=self.owner.get(BASE+'/jobs/'+first['id']+'/verification').json;self.assertGreater(data['estimated_additional']['low'],0)
        self.owner.post(BASE+'/documents/'+self.doc+'/research-budget',json={'limit_usd':5},headers=self.headers)
        response=self.owner.post(BASE+'/jobs/'+first['id']+'/verify',json={},headers=self.headers);self.assertEqual(response.status_code,202,response.json);self.assertEqual(response.json['version'],'1.2')
        row=self.run_job(response.json['id']);self.assertEqual(row['status'],'awaiting_html_review',row['error'])
        self.assertEqual(json.loads(row['state'])['document']['chapters'][1]['paragraphs'][0],CORRECT)
    def test_unchanged_completed_verification_returns_current_version_without_billing(self):
        job=self.start();self.run_job(job['id']);self.owner.post(BASE+'/jobs/'+job['id']+'/approve-html',json={},headers=self.headers);self.run_job(job['id'])
        before=(len(self.ai_calls),len(self.retrieval_calls))
        response=self.owner.post(BASE+'/jobs/'+job['id']+'/verify',json={},headers=self.headers)
        self.assertEqual(response.status_code,202,response.json);self.assertEqual(response.json['id'],job['id']);self.assertTrue(response.json['reused']);self.assertEqual(before,(len(self.ai_calls),len(self.retrieval_calls)))
    def test_invalid_citation_blocks_before_any_research_spending(self):
        self.source_state['document']['chapters'][0]['paragraphs'].append('A fabricated assertion [R404].')
        with db.connect(self.path) as c:c.execute('UPDATE generator_jobs SET state=? WHERE id=?',(json.dumps(self.source_state),self.id))
        job=self.start();row=self.run_job(job['id']);self.assertEqual(row['status'],'failed');self.assertEqual(json.loads(row['state'])['publication_quality']['outcome'],'BLOCKED')
        self.assertEqual(self.ai_calls,[]);self.assertEqual(self.retrieval_calls,[])
    def test_fabricated_evidence_remains_unresolved_even_if_model_says_supported(self):
        self.bad_quote=True;job=self.start();row=self.run_job(job['id']);self.assertEqual(row['status'],'needs_review',row['error'])
        state=json.loads(row['state']);self.assertTrue(all(c['status']=='unresolved' for c in state['research']['claims']));self.assertFalse(state['publication_quality']['passed'])

if __name__=='__main__':unittest.main()
