"""Generated HTML must keep formal revision records readable on phones and desktop."""
from playwright.sync_api import sync_playwright
from portal_api.generator import DEFAULTS
from portal_api.generation_document import assemble


def check():
    state={'warnings':['A source was unavailable; verify this reference.'],'sources':[{'id':'B1','label':'User brief','text':'Research guidance'}],
           'document':{'chapters':[{'title':'Operational recommendations','paragraphs':['Establish a regular evidence review cadence [B1].'],'charts':[]}]},
           'revision_history':[{'version':'1.0','date':'2026-11-05','prepared_by':'Research Team at Nexusflow Inc.','summary':'Initial issue.'},
                               {'version':'1.1','date':'2026-11-05','prepared_by':'Research Team at Nexusflow Inc.','summary':'Expanded the measurement recommendations and clarified ownership.'}]}
    html=assemble({**DEFAULTS,'title':'Operational review guidance','version':'1.1','release_date':'2026-11-05'},state)
    assert 'folio — base layer: STRUCTURE ONLY.' in html and 'report — corporate, confident, safe.' in html
    assert 'data-document-engine="folio"' in html
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,ignore_default_args=['--hide-scrollbars'])
        for width in (1440,375,320,430):
            page=browser.new_page(viewport={'width':width,'height':950})
            page.set_content(html)
            assert page.evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth'),width
            assert page.locator('.prepared-by').inner_text().find('Research Team at Nexusflow Inc.')>=0
            assert page.locator('#document-contact a[href="mailto:research@nxflo.com"]').is_visible()
            assert page.locator('#document-contact a[href="https://www.nxflo.com"]').is_visible()
            assert page.locator('.revision-table tbody tr').count()==2
            assert 'Review required' not in page.locator('.cover').inner_text()
            assert page.locator('.cover').evaluate('element=>element===document.querySelector("main").firstElementChild')
            assert 'A source was unavailable' in page.locator('#editorial-notes').inner_text()
            assert page.locator('#editorial-notes').evaluate('element=>element.compareDocumentPosition(document.querySelector("#document-control")) & Node.DOCUMENT_POSITION_FOLLOWING')
            assert page.locator('.revision-table caption').bounding_box()['height']<42,'Revision caption is too narrow'
            assert page.locator('.revision-table td').evaluate_all("cells=>cells.every(cell=>parseFloat(getComputedStyle(cell).fontSize)>=12)")
            for link in page.locator('nav a').all():assert page.locator(link.get_attribute('href')).count()==1
            if width in (1440,375):
                page.screenshot(path='/tmp/nxflo-folio-'+str(width)+'.png',full_page=True)
            if width<=430:
                assert page.locator('.revision-table td').first.get_attribute('data-label')=='Version'
            page.close()
        browser.close()
    print('Generated document contacts and revision records passed at 1440, 375, 320, 430px without overflow.')

if __name__=='__main__':check()
