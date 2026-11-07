"""Isolated browser/API integration checks. Synthetic Google identities exist only here."""
from functools import partial
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import threading

from flask import send_from_directory
from werkzeug.serving import make_server, WSGIRequestHandler
from playwright.sync_api import sync_playwright

from portal_api import db
from build import PORTAL_FILES
from test_portal_auth import make_test_app

ROOT = Path(__file__).resolve().parents[1]
FAKE_GIS = '''window.google={accounts:{id:{initialize(options){window.testGoogleOptions=options},renderButton(slot){const button=document.createElement('button');button.textContent='Sign in with Google';button.className='google-sign-in';button.addEventListener('click',()=>window.testGoogleOptions.callback({credential:JSON.stringify({...window.testIdentity,nonce:window.testGoogleOptions.nonce})}));slot.append(button)},disableAutoSelect(){}}}};'''


def check(executable, screenshots):
    with TemporaryDirectory() as directory:
        path = Path(directory) / 'bms.sqlite3'
        app = make_test_app(path)
        with db.connect(path) as conn:
            pending, _ = db.login_identity(conn, {'sub':'pending','email':'pending@example.com','email_verified':True,'name':'Pending Customer'}, 'gideont@gmail.com')
            viewer, _ = db.login_identity(conn, {'sub':'viewer','email':'viewer@example.com','email_verified':True,'name':'Viewer Customer'}, 'gideont@gmail.com')
            db.login_identity(conn, {'sub':'xss','email':'xss@example.com','email_verified':True,'name':'<img src=x onerror=alert(1)>'}, 'gideont@gmail.com')
            with db.transaction(conn):
                alpha = conn.execute('INSERT INTO projects(name,created_at) VALUES(?,?)',('Alpha integration project',db.now())).lastrowid
                beta = conn.execute('INSERT INTO projects(name,created_at) VALUES(?,?)',('Beta restricted project',db.now())).lastrowid
                role_id = conn.execute("SELECT id FROM roles WHERE name='Viewer'").fetchone()[0]
                conn.execute("UPDATE users SET status='approved',role_id=? WHERE id=?",(role_id,viewer['id']))
                conn.execute('INSERT INTO user_project_access VALUES(?,?,?,?)',(viewer['id'],alpha,viewer['id'],db.now()))

        @app.get('/bms_integration_hub')
        @app.get('/bms_integration_hub/')
        def index():
            return send_from_directory(ROOT/'bms_integration_hub','index.html')

        @app.get('/bms_integration_hub/<name>')
        def static_portal(name):
            if name not in PORTAL_FILES:
                return {'error':'Not found'},404
            return send_from_directory(ROOT/'bms_integration_hub',name)

        @app.get('/fonts/<name>')
        def font_asset(name):
            return send_from_directory(ROOT/'fonts',name)

        class Quiet(WSGIRequestHandler):
            def log_request(self,*args): pass
        server = make_server('127.0.0.1',0,app,threaded=True,request_handler=Quiet)
        origin = f'http://127.0.0.1:{server.server_port}'
        app.config['PUBLIC_ORIGIN'] = origin
        threading.Thread(target=server.serve_forever,daemon=True).start()
        try:
            with sync_playwright() as p:
                options={'headless':True,'ignore_default_args':['--hide-scrollbars']}
                if executable: options['executable_path']=executable
                browser=p.chromium.launch(**options)
                errors=[]
                def context_for(subject,email,name):
                    context=browser.new_context(viewport={'width':1440,'height':1000})
                    context.add_init_script('window.testIdentity='+json.dumps({'sub':subject,'email':email,'name':name,'email_verified':True}))
                    context.route('https://accounts.google.com/gsi/client',lambda route:route.fulfill(status=200,content_type='application/javascript',body=FAKE_GIS))
                    page=context.new_page();page.on('pageerror',lambda error:errors.append(str(error)))
                    page.goto(origin+'/bms_integration_hub')
                    page.get_by_role('button',name='Sign in with Google',exact=True).click()
                    page.wait_for_selector('#workspace:not([hidden])')
                    return context,page

                owner_context,owner=context_for('owner','gideont@gmail.com','Portal Owner')
                owner.get_by_role('heading',name='Project overview',exact=True).wait_for()
                owner.get_by_role('button',name='Settings',exact=True).last.click()
                owner.locator('#admin-card').click()
                owner.get_by_role('heading',name='Users',exact=True).wait_for()
                owner.locator('.user-card').filter(has_text='pending@example.com').get_by_role('button',name='Manage access').click()
                form=owner.locator('#user-access-form')
                form.locator('select[name=status]').select_option('approved')
                form.locator(f'input[name=project_ids][value="{alpha}"]').check()
                form.get_by_role('button',name='Save access').click()
                owner.get_by_text('Access settings saved.',exact=True).wait_for()
                with db.connect(path) as conn:
                    assert conn.execute('SELECT status FROM users WHERE id=?',(pending['id'],)).fetchone()[0]=='approved'
                    assert conn.execute('SELECT project_id FROM user_project_access WHERE user_id=?',(pending['id'],)).fetchone()[0]==alpha
                assert owner.locator('#user-results img').count()==0,'Profile HTML executed'

                owner.get_by_role('button',name='Roles & permissions',exact=True).click()
                owner.get_by_role('button',name='New role',exact=True).click()
                owner.locator('#role-form input[name=name]').fill('Custom reviewer')
                owner.locator('input[value="projects.view"]').check()
                owner.locator('input[value="tasks.edit"]').check()
                assert owner.locator('input[value="tasks.view"]').is_checked()
                owner.get_by_role('button',name='Create role',exact=True).click()
                owner.get_by_text('Role permissions saved.',exact=True).wait_for()
                owner.get_by_role('button',name='Save permissions',exact=True).click()
                assert 'all 0 users' in owner.locator('#confirm-message').inner_text()
                owner.locator('#confirm-dialog').get_by_role('button',name='Confirm',exact=True).click()
                owner.wait_for_function("!document.getElementById('confirm-dialog').open")
                owner.get_by_text('Role permissions saved.',exact=True).wait_for()

                for width in (1440,375,320,430):
                    owner.set_viewport_size({'width':width,'height':1000})
                    for view,label in (('users','Users'),('roles','Roles & permissions'),('history','Access history'),('projects','Projects')):
                        if view in ('users','roles','history') and not owner.locator('#admin-navigation').is_visible():
                            owner.locator('#workspace-nav [data-view=settings]').click()
                            owner.locator('#admin-card').click()
                        owner.get_by_role('button',name=label,exact=True).last.click()
                        owner.wait_for_selector({'users':'#user-results .user-card','roles':'#role-form','history':'.history-card','projects':'#rfs-results .cell-link'}[view])
                        assert owner.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth'),(view,width)
                        if view=='users':
                            owner.locator('.user-card').filter(has_text='pending@example.com').get_by_role('button',name='Manage access').click()
                            assert owner.locator('#edit-dialog').is_visible()
                            assert owner.evaluate('document.documentElement.scrollWidth <= innerWidth')
                            owner.keyboard.press('Escape')
                            assert not owner.locator('#edit-dialog').is_visible()
                        if view=='roles':
                            box=owner.locator('input[name=permissions]').first
                            owner.keyboard.press('Tab');box.focus();assert box.evaluate("e=>getComputedStyle(e).outlineStyle")!='none'
                        if screenshots and width in (1440,375):
                            Path(screenshots).mkdir(parents=True,exist_ok=True)
                            owner.evaluate('document.activeElement.blur();window.scrollTo(0,0)')
                            owner.screenshot(path=f'{screenshots}/admin-{view}-{width}.png',full_page=True)
                    print(f'{width}px: owner Users, permission matrix, history, projects, dialog, and overflow checks passed',flush=True)

                member_context,member=context_for('viewer','viewer@example.com','Viewer Customer')
                member.get_by_role('heading',name='Project overview',exact=True).wait_for()
                member.locator('#rfs-results').get_by_role('button',name='Alpha integration project',exact=True).wait_for()
                assert 'Beta restricted project' not in member.locator('#workspace-content').inner_text()
                assert not member.locator('#admin-navigation').is_visible()
                assert member.evaluate("fetch('/bms_integration_hub/api/admin/users').then(r=>r.status)")==403
                assert member.evaluate(f"fetch('/bms_integration_hub/api/projects/{beta}').then(r=>r.status)")==404
                member.locator('#rfs-results').get_by_role('button',name='Alpha integration project',exact=True).click()
                member.get_by_role('heading',name='Alpha integration project',exact=True).wait_for()
                owner.locator('#workspace-nav [data-view=settings]').click()
                owner.locator('#admin-card').click()
                owner.locator('.user-card').filter(has_text='viewer@example.com').get_by_role('button',name='Manage access').click()
                owner.locator('#user-access-form select[name=status]').select_option('revoked')
                owner.get_by_role('button',name='Save access',exact=True).click()
                owner.get_by_text('Access settings saved.',exact=True).wait_for()
                assert member.evaluate("fetch('/bms_integration_hub/api/projects').then(r=>r.status)")==401
                member.get_by_role('button',name='Projects',exact=True).click()
                member.get_by_role('button',name='Sign in with Google',exact=True).wait_for()

                pending_context,pending_page=context_for('new-pending','new@example.com','New Customer')
                pending_page.get_by_role('heading',name='Awaiting administrator approval',exact=True).wait_for()
                assert pending_page.evaluate("fetch('/bms_integration_hub/api/projects').then(r=>r.status)")==403
                pending_page.get_by_role('button',name='Check approval status').click()
                assert pending_page.get_by_role('heading',name='Awaiting administrator approval').is_visible()
                pending_page.locator('.profile-menu summary').click()
                pending_page.get_by_role('button',name='Sign out',exact=True).click()
                pending_page.get_by_role('button',name='Sign in with Google',exact=True).wait_for()
                assert not errors,errors
                browser.close()
                print('Actual HTTP/API flow: owner bootstrap, approval, custom role, confirmation, escaped profile names, member isolation, revocation, pending gate, and logout passed',flush=True)
        finally:
            server.shutdown();server.server_close()


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--browser-executable')
    parser.add_argument('--screenshots')
    args=parser.parse_args()
    check(args.browser_executable,args.screenshots)
