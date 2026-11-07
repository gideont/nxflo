"""Check shared footer content, styling, keyboard access, and responsive layout.

Requires Playwright with Chromium and a running built site.
"""
import argparse
from pathlib import Path


def check(url, executable, screenshots):
    from playwright.sync_api import sync_playwright

    pages = [path.name for path in sorted(Path(__file__).resolve().parents[1].glob("*.html"))]
    footer_geometry = """footer => {
        const origin = footer.getBoundingClientRect();
        const rect = element => {
            const box = element.getBoundingClientRect();
            const style = getComputedStyle(element);
            return [box.x - origin.x, box.y - origin.y, box.width, box.height]
                .map(value => Math.round(value * 100) / 100)
                .concat(style.fontFamily, style.fontSize, style.color, style.backgroundColor);
        };
        return [rect(footer), ...[...footer.querySelectorAll(
            '.footer-grid, .footer-logo, h2, .footer-description, .footer-positioning, .footer-canadian-logo, .footer-links a, .footer-artwork, .footer-bottom, .footer-bottom p, .footer-vancouver-art'
        )].map(rect)];
    }"""

    with sync_playwright() as playwright:
        options = {"headless": True, "ignore_default_args": ["--hide-scrollbars"]}
        if executable:
            options["executable_path"] = executable
        browser = playwright.chromium.launch(**options)
        page = browser.new_page(ignore_https_errors=True)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        if screenshots:
            Path(screenshots).mkdir(parents=True, exist_ok=True)

        for width in (1440, 960, 768, 375, 320, 430):
            page.set_viewport_size({"width": width, "height": 1000})
            baseline = None
            markup = None
            for name in pages:
                response = page.goto(f"{url.rstrip('/')}/{name}", wait_until="networkidle")
                assert response.status == 200, name
                page.evaluate("document.fonts.ready")
                footer = page.locator("footer.site-footer")
                assert footer.count() == 1
                footer.scroll_into_view_if_needed()
                footer.locator("img").evaluate_all("images => Promise.all(images.map(image => image.decode()))")
                assert footer.locator('.footer-local h2').inner_text() == 'Vancouver, Canada. Internationally connected.'
                assert footer.locator('.footer-positioning').inner_text() == 'Proudly based in Vancouver, Canada, supporting businesses locally and internationally including Asia.'
                legal = footer.locator('.footer-bottom')
                assert 'Vancouver, BC, Canada · BC Incorporation No. BC1535270 · All rights reserved.' in ' '.join(legal.inner_text().split())
                assert legal.evaluate('element => parseFloat(getComputedStyle(element).borderTopWidth)') > 0
                legal_font = legal.locator('p').evaluate('element => parseFloat(getComputedStyle(element).fontSize)')
                assert 13 <= legal_font < footer.evaluate('element => parseFloat(getComputedStyle(element).fontSize)')
                columns = footer.locator('.footer-grid').evaluate('element => getComputedStyle(element).gridTemplateColumns.split(" ").length')
                assert columns == (1 if width <= 800 else 3), (name, width, columns)
                illustration = footer.locator('.footer-vancouver-art').bounding_box()
                artwork = footer.locator('.footer-artwork').bounding_box()
                main = footer.locator('.footer-grid').bounding_box()
                assert main['y'] + main['height'] <= artwork['y']
                assert illustration['y'] + illustration['height'] <= legal.bounding_box()['y'] + 0.5, 'Illustration overlaps legal information'
                assert footer.locator('a[href="mailto:sales@nxflo.com"]').inner_text() == "sales@nxflo.com"
                assert footer.locator('a[href="tel:+16042609218"]').inner_text() == "+1 (604) 260-9218"
                assert footer.locator('nav[aria-label="Footer"] a').all_text_contents() == ["Home", "Articles", "Services", "Contact", "Apps"]
                for link in footer.locator("a").all():
                    assert link.is_visible()
                    minimum_height = 44 if width <= 800 or link.get_attribute("class") == "footer-brand" else 30
                    assert link.bounding_box()["height"] >= minimum_height, (name, width, link.inner_text())
                assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth"), (name, width)
                current = footer.evaluate(footer_geometry)
                current_markup = footer.evaluate("element => element.outerHTML")
                if baseline is None:
                    baseline, markup = current, current_markup
                assert current == baseline, f"Footer layout/style differs on {name} at {width}px"
                assert current_markup == markup, f"Footer content differs on {name}"
                email = footer.locator('a[href="mailto:sales@nxflo.com"]')
                email.focus()
                assert email.evaluate("element => getComputedStyle(element).outlineStyle") != "none"
                page.keyboard.press("Tab")
                assert page.locator(":focus").get_attribute("href") == "tel:+16042609218"
                if screenshots and width in (1440, 375) and name != "thanks.html":
                    footer.screenshot(path=f"{screenshots}/{name.removesuffix('.html')}-{width}.png")
            print(f"{width}px: all {len(pages)} footers match; contact links, keyboard focus, touch targets, and overflow checks passed")

        page.locator('footer nav a[href="contact.html"]').click()
        page.wait_for_url("**/contact.html")
        assert page.locator("h1").inner_text() == "Contact Nexusflow"
        assert not errors, errors

        touch = browser.new_context(ignore_https_errors=True, viewport={"width": 1440, "height": 1000}, has_touch=True)
        touch_page = touch.new_page()
        touch_page.goto(f"{url.rstrip('/')}/index.html", wait_until="networkidle")
        for link in touch_page.locator("footer a").all():
            assert link.bounding_box()["height"] >= 44, "Touch devices need larger link targets"

        fallback = browser.new_context(java_script_enabled=False, ignore_https_errors=True)
        no_js = fallback.new_page()
        no_js.goto(f"{url.rstrip('/')}/index.html", wait_until="networkidle")
        assert no_js.locator('footer a[href="tel:+16042609218"]').count() == 1
        assert no_js.locator('footer a[href="mailto:sales@nxflo.com"]').count() == 1
        assert no_js.locator("footer [data-current-year]").inner_text()
        browser.close()
        print("Footer navigation and contact details work with native HTML; no JavaScript errors")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:9001")
    parser.add_argument("--browser-executable")
    parser.add_argument("--screenshots", help="Optional output directory for footer review")
    args = parser.parse_args()
    check(args.url, args.browser_executable, args.screenshots)
