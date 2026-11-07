"""Generator persistence, owner isolation, validation, and explicit publication gate."""
import base64
import io
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_portal_auth import make_test_app,sign_in,ORIGIN
from portal_api import db
from portal_api.generator import BASE,DEFAULTS

class GeneratorTests(unittest.TestCase):
    def setUp(self):
        self.key=patch.dict(os.environ,{'OPENROUTER_API_KEY':'synthetic-test-key'});self.key.start()
        self.temp=TemporaryDirectory();self.path=Path(self.temp.name)/'test.sqlite3';self.app=make_test_app(self.path)
        self.owner=self.app.test_client();sign_in(self.owner);self.csrf=self.owner.get('/bms_integration_hub/api/me').json['csrf_token']
        self.headers={'Origin':ORIGIN,'X-CSRF-Token':self.csrf}
        self.config={**DEFAULTS,'title':'Evidence report','topic':'A useful topic','release_date':'2026-11-05'}
    def tearDown(self): self.temp.cleanup();self.key.stop()
    def put(self,config=None,revision=0): return self.owner.put(BASE,json={'config':config or self.config,'revision':revision},headers=self.headers)
    def test_owner_only_and_csrf(self):
        anon=self.app.test_client();self.assertEqual(anon.get(BASE).status_code,401)
        sign_in(anon,'member','member@example.com');self.assertEqual(anon.get(BASE).status_code,403)
        self.assertEqual(self.owner.put(BASE,json={'config':self.config,'revision':0},headers={'Origin':ORIGIN}).status_code,403)
    def test_persist_settings_restart_and_conflict(self):
        self.assertEqual(self.put().json['revision'],1)
        self.assertEqual(self.put().status_code,409)
        restarted=make_test_app(self.path).test_client();sign_in(restarted)
        self.assertEqual(restarted.get(BASE).json['config'],self.config)
        self.assertEqual(self.put({**self.config,'version':'1.1'},1).status_code,200)
    def test_validation_and_missing_key(self):
        for change in ({'color':'red;body{}'},{'pages':-1},{'toc':'true'},{'youtube':'https://localhost/video'},{'logo':'data:image/svg+xml;base64,PHN2Zz4='},{'review_passes':99},{'documents':[{'name':'x','text':1}]}):
            self.assertEqual(self.put({**self.config,**change}).status_code,400,change)
        with patch.dict(os.environ,{'OPENROUTER_API_KEY':''}):
            response=self.owner.post(BASE+'/jobs',json={'config':self.config},headers=self.headers)
            self.assertEqual(response.status_code,503)
    def test_upload_extract_and_reject_empty(self):
        response=self.owner.post(BASE+'/extract',data={'file':(io.BytesIO(b'Useful evidence'),'source.txt')},headers=self.headers)
        self.assertEqual(response.json,{'name':'source.txt','text':'Useful evidence'})
        empty=self.owner.post(BASE+'/extract',data={'file':(io.BytesIO(b''),'source.txt')},headers=self.headers)
        self.assertEqual(empty.status_code,400)
    def test_pdf_and_word_extraction(self):
        from docx import Document
        document=Document();document.add_paragraph('A locally extracted research source.')
        row=document.add_table(rows=1,cols=2).rows[0];row.cells[0].text='Metric';row.cells[1].text='42'
        output=io.BytesIO();document.save(output)
        word=self.owner.post(BASE+'/extract',data={'file':(io.BytesIO(output.getvalue()),'evidence.docx')},headers=self.headers)
        self.assertEqual(word.status_code,200)
        self.assertIn('Metric | 42',word.json['text'])
        from pypdf import PdfWriter
        from pypdf.generic import NameObject,DictionaryObject,DecodedStreamObject
        writer=PdfWriter();page=writer.add_blank_page(width=300,height=300)
        font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
        page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
        stream=DecodedStreamObject();stream.set_data(b'BT /F1 12 Tf 20 200 Td (Verified source number 42) Tj ET')
        page[NameObject('/Contents')]=writer._add_object(stream)
        output=io.BytesIO();writer.write(output)
        pdf=self.owner.post(BASE+'/extract',data={'file':(io.BytesIO(output.getvalue()),'evidence.pdf')},headers=self.headers)
        self.assertEqual(pdf.status_code,200)
        self.assertIn('Verified source number 42',pdf.json['text'])
    def test_invalid_body_and_preview_required_fields(self):
        self.assertEqual(self.owner.put(BASE,json=['bad'],headers=self.headers).status_code,400)
        self.assertEqual(self.owner.post(BASE+'/jobs',json={'config':{**self.config,'topic':''}},headers=self.headers).status_code,400)
        self.assertEqual(self.owner.post(BASE+'/jobs',json={'config':self.config,'parent_id':{}},headers=self.headers).status_code,400)

    def test_preview_snapshot_is_immutable(self):
        response=self.owner.post(BASE+'/jobs',json={'config':self.config},headers=self.headers)
        self.assertEqual(response.status_code,202)
        self.put({**self.config,'title':'Changed settings'})
        self.assertEqual(self.owner.get(BASE+'/jobs/'+response.json['id']).json['config']['title'],'Evidence report')
    def test_job_cancellation_and_single_active(self):
        job=self.owner.post(BASE+'/jobs',json={'config':self.config},headers=self.headers).json['id']
        self.assertEqual(self.owner.get(BASE+'/jobs/'+job).json['status'],'queued')
        self.assertEqual(self.owner.post(BASE+'/jobs',json={'config':self.config},headers=self.headers).status_code,409)
        self.assertEqual(self.owner.get(BASE+'/jobs/'+job+'/download/pdf').status_code,409)
        self.assertEqual(self.app.test_client().get(BASE+'/jobs/'+job).status_code,401)
        self.assertEqual(self.owner.post(BASE+'/jobs/'+job+'/cancel',json={},headers=self.headers).status_code,200)
        self.assertEqual(self.owner.get(BASE+'/jobs/'+job).json['status'],'cancelled')
        self.assertEqual(self.owner.post(BASE+'/jobs',json={'config':self.config},headers=self.headers).status_code,202)

    def test_download_requires_owner_and_completed_job(self):
        job=self.owner.post(BASE+'/jobs',json={'config':self.config},headers=self.headers).json['id']
        directory=self.path.parent/'generated'/job;directory.mkdir(parents=True)
        (directory/'document.pdf').write_bytes(b'%PDF-synthetic')
        with db.connect(self.path) as connection:connection.execute("UPDATE generator_jobs SET status='ready' WHERE id=?",(job,))
        url=BASE+'/jobs/'+job+'/download/pdf'
        self.assertEqual(self.app.test_client().get(url).status_code,401)
        result=self.owner.get(url)
        self.assertEqual(result.status_code,200)
        self.assertEqual(result.data,b'%PDF-synthetic')
        self.assertIn('attachment',result.headers['Content-Disposition'])
        self.assertIn('no-store',result.headers['Cache-Control']);result.close()
        self.assertEqual(self.owner.post(BASE+'/jobs/'+job+'/publish',json={},headers=self.headers).status_code,409)
        self.assertEqual(self.owner.get(BASE+'/jobs/'+job+'/download/env').status_code,409)

    def test_resume_keeps_checkpoint_version_and_existing_batch(self):
        job=self.owner.post(BASE+'/jobs',json={'config':self.config},headers=self.headers).json['id']
        with db.connect(self.path) as connection:
            original=connection.execute('SELECT config,state FROM generator_jobs WHERE id=?',(job,)).fetchone()
            state={**json.loads(original['state']),'next_step':'summarize','sources':[{'id':'B1','text':'Saved evidence'}]}
            connection.execute("UPDATE generator_jobs SET status='failed',step='summarize',state=?,error='Old parser error' WHERE id=?",(json.dumps(state),job))
            connection.execute("INSERT INTO generator_calls(job_id,call_key,status,stage,remote_id,result) VALUES(?,?,'submitted','summarize',?,?)",(job,'saved-batch','batch-original',json.dumps({'status':'in_progress'})))
        url=BASE+'/jobs/'+job+'/resume'
        self.assertEqual(self.app.test_client().post(url,json={},headers={'Origin':ORIGIN}).status_code,401)
        member=self.app.test_client();sign_in(member,'member','member@example.com')
        token=member.get('/bms_integration_hub/api/me').json['csrf_token']
        self.assertEqual(member.post(url,json={},headers={'Origin':ORIGIN,'X-CSRF-Token':token}).status_code,403)
        self.assertEqual(self.owner.post(url,json={},headers={'Origin':ORIGIN}).status_code,403)
        self.assertEqual(self.owner.post(url,json={},headers=self.headers).status_code,202)
        self.assertEqual(self.owner.post(url,json={},headers=self.headers).status_code,202)
        with db.connect(self.path) as connection:
            row=connection.execute('SELECT * FROM generator_jobs WHERE id=?',(job,)).fetchone()
            self.assertEqual(row['status'],'queued');self.assertEqual(row['config'],original['config']);self.assertEqual(json.loads(row['state']),state)
            self.assertEqual(connection.execute('SELECT remote_id FROM generator_calls WHERE job_id=?',(job,)).fetchone()[0],'batch-original')
            self.assertEqual(connection.execute('SELECT count(*) FROM generator_jobs').fetchone()[0],1)

    def test_resume_blocks_unknown_submission_and_other_active_job(self):
        job=self.owner.post(BASE+'/jobs',json={'config':self.config},headers=self.headers).json['id']
        with db.connect(self.path) as connection:
            connection.execute("UPDATE generator_jobs SET status='failed' WHERE id=?",(job,))
            connection.execute("INSERT INTO generator_calls(job_id,call_key,status,stage) VALUES(?,?,'submitting','summarize')",(job,'unknown'))
        result=self.owner.post(BASE+'/jobs/'+job+'/resume',json={},headers=self.headers)
        self.assertEqual(result.status_code,409);self.assertIn('unknown provider outcome',result.json['error'])
        self.assertFalse(self.owner.get(BASE+'/jobs/'+job).json['recovery']['can_resume'])
        with db.connect(self.path) as connection:connection.execute("UPDATE generator_calls SET status='rejected' WHERE job_id=?",(job,))
        other=self.owner.post(BASE+'/jobs',json={'config':self.config},headers=self.headers).json['id']
        self.assertEqual(self.owner.post(BASE+'/jobs/'+job+'/resume',json={},headers=self.headers).status_code,409)
        self.owner.post(BASE+'/jobs/'+other+'/cancel',json={},headers=self.headers)
        self.assertEqual(self.owner.post(BASE+'/jobs/'+job+'/resume',json={},headers=self.headers).status_code,202)

    def test_check_now_is_idempotent_and_cannot_bypass_automatic_backoff(self):
        job=self.owner.post(BASE+'/jobs',json={'config':self.config},headers=self.headers).json['id'];url=BASE+'/jobs/'+job+'/resume'
        with db.connect(self.path) as connection:
            connection.execute("UPDATE generator_jobs SET next_run_at=9999999999,recovery=? WHERE id=?",(json.dumps({'attempts':1}),job))
        self.assertEqual(self.owner.post(url,json={},headers=self.headers).status_code,202)
        self.assertEqual(self.owner.get(BASE+'/jobs/'+job).json['recovery']['retry_at'],9999999999)
        with db.connect(self.path) as connection:connection.execute("UPDATE generator_jobs SET status='running' WHERE id=?",(job,))
        self.assertEqual(self.owner.post(url,json={},headers=self.headers).json['status'],'running')
        self.assertEqual(self.owner.get(BASE+'/jobs/'+job).json['status'],'running')

    def test_cancelled_job_can_resume_but_ready_job_cannot(self):
        job=self.owner.post(BASE+'/jobs',json={'config':self.config},headers=self.headers).json['id'];url=BASE+'/jobs/'+job+'/resume'
        self.owner.post(BASE+'/jobs/'+job+'/cancel',json={},headers=self.headers)
        self.assertEqual(self.owner.post(url,json={},headers=self.headers).status_code,202)
        with db.connect(self.path) as connection:connection.execute("UPDATE generator_jobs SET status='ready' WHERE id=?",(job,))
        self.assertEqual(self.owner.post(url,json={},headers=self.headers).status_code,409)

    def test_terminal_provider_batch_is_held_for_reconciliation(self):
        job=self.owner.post(BASE+'/jobs',json={'config':self.config},headers=self.headers).json['id']
        with db.connect(self.path) as connection:
            connection.execute("UPDATE generator_jobs SET status='failed' WHERE id=?",(job,))
            connection.execute("INSERT INTO generator_calls(job_id,call_key,status,stage,remote_id,result) VALUES(?,?,'submitted','summarize',?,?)",(job,'terminal','batch-expired',json.dumps({'status':'expired'})))
        result=self.owner.post(BASE+'/jobs/'+job+'/resume',json={},headers=self.headers)
        self.assertEqual(result.status_code,409);self.assertIn('reconciled',result.json['error'])
        self.assertFalse(self.owner.get(BASE).json['jobs'][0]['can_resume'])

    def test_review_options_and_price_catalog(self):
        for passes in (1,2,3,4):
            response=self.put({**self.config,'review_passes':passes},passes-1)
            self.assertEqual(response.status_code,200)
        pricing=self.owner.get(BASE+'/pricing').json
        self.assertAlmostEqual(pricing['models']['openai/gpt-6-luna']['input'],.1)
        self.assertAlmostEqual(pricing['models']['openai/gpt-6-luna']['output'],.5)
        self.assertEqual(self.app.test_client().get(BASE+'/pricing').status_code,401)
        import requests
        with patch('portal_api.generator_pricing.requests.get',side_effect=requests.RequestException):
            fallback=self.owner.get(BASE+'/pricing?refresh=1').json
        self.assertIn('warning',fallback)
        self.assertIn('openai/gpt-6-luna',fallback['models'])

    def test_optional_metadata_and_discounted_models(self):
        config={**self.config,**{key:'' for key in ('company','title','credits','version','release_date','questions')}}
        preview=self.owner.post(BASE+'/jobs',json={'config':config},headers=self.headers)
        self.assertEqual(preview.status_code,202)
        self.assertEqual(self.owner.get(BASE+'/jobs/'+preview.json['id']).json['config']['title'],'')
        pricing=self.owner.get(BASE+'/pricing').json
        self.assertFalse(any(model.endswith(':batch') for model in pricing['models']))
        self.assertAlmostEqual(pricing['models']['openai/gpt-6-luna']['input'],.1)

    def test_autofill_only_blank_fields_and_never_uploads(self):
        cfg={**self.config,'title':'','questions':'','documents':[{'name':'secret.txt','text':'PRIVATE UPLOADED DOCUMENT'}],'youtube':'https://youtu.be/abcdefghijk'}
        response=__import__('unittest').mock.Mock(status_code=200)
        response.json.return_value={'choices':[{'message':{'content':json.dumps({'title':'AI title','questions':'A useful question','company':'Must not overwrite'})},'finish_reason':'stop'}]}
        with patch.dict(os.environ,{'OPENROUTER_API_KEY':'synthetic-test-key'}),patch('portal_api.generator_autofill.requests.post',return_value=response) as call:
            filled=self.owner.post(BASE+'/autofill',json={'config':cfg},headers=self.headers)
        self.assertEqual(filled.status_code,200)
        self.assertEqual(filled.json['updates'],{'title':'AI title','questions':'A useful question'})
        sent=call.call_args.kwargs['json'];self.assertEqual(sent['service_tier'],'flex')
        self.assertFalse(sent['provider']['allow_fallbacks'])
        self.assertNotIn('PRIVATE UPLOADED DOCUMENT',json.dumps(sent))
        self.assertNotIn('abcdefghijk',json.dumps(sent))
        self.assertEqual(self.app.test_client().post(BASE+'/autofill',json={'config':cfg},headers={'Origin':ORIGIN}).status_code,401)
        with patch.dict(os.environ,{'OPENROUTER_API_KEY':''}):
            self.assertEqual(self.owner.post(BASE+'/autofill',json={'config':cfg},headers=self.headers).status_code,503)

    def test_single_model_default_and_advanced_override(self):
        config={**self.config,'summary_model':'anthropic/claude-haiku-5.5','summary_service':'default'}
        self.assertEqual(self.put(config).status_code,200)
        saved=self.owner.get(BASE).json['config']
        self.assertFalse(saved['advanced_models'])
        self.assertEqual({saved[role+'_model'] for role in ('summary','draft','polish')},{'anthropic/claude-haiku-5.5'})
        config={**self.config,'advanced_models':True,'summary_model':'anthropic/claude-haiku-5.5','summary_service':'default'}
        self.assertEqual(self.put(config,1).status_code,200)
        saved=self.owner.get(BASE).json['config']
        self.assertTrue(saved['advanced_models'])
        self.assertNotEqual(saved['summary_model'],saved['polish_model'])

    def test_long_research_brief_round_trip_without_trimming(self):
        # More than the old 12k cap; preserve Unicode, indentation and the final paragraph.
        brief='  Opening research αβ\n'+('Detailed finding and evidence. '*10000)+'\nFINAL RESEARCH PARAGRAPH  '
        self.assertEqual(self.put({**self.config,'topic':brief}).status_code,200)
        self.assertEqual(self.owner.get(BASE).json['config']['topic'],brief)
        preview=self.owner.post(BASE+'/jobs',json={'config':{**self.config,'topic':brief}},headers=self.headers)
        self.assertEqual(preview.status_code,202)
        self.assertEqual(self.owner.get(BASE+'/jobs/'+preview.json['id']).json['config']['topic'],brief)

    def test_research_limit_reports_error_instead_of_truncating(self):
        maximum='α'*2000000
        self.assertEqual(self.put({**self.config,'topic':maximum}).status_code,200)
        self.assertEqual(self.owner.get(BASE).json['config']['topic'],maximum)
        too_long=self.put({**self.config,'topic':maximum+'x'},1)
        self.assertEqual(too_long.status_code,400)
        self.assertIn('2,000,000',too_long.json['error'])
        self.assertEqual(self.owner.get(BASE).json['config']['topic'],maximum)
        self.assertEqual(self.owner.post(BASE+'/jobs',json={'config':{**self.config,'topic':'   '}},headers=self.headers).status_code,400)

    def complete(self,job):
        with db.connect(self.path) as connection:
            row=connection.execute('SELECT state FROM generator_jobs WHERE id=?',(job,)).fetchone();state=json.loads(row['state'])
            state.update(document={'chapters':[{'title':'Existing findings','paragraphs':['Existing supported analysis [B1].'],'charts':[]}]},sources=[{'id':'B1','label':'Brief','text':'A useful topic'}])
            connection.execute("UPDATE generator_jobs SET status='ready',state=? WHERE id=?",(json.dumps(state),job))
    def test_company_website_and_editable_team_contacts(self):
        initial=self.owner.get(BASE).json['config']
        self.assertEqual(initial['company'],'Nexusflow Inc.')
        self.assertEqual(initial['website'],'https://www.nxflo.com')
        self.assertEqual(initial['teams'][0]['email'],'research@nxflo.com')
        teams=[*DEFAULTS['teams'],{'id':'engineering','name':'Engineering Team','email':'engineering@nxflo.com'}]
        cfg={**self.config,'teams':teams,'prepared_team':'engineering'}
        self.assertEqual(self.put(cfg).status_code,200)
        self.assertEqual(self.owner.get(BASE).json['config']['teams'],teams)
        for change in ({'website':'javascript:alert(1)'},{'website':'https://user:password@example.com'},{'prepared_team':'missing'},{'teams':[{'id':'x','name':'X','email':'bad\n@host.com'}]}):
            self.assertEqual(self.put({**cfg,**change},1).status_code,400,change)
        self.assertEqual(self.put({**cfg,'prepared_team':''},1).status_code,200)
    def test_research_team_email_is_restored_if_blank(self):
        cfg={**self.config,'teams':[{'id':'research','name':'Research Team at Nexusflow Inc.','email':''}]}
        self.assertEqual(self.put(cfg).status_code,200)
        self.assertEqual(self.owner.get(BASE).json['config']['teams'][0]['email'],'research@nxflo.com')
    def test_feedback_revisions_assign_versions_and_immutable_history(self):
        parent=self.owner.post(BASE+'/jobs',json={'config':self.config},headers=self.headers).json['id'];self.complete(parent)
        cfg={**self.config,'revision_parent':parent,'version':'99.99','feedback':'Private editorial feedback','change_summary':'Clarified the implementation recommendations.'}
        first=self.owner.post(BASE+'/jobs',json={'config':cfg},headers=self.headers)
        self.assertEqual(first.status_code,202,first.json);self.assertEqual(first.json['version'],'1.1')
        first_id=first.json['id'];self.complete(first_id)
        second=self.owner.post(BASE+'/jobs',json={'config':{**cfg,'revision_parent':first_id}},headers=self.headers)
        self.assertEqual(second.json['version'],'1.2')
        with db.connect(self.path) as connection:
            state=json.loads(connection.execute('SELECT state FROM generator_jobs WHERE id=?',(second.json['id'],)).fetchone()[0]);history=state['revision_history']
            self.assertEqual([entry['version'] for entry in history],['1.0','1.1','1.2'])
            self.assertNotIn('Private editorial feedback',json.dumps(history))
            self.assertEqual(history[-1]['summary'],'Clarified the implementation recommendations.')
            self.assertEqual(history[-1]['prepared_by'],'Research Team at Nexusflow Inc.')
        self.owner.post(BASE+'/jobs/'+second.json['id']+'/cancel',json={},headers=self.headers)
        branch=self.owner.post(BASE+'/jobs',json={'config':cfg},headers=self.headers)
        self.assertEqual(branch.json['version'],'1.3','Revising an older PDF must not duplicate an existing version')
        self.assertEqual(self.owner.get(BASE+'/jobs/'+parent).json['config']['version'],'1.0')
    def test_revision_link_persists_in_saved_configuration(self):
        parent=self.owner.post(BASE+'/jobs',json={'config':self.config},headers=self.headers).json['id'];self.complete(parent)
        cfg={**self.config,'revision_parent':parent,'feedback':'Expand the conclusion.'}
        self.assertEqual(self.put(cfg).status_code,200)
        restarted=make_test_app(self.path).test_client();sign_in(restarted)
        saved=restarted.get(BASE).json['config'];self.assertEqual(saved['revision_parent'],parent);self.assertEqual(saved['feedback'],cfg['feedback'])

    def test_web_budget_is_saved_and_cannot_exceed_thirty_cents(self):
        self.assertEqual(self.owner.get(BASE).json['config']['web_budget_usd'],.30)
        for value in (-.01,.31,True,'0.30',float('nan')):
            self.assertEqual(self.put({**self.config,'web_budget_usd':value}).status_code,400)
        self.assertEqual(self.put({**self.config,'web_budget_usd':0}).status_code,200)
        self.assertEqual(self.owner.get(BASE).json['config']['web_budget_usd'],0)

    def test_inline_references_are_in_saved_job(self):
        brief='Research notes. [Paper](https://example.com/research.pdf) Video https://youtu.be/abcdefghijk. Citation: Smith (2025).'
        job=self.owner.post(BASE+'/jobs',json={'config':{**self.config,'topic':brief}},headers=self.headers).json['id']
        self.assertEqual(self.owner.get(BASE+'/jobs/'+job).json['config']['topic'],brief)

if __name__=='__main__': unittest.main()
