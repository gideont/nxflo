"""Browser checks against isolated synthetic schedules; never writes to the production database."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
from flask import send_from_directory
from werkzeug.serving import make_server, WSGIRequestHandler
from playwright.sync_api import sync_playwright
from portal_api import db
from test_portal_auth import make_test_app
from check_portal_admin import FAKE_GIS
from build import PORTAL_FILES
ROOT=Path(__file__).resolve().parents[1]


def check(executable, screenshots):
    with TemporaryDirectory() as directory:
        path=Path(directory)/'workspace.sqlite3';app=make_test_app(path)
        with db.connect(path) as conn:
            for i,(status,health) in enumerate([('completed','on_track'),('planned','on_track'),('in_progress','in_progress'),('on_hold','on_hold'),('in_progress','watch'),('planned','delayed')]):
                conn.execute('INSERT INTO projects(name,customer,site_code,status,health,start_date,rfs_date,notes,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)',
                             (f'Integration project {i+1}',f'Customer {chr(65+i//2)}',f'SITE{i+1}',status,health,'2026-09-01',f'2027-0{i+1}-20','Commissioning review' if health=='watch' else '',db.now(),db.now()))
            for project in (1,2):
                for i,(group,title,status) in enumerate([('Data Collection','Collect Modbus points','completed'),('Data Collection','Buffer incoming readings','completed'),('Data Transformation','Map equipment point list','completed'),('Data Transformation','Automate validation','in_progress'),('Data Transformation','Transform payload to JSON','in_progress'),('Data Load','Publish to MQTT broker','planned'),('Data Load','Configure publish frequency','planned')]):
                    conn.execute('INSERT INTO tasks(project_id,title,group_name,owner_name,status,effort_md,start_date,end_date,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)',
                                 (project,title,group,'Test Engineer',status,i+1,f'2026-{9+i//3:02d}-{1+i%3*8:02d}',f'2026-{9+i//3:02d}-{8+i%3*8:02d}',db.now(),db.now()))
        @app.get('/bms_integration_hub')
        def index(): return send_from_directory(ROOT/'bms_integration_hub','index.html')
        @app.get('/bms_integration_hub/<name>')
        def asset(name):
            if name not in PORTAL_FILES:return {},404
            return send_from_directory(ROOT/'bms_integration_hub',name)
        @app.get('/fonts/<name>')
        def font_asset(name):
            return send_from_directory(ROOT/'fonts',name)

        class Quiet(WSGIRequestHandler):
            def log_request(self,*args):pass
        server=make_server('127.0.0.1',0,app,threaded=True,request_handler=Quiet)
        origin=f'http://127.0.0.1:{server.server_port}';app.config['PUBLIC_ORIGIN']=origin
        threading.Thread(target=server.serve_forever,daemon=True).start()
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch(executable_path=executable,headless=True,ignore_default_args=['--hide-scrollbars'])
                context=browser.new_context(viewport={'width':1440,'height':1050});errors=[]
                context.add_init_script('window.testIdentity='+json.dumps({'sub':'owner','email':'gideont@gmail.com','name':'Portal Owner','email_verified':True}))
                context.route('https://accounts.google.com/gsi/client',lambda route:route.fulfill(status=200,content_type='application/javascript',body=FAKE_GIS))
                page=context.new_page();page.on('pageerror',lambda error:errors.append(str(error)))
                page.goto(origin+'/bms_integration_hub');page.get_by_role('button',name='Sign in with Google',exact=True).click()
                page.get_by_role('heading',name='Project overview',exact=True).wait_for()
                assert page.locator('.kpi-value').all_text_contents()==['1','2','2','1','2']
                assert page.locator('#rfs-results tbody tr').count()==6
                page.locator('[data-kpi=watch]').click();page.get_by_role('heading',name='Projects',exact=True).wait_for();assert page.locator('#rfs-results tbody tr').count()==2
                page.locator('#clear-project-filter').click();assert page.locator('#rfs-results tbody tr').count()==6
                page.locator('#workspace-nav [data-view=home]').click();page.locator('.kpi-grid').wait_for()
                page.locator('#rfs-customer').select_option('Customer A');assert page.locator('#rfs-results tbody tr').count()==2
                page.locator('#rfs-customer').select_option('');page.locator('#rfs-query').fill('SITE5');assert page.locator('#rfs-results tbody tr').count()==1
                page.locator('#rfs-query').fill('');page.locator('#rfs-health').select_option('watch');assert page.locator('#rfs-results tbody tr').count()==1
                page.locator('#rfs-health').select_option('');page.locator('#rfs-from').fill('2027-03-01');page.locator('#rfs-from').dispatch_event('change');assert page.locator('#rfs-results tbody tr').count()==4
                page.locator('#rfs-from').fill('');page.locator('#rfs-from').dispatch_event('change')
                page.locator('[data-rfs-mode=table]').click();assert page.locator('#rfs-results .timeline-track').count()==0
                page.locator('[data-rfs-mode=timeline]').click();assert page.locator('#rfs-results .timeline-track').count()==6
                page.locator('[data-sort=rfs_date]').click();assert page.locator('#rfs-results tbody tr').first.inner_text().startswith('SITE6')
                page.locator('[data-sort=rfs_date]').click()
                initial=page.locator('#rfs-results .range-label').inner_text();page.locator('#rfs-next').click();assert page.locator('#rfs-results .range-label').inner_text()!=initial;page.locator('#rfs-prev').click()
                page.locator('#task-project').select_option('1');assert page.locator('#task-results [data-task]').count()==14
                page.locator('[data-group="0"]').click();assert page.locator('#task-results [data-task]').count()==10
                page.locator('[data-group="0"]').click()
                for scale in ('daily','monthly','weekly'):
                    page.locator('#task-scale').select_option(scale);assert page.locator('#task-results .timeline-labels span').count()=={'daily':21,'weekly':16,'monthly':12}[scale]
                before=page.locator('#task-results .range-label').inner_text();page.locator('#task-next').click();assert page.locator('#task-results .range-label').inner_text()!=before;page.locator('#task-prev').click()
                page.locator('#task-project').select_option('3');assert page.get_by_role('heading',name='No implementation tasks yet').is_visible()
                page.locator('#task-project').select_option('1')
                page.locator('#task-results [data-task]').first.click();page.locator('#edit-task').click();page.locator('#task-edit-form input[name=owner_name]').fill('Updated Engineer');page.get_by_role('button',name='Save task',exact=True).click();page.get_by_text('Task saved.',exact=True).wait_for();assert 'Updated Engineer' in page.locator('#task-results').inner_text()
                page.locator('#new-task').click();page.locator('#task-edit-form input[name=title]').fill('Verify gateway');page.get_by_role('button',name='Save task',exact=True).click();page.get_by_text('Task saved.',exact=True).wait_for();assert 'Verify gateway' in page.locator('#task-results').inner_text()
                page.locator('#global-search').fill('gateway');page.locator('#global-search-form').press('Enter');page.locator('.search-result').wait_for();assert page.locator('.search-result').count()==1
                page.locator('#notifications').click();page.get_by_role('heading',name='Notifications',exact=True).wait_for();assert page.locator('[data-alert-project]').count()==2;page.keyboard.press('Escape')
                page.locator('#workspace-nav [data-view=home]').click();page.locator('.kpi-grid').wait_for()
                page.locator('#sidebar-toggle').click();assert page.locator('#workspace').evaluate("e=>e.classList.contains('sidebar-collapsed')")
                page.reload();page.get_by_role('heading',name='Project overview',exact=True).wait_for();assert page.locator('#workspace').evaluate("e=>e.classList.contains('sidebar-collapsed')")
                page.locator('#sidebar-toggle').click()
                page.wait_for_function("Math.abs(document.getElementById('workspace-nav').getBoundingClientRect().width-240)<1")
                rail=page.locator('#sidebar-resizer');box=rail.bounding_box()
                page.mouse.move(box['x']+box['width']/2,box['y']+150);page.mouse.down();page.mouse.move(box['x']+box['width']/2+100,box['y']+150,steps=8);page.mouse.up()
                page.wait_for_function("Math.abs(document.getElementById('workspace-nav').getBoundingClientRect().width-340)<1")
                assert page.evaluate("localStorage.getItem('bms.sidebar.width')")=='340'
                page.reload();page.get_by_role('heading',name='Project overview',exact=True).wait_for()
                page.wait_for_function("Math.abs(document.getElementById('workspace-nav').getBoundingClientRect().width-340)<1")
                rail.focus();page.keyboard.press('ArrowLeft');assert rail.get_attribute('aria-valuenow')=='330'
                page.keyboard.press('Home');assert rail.get_attribute('aria-valuenow')=='180'
                page.keyboard.press('End');assert rail.get_attribute('aria-valuenow')=='420'
                page.wait_for_function("Math.abs(document.getElementById('workspace-nav').getBoundingClientRect().width-420)<1")
                box=rail.bounding_box();page.mouse.move(box['x']+4,box['y']+150);page.mouse.down();page.mouse.move(1000,box['y']+150);page.mouse.up()
                assert rail.get_attribute('aria-valuenow')=='420'
                rail.dblclick();page.wait_for_function("Math.abs(document.getElementById('workspace-nav').getBoundingClientRect().width-240)<1")
                print('Sidebar drag, width persistence, keyboard adjustment, limits and reset passed',flush=True)
                for width in (1920,1440,1280,768,430,375,320):
                    page.set_viewport_size({'width':width,'height':1050})
                    assert page.evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth'),width
                    assert page.locator('#workspace-nav [data-view=home]').is_visible()
                    for view in ('home','projects','tasks','settings','requirements','architecture','monitoring'):
                        page.locator('#workspace-nav [data-view='+view+']').click();page.wait_for_function("!document.querySelector('.loading-skeleton')")
                        assert page.evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth'),(width,view)
                    page.locator('#workspace-nav [data-view=home]').click();page.locator('.kpi-grid').wait_for()
                    if screenshots and width in (1440,375,320):
                        Path(screenshots).mkdir(parents=True,exist_ok=True);page.screenshot(path=f'{screenshots}/dashboard-{width}.png',full_page=True)
                    if width in (375,320):
                        page.locator('#sidebar-toggle').click()
                        rail=page.locator('#sidebar-resizer');rail.wait_for(state='visible')
                        box=rail.bounding_box();page.mouse.move(box['x']+5,box['y']+120);page.mouse.down();page.mouse.move(width-2,box['y']+120,steps=5);page.mouse.up()
                        assert int(rail.get_attribute('aria-valuenow'))<=width-54
                        assert page.evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth')
                        rail.focus();page.keyboard.press('Home');assert rail.get_attribute('aria-valuenow')=='180'
                        page.locator('#workspace-nav [data-view=projects]').click()
                        page.wait_for_function("!document.querySelector('.loading-skeleton')")
                        assert not page.locator('#sidebar-resizer').is_visible()
                        page.locator('#workspace-nav [data-view=home]').click();page.locator('.kpi-grid').wait_for()
                    print(f'{width}px dashboard, schedules, sidebar and navigation passed',flush=True)
                page.set_viewport_size({'width':1440,'height':1050});page.locator('#rfs-results [data-project="1"]').first.click();page.get_by_role('heading',name='Integration project 1',exact=True).wait_for()
                page.locator('#edit-project').click();page.locator('#project-edit-form input[name=rfs_date]').fill('2027-02-28');page.get_by_role('button',name='Save project',exact=True).click();page.get_by_text('Project saved.',exact=True).wait_for()
                assert not errors,errors
                browser.close();print('KPI counts, filters, sorting, timelines, task groups, CRUD, search, notifications, sidebar persistence and project details passed',flush=True)
        finally:server.shutdown();server.server_close()

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--browser-executable',required=True);parser.add_argument('--screenshots');args=parser.parse_args();check(args.browser_executable,args.screenshots)
