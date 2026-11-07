"""Real-provider heading presentation must not strand safely cached intent results."""
import unittest
from portal_api.generation_intent import locate,build_contract,source_chunks,digest
from portal_api.generator import DEFAULTS


class IntentSourceMatchingTests(unittest.TestCase):
    def test_sentence_case_and_added_period_resolve_to_exact_original_heading(self):
        text='# 10. The Investment Should Begin as an Experiment, Not a Promise\n\nExplain the reversible pilot.'
        start,end=locate('The investment should begin as an experiment, not a promise.',text)
        self.assertEqual(text[start:end],'The Investment Should Begin as an Experiment, Not a Promise')
        text='# 13. The Most Important Return Is Better Decision-Making\n'
        start,end=locate('The most important return is better decision-making',text)
        self.assertEqual(text[start:end],'The Most Important Return Is Better Decision-Making')

    def test_normalization_does_not_accept_paraphrases_changed_numbers_or_prefixes(self):
        source='The projected cash deficit is $1,270.50 in month seven.'
        for quote in ('The projected cash deficit is $1,200.50 in month seven.',
                      'The projected cash deficit is $1,270',
                      'The projected cash deficit is $1,270.5',
                      'The expected cash deficit is $1,270.50 in month seven.'):
            self.assertIsNone(locate(quote,source),quote)
        self.assertIsNone(locate('The revenue is 100','The revenue is 1000'))
        self.assertIsNone(locate('The revenue is 100.','The revenue is 100.05'))

    def test_contract_keeps_original_spans_and_numbered_body_structure(self):
        text='# Essay Title\n\n## Editorial and Visual Direction\n\nWrite a practical essay.\n\n# 01. Model the Investment Decision\n\n## Figure 1 — The Missing Step\n\nExplain the model.\n\n# 02. The Most Important Return Is Better Decision-Making\n'
        parts=source_chunks(text)
        results=[{'items':[{'role':'thesis','label':'Better decision-making','quote':'The most important return is better decision-making.'}]}]
        cfg={**DEFAULTS,'document_intent':'content_preserving_rewrite','topic':text}
        contract=build_contract(cfg,parts,results)
        self.assertEqual(contract['source_hash'],digest(text))
        self.assertEqual([h['title'] for h in contract['narrative_structure']],['01. Model the Investment Decision','02. The Most Important Return Is Better Decision-Making'])
        for item in contract['items']:self.assertEqual(text[item['start']:item['end']],item['quote'])

if __name__=='__main__':unittest.main()
