"""Publication reviews must inspect real figures and explicitly defined calculations."""
from copy import deepcopy
import unittest
from portal_api.generator import DEFAULTS
from portal_api.generation_intent import build_contract,source_chunks,digest
from portal_api.generation_authored_finance import authored_financial_plan
from portal_api.generation_finance import build_financials
from portal_api.generation_publication import publication_assets,review_blocks,validate_bound_review,automation_calculation,render_asset
from portal_api.generation_quality import criteria,publication_fingerprint
from portal_api.generation_errors import GenerationError
from test_authored_finance import brief


class PublicationAssetsTests(unittest.TestCase):
    def state(self):
        source=brief().replace('| Total monthly operating expense | $150 | Monthly |','| AI tools | $70 | Monthly |\n| Production | $80 | Monthly |\n| Total monthly operating expense | $150 | Monthly |')
        source+='''
## Figure 1 — The Missing Step
IDEA → FINANCIAL MODEL → INVESTMENT DECISION → EXECUTION
## Figure 2 — What a Small Investment Really Costs
Use the stated cost assumptions.
## Figure 3 — Revenue Is Growing
Use the monthly revenue and expenses.
## Figure 4 — The Cash Flow Valley
Use cumulative cash flow.
## Figure 5 — Three Possible Futures
Compare the three scenarios.
## Figure 6 — The Hidden Cost of Free Labor
Compare cash and non-cash opportunity value.
## Figure 7 — How Easily a Forecast Can Change
Compare revenue 20% lower, a one-month delay, and monthly costs $20 higher.
## Figure 8 — Investment as a Series of Decisions
**Day 0 — Define**

Define the investment limit.

**Day 30 — Measure**

Measure actual performance.

**Day 60 — Reforecast**

Reforecast from actual results.

**Day 90 — Decide**

Decide the next commitment.

CONTINUE / ADAPT / SCALE / STOP
### Proposed Product Experience
**1. Investment Setup**

Define the project.

**2. Business Drivers**

Connect activities to financial assumptions.

**3. Scenario Simulator**

Compare different outcomes.

**4. Financial Dashboard**

Show cash flows and returns.

**5. Performance Tracking**

Compare actual performance with the forecast.
## Final Full-Page Visual
On the left: ideas, people and resources.
In the center: a financial model connecting assumptions and outcomes.
On the right: an informed investment decision.
'''
        config={**DEFAULTS,'topic':source,'document_intent':'content_preserving_rewrite'}
        contract=build_contract(config,source_chunks(source),[{'items':[{'role':'thesis','label':'Investment example','quote':'Original investment example'}]}])
        return {'author_original':source,'author_contract':contract,'document':{'chapters':[{'title':'Original investment example','paragraphs':['A financial model supports an informed investment decision.'],'tables':[]}]},'outline':{'chapters':[{'section_keys':[h['id'] for h in contract['structure']],'author_refs':['A1']}]},'financials':build_financials(authored_financial_plan(source)),'charts':[]}
    def test_all_requested_visuals_are_real_source_owned_assets(self):
        state=self.state();assets,calcs=publication_assets(state)
        self.assertEqual({a['id'] for a in assets},{'F'+str(i) for i in range(1,9)}|{'PRODUCT-EXPERIENCE','CLOSING-VISUAL'})
        self.assertEqual([n['label'] for n in next(a for a in assets if a['id']=='F8')['nodes']],['Day 0','Day 30','Day 60','Day 90'])
        self.assertEqual(len(next(a for a in assets if a['id']=='PRODUCT-EXPERIENCE')['nodes']),5)
        self.assertEqual(next(a for a in assets if a['id']=='F7')['series'][0][1],[10,-412,-690,-230])
        self.assertTrue(all('<figure' in render_asset(a) for a in assets))
        returns=next(c for c in calcs if c['id']=='return-definitions')['table']['rows'][1]
        self.assertEqual(returns[1:3],['3.33','0.48'])
    def test_funding_ratio_and_recovery_are_explicit_calculations(self):
        _,calcs=publication_assets(self.state())
        funding=next(c for c in calcs if c['id']=='funding-definitions')
        self.assertEqual(funding['table']['rows'][1],['base','300.00','1,270.00','4.23','12'])
        self.assertIn('first month',funding['formulas']['cash_recovery_month'])
    def test_response_syntax_recovery_never_changes_values_or_infers_missing_work(self):
        import json
        from portal_api.generation_response import decode_object
        raw='{"checks":[{"passed":false,"reason":"Keep this rejection.","}]}'
        self.assertEqual(decode_object(raw,True),{'checks':[{'passed':False,'reason':'Keep this rejection.'}]})
        quoted={'reason':'Literal ,"} and escaped \\" quote must stay intact.'}
        self.assertEqual(decode_object(json.dumps(quoted),True),quoted)
        for raw in ('{"checks":[{"passed":true', '{"checks":[{"passed":true,"unknown"}]}', '[{"passed":true}]'):
            with self.assertRaises(ValueError):decode_object(raw,True)
        with self.assertRaises(ValueError):decode_object('{"passed":true,"}',False)
    def test_automation_uses_economic_benefit_and_total_cash_expenditure(self):
        source='10 hours × $40 × 48 weeks = $19,200\nImplementation cost: $4,000\nMonthly operating cost: $200\nFirst-year cash expenditure: $6,400\nNet modeled economic benefit: $12,800'
        calc=automation_calculation(source)
        self.assertEqual(calc['outputs']['economic_return_on_cash_expenditure_pct'],200)
        self.assertEqual(calc['outputs']['first_year_cash_expenditure'],6400)
        self.assertIn('not automatically realized cash',calc['note'])
        with self.assertRaises(GenerationError):automation_calculation(source.replace('$12,800','$12,900'))
    def test_unknown_evidence_and_actual_editorial_rejection_cannot_pass(self):
        state=self.state();state['publication_assets'],state['publication_calculations']=publication_assets(state);blocks=review_blocks(state)
        checks=[{'criterion':key,'passed':True,'evidence_blocks':[next(iter(blocks))],'reason':'Supported by actual publication content.'} for key in criteria(state['author_contract'])]
        failures,bound=validate_bound_review({'checks':checks},state,blocks);self.assertEqual(failures,[]);self.assertTrue(bound[0]['evidence'])
        checks[0]['evidence_blocks']=['invented block'];self.assertTrue(validate_bound_review({'checks':checks},state,blocks)[0])
        checks[0].update(passed=False,reason='The author’s purpose was changed.');self.assertTrue(validate_bound_review({'checks':checks},state,blocks)[0])
    def test_artifact_changes_are_bound_to_the_publication_fingerprint(self):
        state=self.state();legacy=publication_fingerprint(state)
        self.assertNotEqual(legacy,digest({'document':state['document'],'contract':state['author_contract'],'financials':state['financials']}),'New approvals must also bind evidence and validation criteria')
        state['publication_assets'],state['publication_calculations']=publication_assets(state);fingerprint=publication_fingerprint(state)
        state['publication_assets'][0]['nodes'][0]['title']='Changed asset';self.assertNotEqual(fingerprint,publication_fingerprint(state))

if __name__=='__main__':unittest.main()
