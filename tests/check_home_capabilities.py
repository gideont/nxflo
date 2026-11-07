"""Verify the editorial homepage showcase, visible service content, and responsive layout."""
import argparse
from pathlib import Path
from playwright.sync_api import sync_playwright

TITLES = ['Data Engineering & Architecture','Systems & Industrial Integration','Analytics & Intelligence','Automation & Applications']
LINKS = ['etl-data-pipelines.html','databricks-consulting.html','bms-data-integration.html','entra-id-integration.html','power-bi-consulting.html']
# Coverage from the nine original descriptions: transfers, scale, architecture,
# systems, industrial data, dashboards, AI, recurring reporting, workflow tools.
TERMS = ['ETL — Extract, Transform, Load','scheduled transfers','periodic backups','pandas','legacy data jobs',
         'Apache Spark','Databricks','multiple machines','data lakes','lakehouse','ETL or ELT','storage',
         'business applications, APIs, files, and scripts','validating','manual handoffs','industrial and IoT',
         'Modbus, OPC UA, MQTT, and SNMP','Kafka','monitoring','data quality','refresh pipelines','Power BI',
         'analytics and AI','trends','anomaly detection','near-real-time','earlier action',
         'CSV exports','spreadsheet cleanup','automated data collection','report refreshes','recurring reporting',
         'copy information by hand','automations, internal tools, and workflow integrations']


def check(url, executable, screenshots):
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=executable,headless=True,ignore_default_args=['--hide-scrollbars'])
        page=browser.new_page();errors=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        for width in (1440,1920,1024,768,430,375,320):
            page.set_viewport_size({'width':width,'height':1000})
            page.goto(url.rstrip('/')+'/',wait_until='networkidle');page.evaluate('document.fonts.ready')
            section=page.locator('#examples')
            assert section.locator('article').count()==4
            assert section.locator('h3').evaluate_all("els=>els.map(e=>e.innerText.replace(/\\s+/g,' ').trim())")==TITLES
            assert section.locator('details,summary,button').count()==0
            copy=section.inner_text()
            assert all(term in copy for term in TERMS),[term for term in TERMS if term not in copy]
            assert section.locator('a').evaluate_all("els=>els.map(e=>e.getAttribute('href'))")==LINKS
            assert page.evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth'),width
            assert page.locator('.site-header').evaluate('e=>getComputedStyle(e).position')=='static'
            for article in section.locator('article').all():
                assert article.is_visible()
                assert article.locator('.capability-description').is_visible()
                assert article.evaluate("e=>e.scrollWidth<=e.clientWidth"),width
                assert article.evaluate("e=>getComputedStyle(e).borderRadius")=='0px'
            for image in section.locator('img').all():
                image.scroll_into_view_if_needed();image.evaluate("e=>e.loading='eager'")
                image.evaluate('e=>e.decode()')
                assert image.evaluate('e=>e.naturalWidth>0')
                assert image.get_attribute('alt')
            assert page.locator('.site-nav > a').count()==4
            assert section.locator('a').evaluate_all('els=>els.every(e=>e.getBoundingClientRect().height>=44)')
            if screenshots and width in (1440,375):
                Path(screenshots).mkdir(parents=True,exist_ok=True)
                page.evaluate("window.scrollTo({top:document.getElementById('examples').offsetTop,behavior:'instant'})")
                page.screenshot(path=f'{screenshots}/capabilities-{width}.png')
                section.screenshot(path=f'{screenshots}/capabilities-full-{width}.png')
            print(f'{width}px: four visible capabilities, original topic coverage, service links, images and no overflow passed',flush=True)
        page.set_viewport_size({'width':1440,'height':1000})
        page.goto(url.rstrip('/')+'/',wait_until='networkidle')
        for href in LINKS:
            link=page.locator(f'#examples a[href="{href}"]');link.focus()
            assert link.evaluate('e=>getComputedStyle(e).outlineStyle')!='none'
            assert page.request.get(url.rstrip('/')+'/'+href).status==200
        context=browser.new_context(java_script_enabled=False,viewport={'width':375,'height':900})
        fallback=context.new_page();fallback.goto(url.rstrip('/')+'/',wait_until='networkidle')
        assert all(term in fallback.locator('#examples').inner_text() for term in TERMS)
        assert fallback.locator('#examples article').count()==4
        assert not errors,errors
        browser.close();print('Keyboard links and complete content without JavaScript passed',flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--url',default='http://127.0.0.1:8013');parser.add_argument('--browser-executable',required=True);parser.add_argument('--screenshots');args=parser.parse_args();check(args.url,args.browser_executable,args.screenshots)
