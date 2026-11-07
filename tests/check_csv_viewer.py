"""Real browser coverage for Nexusflow's Apps menu and CSV/Excel integration."""
import argparse
from pathlib import Path
from playwright.sync_api import sync_playwright, expect


def check(url):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, ignore_default_args=['--hide-scrollbars'])
        page = browser.new_page(ignore_https_errors=True)
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        for width in (1440, 375, 320, 430):
            page.set_viewport_size({'width': width, 'height': 900})
            page.goto(url.rstrip('/') + '/csv-viewer.html', wait_until='networkidle')
            expect(page.get_by_text('Drop a CSV or Excel file here')).to_be_visible()
            toggle = page.get_by_role('button', name='Show apps menu')
            if width == 1440:
                toggle.hover()
            else:
                toggle.click()
            expect(page.get_by_text('Free Apps & Utilities')).to_be_visible()
            expect(page.locator('#tools-menu a')).to_have_text(['PDF Merge', 'CSV Viewer'])
            assert page.locator('#tools-menu').bounding_box()['x'] >= 0
            page.keyboard.press('Escape')
            expect(toggle).to_have_attribute('aria-expanded', 'false')
            toggle.focus()
            page.keyboard.press('ArrowDown')
            expect(page.locator('#tools-menu a').first).to_be_focused()
            page.keyboard.press('Escape')
            requests = []
            page.on('request', lambda request: requests.append(request.url))
            data = 'Name,Amount,Notes\r\nItem 10,10,"hello, world"\r\nItem 2,2,"line one\nline two"\r\n'
            data += '\r\n'.join(f'Item {i},{i},<script>alert(1)</script>' for i in range(120))
            page.locator('input[type=file]').set_input_files({'name':'sample.csv','mimeType':'text/csv','buffer':data.encode()})
            expect(page.get_by_text('122 rows, 3 columns', exact=True)).to_be_visible()
            headers = page.get_by_role('columnheader')
            expect(headers).to_have_count(3)
            headers.nth(1).click()
            expect(headers.nth(1)).to_have_attribute('aria-sort', 'ascending')
            expect(page.get_by_role('cell').nth(1)).to_have_text('0')
            headers.nth(1).click()
            expect(page.get_by_role('cell').nth(1)).to_have_text('119')
            page.get_by_label('Rows per page', exact=True).select_option('25')
            expect(page.get_by_text('Page 1 of 5', exact=True)).to_be_visible()
            page.get_by_role('button', name='Next page', exact=True).click()
            expect(page.get_by_text('Page 2 of 5', exact=True)).to_be_visible()
            # Expanding the frame preserves the current file, sort and page.
            frame = page.locator('#csv-data-panel')
            original_width = frame.bounding_box()['width']
            header_box = page.locator('.site-header').bounding_box()
            page.get_by_role('button', name='Expand table', exact=True).click()
            expanded = page.get_by_role('button', name='Restore table size', exact=True)
            expect(expanded).to_have_attribute('aria-pressed', 'true')
            expect(page.locator('#csv-viewer aside')).to_be_hidden()
            expect(page.get_by_text('Page 2 of 5', exact=True)).to_be_visible()
            expect(headers.nth(1)).to_have_attribute('aria-sort', 'descending')
            assert frame.bounding_box()['width'] > original_width
            assert abs(frame.bounding_box()['width'] - page.evaluate('document.documentElement.clientWidth')) < 1
            expect(page.locator('.site-header')).to_be_hidden()
            expect(page.locator('.csv-page-container')).to_be_hidden()
            expect(page.locator('.site-footer')).to_be_hidden()
            assert page.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth')
            viewport = page.locator('.csv-viewport')
            workspace = page.locator('.csv-workspace')
            assert abs(workspace.bounding_box()['y']) < 1
            assert abs(viewport.bounding_box()['y'] + viewport.bounding_box()['height'] - 900) < 2
            assert viewport.bounding_box()['height'] > 100
            assert expanded.bounding_box()['y'] >= 0
            page.screenshot(path=f'/tmp/nxflo-csv-expanded-{width}.png')
            if width == 1440:
                page.set_viewport_size({'width':1280, 'height':700})
                assert abs(frame.bounding_box()['width'] - page.evaluate('document.documentElement.clientWidth')) < 1
                page.wait_for_function("Math.abs(document.querySelector('.csv-workspace').getBoundingClientRect().y) < 1")
                assert abs(viewport.bounding_box()['y'] + viewport.bounding_box()['height'] - 700) < 2
                page.set_viewport_size({'width':width, 'height':900})
                page.wait_for_function("Math.abs(document.querySelector('.csv-workspace').getBoundingClientRect().y) < 1")
            expanded.click()
            expect(page.get_by_role('button', name='Expand table', exact=True)).to_have_attribute('aria-pressed', 'false')
            expect(page.locator('#csv-viewer aside')).to_be_visible()
            expect(page.locator('.site-header')).to_be_visible()
            expect(page.locator('.csv-page-container')).to_be_visible()
            assert abs(frame.bounding_box()['width'] - original_width) < 1
            expect(page.get_by_text('Page 2 of 5', exact=True)).to_be_visible()
            page.get_by_role('button', name='compact', exact=True).click()
            page.get_by_label('Table header background color').fill('#174bbf')
            page.get_by_role('button', name='Collapse dataset summary').click()
            page.get_by_role('button', name='Expand dataset summary').click()
            page.get_by_role('button', name='Switch to dark mode').click()
            page.get_by_role('button', name='Expand table', exact=True).click()
            assert page.locator('#csv-viewer .csv-workspace').evaluate("e => e.classList.contains('dark') && e.classList.contains('is-expanded')")
            assert abs(workspace.bounding_box()['y'] + workspace.bounding_box()['height'] - 900) < 2
            assert viewport.bounding_box()['height'] > 100
            assert page.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth')
            if width in (320, 375):
                short_height = 568 if width == 320 else 667
                page.set_viewport_size({'width':width, 'height':short_height})
                workspace.evaluate("e => e.scrollIntoView({block:'start',behavior:'instant'})")
                assert abs(workspace.bounding_box()['y'] + workspace.bounding_box()['height'] - short_height) < 2
                assert viewport.bounding_box()['height'] > 80
                assert viewport.bounding_box()['height'] > short_height / 2
                expect(page.get_by_role('button', name='Restore table size', exact=True)).to_be_in_viewport()
                assert page.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth')
                page.screenshot(path=f'/tmp/nxflo-csv-expanded-short-{width}.png')
                page.set_viewport_size({'width':width, 'height':900})
            page.get_by_role('button', name='Restore table size', exact=True).click()
            assert page.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth')
            page.screenshot(path=f'/tmp/nxflo-csv-dark-{width}.png', full_page=True)
            page.get_by_role('button', name='Switch to light mode').click()
            page.screenshot(path=f'/tmp/nxflo-csv-{width}.png', full_page=True)
            assert not requests, f'Local files triggered network requests: {requests}'
            page.get_by_role('button', name='Clear', exact=True).click()
            page.locator('input[type=file]').set_input_files({'name':'empty.csv','mimeType':'text/csv','buffer':b''})
            expect(page.get_by_role('alert')).to_be_visible()
            page.locator('input[type=file]').set_input_files({'name':'bad.csv','mimeType':'text/csv','buffer':b'Name,Value\n"broken,1'})
            expect(page.get_by_role('alert')).to_be_visible()
            # XLSX fixture contains an empty sheet and two populated worksheets.
            page.locator('input[type=file]').set_input_files(Path(__file__).parent / 'fixtures/csv-viewer-workbook.xlsx')
            expect(page.get_by_role('dialog')).to_be_visible()
            page.get_by_role('button', name='Empty', exact=True).click()
            expect(page.get_by_text('"Empty" sheet is empty.', exact=False)).to_be_visible()
            page.get_by_role('button', name='Data', exact=True).click()
            expect(page.get_by_role('dialog')).to_have_count(0)
            expect(page.get_by_text('2 rows, 2 columns', exact=True)).to_be_visible()
            page.locator('input[type=file]').set_input_files(Path(__file__).parent / 'fixtures/csv-viewer-workbook.xlsx')
            expect(page.get_by_role('dialog')).to_be_visible()
            page.keyboard.press('Escape')
            expect(page.get_by_role('dialog')).to_have_count(0)
            # Real browser drag-and-drop upload.
            page.locator('#csv-viewer').get_by_text('No file loaded').evaluate('''element => {
                const transfer = new DataTransfer();
                transfer.items.add(new File(['A,B\\n1,2'], 'drop.csv', {type:'text/csv'}));
                element.dispatchEvent(new DragEvent('drop', {bubbles:true, cancelable:true, dataTransfer:transfer}));
            }''')
            expect(page.get_by_text('1 rows, 2 columns', exact=True)).to_be_visible()
            assert page.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth')
            print(f'{width}px: menu, CSV parsing, expand/restore, sorting, pagination, themes, errors, worksheets, drag/drop, overflow passed')
        touch = browser.new_page(has_touch=True, is_mobile=True, viewport={'width':375, 'height':812}, ignore_https_errors=True)
        touch.goto(url.rstrip('/') + '/index.html', wait_until='networkidle')
        touch.get_by_role('button', name='Show apps menu').tap()
        expect(touch.locator('#tools-menu')).to_be_visible()
        touch.locator('#tools-menu a[href="csv-viewer.html"]').tap()
        expect(touch.get_by_role('heading', name='CSV Viewer', exact=True)).to_be_visible()
        touch.get_by_role('button', name='Show apps menu').tap()
        touch.locator('#tools-menu a[href="pdf-combiner.html"]').tap()
        expect(touch.locator('#combiner')).to_be_visible()
        print('Touch navigation: Home → CSV Viewer → PDF Merge passed')
        assert not errors, errors
        browser.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8012')
    check(parser.parse_args().url)
