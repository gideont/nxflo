"""Keep authored schedules rather than fitting a different revenue curve."""
import unittest
from portal_api.generation_authored_finance import authored_financial_plan
from portal_api.generation_finance import build_financials,financial_figures,financial_tables
from portal_api.generation_errors import GenerationError


def brief():
    base=[0,0,0,0,0,0,80,160,260,390,520,700]
    low=[0,0,0,0,0,0,0,0,0,20,50,100]
    high=[0,0,0,0,0,120,300,500,700,900,1200,1500]
    return ('# Original investment example\n\n| Expense | Amount | Frequency |\n|---|---:|---|\n| Initial setup | $300 | One-time |\n| Total monthly operating expense | $150 | Monthly |\n\n'
            '## Illustrative Base-Case Revenue\n\n| Month | Revenue | Operating Expense | Monthly Operating Cash Flow |\n|---|---:|---:|---:|\n'+
            ''.join(f'| {i+1} | ${value} | $150 | {value-150} |\n' for i,value in enumerate(base))+
            '\nAll values below are hypothetical USD revenue per month.\n\n| Month | Conservative | Base | Optimistic |\n|---|---:|---:|---:|\n'+
            ''.join(f'| {i+1} | ${low[i]} | ${base[i]} | ${high[i]} |\n' for i in range(12))+
            '| **Total Revenue** | **$170** | **$2,110** | **$5,220** |\n\n**312 hours × $25 = $7,800 of contributed labor value**\n')


class AuthoredScheduleTests(unittest.TestCase):
    def test_exact_authored_monthly_numbers_produce_original_worked_outcomes(self):
        text=brief();plan=authored_financial_plan(text);result=build_financials(plan);group=result['groups'][0]
        cases={r['case']:r for r in group['results']};base=cases['base']
        self.assertEqual(base['net_gain'],10);self.assertEqual(base['maximum_funding_requirement'],1270)
        self.assertEqual(base['unallocated_funding_gap'],1270);self.assertEqual(base['distributions'],[])
        self.assertEqual(base['cash_flows'][:8],[-300,-150,-150,-150,-150,-150,-150,-70])
        self.assertEqual(sum(row['cash_costs'] for row in base['rows'])+base['initial_investment'],2100)
        self.assertEqual(cases['conservative']['net_gain'],-1930);self.assertEqual(cases['optimistic']['net_gain'],3120)
        self.assertEqual(base['total_opportunity_cost'],7800);self.assertEqual(base['economic_gain'],-7790)
        self.assertEqual(group['participants'],[])
        for span in group['source_spans']:self.assertEqual(text[span['start']:span['end']],span['quote'])
        figures,heat=financial_figures(group);self.assertEqual(len(figures),6)
        self.assertTrue(any('Monthly revenue' in fig['caption'] for fig in figures));self.assertTrue(heat['rows'])
        self.assertTrue(financial_tables(group))
        from portal_api.generation_blocks import worked_examples
        html=worked_examples({'financials':result,'outline':{'chapters':[{'section_keys':['financial_projections']}]},'config':{'charts':True}},0)
        self.assertIn('Financing still required: USD 1,270.00',html)
        self.assertIn('net project gain is USD 10.00',html)
        self.assertEqual(html.count('class="calculated-figure"'),6)
        self.assertNotIn('Hypothetical participant funding',html)

    def test_rewrite_uses_source_schedule_without_paid_financial_planning(self):
        from types import SimpleNamespace
        from portal_api.generation_intent import build_contract,source_chunks,digest
        from portal_api.generation_v2 import IntentPipeline
        from portal_api.generator import DEFAULTS
        text=brief();config={**DEFAULTS,'document_intent':'content_preserving_rewrite','topic':text}
        extraction={'items':[{'role':'thesis','label':'Original investment example','quote':'Original investment example'}]}
        contract=build_contract(config,source_chunks(text),[extraction]);calls=[]
        def many(role,prompts,stage):
            calls.append(stage);self.assertEqual(stage,'outline')
            return [{'title':'Original example','chapters':[{'title':'Original example','brief':'Retain the original scenarios.','section_keys':contract['required_sections'],'author_refs':['A1'],'charts_needed':[]}]}]
        engine=SimpleNamespace(config=config,models=SimpleNamespace(many=many))
        state={'author_original':text,'author_source_hash':digest(text),'author_contract':contract,'sources':[],'notes':[],'intent_audits':[]}
        result=IntentPipeline(engine).outline(state)
        self.assertEqual(calls,['outline'])
        self.assertEqual(result['financials']['groups'][0]['kind'],'schedule')
        self.assertTrue(result['intent_audits'][-1]['passed'])

    def test_contradictory_authored_arithmetic_is_rejected(self):
        for text in (brief().replace('| 7 | $80 | $150 | -70 |','| 7 | $80 | $150 | -60 |'),
                     brief().replace('**$2,110**','**$2,120**'),
                     brief().replace('$7,800 of contributed','$7,900 of contributed')):
            with self.assertRaises(GenerationError):build_financials(authored_financial_plan(text))

    def test_empirical_or_incomplete_tables_do_not_become_hypothetical_projections(self):
        self.assertIsNone(authored_financial_plan('No monthly scenario inputs provided.'))
        self.assertIsNone(authored_financial_plan(brief().replace('hypothetical USD revenue per month','observed USD revenue per month')))

    def test_a_financing_gap_is_reported_without_inventing_contributions(self):
        from types import SimpleNamespace
        from portal_api.generation_v2 import IntentPipeline
        from intent_fixtures import financial_plan,BRIEF
        plan=financial_plan()
        for group in plan['groups']:
            for person in group['participants']:person['cash_contribution']=0
        result=IntentPipeline(SimpleNamespace(config={},models=None)).validate_financial_plan(plan,{'author_original':BRIEF})
        for group in result['groups']:
            base=next(r for r in group['results'] if r['case']=='base')
            self.assertGreater(base['unallocated_funding_gap'],0)
            self.assertEqual(base['distributions'],[])
            self.assertTrue(all(person['cash_contribution']==0 for person in group['participants']))

    def test_registered_schedule_cannot_double_count_costs_or_accept_bad_rows(self):
        plan=authored_financial_plan(brief());plan['groups'][0]['scenarios'][0]['inputs']['fixed_monthly_cost']=150
        with self.assertRaises(GenerationError):build_financials(plan)
        plan=authored_financial_plan(brief());plan['groups'][0]['authored_schedule']['base']['revenue'].pop()
        with self.assertRaises(GenerationError):build_financials(plan)

if __name__=='__main__':unittest.main()
