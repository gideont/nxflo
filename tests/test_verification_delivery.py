"""Publication warning delivery from durable checkpoints, with no live requests."""
import json
import os
import unittest
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from portal_api import db
from portal_api.generator import BASE,DEFAULTS
from portal_api.generator_worker import Engine
from portal_api.generation_models import Models
from portal_api.generation_quality import assert_publication,publication_fingerprint
from portal_api.generation_verification import decide,research
from portal_api.generation_publication import review_blocks
from portal_api.generation_errors import GenerationError
from test_portal_auth import make_test_app,sign_in,ORIGIN
from regulatory_fixtures import BRIEF,REJECTION,saved_state

class NoPaidCalls(Models):
    def request(self,*a,**kw):raise AssertionError('Recovery must not submit or poll a provider request')

class VerificationDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.path=Path(self.temp.name)/'db.sqlite3';self.app=make_test_app(self.path);self.app.config['GENERATOR_PIPELINE_VERSION']=2
        self.owner=self.app.test_client();sign_in(self.owner);csrf=self.owner.get('/bms_integration_hub/api/me').json['csrf_token'];self.headers={'Origin':ORIGIN,'X-CSRF-Token':csrf}
        self.config={**DEFAULTS,'title':'The Backyard Espresso Paradox','document_intent':'content_preserving_rewrite','topic':BRIEF,'web_search':False}
        with patch.dict(os.environ,{'OPENROUTER_API_KEY':'synthetic'}):response=self.owner.post(BASE+'/jobs',json={'config':self.config},headers=self.headers)
        self.assertEqual(response.status_code,202,response.json);self.id=response.json['id'];self.state=saved_state(self.config)
        self.save()
    def tearDown(self):self.temp.cleanup()
    def save(self):
        review=self.state['publication_review']
        with db.connect(self.path) as c:
            c.execute("UPDATE generator_jobs SET status='failed',step='assemble',error=?,state=? WHERE id=?",('Publication-quality gate rejected the manuscript: accuracy: '+REJECTION,json.dumps(self.state),self.id))
            c.execute('DELETE FROM generator_calls WHERE job_id=?',(self.id,))
            c.execute("INSERT INTO generator_calls(job_id,call_key,status,stage,result,cost,cost_known) VALUES(?,?,'complete','publication-quality-assets-v2:0',?,0.02,1)",(self.id,'saved-regulatory-review',json.dumps([{'content':'```json\n'+json.dumps(review)+'\n```'}])))
    def row(self):
        with db.connect(self.path) as c:return dict(c.execute('SELECT * FROM generator_jobs WHERE id=?',(self.id,)).fetchone())
    def test_exact_saved_regulatory_failure_delivers_marked_html_and_pdf_without_paid_calls(self):
        with patch.dict(os.environ,{'OPENROUTER_API_KEY':'synthetic'}):
            response=self.owner.post(BASE+'/jobs/'+self.id+'/resume',json={},headers=self.headers)
        self.assertEqual(response.status_code,202,response.json)
        Engine(self.path,self.id,NoPaidCalls).run();row=self.row();self.assertEqual(row['status'],'needs_review',row['error'])
        state=json.loads(row['state']);gate=state['publication_quality'];self.assertEqual(gate['outcome'],'WARNING');self.assertFalse(gate['passed'])
        self.assertEqual(state['document'],self.state['document']);self.assertEqual(state['author_original'],BRIEF)
        self.assertEqual(state['publication_correction']['attempts'],1);self.assertEqual(state['next_step'],'end')
        for kind in ('html','pdf'):
            response=self.owner.get(BASE+'/jobs/'+self.id+'/download/'+kind);self.assertEqual(response.status_code,200);self.assertTrue(response.data);response.close()
        response=self.owner.get(BASE+'/jobs/'+self.id+'/download/html');html=response.data.decode();response.close()
        for phrase in ('UNVERIFIED DRAFT','confirmation required','not authoritative legal guidance','33.3%','46 m²','$100,000','Outstanding verification issues',REJECTION):self.assertIn(phrase.replace("'",'&#x27;') if phrase==REJECTION else phrase,html)
        from pypdf import PdfReader
        text=' '.join(p.extract_text() or '' for p in PdfReader(self.path.parent/'generated'/self.id/'document.pdf').pages)
        self.assertIn('UNVERIFIED DRAFT',text);self.assertIn('confirmation required',text)
        api=self.owner.get(BASE+'/jobs/'+self.id).json;self.assertTrue(any(REJECTION in warning for warning in api['warnings']))
        with db.connect(self.path) as c:self.assertEqual(c.execute('SELECT count(*) FROM generator_calls WHERE job_id=?',(self.id,)).fetchone()[0],1)
        Engine(self.path,self.id,NoPaidCalls).run();self.assertEqual(json.loads(self.row()['state'])['publication_correction']['attempts'],1)
    def test_unchanged_integrity_rejection_remains_blocked_without_retry_billing(self):
        self.state['publication_review']['checks'][-1].update(passed=False,reason='The document contains an unusable editorial section.',issue_type='integrity')
        self.save();Engine(self.path,self.id,NoPaidCalls).run();row=self.row();self.assertEqual(row['status'],'failed')
        self.assertEqual(json.loads(row['state'])['publication_quality']['outcome'],'BLOCKED')
        response=self.owner.post(BASE+'/jobs/'+self.id+'/resume',json={},headers=self.headers);self.assertEqual(response.status_code,409);self.assertIn('unchanged',response.json['error'])
        Engine(self.path,self.id,NoPaidCalls).run()
        with db.connect(self.path) as c:self.assertEqual(c.execute('SELECT count(*) FROM generator_calls WHERE job_id=?',(self.id,)).fetchone()[0],1)
        self.assertEqual(self.owner.get(BASE+'/jobs/'+self.id+'/download/html').status_code,409)
    def test_fabrications_and_broken_formulas_are_not_verification_warnings(self):
        for content in ('The regulator permits this [R404].','ROI = revenue / initial_investment','TODO: insert chart here'):
            with self.subTest(content=content):
                self.state=saved_state(self.config);self.state['document']['chapters'][0]['paragraphs'].append(content);self.save()
                Engine(self.path,self.id,NoPaidCalls).run();state=json.loads(self.row()['state'])
                self.assertEqual(state['publication_quality']['outcome'],'BLOCKED')
        state=saved_state(self.config);state['publication_review']['checks'][-3].update(criterion='accuracy',passed=False,reason='A fabricated citation was found.',issue_type='unverified_claim')
        # Even a reviewer mislabel cannot downgrade explicit fabrication.
        review=deepcopy(state['publication_review']);review['checks']=[c for c in review['checks'] if c['criterion']!='accuracy']+[{'criterion':'accuracy','passed':False,'evidence_blocks':['P0.0'],'reason':'A fabricated citation was found.','issue_type':'unverified_claim'}]
        self.assertEqual(decide(state,review,review_blocks(state))[0],'BLOCKED')
    def test_explicit_missing_evidence_on_intent_or_publication_checks_is_advisory_only_for_research(self):
        state=deepcopy(self.state);state['research_policy']=2
        review=deepcopy(state['publication_review'])
        for check in review['checks']:
            check.update(passed=False,issue_type='unverified_claim',reason='The argument and structure are complete, but regulatory assertions remain uncorroborated.',evidence_blocks=['P0.0'])
        self.assertEqual(decide(state,review,review_blocks(state))[0],'WARNING')
        review['checks'][0]['reason']='An unverified assertion includes a fabricated citation.'
        self.assertEqual(decide(state,review,review_blocks(state))[0],'BLOCKED')
    def test_conflicting_external_evidence_is_advisory_but_internal_formula_contradictions_block(self):
        state=deepcopy(self.state);state['research_policy']=2;review=deepcopy(state['publication_review'])
        accuracy=next(c for c in review['checks'] if c['criterion']=='accuracy')
        accuracy.update(passed=False,issue_type='unverified_claim',evidence_blocks=['P1.0'],reason='Primary evidence contradicts the author-provided regulatory date; it remains unverified and qualified in this draft.')
        self.assertEqual(decide(state,review,review_blocks(state))[0],'WARNING')
        accuracy['reason']='The manuscript contains internally contradictory ROI formulas.'
        self.assertEqual(decide(state,review,review_blocks(state))[0],'BLOCKED')
    def test_fingerprint_invalidates_manuscript_evidence_and_criteria_changes(self):
        state=saved_state(self.config);original=publication_fingerprint(state)
        for change in ('document','source','criteria','chart'):
            other=deepcopy(state)
            if change=='document':other['document']['chapters'][0]['paragraphs'].append('Different manuscript.')
            elif change=='source':other['sources'].append({'id':'R1','role':'external','text':'New government evidence.'})
            elif change=='criteria':other['author_contract']['required_sections'].append('new-criterion')
            else:other['charts'].append({'chapter':0,'caption':'Changed figure','svg':'changed'})
            self.assertNotEqual(original,publication_fingerprint(other))
        other=deepcopy(state);other['publication_quality']={'outcome':'WARNING','passed':False,'fingerprint':original,'html_hash':'old'}
        other['sources'][0]['text']+='changed'
        with self.assertRaises(GenerationError):assert_publication(other)

    def test_changed_evidence_invalidates_review_once_and_unchanged_recovery_reuses_it(self):
        self.state['publication_review_fingerprint']=publication_fingerprint(self.state)
        self.state['sources'].append({'id':'R1','role':'external','label':'New reference','text':'New evidence packet, not proof of these claims.','url':'https://example.gov/rules'})
        self.save();calls=[];expected=deepcopy(self.state['publication_review'])
        class ReReview(Models):
            def request(models,method,path,body=None):
                self.assertEqual(method,'POST');calls.append(body)
                return {'choices':[{'message':{'content':json.dumps(expected)},'finish_reason':'stop'}],'usage':{'cost':0.01,'is_byok':False}}
        Engine(self.path,self.id,ReReview).run();self.assertEqual(self.row()['status'],'needs_review',self.row()['error']);self.assertEqual(len(calls),1)
        state=json.loads(self.row()['state']);state['next_step']='assemble'
        with db.connect(self.path) as c:c.execute("UPDATE generator_jobs SET status='queued',state=? WHERE id=?",(json.dumps(state),self.id))
        Engine(self.path,self.id,NoPaidCalls).run();self.assertEqual(self.row()['status'],'needs_review');self.assertEqual(len(calls),1)

    def test_author_claim_without_external_evidence_is_not_certified_by_reviewer_approval(self):
        state=deepcopy(self.state)
        for check in state['publication_review']['checks']:check['passed']=True
        outcome,findings,_=decide(state,state['publication_review'],review_blocks(state))
        self.assertEqual(outcome,'WARNING');self.assertTrue(any(f.get('claim')==state['document']['chapters'][3]['paragraphs'][0] for f in findings))
        self.assertFalse(any(f.get('claim')==state['document']['chapters'][4]['paragraphs'][0] for f in findings),'An authorial proposal is not an empirical regulatory assertion')

    def test_authoritative_research_is_optional_bounded_and_saved(self):
        from types import SimpleNamespace
        state=deepcopy(self.state);checkpoints=[];requests=[]
        class ResearchModels:
            def check(self):pass
            def many(self,*args,**kwargs):
                requests.append((args,kwargs))
                return [{'content':'Search notes are not verification.','annotations':[{'type':'url_citation','url_citation':{'url':url}} for url in ('https://vancouver.ca/rules','https://untrusted.example/rules','https://www.bclaws.gov.bc.ca/food')]}]
        pipeline=SimpleNamespace(config={**self.config,'web_search':True,'web_budget_usd':0.30},models=ResearchModels(),e=SimpleNamespace(db=None,id='fixture',checkpoint=checkpoints.append,message=lambda text:None))
        with patch('portal_api.generation_tasks.monitored_call',side_effect=lambda *args,**kwargs:('Official rule text.',args[5][0])) as fetch:
            result=research(pipeline,state)
        self.assertEqual(len(requests),1);self.assertEqual(fetch.call_count,2);self.assertEqual(len(result['sources']),3)
        self.assertEqual(research(pipeline,result),result);self.assertEqual(len(requests),1)
        pipeline.config['web_budget_usd']=0
        research(pipeline,state);self.assertEqual(len(requests),1)
        self.assertFalse(any(s.get('text')=='Search notes are not verification.' for s in result['sources']))

    def test_legacy_approved_html_remains_bound_and_exportable(self):
        from portal_api.generation_intent import digest
        state=deepcopy(self.state)
        legacy={key:state.get(key) for key in ('document','financials')};legacy['contract']=state['author_contract']
        legacy.update(publication_assets=state['publication_assets'],publication_calculations=state['publication_calculations'])
        state['publication_quality']={'passed':True,'fingerprint':digest(legacy),'html_hash':digest('old html')}
        assert_publication(state,'old html')
        with self.assertRaises(GenerationError):assert_publication(state,'altered html')

    def test_missing_empirical_evidence_is_a_warning_but_fabricated_quotations_are_blocked(self):
        claim=self.state['document']['chapters'][1]['claims'][0]
        claim.update(classification='empirical',source_id='',quote='')
        self.save();Engine(self.path,self.id,NoPaidCalls).run();self.assertEqual(self.row()['status'],'needs_review',self.row()['error'])
        self.state=saved_state(self.config);claim=self.state['document']['chapters'][1]['claims'][0]
        claim.update(classification='empirical',source_id='B1',quote='A made-up regulatory quote.')
        self.save();Engine(self.path,self.id,NoPaidCalls).run()
        self.assertEqual(json.loads(self.row()['state'])['publication_quality']['outcome'],'BLOCKED')

    def test_tampered_saved_calculations_remain_blocked_before_semantic_review(self):
        from intent_fixtures import financial_plan
        from portal_api.generation_finance import build_financials
        self.state['financials']=build_financials(financial_plan())
        self.state['financials']['groups'][0]['results'][0]['net_gain']+=1
        self.save();Engine(self.path,self.id,NoPaidCalls).run()
        self.assertEqual(json.loads(self.row()['state'])['publication_quality']['outcome'],'BLOCKED')
        self.assertIn('contradict',self.row()['error'])

if __name__=='__main__':unittest.main()
