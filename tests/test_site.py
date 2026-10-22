from pathlib import Path
from tempfile import TemporaryDirectory
import re
import unittest

from lib.site import FOOTER_INCLUDE, HEADER_INCLUDE, render_page
from lib.seo import PAGES

ROOT = Path(__file__).resolve().parents[1]


class SharedLayoutTests(unittest.TestCase):
    def test_all_pages_include_shared_header_and_correct_active_link(self):
        for page in ROOT.glob("*.html"):
            with self.subTest(page=page.name):
                source = page.read_text()
                self.assertEqual(source.count(HEADER_INCLUDE), 1)
                self.assertNotIn('<header class="site-header">', source)
                rendered = render_page(source, page.name, ROOT)
                self.assertEqual(rendered.count('<header class="site-header">'), 1)
                navigation = PAGES[page.name].navigation
                if navigation is None:
                    self.assertNotIn('aria-current="page"', rendered)
                else:
                    key = "home" if navigation == "index.html" else Path(navigation).stem
                    self.assertIn(f'href="{navigation}" data-nav="{key}" class="is-active" aria-current="page"', rendered)

    def test_every_page_has_the_same_complete_footer(self):
        footers = []
        for page in ROOT.glob("*.html"):
            with self.subTest(page=page.name):
                source = page.read_text()
                self.assertEqual(source.count(FOOTER_INCLUDE), 1)
                self.assertNotIn('<footer', source)
                rendered = render_page(source, page.name, ROOT)
                footer = re.findall(r'<footer\b.*?</footer>', rendered, re.S)
                self.assertEqual(len(footer), 1)
                self.assertIn('href="tel:+16042609218"', footer[0])
                self.assertIn('+1 (604) 260-9218', footer[0])
                self.assertIn('href="mailto:sales@nxflo.com"', footer[0])
                self.assertIn('Vancouver, Canada. Internationally connected.', footer[0])
                self.assertIn('Vancouver, BC, Canada', footer[0])
                self.assertIn('BC Incorporation No. BC1535270', ' '.join(footer[0].split()))
                self.assertIn('images/vancouver-sketch.svg', footer[0])
                footers.append(footer[0])
        self.assertEqual(len(set(footers)), 1)

    def test_shared_template_edit_reaches_every_page(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "lib").mkdir()
            for asset in ("styles.css", "script.js"):
                (root / asset).write_text("initial")
            header = root / "lib/header.html"
            header.write_text('<header>Shared navigation update</header>')
            footer = root / "lib/footer.html"
            footer.write_text('<footer>Shared contact update</footer>')
            for name in ("index.html", "contact.html", "thanks.html"):
                rendered = render_page(HEADER_INCLUDE + FOOTER_INCLUDE, name, root)
                self.assertIn('Shared navigation update', rendered)
                self.assertIn('Shared contact update', rendered)
            footer.write_text('<footer>Updated everywhere</footer>')
            for name in ("index.html", "contact.html", "thanks.html"):
                self.assertIn('Updated everywhere', render_page(HEADER_INCLUDE + FOOTER_INCLUDE, name, root))

    def test_asset_urls_change_when_content_changes(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "lib").mkdir()
            (root / "lib/header.html").write_text('<header></header>')
            (root / "lib/footer.html").write_text('<footer></footer>')
            for asset in ("styles.css", "script.js"):
                (root / asset).write_text("old")
            source = HEADER_INCLUDE + FOOTER_INCLUDE + '<link href="styles.css"><script src="script.js"></script>'
            before = render_page(source, "index.html", root)
            (root / "styles.css").write_text("new")
            self.assertNotEqual(before, render_page(source, "index.html", root))

    def test_story_banner_urls_change_when_image_content_changes(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "lib").mkdir()
            (root / "images").mkdir()
            (root / "lib/header.html").write_text('<header></header>')
            (root / "lib/footer.html").write_text('<footer></footer>')
            for name in ("about-collaboration.png", "services-data-workflow.png"):
                image = root / "images" / name
                image.write_bytes(b"first image")
                source = HEADER_INCLUDE + FOOTER_INCLUDE + f'<img src="images/{name}">'
                before = render_page(source, "about.html", root)
                self.assertRegex(before, rf'images/{re.escape(name)}\?v=[0-9a-f]{{12}}')
                image.write_bytes(b"updated image")
                self.assertNotEqual(before, render_page(source, "about.html", root))

    def test_missing_or_duplicate_include_fails(self):
        for source in ("<main></main>", FOOTER_INCLUDE, HEADER_INCLUDE, HEADER_INCLUDE * 2 + FOOTER_INCLUDE, HEADER_INCLUDE + FOOTER_INCLUDE * 2):
            with self.assertRaises(ValueError):
                render_page(source, "index.html", ROOT)
