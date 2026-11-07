"""Verify article publication details, responsive previews, and the PDF download."""
import argparse
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
PDF = 'articles/Nexusflow_Stale_by_Thursday_Report.pdf'


def check(url, screenshots):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, ignore_default_args=['--hide-scrollbars'])
        page = browser.new_page()
        for width in (1440, 375, 320, 430):
            page.set_viewport_size({'width': width, 'height': 1000})
            page.goto(url.rstrip('/') + '/articles.html', wait_until='networkidle')
            page.evaluate('document.fonts.ready')
            assert page.locator('h1').inner_text() == 'Stale by Thursday'
            assert page.locator('time').get_attribute('datetime') == '2026-11-01'
            assert page.locator('time').inner_text() == 'November 1, 2026'
            assert page.locator('.site-nav [aria-current="page"]').get_attribute('href') == 'articles.html'
            assert page.locator('.site-nav a[href="about.html"]').count() == 0
            assert page.locator('.article-summary').is_visible()
            assert page.locator('.article-chart').count() == 2
            for image in page.locator('.articles-main img').all():
                image.scroll_into_view_if_needed()
                image.evaluate('e => e.decode()')
                assert image.evaluate('e => e.naturalWidth > 0')
                assert image.get_attribute('alt')
                assert image.bounding_box()['width'] <= width
            for link in page.locator('.article-chart a').all():
                assert page.request.get(url.rstrip('/') + '/' + link.get_attribute('href')).ok
            reporting = page.locator('#reporting-time-chart')
            reporting_tip = reporting.locator('.reporting-time-tooltip')
            assert reporting.locator('img').count() == 0
            rows = reporting.locator('.reporting-time-row')
            expected_values = ['More than 9 hours/week', 'Up to 8 hours/week', 'About 3 hours/week', 'About 1.5 hours/week']
            for index, value in enumerate(expected_values):
                row = rows.nth(index)
                assert row.bounding_box()['height'] >= 44
                track_width = row.locator('.reporting-time-track').bounding_box()['width']
                bar_width = row.locator('.reporting-time-bar').bounding_box()['width']
                assert abs(bar_width / track_width - [0.9, 0.8, 0.3, 0.15][index]) < 0.01
                row.hover()
                assert reporting_tip.is_visible()
                assert reporting_tip.locator('span').first.inner_text() == value
                assert reporting_tip.locator('strong').inner_text() == row.get_attribute('data-source')
                assert reporting_tip.locator('.reporting-time-detail').inner_text() == row.get_attribute('data-detail')
                bounds = reporting_tip.bounding_box()
                assert bounds['x'] >= 0 and bounds['x'] + bounds['width'] <= width
            rows.first.focus()
            assert 'More than 9' in reporting_tip.inner_text()
            page.keyboard.press('ArrowDown')
            assert 'Up to 8' in reporting_tip.inner_text()
            page.keyboard.press('End')
            assert 'About 1.5' in reporting_tip.inner_text()
            page.keyboard.press('Escape')
            assert reporting_tip.is_hidden()
            page.mouse.move(0, 0)
            assert reporting_tip.is_hidden()
            if screenshots and width in (1440, 375):
                Path(screenshots).mkdir(parents=True, exist_ok=True)
                reporting.scroll_into_view_if_needed()
                rows.first.hover()
                page.screenshot(path=f'{screenshots}/reporting-time-hover-{width}.png')
                page.mouse.move(0, 0)
            chart = page.locator('#payback-chart')
            tip = chart.locator('.payback-tooltip')
            chart.scroll_into_view_if_needed()
            box = chart.bounding_box()
            for cost, weeks in ((1500, 6), (3000, 12), (6000, 24)):
                x = (77.5 + 83.6 * 5) / 1008 * box['width']
                y = (401 - 9.725 * weeks) / 480 * box['height']
                page.mouse.move(box['x'] + x, box['y'] + y)
                assert tip.is_visible()
                assert tip.locator('strong').inner_text() == f'Build cost ${cost:,}'
                assert tip.locator('span').inner_text() == f'5.0 hours saved/week · {weeks:.1f} weeks to pay back'
                bounds = tip.bounding_box()
                assert bounds['x'] >= box['x'] - 1
                assert bounds['x'] + bounds['width'] <= box['x'] + box['width'] + 1
            chart.focus()
            page.keyboard.press('ArrowDown')
            assert '3,000' in tip.inner_text()
            page.keyboard.press('ArrowRight')
            assert '5.5 hours saved/week' in tip.inner_text()
            assert '10.9 weeks to pay back' in tip.inner_text()
            page.keyboard.press('Escape')
            assert tip.is_hidden()
            page.mouse.move(0, 0)
            assert page.locator('main > article a[download]').count() == 1
            assert page.locator('main > article .article-download').count() == 0
            assert 'Read the complete report' not in page.locator('main').inner_text()
            for link in page.locator('main > article a[download]').all():
                assert link.get_attribute('href') == PDF
                assert link.bounding_box()['height'] >= 44
            assert page.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth')
            page.locator('.nav-tools-toggle').click()
            assert page.locator('#tools-menu').is_visible()
            page.mouse.move(0, 0)
            page.keyboard.press('Escape')
            assert page.locator('#tools-menu').is_hidden()
            if screenshots and width in (1440, 375):
                Path(screenshots).mkdir(parents=True, exist_ok=True)
                page.evaluate("window.scrollTo({top:0,behavior:'instant'})")
                page.screenshot(path=f'{screenshots}/articles-{width}.png', full_page=True)
            print(f'{width}px: article summary, publication date, charts, navigation and no overflow passed', flush=True)
        with page.expect_download() as download_info:
            page.locator('main > article a[download]').first.click()
        download = download_info.value
        assert download.suggested_filename == Path(PDF).name
        assert Path(download.path()).read_bytes() == (ROOT / PDF).read_bytes()
        response = page.request.get(url.rstrip('/') + '/' + PDF)
        assert response.ok and response.headers['content-type'].startswith('application/pdf')
        assert response.body() == (ROOT / PDF).read_bytes()
        touch = browser.new_context(has_touch=True, is_mobile=True, viewport={'width': 375, 'height': 900})
        mobile = touch.new_page()
        mobile.goto(url.rstrip('/') + '/articles.html', wait_until='networkidle')
        reporting = mobile.locator('#reporting-time-chart')
        for index, value in enumerate(['More than 9', 'Up to 8', 'About 3', 'About 1.5']):
            reporting.locator('.reporting-time-row').nth(index).tap()
            assert value in reporting.locator('.reporting-time-tooltip').inner_text()
            assert reporting.locator('.reporting-time-tooltip').is_visible()
            assert mobile.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth')
        if screenshots:
            mobile.screenshot(path=f'{screenshots}/reporting-time-touch-375.png')
        mobile.locator('h1').tap()
        assert reporting.locator('.reporting-time-tooltip').is_hidden()
        chart = mobile.locator('#payback-chart')
        chart.scroll_into_view_if_needed()
        box = chart.bounding_box()
        mobile.touchscreen.tap(box['x'] + (77.5 + 83.6 * 5) / 1008 * box['width'], box['y'] + (401 - 9.725 * 12) / 480 * box['height'])
        assert chart.locator('.payback-tooltip').is_visible()
        assert '3,000' in chart.locator('.payback-tooltip').inner_text()
        assert '12.0 weeks to pay back' in chart.locator('.payback-tooltip').inner_text()
        assert mobile.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth')
        if screenshots:
            mobile.screenshot(path=f'{screenshots}/payback-touch-375.png')
        mobile.locator('h1').tap()
        assert chart.locator('.payback-tooltip').is_hidden()
        touch.close()
        browser.close()
        print('Nearest-line values, keyboard controls, tooltip bounds, and mobile tap/dismiss passed', flush=True)
        print('PDF download returns the complete original document', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8013')
    parser.add_argument('--screenshots')
    args = parser.parse_args()
    check(args.url, args.screenshots)
