#!/usr/bin/env python3
"""Arrange the Ukraine data into an archive-website-ready structure.

The scrape produced 44 files that resolve to only TWO unique articles:
  * the main "Ukraine" country overview, and
  * the "Russia-Ukraine War" article.

This script keeps the two unique articles as real, cleaned pages and turns every
topical filename into an *alias/topic* that points at its canonical article.
The result is a structure any static-site/archive generator can consume:

    archive/
      manifest.json          # sections -> topics(aliases) -> canonical article
      articles/
        ukraine-overview.md
        russia-ukraine-war.md

It reuses the classification produced by `build_index.py` (index.json). Run
that first; no OpenAI call is made here.

Usage:
    python build_index.py       # once, to create index.json
    python arrange_archive.py
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data-ukraine"
INDEX_JSON = ROOT / "index.json"
OUT_DIR = ROOT / "archive"
ARTICLES_DIR = OUT_DIR / "articles"

# Canonical articles. Each entry defines how to recognize the article from a
# document body and the metadata for its cleaned page.
CANONICAL = {
    "russia-ukraine-war": {
        "title": "Russia\u2013Ukraine War",
        "match": ("special military operation", "Battle of Kyiv", "the war in the Donbas"),
    },
    "ukraine-overview": {
        "title": "Ukraine: Country Overview",
        "match": (),  # default fallback
    },
}

# Ordering for sections in the manifest (mirrors build_index.py).
SECTION_ORDER = [
    "Overview & Quick Facts",
    "Land & Geography",
    "People, Society & Religion",
    "Culture & Arts",
    "Economy & Industry",
    "Government & Politics",
    "History: Early & Medieval",
    "History: Imperial & Soviet Era",
    "History: Independence & Modern",
    "Russia\u2013Ukraine War",
    "Other",
]

# --- Cleaning ---------------------------------------------------------------

JUNK_SUBSTRINGS = (
    "cdn.britannica.com",
    "premium.britannica.com",
    "subscribe",
    "britannica quiz",
    "about-britannica-ai",
    "ai-generated answers",
    "ai makes mistakes",
    "the trusted destination",
    "national anthem of ukraine",
    "audio file:",
)


def clean_body(md: str) -> str:
    """Remove scrape boilerplate/marketing so the archive page is clean."""
    out: list[str] = []
    for line in md.splitlines():
        low = line.strip().lower()
        if not low:
            out.append("")
            continue
        if any(j in low for j in JUNK_SUBSTRINGS):
            continue
        if low in ("news \u2022", "## news \u2022", "top questions"):
            continue
        out.append(line)
    text = "\n".join(out)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


def slugify(text: str) -> str:
    s = text.strip().lower()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_]+", "-", s)
    return re.sub(r"-{2,}", "-", s).strip("-")


def canonical_for(body: str) -> str:
    for cid, meta in CANONICAL.items():
        if any(token.lower() in body.lower() for token in meta["match"]):
            return cid
    return "ukraine-overview"


# --- Main -------------------------------------------------------------------


def main() -> int:
    if not INDEX_JSON.exists():
        sys.exit("index.json not found. Run `python build_index.py` first.")
    entries = json.loads(INDEX_JSON.read_text(encoding="utf-8"))

    # Determine the canonical article for each source file and write the two
    # cleaned canonical pages (using the first file seen for each).
    if ARTICLES_DIR.exists():
        shutil.rmtree(OUT_DIR)
    ARTICLES_DIR.mkdir(parents=True, exist_ok=True)

    written_articles: dict[str, dict] = {}
    file_to_canonical: dict[str, str] = {}

    for e in entries:
        src = DATA_DIR / e["file"]
        raw = src.read_text(encoding="utf-8")
        cid = canonical_for(raw)
        file_to_canonical[e["file"]] = cid
        if cid not in written_articles:
            cleaned = clean_body(raw)
            title = CANONICAL[cid]["title"]
            page = f"# {title}\n\n{cleaned}\n"
            (ARTICLES_DIR / f"{cid}.md").write_text(page, encoding="utf-8")
            written_articles[cid] = {
                "id": cid,
                "title": title,
                "path": f"articles/{cid}.md",
                "source_files": [],
            }
        written_articles[cid]["source_files"].append(e["file"])

    # Build sections -> topics(aliases).
    sections: dict[str, list[dict]] = {}
    used_slugs: set[str] = set()
    for e in entries:
        slug = slugify(e["title"])
        base = slug
        n = 2
        while slug in used_slugs:
            slug = f"{base}-{n}"
            n += 1
        used_slugs.add(slug)
        topic = {
            "title": e["title"],
            "slug": slug,
            "summary": e.get("summary", ""),
            "tags": e.get("tags", []),
            "article": file_to_canonical[e["file"]],
            "source_file": e["file"],
        }
        sections.setdefault(e["section"], []).append(topic)

    rank = {s: i for i, s in enumerate(SECTION_ORDER)}
    ordered_sections = [
        {
            "id": slugify(name),
            "title": name,
            "topics": sorted(topics, key=lambda t: t["title"].lower()),
        }
        for name, topics in sorted(sections.items(), key=lambda kv: rank.get(kv[0], 999))
    ]

    manifest = {
        "title": "All About Ukraine \u2014 Archive",
        "description": "An archive of encyclopedic material about Ukraine, organized by section.",
        "counts": {
            "topics": len(entries),
            "sections": len(ordered_sections),
            "canonical_articles": len(written_articles),
        },
        "articles": [written_articles[c] for c in CANONICAL if c in written_articles],
        "sections": ordered_sections,
    }
    (OUT_DIR / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"Canonical articles written to {ARTICLES_DIR.relative_to(ROOT)}/:")
    for c, a in written_articles.items():
        print(f"  - {a['path']}  <- {len(a['source_files'])} source file(s)")
    print(f"\nSections ({len(ordered_sections)}):")
    for s in ordered_sections:
        print(f"  - {s['title']}: {len(s['topics'])} topic(s)")
    print(f"\nManifest: {(OUT_DIR / 'manifest.json').relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
