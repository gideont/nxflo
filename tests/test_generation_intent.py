"""End-to-end intent, financial and publication regressions without provider spending."""
import json
import math
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from test_portal_auth import make_test_app,sign_in,ORIGIN
from portal_api import db
from portal_api.generator import BASE,DEFAULTS
from portal_api.generator_worker import Engine
from portal_api.generation_errors import GenerationError
from portal_api.generation_intent import context,digest,source_chunks,fidelity_issues
from portal_api.generation_finance import build_financials,calculate,npv,irr,financial_figures,validate_plan
from portal_api.generation_quality import local_publication_issues,assert_publication
from intent_fixtures import BRIEF,ANCHORS,FixtureModels,contract,outline,manuscript,financial_plan


class IntentPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.path=Path(self.temp.name)/'db.sqlite3';self.app=make_test_app(self.path);self.app.config['GENERATOR_PIPELINE_VERSION']=2
        self.owner=self.app.test_client();sign_in(self.owner);token=self.owner.get('/bms_integration_hub/api/me').json['csrf_token'];self.headers={'Origin':ORIGIN,'X-CSRF-Token':token}
        self.config={**DEFAULTS,'document_intent':'product_concept','report_type':'White paper','title':'Investment & Return Simulator','topic':BRIEF,'web_search':False,'review_passes':1}
        FixtureModels.requests=[];FixtureModels.bad_stage=None;FixtureModels.reject_publication=False
        with patch.dict(os.environ,{'OPENROUTER_API_KEY':'synthetic'}):
            response=self.owner.post(BASE+'/jobs',json={'config':self.config},headers=self.headers)
        self.assertEqual(response.status_code,202,response.json);self.id=response.json['id']
    def tearDown(self):self.temp.cleanup()
    def row(self):
        with db.connect(self.path) as c:return dict(c.execute('SELECT * FROM generator_jobs WHERE id=?',(self.id,)).fetchone())
    def run_to_html(self):Engine(self.path,self.id,FixtureModels).run();return self.row()

    def test_original_investment_brief_survives_to_white_paper_with_real_financials(self):
        row=self.run_to_html();self.assertEqual(row['status'],'awaiting_html_review',row['error']);state=json.loads(row['state'])
        self.assertEqual(state['author_original'],BRIEF);self.assertEqual(state['author_contract']['source_hash'],digest(BRIEF))
        self.assertEqual(len(state['author_contract']['items']),len(ANCHORS));self.assertTrue(state['publication_quality']['passed'])
        self.assertEqual([a['stage'] for a in state['intent_audits']],['extract','outline','draft','polish','publication'])
        path=self.path.parent/'generated'/self.id/'document.html';html=path.read_text()
        for phrase in ('FP&amp;A','decision simulator','Three Brothers AI Cartoon','SaaS','Budget-versus-actual','90 days','monthly projection','Non-cash opportunity cost','ROI sensitivity','Participant contributions','Calculation definitions'):
            self.assertIn(phrase,html)
        self.assertGreaterEqual(html.count('class="calculated-figure"'),14)
        self.assertGreaterEqual(html.count('class="report-data-table"'),12)
        self.assertNotIn('not independently verified',html)
        self.assertNotIn('class="cover-credits"',html)
        youtube=state['financials']['groups'][0];base=next(r for r in youtube['results'] if r['case']=='base')
        self.assertEqual([r['revenue'] for r in base['rows'][:2]],[0,0]);self.assertGreater(base['rows'][2]['revenue'],0)
        self.assertLess(next(r for r in youtube['results'] if r['case']=='conservative')['net_gain'],0)
        self.assertGreater(base['net_gain'],0)
        before=list(FixtureModels.requests);self.run_to_html();self.assertEqual(FixtureModels.requests,before)
        self.assertEqual(self.owner.post(BASE+'/jobs/'+self.id+'/approve-html',json={},headers=self.headers).status_code,202)
        Engine(self.path,self.id,FixtureModels).run();self.assertIn(self.row()['status'],('ready','needs_review'))
        from pypdf import PdfReader
        reader=PdfReader(path.with_suffix('.pdf'));text=' '.join(p.extract_text() or '' for p in reader.pages)
        self.assertIn('Worked investment scenarios',text);self.assertIn('hypothetical',text.lower());self.assertIn('NPV',text)
        self.assertEqual(FixtureModels.requests,before,'PDF approval must not repeat paid writing requests')

    def test_material_drift_is_rejected_before_a_preview_exists(self):
        FixtureModels.bad_stage='draft';row=self.run_to_html()
        self.assertEqual(row['status'],'failed');self.assertIn('Intent/provenance gate',row['error'])
        self.assertFalse((self.path.parent/'generated'/self.id/'document.html').exists())
        before=list(FixtureModels.requests);self.run_to_html();self.assertEqual(FixtureModels.requests,before,'Rejected cached content must not be rebilled on resume')

    def test_polishing_cannot_erase_product_examples(self):
        FixtureModels.bad_stage='polish';row=self.run_to_html()
        self.assertEqual(row['status'],'failed');self.assertIn('polish',row['error']);self.assertIn('author anchor',row['error'])

    def test_independent_semantic_gate_can_reject_drift_even_with_structural_coverage(self):
        FixtureModels.reject_publication=True;row=self.run_to_html()
        self.assertEqual(row['status'],'failed');self.assertIn('purpose',row['error']);self.assertIn('academic research',row['error'])
        self.assertFalse((self.path.parent/'generated'/self.id/'document.html').exists())

    def test_v2_shutdown_reuses_completed_requests_and_keeps_author_contract(self):
        from portal_api import generation_shutdown as shutdown
        original_request=FixtureModels.request
        def stop_after_first_draft(models,method,path,body=None):
            result=original_request(models,method,path,body)
            if models.requests[-1]=='draft:0':shutdown.request_stop()
            return result
        with patch.object(shutdown,'_requested',False):
            with patch.object(FixtureModels,'request',stop_after_first_draft):self.run_to_html()
            self.assertEqual(self.row()['status'],'queued')
            state=json.loads(self.row()['state']);self.assertEqual(state['author_original'],BRIEF);self.assertIn('author_contract',state)
            shutdown._requested=False
            row=self.run_to_html();self.assertEqual(row['status'],'awaiting_html_review',row['error'])
        self.assertEqual(FixtureModels.requests.count('draft:0'),1)
        with db.connect(self.path) as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM generator_calls WHERE status='submitting'").fetchone()[0],0)

    def test_unknown_request_cannot_be_bypassed_with_a_different_prompt_hash(self):
        with db.connect(self.path) as connection:
            connection.execute("INSERT INTO generator_calls(job_id,call_key,status,stage) VALUES(?,?,'submitting','older-draft:0')",(self.id,'unknown-old-hash'))
        row=self.run_to_html();self.assertEqual(row['status'],'failed');self.assertIn('unknown billing outcome',row['error'])
        self.assertEqual(FixtureModels.requests,[])
        with db.connect(self.path) as connection:self.assertEqual(connection.execute('SELECT count(*) FROM generator_calls WHERE job_id=?',(self.id,)).fetchone()[0],1)

    def test_v2_databricks_receives_json_schema_without_openrouter_fields(self):
        from portal_api.generation_models import Models
        settings={'DATABRICKS_AI_KEY':'synthetic','DATABRICKS_BASE_URL':'https://workspace.example/ai-gateway/mlflow/v1','DATABRICKS_MODEL':'system.ai.claude-haiku-5-5'}
        cfg={**self.config,'provider':'databricks','databricks_model':settings['DATABRICKS_MODEL'],'_pipeline_version':2}
        result={'id':'db-fixture','choices':[{'message':{'content':'{"items":[]}'},'finish_reason':'stop'}],'usage':{'prompt_tokens':50,'completion_tokens':10}}
        with db.connect(self.path) as connection,patch.dict(os.environ,settings),patch('portal_api.generation_models.monitored_call',return_value=result) as transport:
            models=Models(connection,self.id,cfg,lambda text:None)
            self.assertEqual(models.many('summary',['Extract exact author intent.'],'author-intent'),[{'items':[]}])
            payload=transport.call_args.args[5][2]
            self.assertIn('OUTPUT_SCHEMA',payload['messages'][-1]['content']);self.assertIn('author-intent analyst',payload['messages'][0]['content'])
            self.assertNotIn('response_format',payload);self.assertNotIn('provider',payload)
            row=connection.execute('SELECT billing,cost_known FROM generator_calls WHERE job_id=?',(self.id,)).fetchone()
            self.assertEqual(json.loads(row['billing'])['billing_provider'],'databricks');self.assertEqual(row['cost_known'],0)

    def test_existing_v2_prompt_policy_is_pinned_for_cached_recovery(self):
        from portal_api.generation_models import Models
        from portal_api.generation_intent import instructions
        with db.connect(self.path) as connection:
            state=json.loads(connection.execute('SELECT state FROM generator_jobs WHERE id=?',(self.id,)).fetchone()[0]);state.pop('prompt_policy_version',None)
            connection.execute('UPDATE generator_jobs SET state=? WHERE id=?',(json.dumps(state),self.id))
        engine=Engine(self.path,self.id);self.assertEqual(engine.config['_prompt_policy_version'],1)
        result={'choices':[{'message':{'content':'{"notes":"Evidence"}'},'finish_reason':'stop'}],'usage':{'cost':0,'is_byok':False}}
        with patch('portal_api.generation_models.monitored_call',return_value=result) as transport:
            for _ in range(2):self.assertEqual(engine.models.many('summary',['same prompt'],'summarize'),[{'notes':'Evidence'}])
            self.assertEqual(transport.call_count,1)
            payload=transport.call_args.args[5][2]
            self.assertEqual(payload['messages'][0]['content'],'You are a professional document author and editor. '+instructions(engine.config)+' Return only the requested JSON or text.')
        engine.db.close()

    def test_approval_rejects_an_altered_preview(self):
        self.run_to_html();path=self.path.parent/'generated'/self.id/'document.html';path.write_text(path.read_text()+' changed')
        response=self.owner.post(BASE+'/jobs/'+self.id+'/approve-html',json={},headers=self.headers)
        self.assertEqual(response.status_code,409);self.assertIn('changed',response.json['error'])


class ContractAndFinanceTests(unittest.TestCase):
    def setUp(self):
        self.config={**DEFAULTS,'_pipeline_version':2,'document_intent':'product_concept','topic':BRIEF};self.contract=contract(self.config)
    def test_every_brief_character_is_addressed_and_original_context_is_used(self):
        text='original thesis '*2000+'TAIL: preserve the final product principle.'
        self.assertEqual(''.join(p['text'] for p in source_chunks(text)),text)
        state={'author_original':BRIEF,'author_contract':self.contract}
        self.assertIn(BRIEF,context(state,['A1']))
        state['author_original']=BRIEF+'changed'
        with self.assertRaises(GenerationError):context(state)
    def test_publication_rejects_placeholders_leaked_instructions_formulas_and_missing_sections(self):
        for bad in ('TODO: insert chart here','Editorial instruction: rewrite this paragraph','ROI = revenue / initial_investment','This is not financial advice. This is not financial advice.'):
            doc=manuscript();doc['chapters'][0]['paragraphs'].append(bad)
            errors=local_publication_issues(doc,self.contract,self.config,[{'id':'B1','role':'author','text':BRIEF}],outline()['chapters'])
            self.assertTrue(errors,bad)
        doc=manuscript();doc['chapters'][-1]['section_keys']=[]
        self.assertTrue(any('Missing required section' in e for e in local_publication_issues(doc,self.contract,self.config,[{'id':'B1','text':BRIEF}],outline()['chapters'])))
    def test_empirical_fabrications_still_fail(self):
        doc=manuscript();doc['chapters'][0]['paragraphs'].append('Market adoption was 987654.32 percent [R404].')
        errors=local_publication_issues(doc,self.contract,self.config,[{'id':'B1','role':'author','text':BRIEF}],outline()['chapters'])
        self.assertTrue(any('Unknown source' in error for error in errors))
        self.assertTrue(any('absent from' in error for error in errors))
    def test_each_mode_has_distinct_writing_review_and_structure_contracts(self):
        from portal_api.generation_intent import MODES,instructions,review_instructions
        writing=[];reviewing=[]
        for mode in MODES:
            cfg={**self.config,'document_intent':mode};value=contract(cfg)
            self.assertEqual(value['mode'],mode);self.assertTrue(value['required_sections'])
            writing.append(instructions(cfg));reviewing.append(review_instructions(cfg))
        self.assertEqual(len(set(writing)),4);self.assertEqual(len(set(reviewing)),4)

    def test_external_fact_extraction_is_neutral_rather_than_product_advocacy(self):
        from portal_api.generation_intent import system_for_stage
        for stage in ('web-research','summarize','consolidate-0'):
            policy=system_for_stage(self.config,stage)
            self.assertIn('neutral factual evidence analyst',policy)
            self.assertIn('contradictory findings',policy)
            self.assertNotIn('advocate',policy)
        self.assertIn('independent factual and editorial reviewer',system_for_stage(self.config,'publication-quality'))
        self.assertIn('proposed product',system_for_stage(self.config,'draft'))

    def test_uploaded_author_material_is_retained_and_references_are_separate(self):
        from portal_api.generation_intent import author_material
        cfg={**self.config,'documents':[{'name':'manuscript.txt','text':'Preserve this authorial appendix.','role':'author'},{'name':'study.txt','text':'External evidence must not redefine the thesis.','role':'reference'}]}
        text=author_material(cfg)
        self.assertTrue(text.startswith(BRIEF));self.assertIn('Preserve this authorial appendix.',text)
        self.assertNotIn('External evidence must not redefine the thesis.',text)

    def test_content_preserving_rewrite_keeps_the_original_heading_order(self):
        import re
        value=contract({**self.config,'document_intent':'content_preserving_rewrite'})
        main=[entry for entry in value['structure'] if entry['level']==2]
        doc=manuscript();first=doc['chapters'][0]
        paragraphs=[p for ch in doc['chapters'] for p in ch['paragraphs']]
        coverage=[proof for ch in doc['chapters'] for proof in ch['coverage']]
        doc={'chapters':[{'title':re.sub(r'^\d+[. ]*','',entry['title']),'paragraphs':paragraphs if i==0 else ['Additional detail.'],'coverage':coverage if i==0 else []} for i,entry in enumerate(main)]}
        self.assertFalse(fidelity_issues(doc,value))
        doc['chapters'].reverse();self.assertTrue(any('heading sequence' in issue for issue in fidelity_issues(doc,value)))

    def test_known_driver_cash_flows_and_discount_timing(self):
        group={'kind':'generic','months':3,'participants':[{'name':'Founder','cash_contribution':100,'profit_share':1}]}
        scenario={'case':'base','inputs':{'initial_investment':100,'fixed_monthly_cost':0,'hours_per_month':0,'hourly_opportunity_value':0,'annual_discount_rate':.1,'initial_units':1,'monthly_unit_growth':0,'unit_price':110,'variable_cost_per_unit':0}}
        result=calculate(group,scenario)
        self.assertEqual(result['cash_flows'],[-100,110,110,110]);self.assertEqual(result['net_gain'],230)
        self.assertEqual(result['roi_pct'],230);self.assertEqual(result['break_even_month'],1)
        expected=-100+sum(110/(1.1)**(month/12) for month in range(1,4))
        self.assertAlmostEqual(result['npv'],round(expected,2))
        self.assertEqual(result['distributions'][0]['distribution'],330)
        group=financial_plan()['groups'][1];scenario=group['scenarios'][1];scenario['inputs'].update(churn_rate=.1,monthly_acquisition_growth=0)
        result=calculate(group,scenario)
        self.assertEqual(result['rows'][0]['units'],10);self.assertEqual(result['rows'][1]['units'],19)
        self.assertEqual(result['rows'][0]['revenue'],290);self.assertEqual(result['rows'][1]['revenue'],551)

    def test_financial_calculations_balance_and_use_explicit_assumptions(self):
        result=build_financials(financial_plan())
        for group in result['groups']:
            for scenario in group['results']:
                self.assertAlmostEqual(scenario['net_gain'],-scenario['initial_investment']+sum(r['net_cash_flow'] for r in scenario['rows']),places=7)
                self.assertAlmostEqual(scenario['roi_pct'],scenario['net_gain']/scenario['initial_investment']*100)
                self.assertEqual(scenario['maximum_funding_requirement'],max(scenario['initial_investment'],-min(r['cumulative_cash_flow'] for r in scenario['rows'])))
                for row in scenario['rows']:self.assertAlmostEqual(row['economic_profit'],row['net_cash_flow']-row['opportunity_cost'])
                if scenario['distributions']:
                    funding=sum(p['cash_contribution'] for p in group['participants'])
                    self.assertAlmostEqual(sum(p['distribution'] for p in scenario['distributions']),max(0,funding+scenario['net_gain']))
            figures,_=financial_figures(group)
            self.assertEqual(len(figures),7)
            self.assertTrue(all('Hypothetical' in f['caption'] for f in figures))
    def test_npv_timing_irr_and_undefined_cases(self):
        self.assertAlmostEqual(float(npv([-100,110],.1)),0,places=10)
        self.assertAlmostEqual(irr([-100,110]),.1,places=8)
        self.assertIsNone(irr([-100,-10,-20]));self.assertIsNone(irr([-100,230,-132]))
        group=financial_plan()['groups'][0];scenario=group['scenarios'][1];scenario['inputs']['initial_investment']=0
        self.assertIsNone(calculate(group,scenario)['roi_pct'])
    def test_invalid_assumptions_and_non_cash_double_counting(self):
        plan=financial_plan();plan['groups'][0]['scenarios'][0]['inputs']['rpm']=float('nan')
        with self.assertRaises(GenerationError):build_financials(plan)
        plan=financial_plan();plan['groups'][0]['participants'][0]['profit_share']=2
        with self.assertRaises(GenerationError):build_financials(plan)
        group=financial_plan()['groups'][0];scenario=group['scenarios'][1];before=calculate(group,scenario)
        scenario['inputs']['hourly_opportunity_value']*=2;after=calculate(group,scenario)
        self.assertEqual(before['cash_flows'],after['cash_flows']);self.assertLess(after['rows'][0]['economic_profit'],before['rows'][0]['economic_profit'])

if __name__=='__main__':unittest.main()
