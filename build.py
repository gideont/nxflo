#!/usr/bin/env python3
"""Build publishable static files from pages and shared header/footer templates."""
import argparse
from pathlib import Path
import shutil

from lib.site import render_page
from lib.seo import PAGES, SEO_INCLUDE, crawl_assets

ROOT = Path(__file__).resolve().parent
PORTAL_FILES = ("index.html", "portal.css", "portal.js", "dashboard.css", "dashboard.js", "icons.svg", "LUCIDE-LICENSE.txt")


def build(destination: Path) -> None:
    destination = destination.resolve()
    if destination == ROOT or ROOT.is_relative_to(destination):
        raise ValueError("Build output must not overwrite the source directory")
    # Render everything before writing, so a missing include fails the build.
    sources = {source.name: source.read_text(encoding="utf-8") for source in ROOT.glob("*.html")}
    if sources.keys() != PAGES.keys():
        raise ValueError("Every HTML page must have an entry in lib/seo.py, and every entry must have a page")
    if any(source.count(SEO_INCLUDE) != 1 for source in sources.values()):
        raise ValueError("Every page must include shared search metadata exactly once")
    pages = {
        name: render_page(source, name, ROOT)
        for name, source in sources.items()
    }
    # Publish only the login assets; the supplied reference contains demo records.
    portal = ROOT / "bms_integration_hub"
    for name in PORTAL_FILES:
        if not (portal / name).is_file():
            raise ValueError(f"Missing customer portal asset: {name}")
    destination.mkdir(parents=True, exist_ok=True)
    for name, content in pages.items():
        (destination / name).write_text(content, encoding="utf-8")
    for name, content in crawl_assets().items():
        (destination / name).write_text(content, encoding="utf-8")
    for name in ("styles.css", "script.js"):
        shutil.copy2(ROOT / name, destination / name)
    for directory in ("images", "fonts", "tools", "articles"):
        shutil.copytree(ROOT / directory, destination / directory, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("node_modules", "csv-src"))
    portal_output = destination / "bms_integration_hub"
    if portal_output.exists():
        shutil.rmtree(portal_output)
    portal_output.mkdir()
    for name in PORTAL_FILES:
        shutil.copy2(portal / name, portal_output / name)
    print(f"Built {len(pages)} pages with the shared header and footer in {destination}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    build(parser.parse_args().output)
