"""Real draft-boundary repair and durable request reuse; no provider spending."""
import json
import unittest
from unittest.mock import patch
import test_generation_intent as intent_tests
from intent_fixtures import FixtureModels
from portal_api.generator_worker import Engine
from portal_api.generation_v2 import IntentPipeline
from portal_api.generation_errors import GenerationError
from portal_api.generation_chapter_validation import normalize_chapter


class ChapterRepairTests(unittest.TestCase):
    def setUp(self):self.fixture=intent_tests.IntentPipelineTests();self.fixture.setUp()
    def tearDown(self):self.fixture.tearDown()
    def models(self,kind,failed_repair=False):
        class RepairModels(FixtureModels):
            requests=[]
            def request(models,method,path,body=None):
                row=models.db.execute("SELECT stage FROM generator_calls WHERE job_id=? AND status='submitting' ORDER BY rowid DESC LIMIT 1",(models.job_id,)).fetchone()
                stage=row['stage'];response=super().request(method,path,body)
                if stage=='draft:1' or (failed_repair and stage=='intent-repair-draft:1'):
                    value=json.loads(response['choices'][0]['message']['content'])
                    if kind=='alias':value['formula_refs']=['net_cash_flow']
                    elif kind=='unknown':value['formula_refs']=['invented_return_formula']
                    elif kind=='malformed':value['tables']=None
                    elif kind=='chart':value['charts']=[{'kind':'bar','title':'Cash expenditure and labor','labels':['Cash','Labor','Combined'],'values':[1064,6000,7064],'unit':'USD','source_id':'youtube','evidence':[]}]
                    elif kind=='coverage':
                        value['paragraphs']=['An unrelated account of an academic report.'];value['claims']=[]
                        value['coverage'][0]['text_excerpt']='A paraphrase ... absent from the actual prose.'
                    response['choices'][0]['message']['content']=json.dumps(value)
                return response
        return RepairModels
    def run_model(self,models):Engine(self.fixture.path,self.fixture.id,models).run();return self.fixture.row()
    def test_exact_formula_symbol_alias_does_not_require_a_paid_rewrite(self):
        models=self.models('alias');row=self.run_model(models)
        self.assertEqual(row['status'],'awaiting_html_review',row['error'])
        self.assertFalse(any(stage.startswith('intent-repair-') for stage in models.requests))
        original={'formula_refs':['net_cash_flow'],'paragraphs':['The actual prose is here.'],'coverage':[{'author_ref':'A1','text_excerpt':'The actual prose is here.'}]}
        fixed=normalize_chapter(original)
        self.assertEqual(fixed['formula_refs'],['cash_flow']);self.assertEqual(original['formula_refs'],['net_cash_flow'])
        self.assertEqual(normalize_chapter({'formula_refs':['made_up']}),{'formula_refs':['made_up']})
    def test_unknown_formula_and_malformed_fields_repair_only_the_affected_chapter(self):
        for kind in ('unknown','malformed','coverage'):
            with self.subTest(kind=kind):
                models=self.models(kind);row=self.run_model(models)
                self.assertEqual(row['status'],'awaiting_html_review',row['error'])
                self.assertEqual([s for s in models.requests if s.startswith('intent-repair-')],['intent-repair-draft:1'])
                # Recreate an independent job for the next candidate.
                self.fixture.tearDown();self.fixture=intent_tests.IntentPipelineTests();self.fixture.setUp()
    def test_unfixed_unknown_formula_stops_and_resume_reuses_the_repair(self):
        models=self.models('unknown',True)
        for _ in range(2):
            row=self.run_model(models);self.assertEqual(row['status'],'failed')
            self.assertIn('invented_return_formula',row['error'])
        self.assertEqual(models.requests.count('intent-repair-draft:1'),1)
        self.assertEqual(models.requests.count('draft:1'),1)
    def test_crash_after_completed_repair_reuses_it_on_resume(self):
        models=self.models('unknown');original=IntentPipeline.validate_chapters
        def interrupted(pipeline,state,chapters,stage,repair=True):
            if stage=='draft' and not repair:raise GenerationError('Simulated interruption after the repair response was saved.')
            return original(pipeline,state,chapters,stage,repair)
        with patch.object(IntentPipeline,'validate_chapters',interrupted):
            self.assertEqual(self.run_model(models)['status'],'failed')
        row=self.run_model(models);self.assertEqual(row['status'],'awaiting_html_review',row['error'])
        self.assertEqual(models.requests.count('intent-repair-draft:1'),1)
        for i in range(8):self.assertEqual(models.requests.count('draft:'+str(i)),1)
    def test_repair_evidence_is_bound_to_real_paragraphs_with_strict_indices(self):
        value={'paragraphs':['The original investment vision is preserved.','FP&A improves decisions before resources are committed.'],
               'coverage':[{'author_ref':'A1','paragraph_index':1}],
               'claims':[{'paragraph_index':0,'classification':'authorial','source_id':'','quote':''}]}
        fixed=normalize_chapter(value)
        self.assertEqual(fixed['coverage'][0]['text_excerpt'],value['paragraphs'][1])
        self.assertEqual(fixed['claims'][0]['text'],value['paragraphs'][0])
        for index in (-1,2,True):
            value['coverage'][0]['paragraph_index']=index
            self.assertNotIn('text_excerpt',normalize_chapter(value)['coverage'][0])

    def test_source_statements_resolve_mixed_indices_without_guessing_new_prose(self):
        paragraphs=['Other opening context.','The ability to build something is not evidence that building it is a good investment.','Financial Planning & Analysis, or FP&A, can help close the decision gap.']
        contract={'items':[{'id':'A1','role':'thesis','label':'Investment thesis','quote':'> The ability to build something is not evidence that building it is a good investment.'},{'id':'A2','role':'thesis','label':'FP&A','quote':'Financial Planning & Analysis — FP&A — can help close the decision gap.'}]}
        value={'paragraphs':paragraphs,'coverage':[{'author_ref':'A1','paragraph_index':0},{'author_ref':'A2','paragraph_index':3}],'claims':[]}
        fixed=normalize_chapter(value,contract)
        self.assertEqual([p['text_excerpt'] for p in fixed['coverage']],paragraphs[1:])
        self.assertEqual(fixed['paragraphs'],paragraphs)

    def test_only_authored_nonnumeric_closing_statements_can_be_restored(self):
        quotes=["Don't just ask whether you can build it.",'Create a diagram for this chapter.','Revenue increases by 500%.']
        contract={'mode':'content_preserving_rewrite','items':[{'id':'A'+str(i),'role':'message','label':'Closing statement','quote':q} for i,q in enumerate(quotes)],'structure':[{'title':q} for q in quotes]}
        value={'paragraphs':['A supported investment argument.'],'coverage':[],'claims':[]}
        fixed=normalize_chapter(value,contract,restore=True,assigned_refs=['A0','A1','A2'])
        self.assertEqual(fixed['paragraphs'],value['paragraphs']+[quotes[0]])
        self.assertEqual(fixed['coverage'],[{'author_ref':'A0','text_excerpt':quotes[0]}])

    def test_calculator_owned_figures_survive_polishing_without_model_metadata(self):
        models=self.models('chart');row=self.run_model(models)
        self.assertEqual(row['status'],'awaiting_html_review',row['error'])
        state=json.loads(row['state']);refs=state['document']['chapters'][1].get('calculated_chart_refs',[])
        self.assertEqual(len(refs),1);self.assertEqual(refs[0]['recipe'],'labor_value')
        html=(self.fixture.path.parent/'generated'/self.fixture.id/'document.html').read_text()
        self.assertIn('Cash expenditure and contributed labor',html)

    def test_figure_ownership_survives_a_completed_polish_repair_on_resume(self):
        base=self.models('chart')
        class PolishModels(base):
            def request(models,method,path,body=None):
                response=super().request(method,path,body)
                if models.requests[-1]=='polish:1':
                    value=json.loads(response['choices'][0]['message']['content']);value['tables']=None
                    response['choices'][0]['message']['content']=json.dumps(value)
                return response
        original=IntentPipeline.validate_chapters
        def interrupted(pipeline,state,chapters,stage,repair=True):
            if stage=='polish' and not repair:raise GenerationError('Simulated interruption after saved polish repair.')
            return original(pipeline,state,chapters,stage,repair)
        with patch.object(IntentPipeline,'validate_chapters',interrupted):self.assertEqual(self.run_model(PolishModels)['status'],'failed')
        row=self.run_model(PolishModels);self.assertEqual(row['status'],'awaiting_html_review',row['error'])
        self.assertEqual(len(json.loads(row['state'])['document']['chapters'][1]['calculated_chart_refs']),1)
        self.assertEqual(PolishModels.requests.count('intent-repair-polish:1'),1)

    def test_invalid_durable_indices_never_submit_requests(self):
        engine=Engine(self.fixture.path,self.fixture.id,self.models('unknown'))
        try:
            for indices in ([1,1],[True],[-1],[]):
                with self.assertRaisesRegex(GenerationError,'indices'):engine.models.many('draft',['unused'],'intent-repair-test',indices=indices)
            self.assertEqual(engine.db.execute('SELECT count(*) FROM generator_calls WHERE job_id=?',(self.fixture.id,)).fetchone()[0],0)
        finally:engine.db.close()

if __name__=='__main__':unittest.main()
