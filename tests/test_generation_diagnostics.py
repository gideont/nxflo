"""Current validation details remain complete, scoped, and protected by owner auth."""
import json
from unittest import TestCase
from portal_api.generation_diagnostics import failure_details
from portal_api import db
from portal_api.generator import BASE

class GenerationDiagnosticsTests(TestCase):
    def state(self):
        return {'outline':{'chapters':[{'title':'Chapter title '+str(i)} for i in range(1,9)]},
                'chapter_diagnostics':{'8':['The manuscript lost original author anchor A26 (Adapter-based architecture).'],'3':['A prose number is absent from the author material, cited claim register and calculated projections: 0.3.'],'1':['An empirical chart failed source verification.']},
                'quality_errors':['Chapter 1: An empirical chart failed source verification.','An empirical chart failed source verification.','A prose number is absent from the author material, cited claim register and calculated projections: 0.3.','The manuscript lost original author anchor A26 (Adapter-based architecture).']}
    def test_current_failure_keeps_all_chapters_and_important_reasons(self):
        row={'status':'failed','step':'draft','error':'Intent/provenance gate rejected draft: evidence failed','message':''}
        details=failure_details(row,self.state(),[{'stage':'intent-repair-draft:0','status':'complete'}])
        self.assertEqual([chapter['number'] for chapter in details['chapters']],[1,3,8])
        self.assertEqual(details['chapters'][-1]['title'],'Chapter title 8')
        self.assertTrue(details['automatic_correction_completed']);self.assertIn('unchanged results',details['next_action'])
        self.assertTrue(any('0.3' in text for text in details['highlights']));self.assertTrue(any('Adapter' in text for text in details['highlights']))
    def test_stale_validation_is_not_displayed_for_a_new_transport_failure_or_success(self):
        row={'status':'failed','step':'draft','error':'Provider temporarily unavailable','message':''}
        details=failure_details(row,self.state(),[])
        self.assertEqual(details['summary'],row['error']);self.assertEqual(details['chapters'],[]);self.assertEqual(details['issues'],[])
        self.assertIsNone(failure_details({**row,'status':'ready'},self.state(),[]))
    def test_owner_api_exposes_diagnostics_without_mutating_saved_work(self):
        from test_document_library import DocumentLibraryTests
        fixture=DocumentLibraryTests();fixture.setUp()
        try:
            job=fixture.create(status='failed');state=self.state();error='Intent/provenance gate rejected draft: evidence failed'
            with db.connect(fixture.path) as c:c.execute('UPDATE generator_jobs SET state=?,error=?,step=? WHERE id=?',(json.dumps(state),error,'draft',job['id']))
            response=fixture.owner.get(BASE+'/jobs/'+job['id'])
            self.assertEqual(response.status_code,200);self.assertEqual(len(response.json['failure_details']['chapters']),3)
            self.assertEqual(fixture.app.test_client().get(BASE+'/jobs/'+job['id']).status_code,401)
            with db.connect(fixture.path) as c:
                self.assertEqual(c.execute('SELECT state FROM generator_jobs WHERE id=?',(job['id'],)).fetchone()[0],json.dumps(state))
                self.assertEqual(c.execute('SELECT count(*) FROM generator_calls').fetchone()[0],0)
        finally:fixture.tearDown()
