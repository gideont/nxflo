"""Check article discovery, responsive layout, chart assets, and original PDF download."""
import argparse
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
PAGE = 'etl-dashboard-process-playbook.html'
PDF = 'articles/Nexusflow_ETL_Dashboard_Process_Playbook.pdf'


def check(base):
    base = base.rstrip('/')
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, ignore_default_args=['--hide-scrollbars'])
        page = browser.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        for width in (1440, 375, 320, 430):
            page.set_viewport_size({'width': width, 'height': 1000})
            page.goto(base + '/articles.html', wait_until='networkidle')
            assert 'Featured article' in page.locator('.article-hero .eyebrow').text_content()
            assert page.locator('h1').inner_text() == 'Stale by Thursday'
            page.locator('.article-library-card h3 a').click()
            assert page.url.endswith('/' + PAGE)
            assert page.locator('h1').inner_text() == 'ETL and Dashboard Process Playbook'
            assert page.locator('.site-nav [aria-current="page"]').get_attribute('href') == 'articles.html'
            for image in page.locator('main img').all():
                image.scroll_into_view_if_needed()
                image.evaluate('e => e.decode()')
                assert image.evaluate('e => e.naturalWidth > 0')
                assert image.get_attribute('alt')
            assert page.locator('.article-chart').count() == 2
            for link in page.locator('.article-chart a').all():
                assert page.request.get(base + '/' + link.get_attribute('href')).ok
            for link in page.locator('a[download]').all():
                assert link.get_attribute('href') == PDF
                assert link.bounding_box()['height'] >= 44
            assert page.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth')
            page.locator('.nav-tools-toggle').click()
            assert page.locator('#tools-menu').is_visible()
            page.mouse.move(0, 0)
            page.keyboard.press('Escape')
            assert page.locator('#tools-menu').is_hidden()
            if width in (1440, 375):
                page.screenshot(path=f'/tmp/etl-qa/playbook-{width}.png', full_page=True)
            print(f'{width}px: discovery, images, chart links, menu, tap targets and no overflow passed', flush=True)
        with page.expect_download() as event:
            page.locator('a[download]').first.click()
        download = event.value
        assert Path(download.path()).read_bytes() == (ROOT / PDF).read_bytes()
        assert download.suggested_filename == Path(PDF).name
        response = page.request.get(base + '/' + PDF)
        assert response.headers['content-type'].startswith('application/pdf')
        assert response.body() == (ROOT / PDF).read_bytes()
        sitemap = page.request.get(base + '/sitemap.xml').text()
        assert 'https://www.nxflo.com/' + PAGE in sitemap
        assert not errors, errors
        print('Original PDF download, sitemap, and browser error checks passed')
        browser.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8013')
    check(parser.parse_args().url)
