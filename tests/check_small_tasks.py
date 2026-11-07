"""Homepage small-task list and original outsourcing examples: content, links and responsive UI."""
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
PAGE='what-can-we-help-you-with.html'
CATEGORIES=['Reporting & Dashboards','Data Extraction & Integration','Automation & Internal Tools','Data Engineering & Architecture','Industrial & IoT Integration']
QUESTIONS=['Tired of preparing the same Excel report every week?','Need to transfer data between two systems?',"Your Power BI dashboard isn't updating?",'Need data extracted from an API or database?','Have a repetitive manual process?','Need help connecting industrial equipment?']
ANSWERS=['We can automate it.',"We'll build the integration.",'Let us investigate and fix it.','We can write the scripts and pipelines.',"Let's see if we can automate it.",'We work with BMS, MQTT, OPC UA and other protocols.']


def check(url,executable,screenshots):
    fixtures=json.loads((ROOT/'tests/fixtures/original-task-examples.json').read_text())
    normalize=lambda value:' '.join(value.split())
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,executable_path=executable,ignore_default_args=['--hide-scrollbars'])
        page=browser.new_page();errors=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        for width in (1440,1920,1024,768,430,375,320):
            page.set_viewport_size({'width':width,'height':1000})
            for route in ('',PAGE,'services.html'):
                response=page.goto(url.rstrip('/')+'/'+route,wait_until='networkidle');assert response.status==200
                page.evaluate('document.fonts.ready')
                assert page.evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth'),(width,route)
                assert page.locator('.site-header').evaluate('e=>getComputedStyle(e).position')=='static'
                assert page.evaluate("[...document.querySelectorAll('body *')].every(e=>!(['auto','scroll'].includes(getComputedStyle(e).overflowY)&&e.clientHeight>0&&e.scrollHeight>e.clientHeight))")
                assert page.locator('.site-header').count()==1 and page.locator('.site-footer').count()==1
                if route=='':
                    assert page.locator('#examples .capability').count()==4
                    section=page.locator('.small-tasks')
                    assert section.locator('li').count()==6
                    assert section.locator('li h3').all_text_contents()==QUESTIONS
                    assert section.locator('li p').all_text_contents()==ANSWERS
                    assert section.locator('details,summary,button').count()==0
                    assert section.locator('a').evaluate_all('els=>els.every(e=>e.getBoundingClientRect().height>=44)')
                    assert page.locator('#examples').evaluate("e=>e.compareDocumentPosition(document.querySelector('.small-tasks'))&Node.DOCUMENT_POSITION_FOLLOWING")
                    assert section.get_by_role('link',name='Explore More Examples').get_attribute('href')==PAGE
                    assert section.get_by_role('link',name='Discuss a Task').get_attribute('href')=='contact.html'
                    if screenshots and width in (1440,375):
                        Path(screenshots).mkdir(parents=True,exist_ok=True);section.screenshot(path=f'{screenshots}/small-tasks-{width}.png')
                elif route==PAGE:
                    assert page.locator('h1').inner_text()=='What Can We Help You With?'
                    assert page.locator('.outsourcing-category h2').all_text_contents()==CATEGORIES
                    assert page.locator('[data-original-example]').count()==9
                    assert page.locator('details,summary').count()==0
                    assert page.locator('.site-nav a[aria-current=page]').get_attribute('href')=='services.html'
                    for item in fixtures:
                        article=page.locator(f'[data-original-example="{item["id"]}"]')
                        assert normalize(article.locator('h3').inner_text())==item['question']
                        copy=normalize(article.inner_text())
                        assert all(text in copy for text in item['explanations']),item['id']
                        assert article.locator('a').evaluate_all('els=>els.map(e=>e.getAttribute("href"))')==item['links']
                    for link in page.locator('.outsourcing-jump-links a').all():
                        assert page.locator(link.get_attribute('href')).count()==1
                    if screenshots and width in (1440,375):
                        page.evaluate("window.scrollTo({top:0,behavior:'instant'})");page.screenshot(path=f'{screenshots}/examples-{width}.png')
                else:
                    assert page.get_by_role('link',name='Explore practical tasks and outsourcing examples').get_attribute('href')==PAGE
            print(f'{width}px: six tasks, nine preserved explanations, category links, shared navigation and no overflow passed',flush=True)
        page.goto(url.rstrip('/')+'/',wait_until='networkidle')
        page.get_by_role('link',name='Explore More Examples').click();assert page.url.endswith('/'+PAGE)
        page.locator('.outsourcing-jump-links a').last.click()
        assert page.url.endswith('#industrial-iot-integration')
        page.keyboard.press('Tab');page.locator('.outsourcing-category a').first.focus();assert page.evaluate('getComputedStyle(document.activeElement).outlineStyle')!='none'
        for href in {href for item in fixtures for href in item['links']}|{'contact.html',PAGE}:
            assert page.request.get(url.rstrip('/')+'/'+href).status==200,href
        context=browser.new_context(java_script_enabled=False,viewport={'width':375,'height':900})
        fallback=context.new_page();fallback.goto(url.rstrip('/')+'/'+PAGE,wait_until='networkidle')
        assert fallback.locator('[data-original-example]').count()==9
        assert all(item['question'] in normalize(fallback.locator('main').inner_text()) for item in fixtures)
        assert not errors,errors
        browser.close();print('CTA journey, category anchors, keyboard focus, service URLs and no-JavaScript content passed',flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--url');parser.add_argument('--browser-executable',required=True);parser.add_argument('--screenshots');args=parser.parse_args()
    if args.url:
        check(args.url,args.browser_executable,args.screenshots)
    else:
        from functools import partial
        from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
        import threading
        class Quiet(SimpleHTTPRequestHandler):
            def log_message(self,*args):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),partial(Quiet,directory=str(ROOT/'dist')))
        threading.Thread(target=server.serve_forever,daemon=True).start()
        try:check(f'http://127.0.0.1:{server.server_port}',args.browser_executable,args.screenshots)
        finally:server.shutdown();server.server_close()
