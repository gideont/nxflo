"""Shared HTML rendering for the static build and hot-reload preview."""
from hashlib import sha256
from pathlib import Path
import re
from lib.seo import PAGES, SEO_INCLUDE, render_metadata

HEADER_INCLUDE = "<!-- include:site-header -->"
FOOTER_INCLUDE = "<!-- include:site-footer -->"


def render_page(source: str, page_name: str, root: Path) -> str:
    """Expand shared header/footer and mark the current primary navigation link."""
    for marker, name in ((HEADER_INCLUDE, "header"), (FOOTER_INCLUDE, "footer")):
        if source.count(marker) != 1:
            raise ValueError(f"{page_name} must include the shared {name} exactly once")

    header = (root / "lib/header.html").read_text(encoding="utf-8").strip()
    # Service detail pages belong to the Services section; utility pages have no
    # active link. The same mapping supplies metadata and both renderers.
    active_page = PAGES[page_name].navigation if page_name in PAGES else page_name
    header = re.sub(
        r'<a href="([^"]+)" data-nav="([^"]+)">',
        lambda match: match.group(0)[:-1] + ' class="is-active" aria-current="page">'
        if match.group(1) == active_page else match.group(0),
        header,
    )
    footer = (root / "lib/footer.html").read_text(encoding="utf-8").strip()
    result = source.replace(HEADER_INCLUDE, header).replace(FOOTER_INCLUDE, footer)
    if SEO_INCLUDE in result:
        if result.count(SEO_INCLUDE) != 1:
            raise ValueError(f"{page_name} must include search metadata exactly once")
        result = result.replace(SEO_INCLUDE, render_metadata(page_name))
    # Version shared code and page illustrations so browsers fetch fresh
    # content after redeployment instead of reusing stale cached assets.
    for asset in ("styles.css", "script.js", "images/about-collaboration.png",
                  "images/services-data-workflow.png",
                  "images/holographic-analytics-office.png"):
        if f'"{asset}"' not in result:
            continue
        version = sha256((root / asset).read_bytes()).hexdigest()[:12]
        result = result.replace(f'"{asset}"', f'"{asset}?v={version}"')
    return result
