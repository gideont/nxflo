"""Verify article introduction links are available with mouse, keyboard, and touch."""
import argparse
from pathlib import Path
from playwright.sync_api import sync_playwright


def check(base):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, ignore_default_args=['--hide-scrollbars'])
        for width in (1440, 375, 320, 430):
            context = browser.new_context(viewport={'width': width, 'height': 1000}, has_touch=width < 600, is_mobile=width < 600)
            page = context.new_page()
            for target in ('articles.html', 'etl-dashboard-process-playbook.html'):
                page.goto(base.rstrip('/') + '/contact.html', wait_until='networkidle')
                group = page.locator('.nav-articles')
                toggle = group.locator('button')
                menu = page.locator('#articles-menu')
                assert menu.is_hidden()
                if width == 1440:
                    group.locator('[data-nav="articles"]').hover()
                else:
                    toggle.tap()
                assert menu.is_visible()
                menu.evaluate("e => Promise.all(e.getAnimations().map(animation => animation.finished))")
                assert toggle.get_attribute('aria-expanded') == 'true'
                assert menu.locator('a').count() == 2
                for link in menu.locator('a').all():
                    assert link.bounding_box()['height'] >= 44
                bounds = menu.bounding_box()
                assert bounds['x'] >= 0 and bounds['x'] + bounds['width'] <= width
                assert page.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth')
                if target == 'articles.html' and width in (1440, 375):
                    Path('/tmp/etl-nav-qa').mkdir(exist_ok=True)
                    page.screenshot(path=f'/tmp/etl-nav-qa/menu-{width}.png')
                menu.locator(f'a[href="{target}"]').click()
                assert page.url.endswith('/' + target)
                assert page.locator('h1').inner_text() == ('Stale by Thursday' if target == 'articles.html' else 'ETL and Dashboard Process Playbook')
            toggle = page.locator('.nav-articles-toggle')
            toggle.focus()
            page.keyboard.press('ArrowDown')
            assert page.locator('#articles-menu a').first.evaluate('e => e === document.activeElement')
            page.keyboard.press('Escape')
            assert page.locator('#articles-menu').is_hidden()
            assert toggle.evaluate('e => e === document.activeElement')
            toggle.click()
            page.locator('h1').click()
            assert page.locator('#articles-menu').is_hidden()
            page.locator('.nav-tools-toggle').click()
            assert page.locator('#tools-menu').is_visible()
            page.keyboard.press('Escape')
            assert page.locator('#tools-menu').is_hidden()
            print(f'{width}px: article links, dropdown bounds, keyboard, dismissal and Apps regression passed', flush=True)
            context.close()
        browser.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8013')
    check(parser.parse_args().url)
