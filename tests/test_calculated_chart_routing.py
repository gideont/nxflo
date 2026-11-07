"""Model financial chart requests must resolve to exact calculator-owned recipes."""
from copy import deepcopy
import unittest
from portal_api.generation_authored_finance import authored_financial_plan
from portal_api.generation_finance import build_financials
from portal_api.generation_calculated_charts import route_calculated_charts,render_reference
from portal_api.generation_errors import GenerationError
from test_authored_finance import brief


class CalculatedChartRoutingTests(unittest.TestCase):
    def setUp(self):
        self.original=brief().replace('| Total monthly operating expense | $150 | Monthly |','| AI tools | $70 | Monthly |\n| Video production | $80 | Monthly |\n| Total monthly operating expense | $150 | Monthly |')
        self.financials=build_financials(authored_financial_plan(self.original));self.group=self.financials['groups'][0]
    def chart(self,values,kind='bar',labels=None):
        return {'kind':kind,'title':'Illustrative financial example','values':values,'labels':labels or [str(i+1) for i in range(len(values))],'unit':'USD','source_id':self.group['id'],'evidence':[]}
    def test_registered_schedules_and_costs_become_real_hypothetical_figures(self):
        base=next(r for r in self.group['results'] if r['case']=='base')
        cases=[(self.chart([r['revenue'] for r in base['rows']]),'monthly_revenue'),
               (self.chart(base['cash_flows'][:1]+[r['cumulative_cash_flow'] for r in base['rows']],'line',[str(i) for i in range(13)]),'cumulative_cash_flow'),
               (self.chart([300,840,960,2100]),'expense_components'),
               (self.chart([2100,7800,9900]),'labor_value')]
        for chart,recipe in cases:
            ch={'charts':[chart]};route_calculated_charts([ch],self.financials,self.original)
            self.assertEqual(ch['charts'],[]);ref=ch['calculated_chart_refs'][0];self.assertEqual(ref['recipe'],recipe)
            fig=render_reference(ref,self.financials,self.original)
            self.assertIn('<svg',fig['svg']);self.assertIn('Hypothetical',fig['caption']);self.assertTrue(fig['in_chapter'])
    def test_wrong_numbers_unknown_sources_and_nonfinite_values_are_not_reclassified(self):
        for chart in (self.chart([300,841,960,2100]),{**self.chart([2100,7800,9900]),'source_id':'R1'},self.chart([float('nan')])):
            ch={'charts':[chart]};route_calculated_charts([ch],self.financials,self.original)
            self.assertEqual(ch['charts'],[chart]);self.assertNotIn('calculated_chart_refs',ch)
    def test_stored_outputs_cannot_override_registered_formulas(self):
        altered=deepcopy(self.financials);altered['groups'][0]['results'][0]['net_gain']=999999
        with self.assertRaises(GenerationError):route_calculated_charts([{'charts':[]}],altered,self.original)
    def test_fabricated_source_spans_do_not_support_a_calculated_chart(self):
        altered=deepcopy(self.financials);altered['groups'][0]['source_spans'][0]['quote']='Fabricated expense evidence'
        with self.assertRaises(GenerationError):route_calculated_charts([{'charts':[]}],altered,self.original)

    def test_unknown_recipe_cannot_render_untrusted_svg(self):
        with self.assertRaises(GenerationError):render_reference({'group_id':self.group['id'],'recipe':'invented','svg':'<script/>'},self.financials,self.original)

if __name__=='__main__':unittest.main()
