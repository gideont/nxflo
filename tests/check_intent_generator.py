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
                    page.locator('[name=document_intent]').select_option('product_concept')
                    assert page.locator('[name=report_type]').input_value()=='White paper'
                    page.locator('[name=topic]').fill('Preserve this authorial product vision.')
                    page.locator('#generator-save').click()
                    page.wait_for_function("document.querySelector('#generator-save-state').textContent==='Saved'")
                    page.reload();page.wait_for_function("document.querySelector('#generator-save-state').textContent!=='Not loaded'")
                    assert page.locator('[name=document_intent]').input_value()=='product_concept'
                    if width==1440:
                        page.locator('#generator-documents').set_input_files({'name':'author-notes.txt','mimeType':'text/plain','buffer':b'Author material about the reusable calculation engine.'})
                        role=page.locator('.generator-source-role').first;role.wait_for(state='visible');assert role.input_value()=='author'
                        role.select_option('reference');page.locator('#generator-save').click()
                        page.wait_for_function("document.querySelector('#generator-save-state').textContent==='Saved'")
                    else:assert page.locator('.generator-source-role').first.input_value()=='reference'
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
                        page.locator('[name=document_intent]').scroll_into_view_if_needed();page.screenshot(path='/tmp/nxflo-intent-ui-'+str(width)+'.png')
                        # Standalone source uses the same authenticated document and CSS.
                        paper=ctx.new_page();paper.goto(origin+'/bms_integration_hub/api/admin/generator/jobs/'+fixture.id+'/download/html?view=1')
                        paper.locator('.worked-financials h3').scroll_into_view_if_needed();paper.screenshot(path='/tmp/nxflo-intent-paper-'+str(width)+'.png')
                        paper.locator('.calculated-figure').nth(5).scroll_into_view_if_needed();paper.screenshot(path='/tmp/nxflo-intent-heatmap-'+str(width)+'.png')
                        assert paper.evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth')
                    if width<=430:
                        page.locator('.nav-tools-toggle').click();assert page.locator('#tools-menu').is_visible()
                    assert not errors,errors
                    ctx.close()
                browser.close()
        finally:server.shutdown()
    finally:fixture.tearDown()
    print('Intent selection, author/reference roles, financial tables and 14 real figures passed at 1440/375/320/430px with no overflow.')

if __name__=='__main__':check()
