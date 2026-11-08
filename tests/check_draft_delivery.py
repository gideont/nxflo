"""Private version review notes and clean artifacts at desktop/mobile widths."""
import json
import threading
from pathlib import Path
from flask import Flask,send_from_directory
from werkzeug.serving import make_server,WSGIRequestHandler
from playwright.sync_api import sync_playwright
from test_draft_delivery import DraftDeliveryTests
from check_portal_admin import FAKE_GIS

ROOT=Path(__file__).resolve().parents[1]

def check():
    case=DraftDeliveryTests();case.setUp()
    try:
        row=case.run_saved();assert row['status']=='needs_review',row['error']
        fixture=case.f;app=fixture.app;site=Flask('draft-site')
        @site.get('/<path:name>')
        def site_asset(name):return send_from_directory(ROOT/'dist',name)
        class Quiet(WSGIRequestHandler):
            def log_request(self,*args):pass
        def dispatch(environ,start_response):return (app if environ.get('PATH_INFO','').startswith('/bms_integration_hub/api') else site)(environ,start_response)
        server=make_server('127.0.0.1',0,dispatch,threaded=True,request_handler=Quiet);origin=f'http://127.0.0.1:{server.server_port}';app.config['PUBLIC_ORIGIN']=origin
        threading.Thread(target=server.serve_forever,daemon=True).start()
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch(headless=True,ignore_default_args=['--hide-scrollbars'])
                for width in (1440,375,320,430):
                    ctx=browser.new_context(viewport={'width':width,'height':950})
                    ctx.add_init_script('window.testIdentity='+json.dumps({'sub':'owner','email':'gideont@gmail.com','email_verified':True,'name':'Owner'}))
                    ctx.route('https://accounts.google.com/gsi/client',lambda route:route.fulfill(status=200,content_type='application/javascript',body=FAKE_GIS))
                    page=ctx.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                    page.goto(origin+'/admin.html?job='+fixture.id);page.get_by_role('button',name='Sign in with Google',exact=True).click();page.locator('#admin-workspace').wait_for(state='visible');page.locator('#generator-tab').click()
                    result=page.locator('#generator-result');result.wait_for(state='visible');assert 'version history' in result.inner_text()
                    assert not page.locator('#generator-publication').is_visible();assert not page.locator('#generator-failure').is_visible()
                    card=page.locator('.generator-library-document').first;card.locator('.generator-document-title').click()
                    notes=card.locator('.generator-version-notes');notes.locator('summary').first.click()
                    page.wait_for_function("() => document.querySelector('.generator-version-notes')?.dataset.loaded==='done'")
                    assert 'unsupported number' in notes.inner_text();assert 'A12' in notes.inner_text()
                    assert 'no verification annotations' in notes.inner_text()
                    assert page.evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth'),width
                    if width in (1440,375):notes.scroll_into_view_if_needed();page.screenshot(path='/tmp/nxflo-draft-history-'+str(width)+'.png')
                    original=notes.get_by_text('Original claim and citation checks',exact=True);original.click()
                    assert page.evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth'),width
                    if width<=430:page.locator('.nav-tools-toggle').click();assert page.locator('#tools-menu').is_visible()
                    href=page.locator('#generator-download-html').get_attribute('href');response=ctx.request.get(origin+href if href.startswith('/') else href)
                    assert response.status==200
                    html=response.text()
                    for marker in ('UNVERIFIED DRAFT','verification-label','verification-register','research-evidence','Source and editorial notes','[R404]'):assert marker not in html,marker
                    assert not errors,errors
                    page.unroute_all(behavior='wait');ctx.close()
                browser.close()
        finally:server.shutdown()
    finally:case.tearDown()
    print('Clean draft delivery, private version-history notes, original citation records and navigation passed at 1440/375/320/430px without overflow.')

if __name__=='__main__':check()
