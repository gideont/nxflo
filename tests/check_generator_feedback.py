"""Model cost proxies, workflow focus and honest animated progress; no paid requests."""
import os,json,time,threading
from pathlib import Path
from tempfile import TemporaryDirectory
from flask import send_from_directory
from werkzeug.serving import make_server,WSGIRequestHandler
from playwright.sync_api import sync_playwright
from test_portal_auth import make_test_app
from check_portal_admin import FAKE_GIS
from portal_api import db
from portal_api.generator import BASE
ROOT=Path(__file__).resolve().parents[1]

def check():
 os.environ.update(OPENROUTER_API_KEY='synthetic-feedback-key',DATABRICKS_AI_KEY='synthetic-databricks-key',DATABRICKS_BASE_URL='https://workspace.example/ai-gateway/mlflow/v1',DATABRICKS_MODEL='system.ai.claude-haiku-5-5')
 with TemporaryDirectory() as directory:
  path=Path(directory)/'feedback.sqlite3';app=make_test_app(path)
  @app.get('/<path:name>')
  def site(name):return send_from_directory(ROOT/'dist',name)
  class Quiet(WSGIRequestHandler):
   def log_request(self,*a):pass
  server=make_server('127.0.0.1',0,app,threaded=True,request_handler=Quiet);origin=f'http://127.0.0.1:{server.server_port}';app.config['PUBLIC_ORIGIN']=origin
  threading.Thread(target=server.serve_forever,daemon=True).start()
  try:
   with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,ignore_default_args=['--hide-scrollbars'])
    for width in (1440,375,320,430):
     with db.connect(path) as c:c.execute("INSERT INTO generator_meta(key,value) VALUES('heartbeat',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(str(time.time()),))
     context=browser.new_context(viewport={'width':width,'height':950});context.add_init_script('window.testIdentity='+json.dumps({'sub':'owner','email':'gideont@gmail.com','email_verified':True,'name':'Owner'}))
     context.route('https://accounts.google.com/gsi/client',lambda route:route.fulfill(status=200,content_type='application/javascript',body=FAKE_GIS))
     page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
     page.goto(origin+'/admin.html');page.get_by_role('button',name='Sign in with Google',exact=True).click();page.locator('#admin-workspace').wait_for(state='visible');page.locator('#generator-tab').click()
     page.wait_for_function("document.querySelector('#generator-save-state').textContent!=='Not loaded'")
     page.locator('#generator-provider').select_option('databricks')
     page.wait_for_function("document.querySelector('#generator-cost-total').textContent.includes('$')")
     assert 'reference rates' in page.locator('#generator-pricing-status').inner_text()
     assert 'Workspace rate' not in page.locator('#generator-model-rates').inner_text()
     assert '$0.10' in page.locator('#generator-model-rates').inner_text() and '$0.50' in page.locator('#generator-model-rates').inner_text()
     money=lambda:float(page.locator('#generator-cost-total').inner_text().replace('≈','').replace('$','').replace(',','').strip())
     page.locator('[name=review_passes]').select_option('1');low=money();page.locator('[name=review_passes]').select_option('4');assert money()>low>0
     assert 'planning estimate' in page.locator('#generator-cost-assumptions').inner_text()
     assert page.evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth'),width
     if width in (1440,375):page.locator('#generator-cost-total').scroll_into_view_if_needed();page.screenshot(path=f'/tmp/nxflo-cost-reference-{width}.png')
     page.locator('[name=title]').fill('Workflow feedback test');page.locator('[name=topic]').fill('A product concept with clear authorial intent and practical examples.');page.locator('[name=release_date]').fill('2026-11-08')
     page.locator('#generator-start').click();page.wait_for_function("document.activeElement?.dataset.step==='collect'");page.wait_for_timeout(450)
     first=page.locator('[data-step=collect]').bounding_box();assert first['y']>=0 and first['y']+first['height']<=950,(width,first)
     job=page.url.split('job=')[1]
     assert page.locator('#generator-progress-percent').inner_text()=='0%'
     assert page.locator('.generator-progress-animation').evaluate('e=>getComputedStyle(e).animationName')=='generator-progress-flow'
     with db.connect(path) as c:c.execute("UPDATE generator_jobs SET status='running',step='draft',events=?,work_progress=? WHERE id=?",(json.dumps([{'step':s,'status':'complete'} for s in ('collect','summarize','outline')]),json.dumps({'step':'draft','completed':1,'total':4,'unit':'requests'}),job))
     page.wait_for_function("document.querySelector('#generator-progress-percent').textContent==='27%'")
     assert page.locator('#generator-progress').get_attribute('aria-valuetext')=='27% of workflow complete'
     assert 'USD charges are not returned' in page.locator('#generator-cost-actual').inner_text()
     page.emulate_media(reduced_motion='reduce');assert page.locator('.generator-progress-animation').evaluate('e=>getComputedStyle(e).animationName')=='none'
     page.emulate_media(reduced_motion='no-preference')
     assert page.evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth'),width
     if width in (1440,375):page.locator('#generator-workflow').scroll_into_view_if_needed();page.screenshot(path=f'/tmp/nxflo-workflow-progress-{width}.png')
     with db.connect(path) as c:c.execute("UPDATE generator_jobs SET status='failed' WHERE id=?",(job,))
     page.locator('[data-step=draft][data-state=failed]').wait_for();assert page.locator('#generator-progress-percent').inner_text()=='27%';assert page.locator('.generator-progress-animation').evaluate('e=>getComputedStyle(e).animationName')=='none'
     with db.connect(path) as c:c.execute("UPDATE generator_jobs SET status='ready',step='deliver' WHERE id=?",(job,));assert c.execute('SELECT count(*) FROM generator_calls').fetchone()[0]==0
     page.reload();page.wait_for_function("document.querySelector('#generator-progress-percent').textContent==='100%'")
     assert page.locator('#generator-progress').get_attribute('value')=='12'
     assert page.locator('.generator-progress-animation').evaluate('e=>getComputedStyle(e).animationName')=='none'
     assert not errors,errors;context.close()
    browser.close()
  finally:server.shutdown()
 print('Workflow focus, hosted model cost estimates, count-based percentages, paused/completed animation and reduced motion passed at 1440/375/320/430px without overflow or provider calls.')
if __name__=='__main__':check()
