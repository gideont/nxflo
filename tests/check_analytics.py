"""Exercise the admin screen at desktop and mobile widths with synthetic API fixtures."""
from datetime import date,timedelta
import json
from pathlib import Path
from playwright.sync_api import sync_playwright


def check(url):
    paths=['/','/about.html','/services.html','/contact.html','/csv-viewer.html','/pdf-combiner.html','/tools.html','/databricks-consulting.html','/etl-data-pipelines.html','/what-can-we-help-you-with.html']
    series=[dict(path=path,daily=[dict(day=(date(2026,10,1)+timedelta(days=i)).isoformat(),page_views=(i*(j+3)+j*7)%17) for i in range(28)]) for j,path in enumerate(paths)]
    for item in series: item['total_views']=sum(r['page_views'] for r in item['daily'])
    series.sort(key=lambda s:(-s['total_views'],s['path']))
    days=[dict(day=series[0]['daily'][i]['day'],visitors=i%8,page_views=sum(s['daily'][i]['page_views'] for s in series)) for i in range(28)]
    fixture=dict(daily=days,pages=sorted(paths),top_pages=series,started='2026-10-01',start='2026-10-01',requested_start='2026-07-28',end='2026-10-28')
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,ignore_default_args=['--hide-scrollbars'])
        for width in (1440,375,320,430):
            context=browser.new_context(viewport={'width':width,'height':667 if width==375 else 900})
            page=context.new_page()
            settings={'limit':8, 'browser_width':False}
            def api(route):
                path=route.request.url.split('/api')[-1]
                if path=='/me': data={'user':{'is_owner':True,'email':'owner@example.com'},'csrf_token':'fixture'}
                elif path=='/admin/preferences':
                    if route.request.method == 'PUT':
                        assert route.request.headers['x-csrf-token'] == 'fixture'
                        settings['browser_width'] = json.loads(route.request.post_data)['browser_width']
                    data = {'browser_width':settings['browser_width']}
                elif path=='/admin/analytics/preferences':
                    assert route.request.headers['x-csrf-token']=='fixture'
                    settings['limit']=json.loads(route.request.post_data)['top_pages_limit']
                    data={'top_pages_limit':settings['limit']}
                elif path.startswith('/admin/analytics'): data={**fixture,'top_pages':fixture['top_pages'][:settings['limit']],'top_pages_limit':settings['limit']}
                elif path.startswith('/admin/generator/pricing'):
                    from portal_api.generator_pricing import read_prices
                    data=read_prices()
                elif path=='/admin/generator':
                    from portal_api.generator import DEFAULTS
                    data={'config':DEFAULTS,'revision':0,'configured':False,'jobs':[]}
                elif path=='/analytics/collect': data={'collection_status':'ready','counted':False}
                elif path=='/auth/logout': data={'ok':True}
                elif path=='/auth/config': data={'client_id':'fixture','nonce':'fixture','csrf_token':'fixture'}
                else: data={}
                route.fulfill(status=200,content_type='application/json',body=json.dumps(data))
            page.route('**/api/**',api)
            page.route('https://accounts.google.com/**',lambda r:r.abort())
            page.goto(url+'/admin.html');page.locator('#admin-results').wait_for(state='visible')
            page.evaluate('document.fonts.ready')
            toggle = page.locator('#admin-width')
            standard_width = page.locator('.admin-page').bounding_box()['width']
            toggle.click()
            page.wait_for_function("document.getElementById('admin-width').getAttribute('aria-pressed') === 'true'")
            assert page.locator('.admin-page').bounding_box()['width'] >= standard_width
            assert abs(page.locator('.admin-page').bounding_box()['width'] - (page.evaluate('document.documentElement.clientWidth') - 32)) < 2
            assert page.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth')
            page.screenshot(path=f'/tmp/nxflo-admin-browser-width-{width}.png',full_page=True)
            page.reload();page.locator('#admin-results').wait_for(state='visible')
            assert toggle.get_attribute('aria-pressed') == 'true'
            page.locator('#account-tab').click()
            assert toggle.get_attribute('aria-pressed') == 'true'
            page.locator('#analytics-tab').click()
            toggle.click()
            page.wait_for_function("document.getElementById('admin-width').getAttribute('aria-pressed') === 'false'")
            page.reload();page.locator('#admin-results').wait_for(state='visible')
            assert toggle.get_attribute('aria-pressed') == 'false'
            assert page.locator('.admin-metrics').count()==0
            assert page.locator('#views-chart g[data-page]').count()==8
            for chart_id in ('visitor-chart','views-chart'):
                axis_labels=page.locator('#'+chart_id+' svg text').all_text_contents()
                assert '10-01' in axis_labels and '10-28' in axis_labels, chart_id
                assert page.locator('#'+chart_id+' svg').bounding_box()['height']>=100
            assert abs(page.locator('#visitor-chart svg').bounding_box()['y']-page.locator('#views-chart svg').bounding_box()['y'])<2

            assert page.locator('#admin-page-legend li').count()==8
            assert page.locator('#admin-days').count()==0
            assert page.locator('#admin-top-pages').input_value()=='8'
            assert page.locator('#admin-today-views').inner_text()==str(days[-1]['page_views'])
            assert page.locator('.admin-charts svg').first.bounding_box()['height'] <= 155
            if width == 375:
                assert page.locator('.admin-page-trends').bounding_box()['y'] + page.locator('.admin-page-trends').bounding_box()['height'] < 667, 'Overview should fit a small mobile viewport'
            page.screenshot(path=f'/tmp/nxflo-analytics-compact-{width}.png',full_page=True)
            visitor_chart = page.locator('#visitor-chart')
            visitor_tip = visitor_chart.locator('.admin-chart-tooltip')
            visitor_chart.scroll_into_view_if_needed()
            visitor_box = visitor_chart.bounding_box()
            visitor_card = page.locator('.admin-visitor-trends').bounding_box()
            # Header/padding and empty chart areas also reveal visitor details.
            page.mouse.move(visitor_card['x']+visitor_card['width']/2, visitor_card['y']+2)
            assert visitor_tip.is_visible() and 'Daily visitors' in visitor_tip.inner_text()
            assert visitor_chart.locator('g.is-nearest').count() == 1
            page.mouse.move(visitor_box['x']+visitor_box['width']-1, visitor_box['y']+1)
            assert visitor_tip.is_visible() and 'visitors' in visitor_tip.inner_text()
            tip_box = visitor_tip.bounding_box()
            assert tip_box['x'] >= visitor_box['x'] and tip_box['x']+tip_box['width'] <= visitor_box['x']+visitor_box['width']+1
            # The first data point is Oct 1 with zero visitors, and touch uses the same lookup.
            visitor_chart.dispatch_event('pointerdown', {'clientX':visitor_box['x']+(28 if width<700 else 36), 'clientY':visitor_box['y']+visitor_box['height']-23, 'pointerType':'touch'})
            assert '2026-10-01 · 0 visitors' in visitor_tip.inner_text()
            assert page.evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth')
            page.screenshot(path=f'/tmp/nxflo-visitor-hover-{width}.png',full_page=True)
            visitor_chart.dispatch_event('pointercancel')
            assert visitor_tip.is_hidden()
            page.mouse.move(visitor_card['x']+visitor_card['width']/2, visitor_card['y']+2)
            page.mouse.move(0,0)
            assert visitor_tip.is_hidden() and visitor_chart.locator('g.is-nearest').count() == 0
            # Large empty areas still select the closest line; exact stroke hits are unnecessary.
            saved_series = fixture['top_pages']
            fixture['top_pages'] = [
                dict(path='/', total_views=56, daily=[dict(day=row['day'], page_views=2) for row in days]),
                dict(path='/about.html', total_views=392, daily=[dict(day=row['day'], page_views=14) for row in days]),
            ]
            page.locator('#admin-refresh').click();page.locator('#admin-results').wait_for(state='visible')
            chart = page.locator('#views-chart')
            chart.scroll_into_view_if_needed()
            box = chart.bounding_box()
            tooltip = chart.locator('.admin-chart-tooltip')
            page.mouse.move(box['x'] + box['width'] * .6, box['y'] + 1)
            assert tooltip.is_visible() and 'About' in tooltip.inner_text() and '14 views' in tooltip.inner_text()
            assert chart.locator('g.is-nearest').get_attribute('data-page') == '/about.html'
            card_box = page.locator('.admin-page-trends').bounding_box()
            page.mouse.move(card_box['x']+card_box['width']/2,card_box['y']+2)
            assert tooltip.is_visible() and 'About' in tooltip.inner_text()
            page.mouse.move(box['x'] + box['width'] - 1, box['y'] + box['height'] - 1)
            assert 'Home' in tooltip.inner_text() and '2 views' in tooltip.inner_text()
            tip_box = tooltip.bounding_box()
            assert tip_box['x'] >= box['x'] and tip_box['x'] + tip_box['width'] <= box['x'] + box['width'] + 1
            assert page.evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth')
            page.screenshot(path=f'/tmp/nxflo-chart-hover-{width}.png',full_page=True)
            page.mouse.move(0, 0)
            assert tooltip.is_hidden() and chart.locator('g.is-nearest').count() == 0
            # Touch can inspect the same empty chart area without disabling page scrolling.
            box = chart.bounding_box()
            chart.dispatch_event('pointerdown', {'clientX':box['x']+box['width']/2, 'clientY':box['y']+1, 'pointerType':'touch'})
            assert 'About' in tooltip.inner_text() and tooltip.is_visible(), (width, tooltip.inner_text(), box)
            chart.dispatch_event('pointercancel')
            assert tooltip.is_hidden()
            # Between widely spaced data points, choose the nearest line segment.
            fixture['top_pages'] = [
                dict(path='/',total_views=16,daily=[dict(day=days[0]['day'],page_views=0),dict(day=days[1]['day'],page_views=16)]),
                dict(path='/about.html',total_views=20,daily=[dict(day=days[0]['day'],page_views=10),dict(day=days[1]['day'],page_views=10)]),
            ]
            saved_days = fixture['daily'];fixture['daily'] = days[:2]
            page.locator('#admin-refresh').click();page.locator('#admin-results').wait_for(state='visible')
            box = chart.bounding_box()
            left = 28 if width < 700 else 36
            px = left + (box['width']-left-8)*.4
            py = box['height']-23 - 7.4/16*(box['height']-9-23)
            page.mouse.move(box['x']+px, box['y']+py)
            assert 'Home' in tooltip.inner_text() and '0 views' in tooltip.inner_text()
            fixture['daily'] = saved_days;fixture['top_pages'] = saved_series
            page.locator('#admin-refresh').click();page.locator('#admin-results').wait_for(state='visible')
            if width == 375:
                original = fixture['daily']
                original_series = fixture['top_pages']
                fixture['top_pages'] = []
                fixture['daily'] = [{**row, 'visitors':0, 'page_views':0} for row in original]
                page.locator('#admin-refresh').click()
                page.locator('#admin-results').wait_for(state='visible')
                assert page.locator('.admin-page-trends').bounding_box()['y'] + page.locator('.admin-page-trends').bounding_box()['height'] < 667
                assert 'No visits yet' in page.locator('#admin-coverage').inner_text()
                chart.dispatch_event('pointermove', {'clientX':100, 'clientY':100})
                assert chart.locator('.admin-chart-tooltip').is_hidden()
                visitor_chart.dispatch_event('pointermove', {'clientX':100,'clientY':100})
                assert visitor_tip.is_visible() and '0 visitors' in visitor_tip.inner_text()
                fixture['daily'] = original
                fixture['top_pages'] = original_series
                page.locator('#admin-refresh').click()
                page.locator('#admin-results').wait_for(state='visible')
            if width==375:
                saved_fixture=dict(fixture)
                fixture.update(start='2026-10-28',started='2026-10-28',daily=[days[-1]],top_pages=[{**s,'daily':[s['daily'][-1]],'total_views':s['daily'][-1]['page_views']} for s in series])
                page.locator('#admin-refresh').click();page.locator('#admin-results').wait_for(state='visible')
                page.locator('.admin-daily-details summary').click()
                assert page.locator('#admin-daily tr').count()==1
                chart.scroll_into_view_if_needed();box=chart.bounding_box()
                page.mouse.move(box['x']+box['width']-1,box['y']+1)
                assert chart.locator('.admin-chart-tooltip').is_visible()
                assert '2026-10-28' in chart.locator('.admin-chart-tooltip').inner_text()
                visitor_chart.dispatch_event('pointerdown', {'clientX':100,'clientY':100,'pointerType':'touch'})
                assert visitor_tip.is_visible() and '2026-10-28 · 3 visitors' in visitor_tip.inner_text()
                page.mouse.move(0,0)
                assert 'Unavailable' not in page.locator('#admin-daily').inner_text()
                assert '10-01' not in page.locator('#views-chart').inner_text()
                assert page.locator('#views-chart svg text').all_text_contents().count('10-28')==1
                assert page.locator('#visitor-chart svg text').all_text_contents().count('10-28')==1
                assert '10-01' not in page.locator('#visitor-chart').inner_text()
                assert page.locator('#admin-daily-head abbr').first.inner_text()=='#1'
                assert max(page.locator('#admin-daily-head th').evaluate_all('cells=>cells.map(c=>c.getBoundingClientRect().width)'))<110
                page.screenshot(path='/tmp/nxflo-single-day-table-375.png',full_page=True)
                page.locator('.admin-daily-details summary').click()
                fixture.clear();fixture.update(saved_fixture)
                page.locator('#admin-refresh').click();page.locator('#admin-results').wait_for(state='visible')
            assert page.evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth'),width
            page.locator('.admin-method summary').click()
            page.locator('#admin-check-tracking').click()
            page.wait_for_function("document.getElementById('admin-tracking-status').textContent.includes('reachable')")
            if width == 375:
                page.evaluate("Object.defineProperty(navigator,'globalPrivacyControl',{value:true,configurable:true})")
                page.locator('#admin-check-tracking').click()
                assert 'Global Privacy Control' in page.locator('#admin-tracking-status').inner_text()
                page.evaluate("Object.defineProperty(navigator,'globalPrivacyControl',{value:false,configurable:true})")
                page.route('**/api/analytics/collect',lambda route:route.abort())
                page.locator('#admin-check-tracking').click()
                page.wait_for_function("document.getElementById('admin-tracking-status').textContent.includes('failed or was blocked')")
                page.unroute('**/api/analytics/collect')
                assert page.evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth')
            page.locator('.admin-method summary').click()
            page.locator('#admin-period').select_option('6')
            page.locator('#admin-results').wait_for(state='visible')
            page.locator('#admin-top-pages').select_option('5')
            page.locator('#admin-top-pages').wait_for(state='visible')
            page.wait_for_function("!document.getElementById('admin-top-pages').disabled")
            assert page.locator('#views-chart g[data-page]').count()==5
            page.reload();page.locator('#admin-results').wait_for(state='visible')
            assert page.locator('#admin-top-pages').input_value()=='5'
            assert page.locator('#views-chart g[data-page]').count()==5
            page.locator('.admin-daily-details summary').click();assert page.locator('#admin-daily tr').count()==28
            with page.expect_download() as download: page.locator('#admin-export').click()
            assert download.value.suggested_filename.endswith('.csv')
            import csv
            with open(download.value.path()) as exported:
                rows=list(csv.reader(exported))
            assert len(rows[0])==8 and rows[0][3:]==[s['path'] for s in series[:5]]
            assert len(rows)==29
            assert page.evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth')
            page.locator('#account-tab').click();assert page.locator('#account-panel').is_visible()
            page.locator('#account-tab').press('ArrowLeft');assert page.locator('#generator-panel').is_visible()
            page.locator('#generator-tab').press('ArrowLeft');assert page.locator('#analytics-panel').is_visible()
            if width<700:
                page.locator('.nav-tools-toggle').click()
                assert page.locator('#tools-menu').is_visible()
                page.locator('.nav-tools-toggle').click()
            page.screenshot(path=f'/tmp/nxflo-admin-{width}.png',full_page=True)
            # Expired or unauthenticated sessions reveal only the login shell.
            signed_in = False
            def login_api(route):
                nonlocal signed_in
                path = route.request.url.split('/api')[-1]
                if path == '/auth/google':
                    signed_in = True
                    return route.fulfill(status=200, content_type='application/json', body='{"ok":true}')
                if path == '/auth/logout':
                    signed_in = False
                    return route.fulfill(status=200, content_type='application/json', body='{"ok":true}')
                if path == '/auth/config' or signed_in:
                    return api(route)
                route.fulfill(status=401,content_type='application/json',body='{"error":"Please sign in"}')
            page.unroute('**/api/**');page.route('**/api/**',login_api)
            # Isolate Google UI in tests; real identity verification is covered by API tests.
            page.unroute('https://accounts.google.com/**')
            page.route('https://accounts.google.com/**', lambda route: route.fulfill(content_type='application/javascript', body="""
                window.google={accounts:{id:{initialize(options){this.options=options;},
                renderButton(element){const button=document.createElement('button');
                button.textContent='Continue with Google';button.style.cssText='min-height:44px;width:100%;border:1px solid #dadce0;border-radius:24px;background:white;cursor:pointer';
                button.onclick=()=>this.options.callback({credential:'fixture'});element.replaceChildren(button);},
                prompt(){},disableAutoSelect(){}}}};
            """))
            page.reload();page.locator('#admin-login').wait_for(state='visible')
            assert page.locator('#admin-workspace').is_hidden()
            assert page.locator('.admin-page').evaluate("e=>e.classList.contains('is-login')")
            assert page.locator('.admin-heading').is_hidden()
            assert page.locator('.admin-login-art img').evaluate('e=>e.complete && e.naturalWidth>0')
            page.locator('#admin-google button').wait_for(state='visible')
            page.screenshot(path=f'/tmp/nxflo-login-{width}.png',full_page=True)
            page.locator('#admin-google button').click()
            page.locator('#admin-results').wait_for(state='visible')
            assert not page.locator('.admin-page').evaluate("e=>e.classList.contains('is-login')")
            page.locator('#admin-logout').click()
            page.locator('#admin-login').wait_for(state='visible')
            assert page.locator('#admin-workspace').is_hidden()
            assert page.evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth'),width
            context.close()
        browser.close()
    print('Admin browser checks passed at 1440, 375, 320, and 430px.')

if __name__=='__main__':
    import sys
    check(sys.argv[1] if len(sys.argv)>1 else 'http://127.0.0.1:8765')
