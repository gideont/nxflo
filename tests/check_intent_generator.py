"""Real v2 report in the authenticated UI; no real provider requests or production data."""
import json
import threading
from pathlib import Path
from flask import Flask,send_from_directory
from werkzeug.serving import make_server,WSGIRequestHandler
from playwright.sync_api import sync_playwright
from test_generation_intent import IntentPipelineTests
from check_portal_admin import FAKE_GIS

ROOT=Path(__file__).resolve().parents[1]


def check():
    fixture=IntentPipelineTests();fixture.setUp()
    try:
        row=fixture.run_to_html();assert row['status']=='awaiting_html_review',row['error']
        app=fixture.app;site_app=Flask('intent-ui')
        @site_app.get('/<path:name>')
        def site(name):return send_from_directory(ROOT/'dist',name)
        class Quiet(WSGIRequestHandler):
            def log_request(self,*args):pass
        def dispatch(environ,start_response):
            return (app if environ.get('PATH_INFO','').startswith('/bms_integration_hub/api') else site_app)(environ,start_response)
        server=make_server('127.0.0.1',0,dispatch,threaded=True,request_handler=Quiet);origin=f'http://127.0.0.1:{server.server_port}';app.config['PUBLIC_ORIGIN']=origin
        threading.Thread(target=server.serve_forever,daemon=True).start()
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch(headless=True,ignore_default_args=['--hide-scrollbars'])
                for width in (1440,375,320,430):
                    ctx=browser.new_context(viewport={'width':width,'height':950})
                    ctx.add_init_script('window.testIdentity='+json.dumps({'sub':'owner','email':'gideont@gmail.com','email_verified':True,'name':'Owner'}))
                    ctx.route('https://accounts.google.com/gsi/client',lambda route:route.fulfill(status=200,content_type='application/javascript',body=FAKE_GIS))
                    page=ctx.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                    page.goto(origin+'/admin.html?job='+fixture.id)
                    page.get_by_role('button',name='Sign in with Google',exact=True).click()
                    page.locator('#admin-workspace').wait_for(state='visible')
                    page.locator('#generator-tab').click()
                    page.wait_for_function("document.querySelector('#generator-save-state').textContent!=='Not loaded'")
                    page.locator('#generator-html-review').wait_for(state='visible')
                    assert not page.locator('#generator-configuration').evaluate('el=>el.open')
                    page.locator('#generator-configuration>summary').click()
                    page.locator('[name=document_intent]').select_option('product_concept')
                    assert page.locator('[name=report_type]').input_value()=='White paper'
                    page.locator('[name=topic]').fill('Preserve this authorial product vision.')
                    page.locator('#generator-save').click()
                    page.wait_for_function("document.querySelector('#generator-save-state').textContent==='Saved'")
                    page.reload();page.wait_for_function("document.querySelector('#generator-save-state').textContent!=='Not loaded'")
                    page.locator('#generator-html-review').wait_for(state='visible')
                    assert page.locator('[name=document_intent]').input_value()=='product_concept'
                    assert page.locator('[name=youtube],#generator-documents,[name=web_search],[name=web_budget_usd]').count()==0
                    page.locator('#generator-configuration>summary').click()
                    page.locator('#generator-version-settings>summary').click()
                    assert page.locator('[name=version]').get_attribute('readonly') is not None
                    assert page.locator('[name=version]').input_value()=='1.0'
                    page.locator('[name=version_override]').check();page.locator('[name=version]').fill('4.2')
                    page.locator('#generator-save').click();page.wait_for_function("document.querySelector('#generator-save-state').textContent==='Saved'")
                    page.locator('[name=version_override]').uncheck();assert page.locator('[name=version]').input_value()=='1.0'
                    page.locator('#generator-configuration>summary').click()
                    page.locator('#generator-html-review').wait_for(state='visible')
                    page.locator('#generator-html-frame').scroll_into_view_if_needed()
                    frame=page.frame_locator('#generator-html-frame')
                    frame.locator('.worked-financials').wait_for(state='visible')
                    assert frame.locator('.calculated-figure').count()==14
                    assert frame.locator('.report-data-table').count()>=12
                    assert frame.locator('body').inner_text().find('FP&A')>=0
                    assert frame.locator('body').inner_text().find('Worked investment scenarios')>=0
                    assert frame.locator('html').evaluate('el=>el.scrollWidth<=el.clientWidth'),width
                    assert page.evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth'),width
                    assert 'Preserve intent' in page.locator('[data-step=summarize] strong').inner_text()
                    assert page.locator('[data-step=html_review] #generator-review-jump').is_visible()
                    if width in (1440,375):
                        page.locator('#generator-workflow').scroll_into_view_if_needed();page.screenshot(path='/tmp/nxflo-intent-ui-'+str(width)+'.png')
                        # Standalone source uses the same authenticated document and CSS.
                        paper=ctx.new_page();paper.goto(origin+'/bms_integration_hub/api/admin/generator/jobs/'+fixture.id+'/download/html?view=1')
                        paper.locator('.worked-financials h3').scroll_into_view_if_needed();paper.screenshot(path='/tmp/nxflo-intent-paper-'+str(width)+'.png')
                        paper.locator('.calculated-figure').nth(5).scroll_into_view_if_needed();paper.screenshot(path='/tmp/nxflo-intent-heatmap-'+str(width)+'.png')
                        assert paper.evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth')
                    # A failed planning step owns its recovery action, at every viewport.
                    resumes=[]
                    job_snapshot=page.request.get(origin+'/bms_integration_hub/api/admin/generator/jobs/'+fixture.id).json()
                    def failed_job(route):
                        job=json.loads(json.dumps(job_snapshot))
                        job.update(status='failed',step='outline',error='Planning needs recovery.',message='Planning needs recovery.')
                        job['events']=[event for event in job['events'] if event['step'] in ('collect','summarize')]
                        job['recovery']={'can_resume':True,'blocked_reason':''}
                        route.fulfill(status=200,json=job)
                    def resume_job(route):
                        resumes.append(True);route.fulfill(status=202,json={'id':fixture.id,'status':'queued'})
                    page.route('**/jobs/'+fixture.id,failed_job)
                    page.route('**/jobs/'+fixture.id+'/resume',resume_job)
                    page.reload()
                    resume=page.locator('[data-step=outline][data-state=failed] #generator-resume')
                    resume.wait_for(state='visible');resume.scroll_into_view_if_needed()
                    button_box=resume.bounding_box();name_box=page.locator('[data-step=outline] strong').bounding_box()
                    assert button_box['x']>=name_box['x']+name_box['width']-1,(width,button_box,name_box)
                    assert abs(button_box['y']-name_box['y'])<3,(width,button_box,name_box)
                    assert not page.locator('#generator-configuration').evaluate('el=>el.open')
                    assert page.locator('[data-step=outline] strong').evaluate('el=>el.scrollWidth<=el.clientWidth'),width
                    assert button_box['height']>=44
                    assert page.locator('#generator-resume').count()==1
                    assert page.evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth'),width
                    if width in (1440,375):page.screenshot(path='/tmp/nxflo-planning-recovery-'+str(width)+'.png')
                    resume.click();page.wait_for_timeout(200);assert resumes
                    if width<=430:
                        page.locator('.nav-tools-toggle').click();assert page.locator('#tools-menu').is_visible()
                    assert not errors,errors
                    page.unroute_all(behavior='wait')
                    ctx.close()
                browser.close()
        finally:server.shutdown()
    finally:fixture.tearDown()
    print('Collapsed configuration, automatic version override, inline Resume, financial tables and 14 real figures passed at 1440/375/320/430px with no overflow.')

if __name__=='__main__':check()
