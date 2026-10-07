"""Browser regression check for menu shifts between long and short pages.

Requires Playwright with Chromium and a running built site.
"""
import argparse


def check(url: str, executable: str | None) -> None:
    from playwright.sync_api import sync_playwright

    pages = ("index.html", "about.html", "services.html", "contact.html", "thanks.html")
    geometry = """() => [...document.querySelectorAll('.site-header, .brand-logo, .site-nav a')]
        .map(e => { const r = e.getBoundingClientRect(); return [r.x, r.y, r.width, r.height]; })"""
    with sync_playwright() as playwright:
        options = {"headless": True, "ignore_default_args": ["--hide-scrollbars"]}
        if executable:
            options["executable_path"] = executable
        browser = playwright.chromium.launch(**options)
        page = browser.new_page()
        for width, height in ((1440, 900), (1440, 1200), (1920, 1600), (320, 568), (375, 667), (430, 932)):
            page.set_viewport_size({"width": width, "height": height})
            baseline = None
            for name in pages:
                response = page.goto(f"{url.rstrip('/')}/{name}", wait_until="networkidle")
                page.evaluate("document.fonts.ready")
                assert response.status == 200, name
                current = page.evaluate(geometry)
                if baseline is None:
                    baseline = current
                assert current == baseline, f"Header moved on {name} at {width}x{height}"
                assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth"), name
                if name == "contact.html":
                    assert page.locator(".contact-method-link").evaluate_all(
                        "links => links.every(e => e.getBoundingClientRect().bottom <= innerHeight)"
                    ), "Main contact links require scrolling"
            print(f"{width}x{height}: navigation stays aligned across all pages")
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
    arguments = parser.parse_args()
    check(arguments.url, arguments.browser_executable)
