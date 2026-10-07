#!/usr/bin/env python3
"""Build publishable static files from the pages and shared header."""
import argparse
from pathlib import Path
import shutil

from lib.site import render_page

ROOT = Path(__file__).resolve().parent


def build(destination: Path) -> None:
    destination = destination.resolve()
    if destination == ROOT or ROOT.is_relative_to(destination):
        raise ValueError("Build output must not overwrite the source directory")
    # Render everything before writing, so a missing include fails the build.
    pages = {
        source.name: render_page(source.read_text(encoding="utf-8"), source.name, ROOT)
        for source in ROOT.glob("*.html")
    }
    destination.mkdir(parents=True, exist_ok=True)
    for name, content in pages.items():
        (destination / name).write_text(content, encoding="utf-8")
    for name in ("styles.css", "script.js"):
        shutil.copy2(ROOT / name, destination / name)
    shutil.copytree(ROOT / "images", destination / "images", dirs_exist_ok=True)
    print(f"Built {len(pages)} pages with the shared header in {destination}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    build(parser.parse_args().output)
