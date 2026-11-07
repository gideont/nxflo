"""Check the generated search surface, including crawl paths and real links."""
from html.parser import HTMLParser
from hashlib import sha256
import json
from pathlib import Path
import re
import unittest
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree

from lib.seo import PAGES, SEO_INCLUDE, SITE_URL, canonical_url, crawl_assets
from lib.site import render_page

ROOT = Path(__file__).resolve().parents[1]


class Document(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.elements = []
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))

    def attributes(self, tag, key, value):
        return [attrs for element, attrs in self.elements if element == tag and attrs.get(key) == value]


class SearchTests(unittest.TestCase):
    def test_homepage_uses_versioned_engineering_image(self):
        name = "index.html"
        asset = "images/engineering-collaboration.webp"
        source = (ROOT / name).read_text()
        rendered = render_page(source, name, ROOT)
        document = Document(rendered)
        version = sha256((ROOT / asset).read_bytes()).hexdigest()[:12]

        self.assertEqual(PAGES[name].image, asset)
        self.assertEqual(document.attributes("img", "src", f"{asset}?v={version}"), [{
            "src": f"{asset}?v={version}",
            "srcset": "images/engineering-collaboration-768.webp 768w, images/engineering-collaboration.webp 1536w",
            "sizes": "(max-width: 800px) calc(100vw - 40px), 50vw",
            "width": "1536",
            "height": "1024",
            "fetchpriority": "high",
            "alt": "Professionals reviewing data analysis together at a workspace overlooking Vancouver.",
        }])
        self.assertEqual(
            document.attributes("meta", "property", "og:image"),
            [{"property": "og:image", "content": f"{SITE_URL}/{asset}"}],
        )

    def test_registry_covers_real_pages_and_metadata_is_unique(self):
        self.assertEqual(set(PAGES), {page.name for page in ROOT.glob("*.html")})
        self.assertEqual(len(PAGES), len({page.title for page in PAGES.values()}))
        self.assertEqual(len(PAGES), len({page.description for page in PAGES.values()}))
        for name, page in PAGES.items():
            with self.subTest(page=name):
                source = (ROOT / name).read_text()
                self.assertEqual(source.count(SEO_INCLUDE), 1)
                rendered = render_page(source, name, ROOT)
                document = Document(rendered)
                self.assertEqual(len(re.findall(r"<title>.*?</title>", rendered)), 1)
                self.assertEqual(sum(tag == "h1" for tag, _ in document.elements), 1)
                self.assertEqual(document.attributes("meta", "name", "description"), [{"name": "description", "content": page.description}])
                self.assertEqual(document.attributes("link", "rel", "canonical"), [{"rel": "canonical", "href": canonical_url(name)}])
                robots = document.attributes("meta", "name", "robots")
                self.assertEqual(len(robots), 1)
                self.assertIn("index, follow" if page.indexable else "noindex, follow", robots[0]["content"])
                self.assertTrue((ROOT / page.image).is_file(), page.image)
                self.assertEqual(document.attributes("meta", "property", "og:url")[0]["content"], canonical_url(name))

    def test_structured_data_is_valid_and_matches_visible_business_details(self):
        for name, page in PAGES.items():
            with self.subTest(page=name):
                rendered = render_page((ROOT / name).read_text(), name, ROOT)
                blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', rendered, re.S)
                self.assertEqual(len(blocks), 1)
                graph = json.loads(blocks[0])["@graph"]
                organization = next(item for item in graph if item["@type"] == "Organization")
                self.assertEqual(organization["telephone"], "+16042609218")
                self.assertEqual(organization["email"], "sales@nxflo.com")
                self.assertEqual(organization["address"]["addressLocality"], "Vancouver")
                self.assertNotIn("aggregateRating", organization)
                services = [item for item in graph if item["@type"] == "Service"]
                self.assertEqual(len(services), int(page.service is not None))
                if page.service:
                    self.assertEqual(services[0]["name"], page.service)
                    breadcrumb = next(item for item in graph if item["@type"] == "BreadcrumbList")
                    self.assertEqual(breadcrumb["itemListElement"][-1]["item"], canonical_url(name))

    def test_sitemap_contains_only_existing_indexable_canonical_urls(self):
        assets = crawl_assets()
        tree = ElementTree.fromstring(assets["sitemap.xml"])
        urls = [element.text for element in tree.findall("{*}url/{*}loc")]
        self.assertEqual(set(urls), {canonical_url(name) for name, page in PAGES.items() if page.indexable})
        self.assertEqual(len(urls), len(set(urls)))
        self.assertIn(SITE_URL + "/sitemap.xml", assets["robots.txt"])
        self.assertNotIn("Disallow: /", assets["robots.txt"])
        self.assertNotIn("thanks.html", assets["sitemap.xml"])

    def test_local_links_assets_and_fragments_have_real_destinations(self):
        documents = {name: Document(render_page((ROOT / name).read_text(), name, ROOT)) for name in PAGES}
        ids = {name: {attrs["id"] for _, attrs in document.elements if "id" in attrs} for name, document in documents.items()}
        for name, document in documents.items():
            for tag, attrs in document.elements:
                for attribute in ("href", "src"):
                    target = attrs.get(attribute)
                    if not target:
                        continue
                    url = urlsplit(target)
                    if url.scheme or url.netloc:
                        continue
                    path = unquote(url.path).lstrip("/") or name
                    with self.subTest(page=name, target=target):
                        self.assertTrue((ROOT / path).is_file(), target)
                        if url.fragment and path.endswith(".html"):
                            self.assertIn(url.fragment, ids[path])

    def test_service_pages_are_discoverable_from_the_hub(self):
        hub = Document((ROOT / "services.html").read_text())
        links = {attrs.get("href") for tag, attrs in hub.elements if tag == "a"}
        for name, page in PAGES.items():
            if page.service:
                self.assertIn(name, links)
                source = (ROOT / name).read_text()
                self.assertIn('class="service-breadcrumb"', source)
                self.assertNotIn("<form", source)
