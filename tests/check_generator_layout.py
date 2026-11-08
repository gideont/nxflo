"""Sample real rendered widths throughout Resume → queued → running → failed."""
import json
import os
import threading
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from flask import send_from_directory
from werkzeug.serving import make_server,WSGIRequestHandler
from playwright.sync_api import sync_playwright
from test_portal_auth import make_test_app
from portal_api.generator import DEFAULTS
from check_portal_admin import FAKE_GIS

ROOT=Path(__file__).resolve().parents[1]


def check():
    os.environ['OPENROUTER_API_KEY']='synthetic-layout-test-key'
    with TemporaryDirectory() as directory:
        app=make_test_app(Path(directory)/'layout.sqlite3')
        @app.get('/<path:name>')
        def site(name):return send_from_directory(ROOT/'dist',name)
        class Quiet(WSGIRequestHandler):
            def log_request(self,*args):pass
        server=make_server('127.0.0.1',0,app,threaded=True,request_handler=Quiet)
        origin=f'http://127.0.0.1:{server.server_port}';app.config['PUBLIC_ORIGIN']=origin
        threading.Thread(target=server.serve_forever,daemon=True).start()
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch(headless=True,ignore_default_args=['--hide-scrollbars'])
                for width in (1440,375,320,430):
                    ctx=browser.new_context(viewport={'width':width,'height':950})
                    ctx.add_init_script('window.testIdentity='+json.dumps({'sub':'owner','email':'gideont@gmail.com','email_verified':True,'name':'Owner'}))
                    ctx.route('https://accounts.google.com/gsi/client',lambda route:route.fulfill(status=200,content_type='application/javascript',body=FAKE_GIS))
                    stage={'status':'failed'};errors=[];job_id='layout-fixture'
                    def job(route):
                        status=stage['status']
                        route.fulfill(status=200,json={'id':job_id,'status':status,'step':'html_review' if status=='awaiting_html_review' else 'outline','pipeline_version':2,
                            'created_at':'2026-11-07T00:00:00Z','updated_at':'2026-11-07T00:00:20Z','server_time':time.time(),
                            'config':{**DEFAULTS,'title':'Investment & Return Simulator'},'events':[{'step':key,'status':'complete'} for key in ('collect','summarize')],
                            'worker_online':True,'recovery':{'can_resume':status=='failed','blocked_reason':''},'wait_state':{},'step_progress':{},
                            'warnings':[],'billing':[],'cost':0,'unreported_calls':0,'failure_details':{'summary':'Draft evidence checks failed.','highlights':['A prose number is absent from the original material: 0.3.'],'chapters':[{'number':3,'title':'Pricing comparison','issues':['A source quote is missing.']},{'number':8,'title':'Adapter architecture','issues':['An original author message is missing.']}],'issues':[],'error':'Intent/provenance gate rejected draft.','next_action':'Saved corrections were checked. Unchanged responses may fail again.'} if status=='failed' else None,'message':'Plan structure & examples '+status,'error':''})
                    def resume(route):
                        stage['status']='queued';route.fulfill(status=202,json={'id':job_id,'status':'queued'})
                    page=ctx.new_page();page.on('pageerror',lambda error:errors.append(str(error)))
                    page.route('**/jobs/'+job_id,job);page.route('**/jobs/'+job_id+'/resume',resume)
                    page.goto(origin+'/admin.html?job='+job_id)
                    page.get_by_role('button',name='Sign in with Google',exact=True).click()
                    page.locator('#admin-workspace').wait_for(state='visible');page.locator('#generator-tab').click()
                    page.locator('[data-step=outline][data-state=failed] #generator-resume').wait_for(state='visible')
                    page.evaluate('''() => {
                        window.layoutSamples=[];window.layoutSampling=true;
                        const sample=()=>{if(!window.layoutSampling)return;
                          const box=document.querySelector('#generator-workflow').getBoundingClientRect();
                          window.layoutSamples.push({width:box.width,x:box.x,state:document.querySelector('[data-step=outline]').dataset.state});
                          requestAnimationFrame(sample);};sample();
                    }''')
                    for _ in range(2):
                        page.locator('#generator-resume').click()
                        page.locator('[data-step=outline][data-state=queued]').wait_for()
                        stage['status']='running';page.locator('[data-step=outline][data-state=running]').wait_for()
                        stage['status']='failed';page.locator('[data-step=outline][data-state=failed] #generator-resume').wait_for(state='visible')
                    samples=page.evaluate('() => {window.layoutSampling=false;return window.layoutSamples;}')
                    assert {'failed','queued','running'}<={sample['state'] for sample in samples},samples
                    for field in ('width','x'):
                        values=[sample[field] for sample in samples]
                        assert max(values)-min(values)<1,(width,field,min(values),max(values))
                    failure=page.locator('[data-step=outline] #generator-failure');assert failure.is_visible()
                    assert '0.3' in failure.inner_text()
                    failure.locator('#generator-failure-more>summary').click()
                    assert 'Adapter architecture' in page.locator('#generator-failure-chapters').inner_text()
                    assert 'A source quote is missing.' in page.locator('#generator-failure-chapters').inner_text()
                    assert page.evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth')
                    if width in (1440,375):failure.scroll_into_view_if_needed();page.screenshot(path='/tmp/nxflo-failure-details-'+str(width)+'.png')
                    configuration=page.locator('#generator-configuration').bounding_box()
                    compact=page.locator('#generator-workflow').bounding_box()
                    assert not page.locator('#generator-configuration').evaluate('el=>el.open')
                    if width>900:
                        assert abs(configuration['y']-compact['y'])<1
                        assert configuration['x']+configuration['width']<=compact['x']
                        assert compact['width']>configuration['width']*2
                    else:assert compact['y']>=configuration['y']+configuration['height']
                    # Explicitly returning to configuration expands the form; polling must preserve that choice.
                    before=page.locator('#generator-workflow').bounding_box()
                    page.locator('#generator-configuration>summary').click()
                    after=page.locator('#generator-workflow').bounding_box()
                    if width>900:
                        expanded=page.locator('#generator-configuration').bounding_box()
                        assert expanded['width']>configuration['width']
                        assert abs(expanded['y']-after['y'])<1
                        assert expanded['x']+expanded['width']<=after['x']
                    else:assert abs(before['width']-after['width'])<1
                    page.wait_for_timeout(2500)
                    assert page.locator('#generator-configuration').evaluate('el=>el.open')
                    assert page.evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth'),width
                    # Even the initial two-column layout has no status-based width animation.
                    page.evaluate("document.querySelector('.generator-layout').classList.remove('is-focused')")
                    boxes=[]
                    for running in (False,True,False,True):
                        page.evaluate("running=>document.querySelector('.generator-layout').classList.toggle('is-running',running)",running)
                        page.wait_for_timeout(500)
                        boxes.append(page.locator('#generator-workflow').bounding_box()['width'])
                    assert max(boxes)-min(boxes)<1,(width,boxes)
                    page.evaluate("document.querySelector('.generator-layout').classList.add('is-focused');document.querySelector('.generator-layout').classList.remove('is-running')")
                    if width in (1440,375):
                        page.locator('#generator-configuration>summary').click()
                        page.locator('[data-step=outline]').scroll_into_view_if_needed()
                        page.screenshot(path='/tmp/nxflo-stable-workflow-'+str(width)+'.png')
                    if width<=430:
                        page.locator('.nav-tools-toggle').click();assert page.locator('#tools-menu').is_visible()
                    approvals=[]
                    def approve(route):
                        approvals.append(True);stage['status']='queued';route.fulfill(status=202,json={'id':job_id,'status':'queued'})
                    page.route('**/jobs/'+job_id+'/approve-html',approve)
                    ctx.route('**/jobs/'+job_id+'/download/html?view=1',lambda route:route.fulfill(status=200,content_type='text/html',body='<h1>Page 1 preview</h1>'))
                    stage['status']='awaiting_html_review';page.reload()
                    review=page.locator('[data-step=html_review] #generator-review-jump')
                    proceed=page.locator('[data-step=html_review] #generator-approve-html')
                    review.wait_for(state='visible');assert proceed.is_visible()
                    assert review.get_attribute('target')=='_blank'
                    assert page.locator('#generator-html-frame').count()==0
                    review_box=review.bounding_box();continue_box=proceed.bounding_box()
                    assert continue_box['x']>=review_box['x']+review_box['width']-1
                    assert abs(continue_box['y']-review_box['y'])<1
                    assert min(review_box['height'],continue_box['height'])>=44
                    assert page.locator('[data-step=html_review]').bounding_box()['height']<180
                    assert page.evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth')
                    if width in (1440,375):
                        review.scroll_into_view_if_needed();page.screenshot(path='/tmp/nxflo-step10-actions-'+str(width)+'.png')
                    original_url=page.url
                    with page.expect_popup() as opened:review.click()
                    preview=opened.value;preview.wait_for_load_state();assert 'Page 1 preview' in preview.locator('body').inner_text();preview.close()
                    assert page.url==original_url
                    proceed.click();page.locator('#generator-review-actions').wait_for(state='hidden');assert len(approvals)==1
                    assert not errors,errors
                    page.unroute_all(behavior='wait');ctx.close()
                browser.close()
        finally:server.shutdown()
    print('Two Resume/failure cycles retain identical workflow widths and horizontal positions at 1440/375/320/430px; expanded configuration and navigation remain usable.')

if __name__=='__main__':check()
