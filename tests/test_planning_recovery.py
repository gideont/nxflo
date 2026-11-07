"""Rewrite routing and bounded, durably cached planning repairs."""
import json
import unittest
from copy import deepcopy
from portal_api.generation_errors import GenerationError
from portal_api.generation_intent import build_contract,source_chunks,source_owned_outline,fidelity_issues
from portal_api.generation_finance import build_financials
from portal_api.generator import DEFAULTS
from portal_api.generator_worker import Engine
from intent_fixtures import FixtureModels,financial_plan
import test_generation_intent as intent_tests


class SourceOwnedOutlineTests(unittest.TestCase):
    def setUp(self):
        self.text='# Essay\n\nOpening thesis is an informed investment decision.\n\n# 01. Model the Decision\n\nBudgeting differs from investment modeling.\n\n## Figure 1\n\nThe pilot tests financial assumptions.\n\n# 02. Better Decisions\n\nTime has an economic opportunity cost.\n\n## Final Call\n\nStart with a decision model before committing resources.\n'
        quotes=['Opening thesis is an informed investment decision.','Budgeting differs from investment modeling.','The pilot tests financial assumptions.','Time has an economic opportunity cost.','Start with a decision model before committing resources.']
        extraction={'items':[{'role':'thesis' if i==0 else 'argument','label':q,'quote':q} for i,q in enumerate(quotes)]}
        self.contract=build_contract({**DEFAULTS,'topic':self.text,'document_intent':'content_preserving_rewrite'},source_chunks(self.text),[extraction])
        self.plan={'title':'Essay','chapters':[{'title':'A replacement introduction','brief':'Preserve the financial decision model.','charts_needed':[],'section_keys':['H2'],'author_refs':['A1']}]}

    def test_missing_metadata_is_routed_from_exact_original_spans(self):
        value=source_owned_outline(self.plan,self.contract);chapters=value['chapters']
        self.assertEqual([ch['title'] for ch in chapters],['Model the Decision','Better Decisions'])
        self.assertEqual(chapters[0]['author_refs'],['A1','A2','A3'])
        self.assertEqual(chapters[1]['author_refs'],['A4','A5'])
        self.assertEqual(set(k for ch in chapters for k in ch['section_keys']),set(h['id'] for h in self.contract['structure']))
        # Assignment metadata never certifies that the generated prose preserves intent.
        self.assertTrue(fidelity_issues({'chapters':[{'title':ch['title'],'paragraphs':['Unrelated writing.'],'coverage':[]} for ch in chapters]},self.contract,chapters))
        self.assertEqual(self.plan['chapters'][0]['author_refs'],['A1'])

    def test_unknown_anchors_are_still_rejected(self):
        self.plan['chapters'][0]['author_refs']=['A999']
        with self.assertRaises(GenerationError):source_owned_outline(self.plan,self.contract)

    def test_monetization_after_the_forecast_has_zero_revenue(self):
        plan=financial_plan();group=plan['groups'][0]
        for case in group['scenarios']:case['inputs']['monetization_month']=24
        calculated=build_financials(plan)['groups'][0]
        for case in calculated['results']:self.assertTrue(all(row['revenue']==0 for row in case['rows']))
        group['scenarios'][0]['inputs']['monetization_month']=2.5
        with self.assertRaises(GenerationError):build_financials(plan)


class PlanningRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.fixture=intent_tests.IntentPipelineTests();self.fixture.setUp()
    def tearDown(self):self.fixture.tearDown()
    def run_candidate(self,repair_good):
        class RecoveryModels(FixtureModels):
            requests=[]
            def request(models,method,path,body=None):
                row=models.db.execute("SELECT stage FROM generator_calls WHERE job_id=? AND status='submitting' ORDER BY rowid DESC LIMIT 1",(models.job_id,)).fetchone()
                stage=row['stage']
                if stage not in ('financial-plan:0','financial-plan-repair:0'):return super().request(method,path,body)
                models.requests.append(stage);plan=financial_plan()
                if stage=='financial-plan:0' or not repair_good:
                    pilot=deepcopy(plan['groups'][0]);pilot['id']='separate-pilot';pilot['months']=3;plan['groups'].append(pilot)
                return {'choices':[{'message':{'content':json.dumps(plan)},'finish_reason':'stop'}],'usage':{'cost':0,'is_byok':False}}
        for attempt in range(2):
            Engine(self.fixture.path,self.fixture.id,RecoveryModels).run()
            row=self.fixture.row()
            if repair_good:self.assertEqual(row['status'],'awaiting_html_review',row['error'])
            else:
                self.assertEqual(row['status'],'failed');self.assertIn('bounded repair',row['error'])
        self.assertEqual(RecoveryModels.requests.count('financial-plan:0'),1)
        self.assertEqual(RecoveryModels.requests.count('financial-plan-repair:0'),1)
        return RecoveryModels.requests
    def test_invalid_pilot_group_is_repaired_once_and_cached_on_resume(self):self.run_candidate(True)
    def test_invalid_repair_stops_and_resume_does_not_rebill(self):self.run_candidate(False)

if __name__=='__main__':unittest.main()
