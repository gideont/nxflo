"""Real-browser PDF tool checks. Requires Playwright, Pillow and pypdf."""
import argparse
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from pypdf import PdfReader, PdfWriter
from PIL import Image
from playwright.sync_api import sync_playwright, expect


def check(url):
    with TemporaryDirectory() as directory, sync_playwright() as playwright:
        root = Path(directory)
        first = PdfWriter()
        first.add_blank_page(width=200, height=300)
        first.add_blank_page(width=400, height=500)
        first.write(root / 'two-pages.pdf')
        locked = PdfWriter()
        locked.add_blank_page(width=200, height=300)
        locked.encrypt('secret')
        locked.write(root / 'locked.pdf')
        with (root / 'large.jpg').open('wb') as large:
            large.truncate(20 * 1024 * 1024 + 1)
        jpg = BytesIO()
        Image.new('RGB', (120, 80), 'red').save(jpg, format='JPEG')
        browser = playwright.chromium.launch(headless=True, ignore_default_args=['--hide-scrollbars'])
        page = browser.new_page(accept_downloads=True, ignore_https_errors=True)
        errors, requests = [], []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('request', lambda request: requests.append((request.method, request.url)))
        for width in (1440, 375, 320, 430):
            page.set_viewport_size({'width': width, 'height': 900})
            page.goto(url.rstrip('/') + '/pdf-combiner.html', wait_until='networkidle')
            assert page.locator('.page-slot').count() == 0
            assert page.locator('.site-nav [aria-current]').count() == 0
            page.locator('#page-count').select_option('2')
            assert page.locator('.page-slot').count() == 2
            assert page.locator('#combine').is_disabled()
            page.locator('#pdf-name').fill('My combined file.pdf')
            requests.clear()
            page.locator('.page-file-input').nth(0).set_input_files(root / 'two-pages.pdf')
            expect(page.locator('.page-slot').nth(0)).to_have_class('page-slot is-ready')
            # Exercise real DataTransfer drag/drop for the JPG.
            page.locator('.page-slot').nth(1).evaluate('''(element, bytes) => {
                const data = new DataTransfer();
                data.items.add(new File([new Uint8Array(bytes)], 'photo.jpg', {type:'image/jpeg'}));
                element.dispatchEvent(new DragEvent('drop', {bubbles:true, cancelable:true, dataTransfer:data}));
            }''', list(jpg.getvalue()))
            expect(page.locator('#file-summary')).to_contain_text('2 of 2 files ready · 3 output pages')
            expect(page.locator('#combine')).to_be_enabled()
            assert page.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth')
            page.locator('#combine').click()
            expect(page.locator('#download-result')).to_be_visible()
            page.locator('#download-result').screenshot(path=f'/tmp/nxflo-pdf-result-{width}.png')
            with page.expect_download() as pending:
                page.locator('#download-pdf').click()
            download = pending.value
            assert download.suggested_filename == 'My combined file.pdf'
            output = PdfReader(download.path())
            assert len(output.pages) == 3
            assert [float(p.mediabox.width) for p in output.pages[:2]] == [200, 400]
            assert len(output.pages[2].images) == 1
            assert output.pages[2].images[0].image.getpixel((0, 0))[0] > 200
            assert not requests, f'Documents must stay local: {requests}'
            assert page.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth')
            page.locator('#pdf-name').fill('updated')
            expect(page.locator('#download-result')).to_be_hidden()
            page.locator('#page-count').select_option('3')
            assert page.locator('.page-slot').count() == 3
            assert page.locator('.is-ready').count() == 2
            assert page.locator('#combine').is_disabled()
            page.locator('#page-count').select_option('2')
            page.locator('.page-remove').nth(1).click()
            assert page.locator('#combine').is_disabled()
            # Invalid, encrypted and oversize files must leave Combine disabled.
            target = page.locator('.page-file-input').nth(1)
            target.set_input_files({'name': 'fake.pdf', 'mimeType': 'application/pdf', 'buffer': b'not a PDF'})
            expect(page.locator('.page-details').nth(1)).to_contain_text('Choose a valid')
            target.set_input_files(root / 'locked.pdf')
            expect(page.locator('.page-details').nth(1)).to_contain_text('Password-protected')
            target.set_input_files(root / 'large.jpg')
            expect(page.locator('.page-details').nth(1)).to_contain_text('exceeds 20 MB')
            target.set_input_files({'name':'photo.jpg', 'mimeType':'image/jpeg', 'buffer':jpg.getvalue()})
            expect(page.locator('#combine')).to_be_enabled()
            page.locator('#combiner').screenshot(path=f'/tmp/nxflo-pdf-tool-{width}.png')
            for link in page.locator('.site-nav > a').all():
                assert link.is_visible() and link.bounding_box()['height'] >= 44
            page.locator('#clear-files').click()
            assert page.locator('.page-slot').count() == 0
            assert page.locator('#pdf-name').input_value() == ''
            expect(page.locator('#download-result')).to_be_hidden()
            print(f'{width}px: file picker, drop, mixed merge, page order, image, filename, download, errors, reset, local-only processing and overflow passed')
        # Filled form values survive copying into the result.
        page.locator('#page-count').select_option('1')
        page.locator('#pdf-name').fill('form')
        form_bytes = page.evaluate('''async () => {
            const doc = await PDFLib.PDFDocument.create(); doc.addPage([300,300]);
            const text = doc.getForm().createTextField('customer'); text.setText('Nexusflow form check');
            text.addToPage(doc.getPage(0), {x:20,y:100,width:250,height:50});
            return Array.from(await doc.save());
        }''')
        page.locator('.page-file-input').set_input_files({'name':'form.pdf', 'mimeType':'application/pdf', 'buffer':bytes(form_bytes)})
        expect(page.locator('#combine')).to_be_enabled()
        page.locator('#combine').click()
        expect(page.locator('#download-result')).to_be_visible()
        with page.expect_download() as pending:
            page.locator('#download-pdf').click()
        assert 'Nexusflow form check' in PdfReader(pending.value.path()).pages[0].extract_text()
        assert not errors, errors
        browser.close()
        print('Filled PDF form preservation and JavaScript error checks passed')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8001')
    check(parser.parse_args().url)
