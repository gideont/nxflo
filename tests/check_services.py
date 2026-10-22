"""Check service content, native disclosures, touch targets, and responsive UI."""
import argparse
from pathlib import Path


def check(url, executable, screenshots):
    from playwright.sync_api import sync_playwright

    pages = (
        "bms-data-integration.html", "vancouver-it-support.html",
        "entra-id-integration.html", "databricks-consulting.html",
        "etl-data-pipelines.html", "power-bi-consulting.html",
    )
    with sync_playwright() as playwright:
        options = {"headless": True, "ignore_default_args": ["--hide-scrollbars"]}
        if executable:
            options["executable_path"] = executable
        browser = playwright.chromium.launch(**options)
        context = browser.new_context(ignore_https_errors=True)
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        if screenshots:
            Path(screenshots).mkdir(parents=True, exist_ok=True)
        for width in (1440, 375, 320, 430):
            page.set_viewport_size({"width": width, "height": 1000})
            for name in pages:
                response = page.goto(f"{url.rstrip('/')}/{name}", wait_until="networkidle")
                page.evaluate("document.fonts.ready")
                assert response.status == 200, name
                assert page.locator("h1").count() == 1
                assert page.locator("form").count() == 0
                assert page.locator('.site-nav a[aria-current="page"]').get_attribute("href") == "services.html"
                assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth"), (name, width)
                columns = page.locator(".service-detail-hero").evaluate('e => getComputedStyle(e).gridTemplateColumns.split(" ").length')
                assert columns == (2 if width > 800 else 1)
                action = page.locator('.story-actions a[href="contact.html"]')
                assert action.bounding_box()["height"] >= 44
                summary = page.locator(".service-faq summary").first
                assert summary.bounding_box()["height"] >= 44
                summary.focus()
                assert summary.evaluate('e => getComputedStyle(e).outlineStyle') != "none"
                page.keyboard.press("Enter")
                assert page.locator(".service-faq details").first.get_attribute("open") is not None
                assert page.locator(".service-faq details p").first.is_visible()
                page.keyboard.press("Enter")
                assert page.locator(".service-faq details").first.get_attribute("open") is None
                if screenshots and width in (1440, 375):
                    page.evaluate("document.activeElement.blur(); window.scrollTo({top: 0, behavior: 'instant'})")
                    page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
                    page.screenshot(path=f"{screenshots}/{name.removesuffix('.html')}-{width}.png", full_page=True)
            print(f"{width}px: six service pages usable; no overflow; keyboard disclosures and contact actions passed")
        page.goto(f"{url.rstrip('/')}/services.html", wait_until="networkidle")
        for name in pages:
            assert page.locator(f'main a[href="{name}"]').count() == 1
        page.locator('main a[href="bms-data-integration.html"]').click()
        page.wait_for_url("**/bms-data-integration.html")
        assert "building management" in page.locator("main").inner_text().lower()
        fallback = browser.new_context(java_script_enabled=False, ignore_https_errors=True)
        native = fallback.new_page()
        native.goto(f"{url.rstrip('/')}/entra-id-integration.html", wait_until="networkidle")
        assert native.locator('.site-nav a[aria-current="page"]').get_attribute("href") == "services.html"
        native.locator(".service-faq summary").first.click()
        assert native.locator(".service-faq details p").first.is_visible()
        assert not errors, errors
        browser.close()
        print("Service links, section navigation, and no-JavaScript fallback passed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:9001")
    parser.add_argument("--browser-executable")
    parser.add_argument("--screenshots")
    args = parser.parse_args()
    check(args.url, args.browser_executable, args.screenshots)
