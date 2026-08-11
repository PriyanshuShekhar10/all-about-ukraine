#!/usr/bin/env python3
"""Export published pages + graph into the Astro app (web/src/data/wiki/).

Produces:
  web/src/data/wiki/pages/<slug>.json   one file per page
  web/src/data/wiki/index.json          lightweight list for portal/search/A-Z
  web/src/data/wiki/graph.json          backlinks + nodes/edges for the knowledge graph
  web/src/data/wiki/redirects.json      alias -> slug

Usage: python wiki/export.py
"""

from __future__ import annotations

import shutil

from wutil import DATA_WIKI, PAGES_DIR, ROOT, read_json, write_json

WEB_WIKI = ROOT / "web" / "src" / "data" / "wiki"
WEB_PAGES = WEB_WIKI / "pages"


def main() -> int:
    if WEB_PAGES.exists():
        shutil.rmtree(WEB_PAGES)
    WEB_PAGES.mkdir(parents=True, exist_ok=True)

    pages = [read_json(p) for p in sorted(PAGES_DIR.glob("*.json"))]
    pages = [p for p in pages if p]

    index = []
    redirects: dict[str, str] = {}
    for page in pages:
        write_json(WEB_PAGES / f"{page['slug']}.json", page)
        index.append(
            {
                "slug": page["slug"],
                "title": page["title"],
                "type": page.get("type", ""),
                "category": page.get("category", "other"),
                "summary": page.get("summary", ""),
                "aliases": page.get("aliases", []),
            }
        )
        for alias in page.get("aliases", []):
            a_slug = alias.lower().replace(" ", "-")
            if a_slug and a_slug != page["slug"] and a_slug not in redirects:
                redirects[a_slug] = page["slug"]

    index.sort(key=lambda e: e["title"].lower())
    write_json(WEB_WIKI / "index.json", index)
    write_json(WEB_WIKI / "redirects.json", redirects)

    graph = read_json(DATA_WIKI / "graph.json", default={"backlinks": {}, "categories": {}, "category_names": {}})
    write_json(WEB_WIKI / "graph.json", graph)

    print(f"Exported {len(pages)} pages, {len(redirects)} redirects to web/src/data/wiki/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
