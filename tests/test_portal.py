from functools import partial
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen

from build import build, PORTAL_FILES
from dev_server import HotReloadHandler, HotReloadState, ThreadingTCPServer
from lib.seo import PAGES, crawl_assets

ROOT = Path(__file__).resolve().parents[1]


class PortalPackagingTests(unittest.TestCase):
    def test_only_login_assets_are_published_and_portal_is_not_advertised(self):
        with TemporaryDirectory() as directory:
            output = Path(directory)
            # A stale reference must not survive a subsequent build.
            (output / "bms_integration_hub").mkdir()
            (output / "bms_integration_hub" / "old-demo.html").write_text("sample records")
            build(output)
            portal = output / "bms_integration_hub"
            self.assertEqual({p.name for p in portal.iterdir()}, set(PORTAL_FILES))
            self.assertIn('content="noindex, nofollow, noarchive, nosnippet"', (portal / "index.html").read_text())
            self.assertNotIn("DEMO_PROJECTS", (portal / "portal.js").read_text())
            for page in PAGES:
                self.assertNotIn("bms_integration_hub", (output / page).read_text())
            self.assertNotIn("bms_integration_hub", crawl_assets()["sitemap.xml"])


class PortalPreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        class QuietHandler(HotReloadHandler):
            def log_message(self, *args):
                pass
        handler = partial(QuietHandler, directory=str(ROOT), reload_state=HotReloadState(ROOT))
        cls.server = ThreadingTCPServer(("127.0.0.1", 0), handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def test_preview_routes_are_standalone_and_noindex(self):
        for path in ("/bms_integration_hub", "/bms_integration_hub/", "/bms_integration_hub/index.html"):
            with self.subTest(path=path), urlopen(self.base + path) as response:
                self.assertEqual(response.status, 200)
                self.assertIn("noindex", response.headers["X-Robots-Tag"])
                self.assertEqual(response.headers["Cache-Control"], "no-store")
                body = response.read().decode()
                self.assertIn("Sign in | BMS Integration Hub", body)
                self.assertNotIn('class="site-header"', body)
                self.assertNotIn('class="site-footer"', body)
        with self.assertRaises(HTTPError) as error:
            urlopen(self.base + "/bms_integration_hub/BMS_Integration_Hub_Homepage.html")
        self.assertEqual(error.exception.code, 404)
