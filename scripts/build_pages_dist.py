#!/usr/bin/env python3
"""Build a minimal static bundle for GitHub Pages deployment."""

from __future__ import annotations

import re
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = ROOT / "dist-pages"
REQUIRED_FILES = [
    ROOT / "index.html",
    ROOT / "app" / "index.html",
    ROOT / "app" / "app.js",
    ROOT / "app" / "browser_pipeline.js",
    ROOT / "app" / "browser_data.js",
    # Built by scripts/build_align_table.py; loaded lazily for syllable-split suggestions.
    ROOT / "app" / "browser_align.js",
    ROOT / "app" / "styles.css",
]

APP_INDEX_REL = Path("app/index.html")


def _set_static_only_meta(html: str) -> str:
    pattern = re.compile(r'(<meta\s+name="app-static-only"\s+content=")([^"]*)("\s*/?>)', re.IGNORECASE)
    if pattern.search(html):
        return pattern.sub(r'\1on\3', html, count=1)

    viewport_pattern = re.compile(r'(<meta\s+name="viewport"[^>]*>\s*)', re.IGNORECASE)
    if viewport_pattern.search(html):
        return viewport_pattern.sub(r'\1    <meta name="app-static-only" content="on">\n', html, count=1)

    return html


def _set_csp_connect_none(html: str) -> str:
    csp_pattern = re.compile(
        r'(<meta\s+http-equiv="Content-Security-Policy"\s+content=")([^"]*)("\s*/?>)',
        re.IGNORECASE,
    )
    match = csp_pattern.search(html)
    if not match:
        return html

    csp = match.group(2)
    directives = [segment.strip() for segment in csp.split(";") if segment.strip()]
    updated: list[str] = []
    has_connect_src = False

    for directive in directives:
        head = directive.split(" ", 1)[0].strip().lower()
        if head == "connect-src":
            updated.append("connect-src 'none'")
            has_connect_src = True
        else:
            updated.append(directive)

    if not has_connect_src:
        updated.append("connect-src 'none'")

    next_csp = "; ".join(updated)
    return f"{match.group(1)}{next_csp}{match.group(3)}".join([html[: match.start()], html[match.end() :]])


def _harden_pages_index(dist_app_index: Path) -> None:
    raw = dist_app_index.read_text(encoding="utf-8")
    next_text = _set_static_only_meta(raw)
    next_text = _set_csp_connect_none(next_text)
    dist_app_index.write_text(next_text, encoding="utf-8")


def main() -> None:
    missing = [path for path in REQUIRED_FILES if not path.exists()]
    if missing:
        names = ", ".join(str(path.relative_to(ROOT)) for path in missing)
        raise FileNotFoundError(f"Missing required build input(s): {names}")

    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    DIST_DIR.mkdir(parents=True, exist_ok=True)

    for source_path in REQUIRED_FILES:
        rel = source_path.relative_to(ROOT)
        target = DIST_DIR / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target)

    _harden_pages_index(DIST_DIR / APP_INDEX_REL)

    (DIST_DIR / ".nojekyll").write_text("", encoding="utf-8")
    print(f"Built GitHub Pages bundle at: {DIST_DIR}")


if __name__ == "__main__":
    main()
