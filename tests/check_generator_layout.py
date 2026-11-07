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
                        route.fulfill(status=200,json={'id':job_id,'status':status,'step':'outline','pipeline_version':2,
                            'created_at':'2026-11-07T00:00:00Z','updated_at':'2026-11-07T00:00:20Z','server_time':time.time(),
                            'config':{**DEFAULTS,'title':'Investment & Return Simulator'},'events':[{'step':key,'status':'complete'} for key in ('collect','summarize')],
                            'worker_online':True,'recovery':{'can_resume':status=='failed','blocked_reason':''},'wait_state':{},'step_progress':{},
                            'warnings':[],'billing':[],'cost':0,'unreported_calls':0,'message':'Plan structure & examples '+status,'error':''})
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
                    # An expanded configuration must also leave the workflow width alone.
                    before=page.locator('#generator-workflow').bounding_box()
                    page.locator('#generator-configuration>summary').click()
                    after=page.locator('#generator-workflow').bounding_box()
                    assert abs(before['width']-after['width'])<1
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
                    assert not errors,errors
                    page.unroute_all(behavior='wait');ctx.close()
                browser.close()
        finally:server.shutdown()
    print('Two Resume/failure cycles retain identical workflow widths and horizontal positions at 1440/375/320/430px; expanded configuration and navigation remain usable.')

if __name__=='__main__':check()
