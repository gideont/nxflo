"""Shared HTML rendering for the static build and hot-reload preview."""
from hashlib import sha256
from pathlib import Path
import re

HEADER_INCLUDE = "<!-- include:site-header -->"


def render_page(source: str, page_name: str, root: Path) -> str:
    """Expand one shared header and mark only a matching navigation destination."""
    if source.count(HEADER_INCLUDE) != 1:
        raise ValueError(f"{page_name} must include the shared header exactly once")

    header = (root / "lib/header.html").read_text(encoding="utf-8").strip()
    # Determine the active page from the shared links, not a second list of routes.
    header = re.sub(
        r'<a href="([^"]+)" data-nav="([^"]+)">',
        lambda match: match.group(0)[:-1] + ' class="is-active" aria-current="page">'
        if match.group(1) == page_name else match.group(0),
        header,
    )
    result = source.replace(HEADER_INCLUDE, header)
    # A changed stylesheet or script gets a new URL so old browser caches cannot
    # leave one page displaying a previous header design after redeployment.
    for asset in ("styles.css", "script.js"):
        version = sha256((root / asset).read_bytes()).hexdigest()[:12]
        result = result.replace(f'"{asset}"', f'"{asset}?v={version}"')
    return result
