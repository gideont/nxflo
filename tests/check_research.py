"""Responsive research settings, verification reports, budget actions and revisions."""
import json
import threading
from pathlib import Path
from flask import Flask,send_from_directory
from werkzeug.serving import make_server,WSGIRequestHandler
from playwright.sync_api import sync_playwright
from test_research import ResearchTests,ENV
from portal_api.generator import BASE
from check_portal_admin import FAKE_GIS
ROOT=Path(__file__).resolve().parents[1]


def check():
    fixture=ResearchTests();fixture.setUp()
    try:
        job=fixture.start();row=fixture.run_job(job['id']);assert row['status']=='awaiting_html_review',row['error']
        fixture.owner.post(BASE+'/jobs/'+job['id']+'/approve-html',json={},headers=fixture.headers);fixture.run_job(job['id'])
        app=fixture.app;site_app=Flask('research-site')
        @site_app.get('/<path:name>')
        def site(name):return send_from_directory(ROOT/'dist',name)
        class Quiet(WSGIRequestHandler):
            def log_request(self,*a):pass
        def dispatch(environ,start_response):return (app if environ.get('PATH_INFO','').startswith('/bms_integration_hub/api') else site_app)(environ,start_response)
        server=make_server('127.0.0.1',0,dispatch,threaded=True,request_handler=Quiet);origin=f'http://127.0.0.1:{server.server_port}';app.config['PUBLIC_ORIGIN']=origin;fixture.headers['Origin']=origin
        threading.Thread(target=server.serve_forever,daemon=True).start()
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch(headless=True,ignore_default_args=['--hide-scrollbars'])
                for width in (1440,375,320,430):
                    ctx=browser.new_context(viewport={'width':width,'height':950});ctx.add_init_script('window.testIdentity='+json.dumps({'sub':'owner','email':'gideont@gmail.com','email_verified':True,'name':'Owner'}))
                    ctx.route('https://accounts.google.com/gsi/client',lambda route:route.fulfill(status=200,content_type='application/javascript',body=FAKE_GIS))
                    page=ctx.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                    page.goto(origin+'/admin.html?job='+job['id']);page.get_by_role('button',name='Sign in with Google',exact=True).click();page.locator('#admin-workspace').wait_for(state='visible');page.locator('#generator-tab').click()
                    panel=page.locator('#generator-research');panel.wait_for(state='visible')
                    assert 'corrected' in panel.inner_text();assert 'Tavily' in panel.inner_text();assert 'reserved' in panel.inner_text()
                    panel.locator('#generator-research-ledger>summary').click();assert '$150,000' in panel.inner_text()
                    links=panel.locator('#generator-research-claims a');assert links.count()>=2;assert links.first.get_attribute('target')=='_blank'
                    panel.locator('#generator-research-corrections>summary').click();assert 'Previous:' in panel.inner_text();assert '2024' in panel.inner_text();assert '2019' in panel.inner_text()
                    panel.locator('#generator-research-budget>summary').click();page.locator('#generator-research-new-limit').fill('7.5')
                    with page.expect_response('**/documents/*/research-budget') as changed:page.locator('#generator-research-increase').click()
                    assert changed.value.status==200
                    page.wait_for_function("() => document.querySelector('#generator-research-cost').textContent.includes('$7.50')")
                    assert page.locator('#generator-verify-current').is_visible()
                    assert all(secret not in page.locator('body').inner_text() for secret in ENV.values() if secret.startswith('synthetic'))
                    assert page.evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth'),width
                    if width in (1440,375):panel.scroll_into_view_if_needed();page.screenshot(path='/tmp/nxflo-research-'+str(width)+'.png')
                    # The compact configuration still exposes explicit research choices.
                    page.locator('#generator-configuration>summary').click();page.locator('#generator-research-settings>summary').click()
                    assert page.locator('[name=web_search]').is_checked()
                    assert page.locator('[name=web_budget_usd]').input_value()=='5'
                    assert 'Tavily configured' in page.locator('#generator-research-availability').inner_text()
                    if width<=430:page.locator('.nav-tools-toggle').click();assert page.locator('#tools-menu').is_visible()
                    assert page.evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth'),width
                    if width==1440:
                        with page.expect_response('**/jobs/*/verify') as started:page.locator('#generator-verify-current').click()
                        data=started.value.json();assert data['version']=='1.2',data
                        new=fixture.row(data['id']);assert json.loads(new['state'])['reused_generation'];assert new['step']=='assemble'
                        fixture.owner.post(BASE+'/jobs/'+data['id']+'/cancel',json={},headers=fixture.headers)
                    assert not errors,errors
                    page.unroute_all(behavior='wait');ctx.close()
                browser.close()
        finally:server.shutdown()
    finally:fixture.tearDown()
    print('Research settings, evidence/correction reports, explicit budget increases, version-only verification and navigation passed at 1440/375/320/430px without overflow.')

if __name__=='__main__':check()
