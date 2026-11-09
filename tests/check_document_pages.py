"""Browser and PDF checks for private A4 page previews; run in the browser test image."""
import json,sqlite3,threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler,HTTPServer
from portal_api.generator import DEFAULTS
from portal_api.generation_document import assemble,export_pdf
from portal_api.generation_page_preview import paginated_preview
from playwright.sync_api import sync_playwright
from pypdf import PdfReader
cfg={**DEFAULTS,'title':'Investment and Return Simulator: A Financial Decision Tool for Early-Stage Ventures','company':'Nexusflow Inc.','release_date':'2026-11-08','report_type':'White paper'}
s={'sources':[{'id':'B1','label':'Author material','text':'Original concept'}],'warnings':[],
   'document':{'chapters':[{'title':title,'paragraphs':[('An investment model connects startup expenditure, monthly operating costs, projected revenue and the practical decision to continue or revise the plan. '*3)]*12} for title in ('The product vision','A worked financial projection','FP&A and practical decisions')]}}
html=assemble(cfg,s);preview=paginated_preview(html)
class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  if self.path=='/host':
   self.send_response(200);self.send_header('Content-Type','text/html');self.end_headers();self.wfile.write(b'<html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body style="margin:0"><iframe title="Page preview" sandbox="allow-scripts" src="/" style="width:100%;height:95vh;border:0"></iframe></body></html>');return
  path=Path('/app')/self.path.lstrip('/')
  data=preview.encode() if self.path=='/' else path.read_bytes()
  self.send_response(200);self.send_header('Content-Security-Policy',"default-src 'none'; script-src 'self'; img-src data:; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; frame-ancestors 'self'");self.send_header('Content-Type','text/html' if self.path=='/' else 'application/javascript');self.end_headers();self.wfile.write(data)
 def log_message(self,*a):pass
server=HTTPServer(('127.0.0.1',8765),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
with sync_playwright() as p:
 b=p.chromium.launch(headless=True);page=b.new_page(viewport={'width':1440,'height':1000});page.on('pageerror',lambda e:print('BROWSER ERROR:',e));page.goto('http://127.0.0.1:8765/')
 page.wait_for_selector('body[data-pagination="ready"]',timeout=180000)
 count=page.locator('.pagedjs_page').count();assert count>5,count
 page.screenshot(path='/tmp/nxflo-pagination-debug.png')
 assert 'Contents' not in page.locator('.pagedjs_page').nth(0).inner_text()
 assert 'Contents' in page.locator('.pagedjs_page').nth(1).inner_text(),page.locator('.pagedjs_page').nth(1).inner_text()[:100]
 assert page.locator('.contents li').evaluate_all("rows => rows.every(row => getComputedStyle(row).borderBottomWidth === '0px')")
 assert page.locator('.contents h2').evaluate("heading => getComputedStyle(heading).borderBottomStyle === 'solid'")
 for ch in s['document']['chapters']:assert ' '.join(ch['title'].split()) in ' '.join(page.locator('.pagedjs_pages').inner_text().split()),ch['title']
 for width in (1440,375,320,430):
  page.set_viewport_size({'width':width,'height':1000});page.wait_for_timeout(400)
  assert page.evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth'),width
  page.locator('.preview-toolbar select[aria-label="Go to page"]').select_option('0')
  page.locator('.preview-toolbar button').nth(1).click();assert page.locator('.preview-toolbar select[aria-label="Go to page"]').input_value()=='1'
  page.locator('.preview-toolbar button').nth(0).click();assert page.locator('.preview-toolbar select[aria-label="Go to page"]').input_value()=='0'
  page.evaluate('scrollTo(0,0)');page.screenshot(path=f'/tmp/nxflo-cover-paged-{width}.png')
  page.locator('.preview-toolbar select[aria-label="Go to page"]').select_option('1');page.screenshot(path=f'/tmp/nxflo-toc-paged-{width}.png')
 page.locator('select[aria-label="Page zoom"]').select_option('1');page.wait_for_timeout(300)
 assert page.evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth')
 assert page.locator('.preview-toolbar').bounding_box()['y']==0
 host=b.new_page(viewport={'width':375,'height':950});host.goto('http://127.0.0.1:8765/host')
 host.frame_locator('iframe').locator('body[data-pagination="ready"]').wait_for(timeout=90000)
 assert host.evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth')
 b.close()
export_pdf(html,Path('/tmp/nxflo-page-regression.pdf'));reader=PdfReader('/tmp/nxflo-page-regression.pdf')
assert 'Contents' not in reader.pages[0].extract_text()
assert 'Contents' in reader.pages[1].extract_text(),reader.pages[1].extract_text()[:120]
print('Page preview:',count,'pages; cover is page 1, contents starts page 2; all chapters retained; navigation and no overflow at 1440/375/320/430. PDF:',len(reader.pages),'pages.')
