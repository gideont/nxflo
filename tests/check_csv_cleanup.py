"""Browser checks for local NULL cleanup, lossless CSV quoting and fullscreen mode."""
import argparse
import csv
from io import StringIO
from playwright.sync_api import sync_playwright, expect


def check(url):
    records = [['Name', ' NULL ', 'Notes', 'Code'],
               ['NULL', 'null', 'a null value', '001'],
               ['null', 'NuLl', 'quoted, "text"\nsecond line', '000'],
               [' NULL ', 'normal', 'café 東京', '=A1'],
               ['nullify', '', '', ''], ['NULL', 'null', 'NULL', 'null']]
    records += [[f'Row {i}', 'null', 'unchanged', str(i)] for i in range(130)]
    expected = [records[0]] + [['' if value.strip().lower() == 'null' else value for value in row] for row in records[1:]]
    count = sum(value.strip().lower() == 'null' for row in records[1:] for value in row)
    output = StringIO(newline='')
    csv.writer(output).writerows(records)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, ignore_default_args=['--hide-scrollbars'])
        for width, height in ((1440,900),(375,667),(320,568),(430,932)):
            page = browser.new_page(viewport={'width':width,'height':height},has_touch=width<500,is_mobile=width<500,accept_downloads=True,ignore_https_errors=True)
            page.goto(url.rstrip('/')+'/csv-viewer.html',wait_until='networkidle')
            clean = page.get_by_role('button', name='Clear NULL values', exact=True)
            download = page.get_by_role('button', name='Download cleaned CSV', exact=True)
            expect(clean).to_be_disabled(); expect(download).to_be_disabled()
            page.locator('input[type=file]').set_input_files({'name':'data.csv','mimeType':'text/csv','buffer':output.getvalue().encode()})
            expect(page.get_by_text('135 rows, 4 columns',exact=True)).to_be_visible()
            requests=[]
            page.on('request',lambda request: requests.append(request.url) if not request.url.startswith('blob:') else None)
            page.get_by_label('Rows per page',exact=True).select_option('25')
            page.get_by_role('columnheader').first.click()
            page.get_by_role('button',name='Next page',exact=True).click()
            page.get_by_role('button',name='Expand table',exact=True).click()
            expect(page.locator('.site-header')).to_be_hidden()
            expect(page.get_by_role('heading',name='CSV Viewer',exact=True)).to_have_count(0)
            expect(page.locator('.csv-page-container')).to_be_hidden()
            expect(page.locator('.site-footer')).to_be_hidden()
            box=page.locator('.csv-workspace').bounding_box()
            assert all(abs(box[key]-value)<1 for key,value in {'x':0,'y':0,'width':width,'height':height}.items()),box
            assert page.locator('.csv-viewport').bounding_box()['height'] > height/2
            clean.evaluate("e => e.scrollIntoView({inline:'end',block:'nearest'})")
            clean.click()
            expect(page.locator('.csv-clean-status')).to_contain_text(f'Replaced {count} NULL cells with blanks.')
            expect(page.get_by_text('Page 2 of 6',exact=True)).to_be_visible()
            expect(download).to_be_enabled()
            download.evaluate("e => e.scrollIntoView({inline:'end',block:'nearest'})")
            with page.expect_download() as pending:
                download.click()
            result=pending.value
            assert result.suggested_filename=='data-cleaned.csv'
            with open(result.path(),encoding='utf-8-sig',newline='') as handle:
                assert list(csv.reader(handle))==expected
            # A second pass is safe; original headers and non-null substrings remain intact.
            clean.evaluate("e => e.scrollIntoView({inline:'end',block:'nearest'})");clean.click()
            expect(page.locator('.csv-clean-status')).to_contain_text('No NULL values found.')
            assert page.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth')
            page.screenshot(path=f'/tmp/nxflo-csv-cleaned-fullscreen-{width}.png')
            page.keyboard.press('Escape')
            expect(page.locator('.site-header')).to_be_visible()
            expect(page.locator('.csv-page-container')).to_be_visible()
            page.get_by_role('button',name='Clear',exact=True).click()
            expect(download).to_be_disabled()
            expect(page.locator('.csv-clean-status')).to_have_count(0)
            assert not requests,requests
            print(f'{width}x{height}: fullscreen, hidden site chrome, NULL cleanup, all-row downloads, quoting, Unicode, leading zeros, headers, idempotence, reset, no uploads passed')
            page.close()
        browser.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',default='http://127.0.0.1:8024')
    check(parser.parse_args().url)
