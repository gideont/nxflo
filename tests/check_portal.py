"""Verify the deployed anonymous login, API boundaries, and responsive layout."""
import argparse
from pathlib import Path


def check(url, executable, screenshots):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        options={'headless':True,'ignore_default_args':['--hide-scrollbars']}
        if executable: options['executable_path']=executable
        browser=p.chromium.launch(**options)
        page=browser.new_page()
        errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        if screenshots: Path(screenshots).mkdir(parents=True,exist_ok=True)
        for width,height in ((1440,900),(375,667),(320,568),(430,932)):
            page.set_viewport_size({'width':width,'height':height})
            response=page.goto(url.rstrip('/')+'/bms_integration_hub',wait_until='networkidle')
            assert response.status==200
            assert 'noindex' in response.headers.get('x-robots-tag','')
            assert 'noindex' in page.locator('meta[name=robots]').get_attribute('content')
            assert page.locator('#login-shell').is_visible()
            assert not page.locator('#workspace').is_visible()
            assert page.locator('#login-shell h1').count()==1
            assert page.locator('a').evaluate_all("els=>els.every(e=>e.getAttribute('href').startsWith('#'))")
            assert page.evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth'),width
            assert page.locator('.login-shell').evaluate("e=>getComputedStyle(e).gridTemplateColumns.split(' ').length")== (2 if width>760 else 1)
            # The official GIS SDK owns the Google button; no custom credential form is used.
            page.wait_for_function("document.querySelector('#google-sign-in iframe') !== null",timeout=30000)
            page.frame_locator('#google-sign-in iframe').get_by_text('Sign in with Google',exact=True).first.wait_for(state='visible',timeout=30000)
            assert not page.locator('#login-error').is_visible(),page.locator('#login-error').inner_text()
            page.locator('.access-help summary').click()
            assert page.locator('.access-help p').is_visible()
            page.locator('.access-help summary').click()
            for path in ('me','projects','workspace','admin/users','admin/roles','admin/audit'):
                assert page.evaluate("path=>fetch('/bms_integration_hub/api/'+path).then(r=>r.status)",path)==401,path
            if screenshots and width in (1440,375):
                page.evaluate('document.activeElement.blur();window.scrollTo(0,0)')
                page.screenshot(path=f'{screenshots}/portal-{width}.png',full_page=True)
            print(f'{width}px: official Google button, standalone login, no overflow, and anonymous API protection passed',flush=True)
        assert not errors,errors
        browser.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',default='http://127.0.0.1:9001')
    parser.add_argument('--browser-executable')
    parser.add_argument('--screenshots')
    args=parser.parse_args()
    check(args.url,args.browser_executable,args.screenshots)
