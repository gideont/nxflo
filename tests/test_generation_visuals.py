"""Source-backed chart guidance and report attribution behavior."""
import json
import unittest
from unittest.mock import Mock
from portal_api.generator import DEFAULTS
from portal_api.generator_worker import Engine,chart_evidence,chart_guidance
from portal_api.generation_document import assemble


class DocumentVisualTests(unittest.TestCase):
    def test_exact_chart_excerpts_keep_decimals_and_remain_bounded(self):
        text='The rate changed from 42.5% to 27.25%. '+('More context. '*2000)+'The second pilot had 9 units.'
        sources=[{'id':'B1','text':text}]
        excerpts=json.loads(chart_evidence(DEFAULTS,sources).split(': ',1)[1])
        self.assertTrue(excerpts)
        self.assertIn('42.5%',excerpts[0]['exact_excerpts'][0])
        self.assertIn('27.25%',excerpts[0]['exact_excerpts'][0])
        self.assertTrue(all(quote in text for item in excerpts for quote in item['exact_excerpts']))
        self.assertLessEqual(sum(len(quote) for item in excerpts for quote in item['exact_excerpts']),8000)
        self.assertEqual(chart_evidence({**DEFAULTS,'charts':False},sources),'')

    def test_draft_receives_chart_density_and_original_evidence(self):
        worker=object.__new__(Engine);worker.config=DEFAULTS.copy();worker.models=Mock()
        worker.models.many.return_value=[{'title':'Findings','paragraphs':['See [B1].'],'charts':[]}]
        state={'outline':{'chapters':[{'title':'Findings'}]},'notes':[{'notes':'Summarized evidence'}],'sources':[{'id':'B1','text':'Baseline 42.5 units; after 27.25 units.'}]}
        worker.draft(state)
        prompt=worker.models.many.call_args.args[1][0]
        self.assertIn('1–2 useful charts or graphs per 1–2 pages',prompt)
        self.assertIn('Baseline 42.5 units; after 27.25 units.',prompt)
        self.assertIn('Never invent values',prompt)
        worker.config={**DEFAULTS,'charts':False};worker.draft(state)
        prompt=worker.models.many.call_args.args[1][0]
        self.assertIn('Charts are disabled',prompt)
        self.assertNotIn('Original numerical source excerpts',prompt)

    def test_coverage_reports_evidence_gap_without_fabricating_a_chart(self):
        worker=object.__new__(Engine);worker.config=DEFAULTS.copy()
        state={'document':{'chapters':[{'paragraphs':['word '*1800],'charts':[]}]},'sources':[]}
        output=worker.charts(state)
        self.assertEqual(output['charts'],[])
        self.assertIn('Chart coverage: 0 verified charts',output['warnings'][0])
        worker.config={**DEFAULTS,'charts':False}
        self.assertEqual(worker.charts(state),{'charts':[],'warnings':[]})

    def test_prepared_by_replaces_redundant_credits(self):
        html=assemble({**DEFAULTS,'credits':'Independent research; AI-assisted draft'},{'sources':[],'document':{'chapters':[{'title':'Review','paragraphs':['Findings.']}]}})
        self.assertIn('Prepared by',html)
        self.assertNotIn('Created by',html)
        self.assertNotIn('AI-assisted draft',html)
        from portal_api.generator_revisions import history_entry
        entry=history_entry({**DEFAULTS,'prepared_team':'','credits':'AI-assisted draft'},'2026-11-07T00:00:00Z')
        self.assertEqual(entry['prepared_by'],'Not specified')


if __name__=='__main__':unittest.main()
