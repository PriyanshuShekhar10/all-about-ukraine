#!/usr/bin/env python3
"""Resolve cross-links across all pages (Wikipedia-style).

- Builds a global alias -> slug map from all published pages.
- Links the FIRST mention of each target per page, writing [[slug|surface]]
  markers into the paragraph text (idempotent: strips old markers first).
- Computes links_out per page and a global backlink + category graph.
- Gated red links: any notable term (in terms.json) that is mentioned but has no
  page yet is re-queued (status -> "queued") to drive growth.

Usage: python wiki/resolve_links.py
"""

from __future__ import annotations

import re

from seed_terms import CATEGORIES
from wutil import DATA_WIKI, PAGES_DIR, load_terms, read_json, save_terms, write_json

TOKEN_RE = re.compile(r"\[\[([^\]|]+)\|([^\]]+)\]\]")
STOPWORDS = {
    "history", "war", "city", "state", "country", "people", "language",
    "government", "region", "area", "river", "north", "south", "east", "west",
    "national", "union", "party", "world", "european",
}
MIN_ALIAS_LEN = 4


def strip_tokens(text: str) -> str:
    return TOKEN_RE.sub(lambda m: m.group(2), text)


def load_pages() -> list[dict]:
    return [read_json(p) for p in sorted(PAGES_DIR.glob("*.json"))]


def build_alias_map(pages: list[dict]) -> dict[str, str]:
    """lower(alias) -> slug, for published pages only."""
    amap: dict[str, str] = {}
    for page in pages:
        slug = page["slug"]
        surfaces = [page["title"], *page.get("aliases", [])]
        for s in surfaces:
            key = s.lower().strip()
            if len(key) < MIN_ALIAS_LEN or key in STOPWORDS:
                continue
            # Prefer the shortest slug (canonical) if collision.
            if key not in amap:
                amap[key] = slug
    return amap


def build_pattern(alias_map: dict[str, str]) -> re.Pattern | None:
    if not alias_map:
        return None
    # Longest surfaces first so multi-word matches win.
    surfaces = sorted(alias_map.keys(), key=len, reverse=True)
    alt = "|".join(re.escape(s) for s in surfaces)
    return re.compile(rf"\b({alt})\b", re.IGNORECASE)


def link_page(page: dict, pattern: re.Pattern, alias_map: dict[str, str]) -> list[str]:
    self_slug = page["slug"]
    linked: set[str] = set()

    def repl(m: re.Match) -> str:
        surface = m.group(0)
        slug = alias_map.get(surface.lower())
        if not slug or slug == self_slug or slug in linked:
            return surface
        linked.add(slug)
        return f"[[{slug}|{surface}]]"

    for section in page.get("sections", []):
        section["paragraphs"] = [
            pattern.sub(repl, strip_tokens(p)) for p in section["paragraphs"]
        ]
    # Also link within the summary (counts toward first-mention).
    page["summary"] = pattern.sub(repl, strip_tokens(page.get("summary", "")))
    page["links_out"] = sorted(linked)
    return page["links_out"]


def main() -> int:
    pages = [p for p in load_pages() if p]
    print(f"Linking {len(pages)} page(s)…")
    alias_map = build_alias_map(pages)
    pattern = build_pattern(alias_map)
    if not pattern:
        print("No pages to link.")
        return 0

    backlinks: dict[str, list[str]] = {}
    categories: dict[str, list[str]] = {}

    for page in pages:
        links_out = link_page(page, pattern, alias_map)
        write_json(PAGES_DIR / f"{page['qid']}.json", page)
        for target in links_out:
            backlinks.setdefault(target, []).append(page["slug"])
        categories.setdefault(page["category"], []).append(page["slug"])

    for k in backlinks:
        backlinks[k] = sorted(set(backlinks[k]))
    for k in categories:
        categories[k] = sorted(set(categories[k]))

    # Explicit node/edge lists for the interactive knowledge-graph UI. Rebuilt
    # every resolve pass so the viz grows automatically with the corpus.
    edges = [
        {"source": page["slug"], "target": t}
        for page in pages
        for t in page.get("links_out", [])
    ]
    nodes = []
    for page in pages:
        slug = page["slug"]
        degree = len(page.get("links_out", [])) + len(backlinks.get(slug, []))
        nodes.append(
            {
                "id": slug,
                "title": page["title"],
                "category": page.get("category", "other"),
                "degree": degree,
            }
        )
    nodes.sort(key=lambda n: n["id"])

    write_json(
        DATA_WIKI / "graph.json",
        {
            "backlinks": backlinks,
            "categories": categories,
            "category_names": CATEGORIES,
            "nodes": nodes,
            "edges": edges,
        },
    )

    # Gated red links: notable terms mentioned but not yet published -> re-queue.
    terms = load_terms()
    published = {p["slug"] for p in pages}
    corpus = " ".join(
        strip_tokens(" ".join(pp for s in p.get("sections", []) for pp in s["paragraphs"]))
        for p in pages
    ).lower()
    requeued = 0
    for term in terms:
        if term["slug"] in published:
            continue
        if term.get("status") in ("gather_failed", "synth_failed"):
            continue
        names = [term["name"], *term.get("aliases", [])]
        if any(re.search(rf"\b{re.escape(n.lower())}\b", corpus) for n in names if len(n) >= MIN_ALIAS_LEN):
            if term.get("status") not in ("queued", "gathered"):
                term["status"] = "queued"
            requeued += 1
    save_terms(terms)

    print(f"  {sum(len(v) for v in backlinks.values())} links, "
          f"{len(categories)} categories, {requeued} red-link terms queued")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
