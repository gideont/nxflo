"""Real Flask owner session and persisted settings, with browser-only synthetic GIS."""
import json
import io
from PIL import Image
import os
import time
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import threading
from flask import send_from_directory
from werkzeug.serving import make_server,WSGIRequestHandler
from playwright.sync_api import sync_playwright
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_portal_auth import make_test_app
from portal_api import db
from portal_api.generator import DEFAULTS
from check_portal_admin import FAKE_GIS
ROOT=Path(__file__).resolve().parents[1]


def check(widths=(1440,375,320,430)):
    os.environ['OPENROUTER_API_KEY']='synthetic-browser-test-key'
    os.environ.update(DATABRICKS_AI_KEY='synthetic-databricks-key',DATABRICKS_BASE_URL='https://workspace.example/ai-gateway/mlflow/v1',DATABRICKS_MODEL='system.ai.claude-haiku-5-5')
    with TemporaryDirectory() as temp:
        app=make_test_app(Path(temp)/'test.sqlite3')
        @app.before_request
        def fixture_worker_heartbeat():
            with db.connect(Path(temp)/'test.sqlite3') as connection:connection.execute("INSERT OR REPLACE INTO generator_meta VALUES('heartbeat',?)",(str(time.time()),))
        @app.get('/<path:name>')
        def site(name):return send_from_directory(ROOT/'dist',name)
        class Quiet(WSGIRequestHandler):
            def log_request(self,*args):pass
        server=make_server('127.0.0.1',0,app,threaded=True,request_handler=Quiet);origin=f'http://127.0.0.1:{server.server_port}';app.config['PUBLIC_ORIGIN']=origin
        threading.Thread(target=server.serve_forever,daemon=True).start()
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch(headless=True,ignore_default_args=['--hide-scrollbars'])
                for width in widths:
                    context=browser.new_context(viewport={'width':width,'height':1000 if width==1440 else 850})
                    context.add_init_script('window.testIdentity='+json.dumps({'sub':'owner','email':'gideont@gmail.com','email_verified':True,'name':'Owner'}))
                    google_loads=[]
                    def google_script(route):
                        google_loads.append(True);route.fulfill(status=200,content_type='application/javascript',body=FAKE_GIS)
                    context.route('https://accounts.google.com/gsi/client',google_script)
                    page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                    page.goto(origin+'/admin.html');page.get_by_role('button',name='Sign in with Google',exact=True).click()
                    page.locator('#admin-workspace').wait_for(state='visible');page.locator('#analytics-tab').focus();page.keyboard.press('ArrowRight')
                    page.wait_for_function("document.querySelector('#generator-save-state').textContent !== 'Not loaded'")
                    page.wait_for_function("document.querySelector('#generator-cost-total').textContent.includes('$')")
                    if width==1440: assert page.locator('#generator-advanced-models').is_hidden()
                    else: page.locator('[name=advanced_models]').uncheck()
                    assert page.locator('#generator-advanced-models').is_hidden()
                    assert page.locator('[name=web_budget_usd],#generator-documents,[name=youtube]').count()==0
                    assert page.locator('#generator-price-matrix tr').count()>=5
                    assert page.locator('option[value$=":batch"]').count()==0
                    assert page.locator('.generator-step-copy strong').evaluate_all("labels=>labels.every(label=>label.getBoundingClientRect().height < parseFloat(getComputedStyle(label).lineHeight)*1.5 && label.scrollWidth<=label.clientWidth+1 && label.getBoundingClientRect().right<=label.parentElement.getBoundingClientRect().right+1)"),'Workflow step wraps or overflows'
                    rates=page.locator('#generator-price-matrix tr').evaluate_all("rows=>rows.map(row=>[...row.querySelectorAll('td')].map(cell=>Number(cell.textContent.replace('$',''))))")
                    assert rates==sorted(rates),rates
                    page.locator('#generator-common-model').select_option('anthropic/claude-haiku-5.5|default')
                    assert all(page.locator('[name='+role+'_model]').input_value()=='anthropic/claude-haiku-5.5' for role in ('summary','draft','polish'))
                    cheap=page.locator('#generator-cost-total').inner_text()
                    page.locator('#generator-common-model').select_option('anthropic/claude-sonnet-4.5|default')
                    costly=page.locator('#generator-cost-total').inner_text()
                    assert float(cheap.split('$')[1])<float(costly.split('$')[1]),'Estimate did not update immediately'
                    matrix=page.locator('#generator-price-matrix')
                    matrix.get_by_role('button',name='Use GPT-6 Luna Flex · 50% off for all stages',exact=True).click()
                    assert all(page.locator('[name='+role+'_service]').input_value()=='flex' for role in ('summary','draft','polish')), {'common':page.locator('#generator-common-model').input_value(),'values':{role:[page.locator('[name='+role+'_model]').input_value(),page.locator('[name='+role+'_service]').input_value()] for role in ('summary','draft','polish')},'errors':errors}
                    assert matrix.locator('tr.is-selected').count()==1
                    assert page.locator('#generator-common-model').input_value()=='openai/gpt-6-luna|flex'
                    matrix.locator('tr').filter(has=page.get_by_role('button',name='Use Haiku 5.5 Standard for all stages',exact=True)).locator('td').last.click()
                    assert page.locator('#generator-common-model').input_value()=='anthropic/claude-haiku-5.5|default'
                    matrix.get_by_role('button',name='Use GPT-6 Luna Flex · 50% off for all stages',exact=True).click()
                    if width==1440:
                        assert 319<=page.locator('#generator-workflow').bounding_box()['width']<=321
                        assert page.locator('#generator-form').bounding_box()['width']>page.locator('#generator-workflow').bounding_box()['width']*2
                        assert max(matrix.locator('tr').nth(i).bounding_box()['height'] for i in range(matrix.locator('tr').count()))<42
                        assert page.locator('.generator-model-matrix').bounding_box()['x']>page.locator('.generator-model-controls').bounding_box()['x']
                    page.locator('[name=advanced_models]').check()
                    assert page.locator('#generator-advanced-models').is_visible()
                    for name in ('summary_model','draft_model','polish_model'):
                        page.locator('[name='+name+']').select_option('openai/gpt-6-luna')
                    assert page.locator('#generator-model-rates').inner_text().count('GPT-6 Luna')==3
                    page.locator('[name=summary_model]').select_option('anthropic/claude-haiku-5.5')
                    page.locator('[name=draft_model]').select_option('openai/gpt-6-luna')
                    page.locator('[name=polish_service]').select_option('flex')
                    assert '$0.05' in page.locator('#generator-model-rates').inner_text()
                    assert '$0.25' in page.locator('#generator-model-rates').inner_text()
                    page.locator('[name=summary_model]').select_option('openai/gpt-6-luna')
                    page.locator('[name=draft_model]').select_option('openai/gpt-6-luna')
                    assert '$0.10' in page.locator('#generator-model-rates').inner_text()
                    page.locator('[name=review_passes]').select_option('1')
                    one=page.locator('#generator-cost-total').inner_text()
                    page.locator('[name=review_passes]').select_option('3')
                    three=page.locator('#generator-cost-total').inner_text()
                    assert float(one.split('$')[1])<float(three.split('$')[1])
                    assert page.locator('.generator-pass-costs > div').count()==4
                    page.locator('#generator-provider').select_option('databricks')
                    assert page.locator('[name=databricks_model]').input_value()=='system.ai.claude-haiku-5-5'
                    assert page.locator('#generator-common-model').is_hidden()
                    assert page.locator('#generator-advanced-models').is_hidden()
                    assert page.locator('[name=web_search]').count()==0
                    assert page.locator('#generator-cost-total').inner_text()=='Workspace billing'
                    assert page.locator('#generator-price-matrix tr').count()==1
                    assert not page.evaluate('document.documentElement.scrollWidth>innerWidth'),'Databricks provider overflow'
                    if width in (1440,375):page.locator('#generator-form').screenshot(path='/tmp/nxflo-databricks-form-'+str(width)+'.png')
                    page.locator('#generator-save').click()
                    page.wait_for_function("document.querySelector('#generator-save-state').textContent==='Saved'")
                    page.reload();page.wait_for_function("document.querySelector('#generator-save-state').textContent!=='Not loaded'")
                    assert page.locator('#generator-provider').input_value()=='databricks'
                    page.locator('#generator-provider').select_option('openrouter')
                    assert page.locator('[name=web_search]').count()==0
                    assert page.locator('#generator-preview').count()==0
                    page.on('dialog',lambda dialog:dialog.accept())
                    if width==1440:
                        assert page.locator('[name=company]').input_value()=='Nexusflow Inc.'
                        assert page.locator('[name=website]').input_value()=='https://www.nxflo.com'
                    page.locator('[name=company]').fill('Preserved Nexusflow Inc.')
                    assert page.locator('[name=credits]').count()==0
                    assert page.locator('#generator-remove-logo').count()==0
                    assert page.locator('#generator-logo').is_hidden()
                    if width==1440:assert page.locator('#generator-logo-empty').is_visible()
                    else:assert page.locator('#generator-logo-preview').is_visible()
                    logo=io.BytesIO();Image.new('RGBA',(12,12),(30,90,60,0)).save(logo,format='PNG')
                    with page.expect_file_chooser() as chooser:
                        page.locator('#generator-logo-drop').focus();page.keyboard.press('Enter')
                    chooser.value.set_files({'name':'company.png','mimeType':'image/png','buffer':logo.getvalue()})
                    page.locator('#generator-logo-preview').wait_for(state='visible')
                    assert page.locator('#generator-logo-empty').is_hidden()
                    assert page.locator('#generator-logo-help').is_hidden()
                    assert page.locator('#generator-logo-preview img').evaluate("el=>getComputedStyle(el).backgroundColor")=='rgb(255, 255, 255)'
                    page.locator('#generator-logo-drop').dispatch_event('dragover')
                    assert 'is-dragging' in page.locator('#generator-logo-drop').get_attribute('class')
                    page.evaluate("""bytes=>{const dt=new DataTransfer();dt.items.add(new File([new Uint8Array(bytes)],'dropped.png',{type:'image/png'}));document.querySelector('#generator-logo-drop').dispatchEvent(new DragEvent('drop',{bubbles:true,cancelable:true,dataTransfer:dt}));}""",list(logo.getvalue()))
                    assert 'is-dragging' not in page.locator('#generator-logo-drop').get_attribute('class')
                    if width in (1440,375):page.locator('.generator-logo-field').screenshot(path='/tmp/nxflo-logo-drop-'+str(width)+'.png')
                    page.wait_for_function("!document.querySelector('#generator-save').disabled")
                    page.locator('#generator-manage-teams').evaluate('(el)=>el.open=true')
                    assert page.locator('[data-team=research] input[data-team-field=email]').input_value()=='research@nxflo.com'
                    page.locator('#generator-add-team').click()
                    team=page.locator('.generator-team-row').last
                    team.locator('[data-team-field=name]').fill('Client Advisory Team')
                    team.locator('[data-team-field=email]').fill('advisory@nxflo.com')
                    team.locator('[data-team-field=email]').fill('team@nxflo.com')
                    selected_team=page.locator('[name=prepared_team]').input_value()
                    assert 'Client Advisory Team' in page.locator('[name=prepared_team] option:checked').inner_text()
                    assert not page.evaluate('document.documentElement.scrollWidth>innerWidth'),'Team editor overflow'
                    page.locator('#generator-clear-form').click()
                    page.wait_for_function("document.querySelector('#generator-fill-status').textContent.includes('Form cleared')")
                    assert page.locator('[name=topic]').input_value()==''
                    assert page.locator('#generator-start').is_disabled()
                    assert page.locator('[name=topic]').get_attribute('aria-invalid')=='true'
                    assert page.locator('[name=company]').input_value()=='Preserved Nexusflow Inc.'
                    assert page.locator('#generator-logo-preview').is_visible()
                    assert page.locator('[name=prepared_team]').input_value()==selected_team
                    assert page.locator('[data-team-field=email]').last.input_value()=='team@nxflo.com'
                    # Long pasted research remains complete across saves and refresh.
                    research='  Opening evidence\n'+('Research detail '*10000)+'FINAL RESEARCH PARAGRAPH  '
                    topic=page.locator('[name=topic]');topic.fill(research)
                    assert topic.get_attribute('maxlength') is None
                    assert '20,005 words' in page.locator('#generator-topic-count').inner_text()
                    page.locator('#generator-save').click()
                    page.wait_for_function("document.querySelector('#generator-save-state').textContent==='Saved'")
                    page.reload();page.wait_for_function("document.querySelector('[name=topic]').value.includes('FINAL RESEARCH PARAGRAPH')")
                    assert page.locator('[name=topic]').input_value()==research
                    assert page.locator('#generator-panel').is_visible()
                    assert len(google_loads)==1,'Active session requested Google login again'
                    mixed='Research notes. https://youtu.be/abcdefghijk [Paper](https://example.com/research.pdf) DOI: 10.1234/xyz. Smith (2025).'
                    topic.fill(mixed)
                    assert '1 YouTube' in page.locator('#generator-source-summary').inner_text()
                    assert '2 other references' in page.locator('#generator-source-summary').inner_text()
                    assert page.locator('#generator-start').is_enabled()
                    def autofill(route):
                        assert route.request.post_data_json['config']['provider']=='databricks'
                        assert route.request.post_data_json['config']['databricks_model']=='system.ai.claude-haiku-5-5'
                        route.fulfill(status=200,content_type='application/json',body=json.dumps({'updates':{'company':'Test company','title':'Evidence report','credits':'Test author','questions':'What is supported?','release_date':'2026-11-05','version':'1.0'}}))
                    page.route('**/admin/generator/autofill',autofill)
                    page.locator('#generator-provider').select_option('databricks')
                    page.locator('#generator-fill-form').click()
                    page.wait_for_function("document.querySelector('#generator-fill-status').textContent.includes('Blank details filled')")
                    assert page.locator('[name=title]').input_value()=='Evidence report'
                    page.locator('#generator-provider').select_option('openrouter')
                    page.locator('[name=title]').fill('Fine-tuned report')
                    page.locator('#generator-start').click()
                    page.wait_for_function("location.search.includes('job=')")
                    job=page.url.split('job=')[1]
                    page.locator('#generator-cancel').wait_for(state='visible')
                    assert page.locator('#generator-chef').get_attribute('data-phase')=='preparing'
                    page.locator('#generator-timing').wait_for(state='visible')
                    elapsed_before=page.locator('#generator-elapsed').inner_text()
                    page.wait_for_function('before=>document.querySelector("#generator-elapsed").textContent!==before',arg=elapsed_before)
                    assert page.locator('.generator-layout.is-running').count()==1
                    assert not page.locator('#generator-configuration').evaluate('el=>el.open')
                    page.locator('#generator-configuration>summary').click()
                    page.wait_for_timeout(2300)
                    assert page.locator('#generator-configuration').evaluate('el=>el.open'),'Polling collapsed an explicitly reopened configuration'
                    page.locator('#generator-configuration>summary').click()
                    assert page.locator('#generator-start').is_disabled()
                    assert not page.evaluate('document.documentElement.scrollWidth>innerWidth'),'Active job overflow'
                    events=[{'step':'collect','status':'complete'},{'step':'summarize','status':'started','at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime(time.time()-12))}]
                    connection=db.connect(Path(temp)/'test.sqlite3')
                    connection.execute("UPDATE generator_jobs SET status='running',step='summarize',events=?,message='Summarizing real source evidence' WHERE id=?",(json.dumps(events),job))
                    page.wait_for_function("document.querySelectorAll('#generator-steps li[data-state=running]')[0]?.textContent.includes('Summarize')")
                    connection.execute('UPDATE generator_jobs SET work_progress=? WHERE id=?',(json.dumps({'step':'summarize','stage':'summarize','completed':3,'total':12,'unit':'requests'}),job))
                    meter=page.locator('[data-step=summarize] .generator-step-dot')
                    page.wait_for_function("document.querySelector('[data-step=summarize] .generator-step-dot').textContent==='25%'")
                    assert meter.get_attribute('aria-valuenow')=='25'
                    assert '3 / 12 requests' in page.locator('[data-step=summarize]').inner_text()
                    elapsed_before=page.locator('[data-step=summarize] .generator-step-elapsed').inner_text()
                    page.wait_for_function('before=>document.querySelector("[data-step=summarize] .generator-step-elapsed").textContent!==before',arg=elapsed_before)
                    connection.execute("UPDATE generator_jobs SET step='draft' WHERE id=?",(job,))
                    page.wait_for_function("document.querySelector('#generator-chef').dataset.phase==='cooking'")
                    assert page.locator('.capy-stir').evaluate('element=>getComputedStyle(element).animationName')=='capy-stir'
                    if width in (1440,375):page.locator('#generator-workflow').screenshot(path='/tmp/nxflo-capybara-cooking-'+str(width)+'.png')
                    page.emulate_media(reduced_motion='reduce')
                    assert page.locator('.capy-stir').evaluate('element=>getComputedStyle(element).animationName')=='none'
                    page.emulate_media(reduced_motion='no-preference')
                    connection.execute("UPDATE generator_jobs SET step='summarize' WHERE id=?",(job,))
                    waiting={'label':'OpenRouter web research','started_at':time.time()-12,'deadline_at':time.time()+78,'limit_seconds':90}
                    connection.execute('UPDATE generator_jobs SET wait_state=? WHERE id=?',(json.dumps(waiting),job))
                    page.wait_for_function("document.querySelectorAll('#generator-steps li[data-state=waiting]')[0]?.textContent.includes('Summarize')")
                    assert page.locator('#generator-wait-status').is_visible()
                    assert '90s maximum' in page.locator('#generator-wait-status').inner_text()
                    assert not page.evaluate('document.documentElement.scrollWidth>innerWidth'),'Provider waiting status overflow'
                    metadata={'status':'in_progress','request_counts':{'total':47,'completed':12,'failed':0}}
                    connection.execute("INSERT INTO generator_calls(job_id,call_key,status,stage,remote_id,result) VALUES(?,?,?,?,?,?)",(job,'fixture-batch','submitted','summarize','batch-fixture',json.dumps(metadata)))
                    connection.execute("UPDATE generator_jobs SET status='queued',wait_state='{}',next_run_at=? WHERE id=?",(time.time()+60,job))
                    page.wait_for_function("document.querySelector('#generator-wait-status').textContent.includes('12 / 47 requests complete')")
                    assert 'in_progress' in page.locator('#generator-wait-status').inner_text()
                    assert page.locator('#generator-remaining').inner_text()=='Provider queue · unknown'
                    assert page.locator('#generator-finish').inner_text()=='Not available for Batch'
                    assert page.locator('#generator-start').is_disabled()
                    assert not page.evaluate('document.documentElement.scrollWidth>innerWidth'),'Batch status overflow'
                    page.locator('#generator-resume').wait_for(state='visible')
                    assert page.locator('#generator-resume').inner_text()=='Check batch now'
                    page.locator('#generator-resume').click()
                    page.wait_for_function("document.querySelector('#generator-status').textContent.includes('Continuing from saved progress')")
                    assert connection.execute('SELECT count(*) FROM generator_calls WHERE job_id=?',(job,)).fetchone()[0]==1
                    job_count=connection.execute('SELECT count(*) FROM generator_jobs').fetchone()[0]
                    connection.execute("UPDATE generator_jobs SET status='failed',error='Temporary fixture failure',message='Saved progress can resume' WHERE id=?",(job,))
                    page.wait_for_function("document.querySelector('#generator-resume').textContent==='Resume'")
                    assert 'saved progress' in page.locator('#generator-recovery-status').inner_text()
                    assert not page.evaluate('document.documentElement.scrollWidth>innerWidth'),'Resume controls overflow'
                    if width in (1440,375):page.locator('#generator-workflow').screenshot(path='/tmp/nxflo-generator-resume-'+str(width)+'.png')
                    page.reload();pending=page.locator('.generator-library-document').filter(has=page.get_by_role('button',name='Resume',exact=True,include_hidden=True));pending.locator('summary').click();pending.get_by_role('button',name='Resume',exact=True).click()
                    page.locator('#generator-cancel').wait_for(state='visible')
                    assert connection.execute('SELECT remote_id FROM generator_calls WHERE job_id=?',(job,)).fetchone()[0]=='batch-fixture'
                    assert connection.execute('SELECT count(*) FROM generator_jobs').fetchone()[0]==job_count
                    connection.execute("UPDATE generator_jobs SET recovery=?,next_run_at=? WHERE id=?",(json.dumps({'attempts':1,'last_error':'HTTP 429'}),time.time()+120,job))
                    page.wait_for_function("document.querySelector('#generator-recovery-status').textContent.includes('Automatic recovery')")
                    assert page.locator('#generator-resume').is_hidden()
                    assert page.locator('#generator-start').is_disabled()
                    connection.execute("UPDATE generator_jobs SET recovery='{}' WHERE id=?",(job,))
                    connection.execute("DELETE FROM generator_calls WHERE job_id=? AND call_key='fixture-batch'",(job,))
                    connection.execute("UPDATE generator_jobs SET status='running' WHERE id=?",(job,))
                    page.wait_for_function("document.querySelectorAll('#generator-steps li[data-state=running]')[0]?.textContent.includes('Summarize')")
                    assert page.locator('#generator-steps li[data-state=running] .generator-step-dot').evaluate("el=>getComputedStyle(el,'::after').animationName")=='generator-meter-turn'
                    page.reload();page.locator('#generator-cancel').wait_for(state='visible')
                    assert page.locator('#generator-panel').is_visible()
                    # Complete fixture output checks UI and authenticated downloads; the engine suite validates actual PDFs.
                    directory=Path(temp)/'generated'/job;directory.mkdir(parents=True)
                    (directory/'document.html').write_text('<!doctype html><html><head><title>Report</title></head><body>Generated test report</body></html>')
                    review_events=events+[{'step':step,'status':'complete'} for step in ('summarize','outline','draft','review','polish','charts','assemble')]
                    saved_state=json.loads(connection.execute('SELECT state FROM generator_jobs WHERE id=?',(job,)).fetchone()[0]);saved_state['next_step']='html_review'
                    connection.execute("UPDATE generator_jobs SET status='awaiting_html_review',step='html_review',state=?,events=?,message='HTML is ready. Preview the document, then choose Continue to PDF.' WHERE id=?",(json.dumps(saved_state),json.dumps(review_events),job))
                    page.locator('#generator-review-actions').wait_for(state='visible')
                    assert page.locator('[data-step=html_review]').get_attribute('data-state')=='review'
                    assert page.locator('#generator-result').is_hidden()
                    assert page.request.get(origin+'/bms_integration_hub/api/admin/generator/jobs/'+job+'/download/pdf').status==409
                    assert page.locator('[data-step=html_review] #generator-review-jump').is_visible()
                    assert page.locator('#generator-review-jump').count()==1
                    if width in (1440,375):page.locator('[data-step=html_review]').screenshot(path='/tmp/nxflo-step10-'+str(width)+'.png')
                    with page.expect_popup() as opened:page.locator('#generator-review-jump').click()
                    preview=opened.value;preview.wait_for_load_state()
                    assert 'Generated test report' in preview.locator('body').inner_text();preview.close()
                    page.reload();page.locator('#generator-review-actions').wait_for(state='visible')
                    assert page.locator('#generator-approve-html').is_enabled()
                    assert page.locator('#generator-html-frame').count()==0
                    assert not page.evaluate('document.documentElement.scrollWidth>document.documentElement.clientWidth'),'HTML review controls overflow'
                    if width in (1440,375):page.locator('[data-step=html_review]').screenshot(path='/tmp/nxflo-html-review-'+str(width)+'.png')
                    page.locator('#generator-approve-html').click()
                    page.locator('#generator-cancel').wait_for(state='visible')
                    assert json.loads(connection.execute('SELECT state FROM generator_jobs WHERE id=?',(job,)).fetchone()[0])['html_approved'] is True
                    assert page.locator('#generator-review-actions').is_hidden()
                    (directory/'document.pdf').write_bytes(b'%PDF-browser-fixture')
                    events +=[{'step':step,'status':'complete'} for step in ('summarize','outline','draft','review','polish','charts','assemble','html_review','pdf','deliver')]
                    state=json.loads(connection.execute('SELECT state FROM generator_jobs WHERE id=?',(job,)).fetchone()[0]);state.update(document={'chapters':[{'title':'Existing findings','paragraphs':['Existing supported analysis [B1].'],'charts':[]}]},sources=[{'id':'B1','label':'Brief','text':mixed}])
                    connection.execute("UPDATE generator_jobs SET status='ready',step='deliver',state=?,events=?,message='Document ready.' WHERE id=?",(json.dumps(state),json.dumps(events),job));connection.close()
                    page.locator('#generator-result').wait_for(state='visible')
                    assert page.locator('#generator-chef').get_attribute('data-phase')=='done'
                    billing={'generation_id':'gen-test-byok','credit_cost':0,'provider_cost':.701728375,'is_byok':True,'web_search_engine':'native'}
                    connection=db.connect(Path(temp)/'test.sqlite3');connection.execute("INSERT INTO generator_calls(job_id,call_key,status,stage,cost,cost_known,billing) VALUES(?,?,?,?,?,?,?)",(job,'fixture-web','complete','web-research:0',.701728375,1,json.dumps(billing)));connection.close()
                    page.locator('#generator-refresh').click();saved=page.locator('#generator-jobs a[href$="/jobs/'+job+'/download/pdf"]').locator('xpath=ancestor::section[contains(@class,"generator-library-version")]')
                    page.wait_for_timeout(300)
                    history=saved.locator('xpath=ancestor::article').locator('details')
                    if not history.evaluate('el=>el.open'):history.locator('summary').click()
                    saved.get_by_role('button',name='View progress',exact=True).click()
                    page.wait_for_function("document.querySelector('#generator-cost-actual').textContent.includes('0.7017')")
                    assert 'predate this limit' in page.locator('#generator-web-spend').inner_text()
                    page.locator('#generator-billing-details').evaluate('(el)=>el.open=true')
                    assert 'BYOK provider $0.7017' in page.locator('#generator-billing-rows').inner_text()
                    assert not page.evaluate('document.documentElement.scrollWidth>innerWidth'),'Billing details overflow'
                    assert page.locator('#generator-progress').get_attribute('value')=='12'
                    assert page.locator('#generator-cancel').is_hidden()
                    with page.expect_download() as downloaded:page.locator('#generator-download-pdf').click()
                    assert downloaded.value.suggested_filename.endswith('.pdf')
                    assert page.locator('#generator-start').is_enabled()
                    assert not page.evaluate('document.documentElement.scrollWidth>innerWidth'),'Completed job overflow'
                    page.locator('#generator-revise-current').click()
                    page.locator('#generator-revision').wait_for(state='visible')
                    assert page.locator('[name=version]').input_value()=='1.1'
                    assert page.locator('[name=version]').get_attribute('readonly') is not None
                    page.locator('[name=feedback]').fill('Expand the recommendations with a clear measurement plan.')
                    page.locator('[name=change_summary]').fill('Expanded the measurement recommendations.')
                    page.locator('#generator-save').click();page.wait_for_function("document.querySelector('#generator-save-state').textContent==='Saved'")
                    page.reload();page.wait_for_function("document.querySelector('#generator-save-state').textContent!=='Not loaded'")
                    page.locator('#generator-configuration').evaluate('el=>el.open=true')
                    page.locator('#generator-revision').wait_for(state='visible')
                    assert page.locator('[name=feedback]').input_value()=='Expand the recommendations with a clear measurement plan.'
                    assert page.locator('[name=version]').get_attribute('readonly') is not None
                    page.locator('#generator-start').click()
                    page.wait_for_function("old=>new URLSearchParams(location.search).get('job')!==old",arg=job)
                    revision_job=page.url.split('job=')[1]
                    page.locator('#generator-cancel').wait_for(state='visible')
                    connection=db.connect(Path(temp)/'test.sqlite3')
                    revision_state=json.loads(connection.execute('SELECT state FROM generator_jobs WHERE id=?',(revision_job,)).fetchone()[0])
                    assert [item['version'] for item in revision_state['revision_history']]==['1.0','1.1']
                    revision_state.update(document=state['document'],sources=state['sources'])
                    connection.execute("UPDATE generator_jobs SET status='ready',step='deliver',state=?,events=?,message='Revision ready.' WHERE id=?",(json.dumps(revision_state),json.dumps(events),revision_job));connection.close()
                    page.locator('#generator-result').wait_for(state='visible')
                    assert page.locator('[name=version]').input_value()=='1.1'
                    assert not page.evaluate('document.documentElement.scrollWidth>innerWidth'),'Revision form overflow'
                    original_row=page.locator('#generator-jobs a[href$="/jobs/'+job+'/download/pdf"]').locator('xpath=ancestor::section[contains(@class,"generator-library-version")]')
                    original_history=original_row.locator('xpath=ancestor::article').locator('details')
                    if not original_history.evaluate('el=>el.open'):original_history.locator('summary').click()
                    original_row.get_by_role('button',name='Revise document',exact=True).click()
                    page.wait_for_function("id=>document.querySelector('#generator-download-pdf').getAttribute('href').includes(id)",arg=job)
                    page.locator('#generator-manage-teams').evaluate('(el)=>el.open=true')
                    page.locator('.generator-team-row').last.get_by_role('button',name='Remove team').click()
                    assert page.locator('[name=prepared_team]').input_value()==''
                    page.locator('[name=prepared_team]').select_option('research')
                    page.locator('#generator-clear-form').click()
                    page.wait_for_function("document.querySelector('#generator-fill-status').textContent.includes('Form cleared')")
                    assert page.locator('#generator-revision').is_hidden()
                    assert page.locator('#generator-jobs').inner_text().find('Fine-tuned report')>=0,'Clear erased document history'
                    page.locator('#generator-save').click()
                    page.wait_for_function("document.querySelector('#generator-save-state').textContent==='Saved'")
                    page.reload();page.wait_for_function("document.querySelector('#generator-save-state').textContent!=='Not loaded'")
                    assert page.locator('[name=topic]').input_value()==''
                    assert page.locator('[name=company]').input_value()=='Preserved Nexusflow Inc.'
                    page.locator('#generator-result').wait_for(state='visible')
                    page.locator('#generator-configuration').evaluate('el=>el.open=true')
                    assert page.locator('#generator-logo-preview').is_visible()
                    assert page.locator('[name=website]').input_value()=='https://www.nxflo.com'
                    assert page.locator('[name=prepared_team]').input_value()=='research'
                    if width==1440:
                        page.screenshot(path='/tmp/nxflo-generator-desktop.png',full_page=True)
                    if width==375:
                        page.screenshot(path='/tmp/nxflo-generator-mobile.png',full_page=True)
                    assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
                    for tab in ('account','analytics','generator'):
                        page.locator('#'+tab+'-tab').click();page.reload();page.locator('#'+tab+'-panel').wait_for(state='visible')
                        assert page.locator('#admin-login').is_hidden()
                    assert len(google_loads)==1
                    if width<=430:
                        assert page.locator('nav[aria-label="Primary"] a[data-nav="home"]').is_visible()
                        page.locator('.nav-tools-toggle').click();page.locator('#tools-menu').wait_for(state='visible')
                    assert not errors,errors
                    context.close()
                browser.close()
        finally:server.shutdown()
    print('Generator browser checks passed at',widths,'px; branding preservation, team management, saved feedback revisions, version numbers, workflow, downloads and tabs.')

if __name__=='__main__':check()
