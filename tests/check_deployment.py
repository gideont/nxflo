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
    print("Homepage redirect preserves queries; missing pages return 404; HTML compression active")


if __name__ == "__main__":
    # Run from the repository as a module so the shared libraries are available.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:9001")
    parser.add_argument("--alias-header", action="store_true", help="Test the bare-domain Host redirect on a local deployment")
    args = parser.parse_args()
    check(args.url, args.alias_header)
