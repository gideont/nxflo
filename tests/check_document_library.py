"""Responsive Document Library behavior, without production data or provider calls."""
import json,threading
from portal_api import db
from pathlib import Path
from flask import Flask,send_from_directory
from werkzeug.serving import make_server,WSGIRequestHandler
from playwright.sync_api import sync_playwright
from test_document_library import DocumentLibraryTests
from check_portal_admin import FAKE_GIS
from portal_api.generator import BASE
ROOT=Path(__file__).resolve().parents[1]

def check():
    fixture=DocumentLibraryTests();fixture.setUp()
    try:
        original=fixture.create('Investment and Return Simulator');revision=fixture.create('Investment and Return Simulator',original['id'],'awaiting_html_review')
        second=fixture.create('Investment and Return Simulator');draft=fixture.create('Unfinished author concept',status='failed')
        app=fixture.app;site_app=Flask('library-site')
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
                    page.goto(origin+'/admin.html');page.get_by_role('button',name='Sign in with Google',exact=True).click();page.locator('#admin-workspace').wait_for(state='visible');page.locator('#generator-tab').click()
                    cards=page.locator('.generator-library-document');cards.first.wait_for();assert cards.count()==2
                    assert page.locator('.generator-library-versions[open]').count()==0
                    doc=page.locator('[data-document="'+original['document_id']+'"]');doc.locator('summary').click()
                    assert doc.locator('.generator-library-version').count()==2
                    assert doc.locator('.generator-library-version').first.locator('strong').inner_text()=='v1.1 · Current version'
                    assert 'Latest downloadable: v1.0' in doc.inner_text()
                    text=page.locator('#generator-jobs').inner_text();assert 'awaiting_html_review' not in text and original['id'] not in text and 'execution history' not in text.lower()
                    await_row=doc.locator('[data-version="'+revision['version_id']+'"]')
                    assert await_row.get_by_role('link',name='Preview HTML',exact=True).get_attribute('target')=='_blank'
                    assert await_row.get_by_role('button',name='Continue to PDF',exact=True).is_visible()
                    ready_row=doc.locator('[data-version="'+original['version_id']+'"]')
                    assert ready_row.get_by_role('link',name='Download PDF',exact=True).get_attribute('href').endswith(original['id']+'/download/pdf')
                    assert ready_row.get_by_role('button',name='Revise document',exact=True).is_visible()
                    page.locator('#generator-refresh').click();page.wait_for_timeout(300)
                    assert page.locator('[data-document="'+original['document_id']+'"] details').get_attribute('open') is not None
                    other=page.locator('[data-document="'+second['document_id']+'"]');other.locator('summary').click();assert not doc.locator('details').evaluate('e=>e.open')
                    page.locator('#generator-library-search').fill('Unfinished');assert page.locator('.generator-library-document').count()==0
                    page.locator('#generator-library-unfinished').check();assert page.locator('.generator-library-document').count()==1
                    unfinished=page.locator('[data-document="'+draft['document_id']+'"]');unfinished.locator('summary').click()
                    assert unfinished.locator('.generator-library-version').count()==0
                    assert unfinished.get_by_role('button',name='Resume',exact=True).is_visible()
                    assert unfinished.locator('.generator-library-current').is_visible()
                    page.locator('#generator-library-search').fill('Investment');assert cards.count()==2
                    doc.locator('summary').click();ready_row.get_by_role('button',name='Revise document',exact=True).click()
                    page.locator('#generator-revision').wait_for(state='visible');assert page.locator('[name=version]').input_value()=='1.2'
                    assert page.locator('[name=revision_parent]').count()==0 # identity is managed by the form state, never a job-ID control.
                    assert page.evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth'),width
                    page.locator('#generator-jobs').scroll_into_view_if_needed()
                    if width in (1440,375):page.screenshot(path='/tmp/nxflo-document-library-'+str(width)+'.png')
                    page.reload();page.locator('.generator-library-document').first.wait_for();assert page.locator('.generator-library-versions[open]').count()==0
                    # A fresh draft keeps corporate identity and cannot inherit a revision parent.
                    saved=page.request.get(origin+BASE).json();seed=saved['config']
                    logo='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII='
                    seed.update(company='Nexusflow Inc.',website='https://www.nxflo.com',logo=logo,color='#123456',accent='#ab3456',title='Previous document',topic='Previous authored content',feedback='Old correction',change_summary='Previous revision',release_date='2026-11-08',version='4.2',version_override=True,revision_parent=original['id'],documents=[{'name':'prior.txt','text':'Previous source'}],illustrations=[logo])
                    token=page.request.get(origin+'/bms_integration_hub/api/me').json()['csrf_token']
                    response=page.request.put(origin+BASE,data={'config':seed,'revision':saved['revision']},headers={'Origin':origin,'X-CSRF-Token':token});assert response.status==200
                    seed=page.request.get(origin+BASE).json()['config'];logo=seed['logo']
                    page.reload();page.locator('#generator-new-document').wait_for(state='visible');page.wait_for_function("!document.querySelector('#generator-new-document').disabled")
                    with db.connect(fixture.path) as c:before_jobs=c.execute('SELECT count(*) FROM generator_jobs').fetchone()[0];before_calls=c.execute('SELECT count(*) FROM generator_calls').fetchone()[0]
                    dialogs=[];page.on('dialog',lambda dialog:(dialogs.append(dialog.message),dialog.accept()))
                    page.locator('#generator-new-document').click();page.wait_for_function("document.querySelector('#generator-status').textContent.includes('New document ready')")
                    assert not dialogs
                    assert page.locator('#generator-configuration').evaluate('e=>e.open')
                    for field in ('title','topic','feedback','change_summary','release_date'):assert page.locator('[name='+field+']').input_value()==''
                    assert page.locator('[name=version]').input_value()=='1.0' and page.locator('[name=version]').get_attribute('readonly') is not None
                    assert page.locator('#generator-revision').is_hidden()
                    assert page.locator('[name=company]').input_value()=='Nexusflow Inc.'
                    assert page.locator('#generator-logo-preview img').get_attribute('src')==logo
                    fresh=page.request.get(origin+BASE).json()['config']
                    for field in ('company','website','logo','teams','prepared_team','color','accent','provider','databricks_model'):assert fresh[field]==seed[field],field
                    assert fresh['documents']==[] and fresh['illustrations']==[] and fresh['revision_parent']=='' and not fresh['version_override']
                    assert 'new=1' in page.url and 'job=' not in page.url
                    with db.connect(fixture.path) as c:assert c.execute('SELECT count(*) FROM generator_jobs').fetchone()[0]==before_jobs
                    page.reload();page.wait_for_function("document.querySelector('#generator-save-state').textContent!=='Not loaded'")
                    assert page.locator('#generator-configuration').evaluate('e=>e.open')
                    assert page.locator('[name=topic]').input_value()==''
                    assert page.locator('#generator-result').is_hidden()
                    assert page.evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth'),width
                    if width in (1440,375):
                        page.locator('#generator-new-document').scroll_into_view_if_needed();page.screenshot(path='/tmp/nxflo-new-document-'+str(width)+'.png')
                    page.locator('[name=title]').fill('Next document');page.locator('[name=topic]').fill('A new author-owned concept for the next document.');page.locator('[name=release_date]').fill('2026-11-08')
                    page.locator('#generator-start').click();page.wait_for_function("location.search.includes('job=')")
                    next_id=page.url.split('job=')[1];next_job=page.request.get(origin+BASE+'/jobs/'+next_id).json()
                    assert next_job['document_id']!=original['document_id'] and next_job['parent_id'] is None and next_job['config']['version']=='1.0'
                    page.locator('#generator-cancel').wait_for(state='visible');assert not page.locator('#generator-configuration').evaluate('e=>e.open')
                    page.wait_for_function("!document.querySelector('#generator-new-document').disabled")
                    page.locator('#generator-new-document').click();page.wait_for_function("document.querySelector('#generator-status').textContent.includes('New document ready')")
                    page.wait_for_timeout(2300)
                    assert page.locator('#generator-configuration').evaluate('e=>e.open')
                    background=page.request.get(origin+BASE+'/jobs/'+next_id).json()
                    assert background['status']=='queued' and background['config']['title']=='Next document'
                    with db.connect(fixture.path) as c:
                        assert c.execute('SELECT count(*) FROM generator_calls').fetchone()[0]==before_calls
                        c.execute("UPDATE generator_jobs SET status='cancelled' WHERE id=?",(next_id,))
                    if width<=430:page.locator('.nav-tools-toggle').click();assert page.locator('#tools-menu').is_visible()
                    assert not errors,errors
                    ctx.close()
                browser.close()
        finally:server.shutdown()
    finally:fixture.tearDown()
    print('Document Library: persistent identities, collapsed histories, search, current/downloadable versions, recovery and revision actions passed at 1440/375/320/430px without overflow.')
if __name__=='__main__':check()
