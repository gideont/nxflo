"""Check arrow-only homepage disclosures, exclusive expansion, and responsive layout.

Requires Playwright with Chromium and a running built site.
"""
import argparse
from pathlib import Path


def check(url, executable, screenshots):
    from playwright.sync_api import sync_playwright

    def no_overflow(page):
        assert page.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth'), 'Horizontal overflow'

    def expanded(card):
        return card.locator('details').get_attribute('open') is not None

    def open_count(page):
        return page.locator('.home-card-disclosure[open]').count()

    with sync_playwright() as playwright:
        options = {'headless': True, 'ignore_default_args': ['--hide-scrollbars']}
        if executable:
            options['executable_path'] = executable
        browser = playwright.chromium.launch(**options)
        page = browser.new_page(ignore_https_errors=True, viewport={'width': 1440, 'height': 1000})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        response = page.goto(f'{url.rstrip("/")}/index.html', wait_until='networkidle')
        assert response.status == 200
        page.evaluate('document.fonts.ready')
        cards = page.locator('[data-challenge]')
        assert cards.count() == 9 and open_count(page) == 0
        assert not cards.first.locator('.home-example-solution').is_visible()
        banner = page.locator('.home-illustration > img').bounding_box()
        assert 1.6 < banner['width'] / banner['height'] < 1.7
        if screenshots:
            Path(screenshots).mkdir(parents=True, exist_ok=True)
            page.screenshot(path=f'{screenshots}/home-desktop.png', full_page=True)

        first, second = cards.nth(0), cards.nth(1)
        for card in cards.all():
            card.hover()
            page.wait_for_timeout(100)
            assert open_count(page) == 0, 'Hover must not expand a card'
        first.locator('.home-card-challenge').click()
        first.locator('.home-card-hint').click()
        assert open_count(page) == 0, 'Only the arrow may expand a card'
        first.locator('.home-card-toggle').click()
        page.mouse.move(2, 2)
        assert expanded(first) and open_count(page) == 1
        assert first.locator('.home-card-toggle').get_attribute('aria-expanded') == 'true'
        second.locator('.home-card-toggle').click()
        assert expanded(second) and not expanded(first) and open_count(page) == 1
        assert first.locator('.home-card-toggle').get_attribute('aria-expanded') == 'false'
        assert not first.locator('.home-example-solution').is_visible()
        second.locator('.home-card-toggle').click()
        assert open_count(page) == 0
        first.locator('.home-card-toggle').focus()
        page.keyboard.press('Enter')
        assert expanded(first)
        second.locator('.home-card-toggle').focus()
        page.keyboard.press('Space')
        assert expanded(second) and not expanded(first) and open_count(page) == 1
        page.keyboard.press('Escape')
        assert open_count(page) == 0
        assert second.locator('.home-card-toggle').get_attribute('aria-expanded') == 'false'
        print('Desktop: no hover/text expansion; arrow toggle, single answer, and keyboard controls passed')

        for width, columns in ((1440, 3), (911, 3), (768, 2), (430, 1), (375, 1), (320, 1)):
            page.set_viewport_size({'width': width, 'height': 900})
            actual_columns = page.locator('.home-examples-grid').evaluate('e => getComputedStyle(e).gridTemplateColumns.split(" ").length')
            assert actual_columns == columns, (width, actual_columns)
            no_overflow(page)
            previous = None
            for card in cards.all():
                arrow = card.locator('.home-card-toggle')
                assert arrow.bounding_box()['width'] >= 44 and arrow.bounding_box()['height'] >= 44
                arrow.click()
                assert expanded(card) and open_count(page) == 1
                assert card.locator('.home-example-solution').is_visible()
                if previous is not None:
                    assert not expanded(previous)
                no_overflow(page)
                previous = card
            previous.locator('.home-card-toggle').click()
            assert open_count(page) == 0
            print(f'{width}px: {columns} columns; single expansion and no horizontal overflow')
        assert not errors, errors

        touch = browser.new_context(ignore_https_errors=True, viewport={'width': 375, 'height': 812}, is_mobile=True, has_touch=True)
        phone = touch.new_page()
        phone.goto(f'{url.rstrip("/")}/index.html', wait_until='networkidle')
        assert open_count(phone) == 0
        no_overflow(phone)
        if screenshots:
            phone.screenshot(path=f'{screenshots}/home-mobile.png', full_page=True)
        phone_cards = phone.locator('[data-challenge]')
        phone_cards.first.locator('.home-card-challenge').tap()
        assert open_count(phone) == 0
        phone_cards.nth(0).locator('.home-card-toggle').tap()
        assert expanded(phone_cards.nth(0)) and open_count(phone) == 1
        phone_cards.nth(1).locator('.home-card-toggle').tap()
        assert expanded(phone_cards.nth(1)) and not expanded(phone_cards.nth(0)) and open_count(phone) == 1
        phone_cards.nth(1).locator('.home-card-toggle').tap()
        assert open_count(phone) == 0
        print('Mobile: arrow-only touch taps and automatic closing passed')

        fallback = browser.new_context(java_script_enabled=False, ignore_https_errors=True)
        fallback_page = fallback.new_page()
        fallback_page.goto(f'{url.rstrip("/")}/index.html', wait_until='networkidle')
        fallback_page.locator('.home-card-challenge').first.click()
        assert open_count(fallback_page) == 0
        fallback_page.locator('.home-card-toggle').nth(0).click()
        assert open_count(fallback_page) == 1
        fallback_page.locator('.home-card-toggle').nth(1).click()
        assert open_count(fallback_page) == 1
        assert not fallback_page.locator('.home-example-solution').nth(0).is_visible()
        print('Without JavaScript: native grouped arrow disclosures remain usable')
        browser.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:9001')
    parser.add_argument('--browser-executable')
    parser.add_argument('--screenshots', help='Optional output directory for visual review')
    args = parser.parse_args()
    check(args.url, args.browser_executable, args.screenshots)
