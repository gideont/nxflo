"""Warning delivery UI and paginated qualified draft at desktop/mobile widths."""
import json
import threading
from pathlib import Path
from flask import Flask,send_from_directory
from werkzeug.serving import make_server,WSGIRequestHandler
from playwright.sync_api import sync_playwright
from test_verification_delivery import VerificationDeliveryTests,NoPaidCalls
from portal_api.generator_worker import Engine
from portal_api.generator import BASE
from check_portal_admin import FAKE_GIS
ROOT=Path(__file__).resolve().parents[1]

def check():
    fixture=VerificationDeliveryTests();fixture.setUp()
    try:
        Engine(fixture.path,fixture.id,NoPaidCalls).run();assert fixture.row()['status']=='needs_review',fixture.row()['error']
        app=fixture.app;site_app=Flask('verification-site')
        @site_app.get('/<path:name>')
        def site(name):return send_from_directory(ROOT/'dist',name)
        class Quiet(WSGIRequestHandler):
            def log_request(self,*a):pass
        def dispatch(environ,start_response):return (app if environ.get('PATH_INFO','').startswith('/bms_integration_hub/api') else site_app)(environ,start_response)
        server=make_server('127.0.0.1',0,dispatch,threaded=True,request_handler=Quiet);origin=f'http://127.0.0.1:{server.server_port}';app.config['PUBLIC_ORIGIN']=origin
        threading.Thread(target=server.serve_forever,daemon=True).start()
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch(headless=True,ignore_default_args=['--hide-scrollbars'])
                for width in (1440,375,320,430):
                    ctx=browser.new_context(viewport={'width':width,'height':950});ctx.add_init_script('window.testIdentity='+json.dumps({'sub':'owner','email':'gideont@gmail.com','email_verified':True,'name':'Owner'}))
                    ctx.route('https://accounts.google.com/gsi/client',lambda route:route.fulfill(status=200,content_type='application/javascript',body=FAKE_GIS))
                    page=ctx.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                    page.goto(origin+'/admin.html?job='+fixture.id);page.get_by_role('button',name='Sign in with Google',exact=True).click();page.locator('#admin-workspace').wait_for(state='visible');page.locator('#generator-tab').click()
                    panel=page.locator('#generator-publication');panel.wait_for(state='visible');assert 'WARNING' in panel.inner_text()
                    panel.locator('summary').click();assert '33.3%' in panel.inner_text();assert '46 m²' in panel.inner_text()
                    assert page.locator('#generator-result').is_visible();assert 'verification warnings' in page.locator('#generator-result').inner_text()
                    for kind in ('html','pdf'):
                        response=page.request.get(origin+BASE+'/jobs/'+fixture.id+'/download/'+kind);assert response.status==200
                    assert page.locator('#generator-resume').is_hidden()
                    panel.scroll_into_view_if_needed();assert page.evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth')
                    if width in (1440,375):page.screenshot(path='/tmp/nxflo-warning-ui-'+str(width)+'.png')
                    if width<=430:page.locator('.nav-tools-toggle').click();assert page.locator('#tools-menu').is_visible()
                    preview=ctx.new_page();preview.goto(origin+BASE+'/jobs/'+fixture.id+'/download/html?view=1')
                    preview.wait_for_function("() => document.body.dataset.pagination==='ready'")
                    assert 'UNVERIFIED DRAFT' in preview.locator('body').inner_text()
                    assert preview.locator('.verification-label').count()>=3
                    assert preview.locator('#verification-register').count()==1
                    assert preview.evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth')
                    if width in (1440,375):preview.screenshot(path='/tmp/nxflo-warning-preview-'+str(width)+'.png')
                    assert not errors,errors
                    ctx.close()
                browser.close()
        finally:server.shutdown()
    finally:fixture.tearDown()
    print('WARNING drafts: exact outstanding issues, HTML/PDF downloads, navigation and paginated qualifications passed at 1440/375/320/430px without overflow.')

if __name__=='__main__':check()
