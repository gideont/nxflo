from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from lib.site import HEADER_INCLUDE, render_page

ROOT = Path(__file__).resolve().parents[1]


class SharedHeaderTests(unittest.TestCase):
    def test_all_pages_include_shared_header_and_correct_active_link(self):
        for page in ROOT.glob("*.html"):
            with self.subTest(page=page.name):
                source = page.read_text()
                self.assertEqual(source.count(HEADER_INCLUDE), 1)
                self.assertNotIn('<header class="site-header">', source)
                rendered = render_page(source, page.name, ROOT)
                self.assertEqual(rendered.count('<header class="site-header">'), 1)
                if page.name == "thanks.html":
                    self.assertNotIn('aria-current="page"', rendered)
                else:
                    self.assertIn(f'href="{page.name}" data-nav="{page.stem if page.stem != "index" else "home"}" class="is-active" aria-current="page"', rendered)

    def test_shared_template_edit_reaches_every_page(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "lib").mkdir()
            for asset in ("styles.css", "script.js"):
                (root / asset).write_text("initial")
            header = root / "lib/header.html"
            header.write_text('<header>Shared navigation update</header>')
            for name in ("index.html", "contact.html", "thanks.html"):
                self.assertIn('Shared navigation update', render_page(HEADER_INCLUDE, name, root))

    def test_asset_urls_change_when_content_changes(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "lib").mkdir()
            (root / "lib/header.html").write_text('<header></header>')
            for asset in ("styles.css", "script.js"):
                (root / asset).write_text("old")
            source = HEADER_INCLUDE + '<link href="styles.css"><script src="script.js"></script>'
            before = render_page(source, "index.html", root)
            (root / "styles.css").write_text("new")
            self.assertNotEqual(before, render_page(source, "index.html", root))

    def test_missing_or_duplicate_include_fails(self):
        for source in ("<main></main>", HEADER_INCLUDE * 2):
            with self.assertRaises(ValueError):
                render_page(source, "index.html", ROOT)
