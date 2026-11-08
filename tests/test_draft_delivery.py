"""Draft delivery keeps private review history and preserves integrity safeguards."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch
from portal_api import db
from portal_api.generator import BASE
from portal_api.generator_worker import Engine
from portal_api.generation_models import Models
from portal_api.generation_intent import build_contract,source_chunks,source_owned_outline
from portal_api.generation_quality import assert_publication
import test_research as research_fixtures
from intent_fixtures import financial_plan
from portal_api.generation_finance import build_financials

class DraftDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.f=research_fixtures.ResearchTests();self.f.setUp();self.f.app.config['GENERATOR_DELIVERY_POLICY']='draft_first'
        self.state=deepcopy(self.f.source_state)
        self.state['blocked_candidate']=self.state.pop('document');self.state['next_step']='draft'
        self.state['quality_errors']=['Chapter 1: An empirical claim contains an unsupported number.','The manuscript lost original author anchor A12 (Ionic versus covalent bonding).']
        self.state['chapter_diagnostics']={'1':['An empirical claim contains an unsupported number.']}
        self.state['sources'][0]['warning']='Private source verification is incomplete.'
        self.state['blocked_candidate']['chapters'][0]['paragraphs'][0]+=' An unsupported statement [R404].'
        self.state['blocked_candidate']['chapters'][0]['claims'][0].update(classification='empirical',source_id='B1',quote='An invented quotation not present in the source.')
        self.save()
    def tearDown(self):self.f.tearDown()
    def save(self):
        with db.connect(self.f.path) as c:c.execute("UPDATE generator_jobs SET status='failed',step='draft',state=?,error='Saved repairs failed validation' WHERE id=?",(json.dumps(self.state),self.f.id))
    def run_saved(self):
        response=self.f.owner.post(BASE+'/jobs/'+self.f.id+'/resume',json={'delivery_policy':'draft_first'},headers=self.f.headers)
        self.assertEqual(response.status_code,202,response.json)
        with patch.object(Models,'request',side_effect=AssertionError('Saved-draft recovery must not repeat paid requests')):
            Engine(self.f.path,self.f.id).run()
        return self.f.row(self.f.id)
    def test_saved_failed_chapters_deliver_clean_html_pdf_and_private_version_history(self):
        row=self.run_saved();self.assertEqual(row['status'],'needs_review',row['error']);state=json.loads(row['state'])
        self.assertEqual(state['publication_quality']['outcome'],'WARNING');self.assertFalse(state['publication_quality']['passed'])
        response=self.f.owner.get(BASE+'/jobs/'+self.f.id+'/download/html');self.assertEqual(response.status_code,200);html=response.data.decode();response.close()
        for text in ('UNVERIFIED DRAFT','verification-label','verification-register','research-evidence','Source and editorial notes','Private review notes','Private source verification is incomplete.','[R404]','An invented quotation'):
            self.assertNotIn(text,html)
        self.assertIn('An unsupported statement',html)
        from pypdf import PdfReader
        pdf=self.f.path.parent/'generated'/self.f.id/'document.pdf';self.assertTrue(pdf.is_file())
        self.assertNotIn('UNVERIFIED DRAFT',' '.join(p.extract_text() or '' for p in PdfReader(pdf).pages))
        assert_publication(state,(pdf.parent/'document.html').read_text())
        notes=self.f.owner.get(BASE+'/jobs/'+self.f.id+'/review-notes');self.assertEqual(notes.status_code,200)
        text=json.dumps(notes.json);self.assertIn('unsupported number',text);self.assertIn('A12',text);self.assertIn('removed unavailable citation',text)
        self.assertIn('Private source verification is incomplete.',text)
        library=self.f.owner.get(BASE).json['documents'];version=next(d['versions'][0] for d in library if d['id']==self.f.doc)
        self.assertGreater(version['review_notes_count'],0);self.assertEqual(version['status_label'],'Ready')
        self.assertEqual(self.f.app.test_client().get(BASE+'/jobs/'+self.f.id+'/review-notes').status_code,401)
        self.assertEqual(state['author_original'],self.state['author_original'])
    def test_broken_calculations_cannot_be_released_by_requesting_draft_delivery(self):
        self.state['financials']=build_financials(financial_plan());self.state['financials']['groups'][0]['results'][0]['net_gain']+=1;self.save()
        response=self.f.owner.post(BASE+'/jobs/'+self.f.id+'/resume',json={'delivery_policy':'draft_first'},headers=self.f.headers)
        self.assertEqual(response.status_code,409);self.assertIn('Critical integrity',response.json['error'])
        self.assertEqual(self.f.row(self.f.id)['status'],'failed')
    def test_repeated_saved_recovery_does_not_create_calls_or_versions(self):
        row=self.run_saved();self.assertEqual(row['status'],'needs_review',row['error'])
        with db.connect(self.f.path) as c:before=(c.execute('SELECT count(*) FROM generator_calls').fetchone()[0],c.execute('SELECT count(*) FROM generator_versions').fetchone()[0])
        with patch.object(Models,'request',side_effect=AssertionError('No repeat calls')):Engine(self.f.path,self.f.id).run()
        with db.connect(self.f.path) as c:self.assertEqual(before,(c.execute('SELECT count(*) FROM generator_calls').fetchone()[0],c.execute('SELECT count(*) FROM generator_versions').fetchone()[0]))
    def test_resume_is_csrf_protected(self):
        response=self.f.owner.post(BASE+'/jobs/'+self.f.id+'/resume',json={'delivery_policy':'draft_first'})
        self.assertEqual(response.status_code,403);self.assertEqual(self.f.row(self.f.id)['status'],'failed')
    def test_new_documents_use_private_review_delivery(self):
        response=self.f.owner.post(BASE+'/jobs',json={'config':self.f.config},headers=self.f.headers)
        self.assertEqual(response.status_code,202,response.json)
        self.assertEqual(json.loads(self.f.row(response.json['id'])['state'])['delivery_policy'],'draft_first')
    def test_unknown_provider_outcome_keeps_its_hold_and_blocks_resubmission(self):
        with db.connect(self.f.path) as c:
            c.execute("INSERT INTO generator_calls(job_id,call_key,status,stage,reserved_cost,budget_scope) VALUES(?,?,'submitting','draft:unknown',0.25,'research')",(self.f.id,'unknown-call'))
        response=self.f.owner.post(BASE+'/jobs/'+self.f.id+'/resume',json={'delivery_policy':'draft_first'},headers=self.f.headers)
        self.assertEqual(response.status_code,409);self.assertIn('unknown provider outcome',response.json['error'])
        with db.connect(self.f.path) as c:
            row=c.execute('SELECT status,reserved_cost FROM generator_calls WHERE call_key=?',('unknown-call',)).fetchone()
            self.assertEqual(row['status'],'submitting');self.assertEqual(row['reserved_cost'],.25)
    def test_known_fabricated_verbatim_attribution_is_removed_from_prose_before_export(self):
        self.state['blocked_candidate']['chapters'][0]['paragraphs'].append('The regulator said, "An invented quotation not present in the source."')
        self.save();row=self.run_saved();self.assertEqual(row['status'],'needs_review',row['error'])
        html=(self.f.path.parent/'generated'/self.f.id/'document.html').read_text()
        self.assertNotIn('The regulator said',html)
        notes=self.f.owner.get(BASE+'/jobs/'+self.f.id+'/review-notes').json
        self.assertTrue(any('untraceable verbatim quotation' in issue['reason'] for issue in notes['issues']))

class ProductionBriefTests(unittest.TestCase):
    def test_page_plan_becomes_reader_structure_and_editorial_rules_remain_constraints(self):
        text=('# DOCUMENT GENERATION BRIEF\n# EDITORIAL MISSION\nThe periodic table is a map of matter and chemical behaviour.\n'
            '# SOURCE RULES\nNever invent quotations, statistics or source URLs.\n# CONTENT PLAN\n'
            '## PAGE 1 — COVER\nShow the document title.\n## PAGE 2 — ATOMS\nAtoms contain protons, neutrons and electrons.\n'
            '## PAGE 3 — REACTIONS\nChemical reactions rearrange atoms in a closed system.\n# FINAL QUALITY GATE\nCheck all pages before export.\n')
        excerpts=[('thesis','The periodic table is a map of matter and chemical behaviour.'),('message','Never invent quotations, statistics or source URLs.'),('argument','Atoms contain protons, neutrons and electrons.'),('argument','Chemical reactions rearrange atoms in a closed system.')]
        contract=build_contract({'topic':text,'document_intent':'content_preserving_rewrite'},source_chunks(text),[{'items':[{'role':role,'label':quote,'quote':quote} for role,quote in excerpts]}])
        self.assertEqual(contract['input_kind'],'production_brief')
        self.assertEqual([h['title'] for h in contract['narrative_structure']],['PAGE 2 — ATOMS','PAGE 3 — REACTIONS'])
        plan=source_owned_outline({'chapters':[{'title':'Editorial mission','brief':'Execute the brief','author_refs':[i['id'] for i in contract['items']],'section_keys':[],'charts_needed':[]}]},contract)
        self.assertEqual(len(plan['chapters']),2);self.assertNotIn('A2',{ref for ch in plan['chapters'] for ref in ch['author_refs']})
        self.assertEqual(text[contract['items'][1]['start']:contract['items'][1]['end']],contract['items'][1]['quote'])

if __name__=='__main__':unittest.main()
