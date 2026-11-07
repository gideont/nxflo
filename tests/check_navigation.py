"""Browser regression check for menu shifts between long and short pages.

Requires Playwright with Chromium and a running built site.
"""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.seo import PAGES


def check(url: str, executable: str | None, viewports=None) -> None:
    from playwright.sync_api import sync_playwright

    pages = [path.name for path in sorted(Path(__file__).resolve().parents[1].glob("*.html"))]
    geometry = """() => [...document.querySelectorAll('.site-header, .brand-logo, .site-nav a')]
        .map(e => { const r = e.getBoundingClientRect(); return [r.x, r.y, r.width, r.height]; })"""
    with sync_playwright() as playwright:
        options = {"headless": True, "ignore_default_args": ["--hide-scrollbars"]}
        if executable:
            options["executable_path"] = executable
        browser = playwright.chromium.launch(**options)
        page = browser.new_page(ignore_https_errors=True)
        for width, height in (viewports or ((1440, 900), (1440, 1200), (1920, 1600), (768, 1024), (320, 568), (375, 667), (430, 932))):
            page.set_viewport_size({"width": width, "height": height})
            baseline = None
            for name in pages:
                response = page.goto(f"{url.rstrip('/')}/{name}", wait_until="networkidle")
                page.evaluate("document.fonts.ready")
                assert response.status == 200, name
                current = page.evaluate(geometry)
                active = page.locator('.site-nav a[aria-current="page"]')
                expected = PAGES[name].navigation
                if expected is None:
                    assert active.count() == 0
                else:
                    assert active.count() == 1 and active.get_attribute("href") == expected
                if baseline is None:
                    baseline = current
                assert current == baseline, f"Header moved on {name} at {width}x{height}"
                assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth"), name
                assert page.locator('.site-header').evaluate("e => getComputedStyle(e).position") == 'static'
                assert page.evaluate("document.scrollingElement === document.documentElement")
                assert page.evaluate("""() => [...document.querySelectorAll('body *')].filter(e => {
                    const css=getComputedStyle(e);
                    return ['auto','scroll'].includes(css.overflowY) && e.clientHeight>0 && e.scrollHeight>e.clientHeight;
                }).filter(e => !e.closest('#csv-viewer')).length === 0"""), f"Nested scrolling container on {name}"
                initial = page.evaluate("""() => ['.site-header','main','.site-footer'].map(selector =>
                    document.querySelector(selector).getBoundingClientRect().top)""")
                page.evaluate("window.scrollTo({top:600,behavior:'instant'})")
                shift = page.evaluate('window.scrollY')
                after = page.evaluate("""() => ['.site-header','main','.site-footer'].map(selector =>
                    document.querySelector(selector).getBoundingClientRect().top)""")
                assert all(abs((start-end)-shift)<1 for start,end in zip(initial,after)), f"Independent scrolling on {name}"
                if shift > page.locator('.site-header').bounding_box()['height']:
                    assert page.locator('.site-header').bounding_box()['y'] + page.locator('.site-header').bounding_box()['height'] < 0
                page.evaluate("window.scrollTo({top:0,behavior:'instant'})")
                if name == "contact.html":
                    assert page.locator(".contact-method-link").evaluate_all(
                        "links => links.every(e => e.getBoundingClientRect().bottom <= innerHeight)"
                    ), "Main contact links require scrolling"
            print(f"{width}x{height}: navigation stays aligned; header, content and footer use unified document scrolling")
        page.set_viewport_size({"width": 1440, "height": 1200})
        page.goto(f"{url.rstrip('/')}/about.html", wait_until="networkidle")
        before = page.evaluate(geometry)
        assert page.evaluate("document.documentElement.scrollHeight > innerHeight")
        page.evaluate("document.querySelector('main').hidden = true; document.querySelector('footer').hidden = true")
        assert page.evaluate("document.documentElement.scrollHeight <= innerHeight")
        assert page.evaluate(geometry) == before, "Scrollbar disappearance moved the header"
        browser.close()
        print("Scrollbar presence regression: passed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:9001")
    parser.add_argument("--browser-executable")
    parser.add_argument("--viewport", action="append", help="Check a specific WIDTHxHEIGHT; repeat for multiple sizes")
    arguments = parser.parse_args()
    viewports = [tuple(map(int, value.split("x"))) for value in arguments.viewport] if arguments.viewport else None
    check(arguments.url, arguments.browser_executable, viewports)
