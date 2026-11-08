"""Verify deployed content, crawl assets, canonical redirects, and real 404s."""
import argparse
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from lib.seo import PAGES, SITE_URL, crawl_assets
from lib.site import render_page

ROOT = Path(__file__).resolve().parents[1]


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def check(url, alias_header=False):
    opener = build_opener(NoRedirect())
    base = url.rstrip("/")

    def fetch(path, headers=None):
        try:
            response = opener.open(Request(base + path, headers=headers or {}), timeout=20)
        except HTTPError as response_error:
            response = response_error
        with response:
            return response.status, response.headers, response.read()

    for name in PAGES:
        path = "/" if name == "index.html" else "/" + name
        status, _, content = fetch(path)
        assert status == 200, (path, status)
        expected = render_page((ROOT / name).read_text(), name, ROOT).encode()
        assert content == expected, f"Deployment differs from source: {name}"
        print(f"{base}{path}: 200, matches current source")
    for name in ("images/beaver-architect.webp", "styles.css", "script.js", "tools/admin.js", "tools/article-generator.js", "tools/document-preview.js", "tools/vendor/paged-0.4.3.min.js", "tools/vendor/PAGED-LICENSE.txt", "tools/generator-timing.js", "tools/generator-cost.js", "tools/generator-sources.js", "tools/pdf-combiner.js", "tools/csv-viewer.js", "tools/csv-viewer.css", "tools/csv-viewer-LICENSES.txt", "tools/vendor/pdf-lib-1.17.1.min.js", "tools/vendor/PDF-LIB-LICENSE.md"):
        status, _, content = fetch("/" + name)
        assert status == 200 and content == (ROOT / name).read_bytes(), f"Asset differs from source: {name}"
        print(f"{name}: 200, matches current source")
    for name in ("articles/Nexusflow_ETL_Dashboard_Process_Playbook.pdf", "images/articles/etl-dashboard-playbook-cover.webp", "images/articles/etl-runway-scenarios.webp", "images/articles/etl-refresh-cost.webp", "tools/article-payback.js", "tools/article-reporting-time.js", "articles/Nexusflow_Stale_by_Thursday_Report.pdf", "images/articles/stale-by-thursday-cover.webp", "images/articles/manual-reporting-time.webp", "images/articles/automation-payback.webp"):
        status, _, content = fetch("/" + name)
        assert status == 200 and content == (ROOT / name).read_bytes(), f"Article asset differs from source: {name}"
        print(f"{name}: 200, matches current source")
    for name, expected in crawl_assets().items():
        status, _, content = fetch("/" + name)
        assert status == 200 and content.decode() == expected, name
        print(f"{name}: 200, matches registered crawl URLs")
    status, headers, _ = fetch("/index.html?source=seo-check")
    assert status == 301 and headers["Location"] == "/?source=seo-check", (status, headers)
    status, _, _ = fetch("/missing-seo-page.html")
    assert status == 404, f"Missing page returned {status}"
    status, headers, _ = fetch("/services.html", {"Accept-Encoding": "gzip"})
    assert status == 200 and headers.get("Content-Encoding") == "gzip", "HTML compression not active"
    if alias_header:
        status, headers, _ = fetch("/bms-data-integration.html?source=seo-check", {"Host": "nxflo.com"})
        assert status == 301 and headers["Location"] == SITE_URL + "/bms-data-integration.html?source=seo-check", (status, headers)
    # Keep the customer portal separate from the public marketing site.
    for path in ("/bms_integration_hub", "/bms_integration_hub/", "/bms_integration_hub/index.html"):
        status, headers, content = fetch(path)
        assert status == 200, (path, status)
        assert content == (ROOT / "bms_integration_hub/index.html").read_bytes(), path
        assert "noindex" in headers.get("X-Robots-Tag", ""), path
        assert headers.get("Cache-Control") == "no-store", path
        assert headers.get("Referrer-Policy") == "strict-origin-when-cross-origin", path
        print(f"{base}{path}: standalone login, noindex, matches source")
    for name in ("portal.css", "portal.js", "dashboard.css", "dashboard.js", "icons.svg", "LUCIDE-LICENSE.txt"):
        status, headers, content = fetch("/bms_integration_hub/" + name)
        assert status == 200 and content == (ROOT / "bms_integration_hub" / name).read_bytes(), name
        assert "noindex" in headers.get("X-Robots-Tag", ""), name
    for name in ("BMS_Integration_Hub_Homepage.html", "README.md", "missing.html"):
        status, headers, _ = fetch("/bms_integration_hub/" + name)
        assert status == 404, (name, status)
        assert "noindex" in headers.get("X-Robots-Tag", ""), name
    status, headers, content = fetch("/")
    assert "noindex" not in headers.get("X-Robots-Tag", ""), "Portal rules leaked to the main site"
    assert b"bms_integration_hub" not in content, "Main site links to customer portal"
    _, _, sitemap = fetch("/sitemap.xml")
    assert b"bms_integration_hub" not in sitemap, "Portal is listed in the public sitemap"
    status, headers, content = fetch("/bms_integration_hub/api/health")
    assert status == 200 and b'"ok"' in content, "Portal API is unhealthy"
    for path in ("/admin/generator", "/admin/analytics", "/me", "/projects", "/workspace", "/admin/users", "/admin/roles", "/admin/permissions", "/admin/projects", "/admin/audit"):
        status, headers, _ = fetch("/bms_integration_hub/api" + path)
        assert status == 401, (path, status)
        assert "noindex" in headers.get("X-Robots-Tag", ""), path
    print("Portal API healthy; anonymous project and administration requests are denied")
    print("Portal assets verified; reference/demo files unavailable; public homepage and sitemap remain separate")
    print("Homepage redirect preserves queries; missing pages return 404; HTML compression active")


if __name__ == "__main__":
    # Run from the repository as a module so the shared libraries are available.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:9001")
    parser.add_argument("--alias-header", action="store_true", help="Test the bare-domain Host redirect on a local deployment")
    args = parser.parse_args()
    check(args.url, args.alias_header)
