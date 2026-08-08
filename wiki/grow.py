#!/usr/bin/env python3
"""Grow the term dictionary by ADDING new entries, evenly across sections.

Each run asks OpenAI to propose notable, Ukraine-related topics for every
category, resolves them to real English Wikipedia articles (-> Wikidata QID),
drops anything already covered, and APPENDS the survivors to
``data-wiki/terms.json`` with status "queued". It never removes or rewrites
existing terms — ``run.py`` then gathers + synthesizes the freshly queued ones.

"Equally for each section" = the same target number of new entries per category
per run (``--per-category``, default 1).

Usage:
    python wiki/grow.py --per-category 1
    python wiki/grow.py --per-category 2 --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from wutil import load_env, load_terms, save_terms, slugify

from seed_terms import (
    CATEGORIES,
    fetch_entities,
    fetch_labels,
    instance_of,
    resolve_titles,
)

try:
    from openai import OpenAI
except ImportError:
    sys.exit("Run: pip install -r requirements.txt (need openai)")

MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

# Sections we grow (everything except the catch-all "other").
GROW_CATEGORIES = [c for c in CATEGORIES if c != "other"]

SYSTEM = (
    "You suggest real, notable English Wikipedia article titles about Ukraine "
    "for a Ukraine-focused encyclopedia. Every suggestion must be a genuine, "
    "existing Wikipedia article strongly connected to Ukraine. Respond with "
    "valid JSON only."
)


def propose(client: "OpenAI", category: str, cat_name: str,
            avoid: list[str], want: int) -> list[str]:
    """Ask the model for candidate Wikipedia titles for one category."""
    user = (
        f"Category: {cat_name}.\n"
        f"Propose {want} notable topics strongly connected to Ukraine that fit "
        "this category and each have their own English Wikipedia article. "
        "Prefer encyclopedic, well-known subjects (people, places, events, "
        "institutions, works, traditions, companies) specific to Ukraine. "
        "Use the exact English Wikipedia article title for each.\n"
        "Do NOT propose any of these already-covered titles:\n"
        f"{json.dumps(sorted(avoid), ensure_ascii=False)}\n\n"
        'Return JSON EXACTLY as: {"titles": [string, ...]}'
    )
    resp = client.chat.completions.create(
        model=MODEL,
        temperature=0.8,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user},
        ],
    )
    data = json.loads(resp.choices[0].message.content)
    titles = data.get("titles", [])
    return [t.strip() for t in titles if isinstance(t, str) and t.strip()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-category", type=int, default=1,
                    help="new entries to add per section each run")
    ap.add_argument("--dry-run", action="store_true",
                    help="propose + resolve only; do not write terms.json")
    args = ap.parse_args()

    load_env()
    if not os.environ.get("OPENAI_API_KEY"):
        sys.exit("OPENAI_API_KEY not found.")

    terms = load_terms()
    existing_qids = {t["qid"] for t in terms}
    existing_names = {t["name"].lower() for t in terms}
    for t in terms:
        existing_names.update(a.lower() for a in t.get("aliases", []))
    used_slugs = {t["slug"] for t in terms}

    client = OpenAI()
    per_cat = max(1, args.per_category)
    # Over-ask so we still hit the target after dedupe/resolution failures.
    want = max(per_cat * 5, 10)

    new_terms: list[dict] = []
    summary: dict[str, int] = {}

    for cat in GROW_CATEGORIES:
        cat_name = CATEGORIES[cat]
        avoid = sorted({t["name"] for t in terms if t["category"] == cat})[:120]
        try:
            candidates = propose(client, cat, cat_name, avoid, want)
        except Exception as e:  # noqa: BLE001
            print(f"  [{cat}] propose failed: {e}")
            summary[cat] = 0
            continue

        resolved = resolve_titles(candidates) if candidates else {}
        picks: list[tuple[str, str]] = []
        for title in candidates:
            qid = resolved.get(title)
            if not qid or qid in existing_qids or title.lower() in existing_names:
                continue
            picks.append((title, qid))
            existing_qids.add(qid)  # avoid dupes within this run
            if len(picks) >= per_cat:
                break

        if not picks:
            summary[cat] = 0
            print(f"  [{cat}] +0 (no new resolvable topics)")
            continue

        ents = fetch_entities([q for _, q in picks])
        type_qids = [tq for tq in (instance_of(e) for e in ents.values() if e) if tq]
        type_labels = fetch_labels(type_qids)

        added_here = 0
        for title, qid in picks:
            ent = ents.get(qid)
            if not ent:
                continue
            label = ent.get("labels", {}).get("en", {}).get("value") or title
            sitelinks = ent.get("sitelinks", {})
            wp = sitelinks.get("enwiki", {}).get("title")
            if not wp:  # need an English article to ground synthesis on
                continue
            aliases = [a["value"] for a in ent.get("aliases", {}).get("en", [])]
            t31 = instance_of(ent)
            slug = slugify(label)
            base, n = slug, 2
            while slug in used_slugs:
                slug, n = f"{base}-{n}", n + 1
            used_slugs.add(slug)
            existing_names.add(label.lower())
            new_terms.append(
                {
                    "qid": qid,
                    "slug": slug,
                    "name": label,
                    "wp_title": wp,
                    "type": type_labels.get(t31 or "", "topic"),
                    "category": cat,  # honor the requested section
                    "aliases": sorted(set(aliases)),
                    "notability": len(sitelinks),
                    "status": "queued",
                }
            )
            added_here += 1
        summary[cat] = added_here
        picked = ", ".join(t for t, _ in picks[:added_here])
        print(f"  [{cat}] +{added_here}: {picked}")

    total = sum(summary.values())
    if args.dry_run:
        print(f"\n[dry-run] would add {total} new term(s); terms.json unchanged.")
        return 0

    if not new_terms:
        print("\nNo new terms to add this run.")
        return 0

    terms.extend(new_terms)
    save_terms(terms)
    print(f"\nAdded {total} new term(s); terms.json now has {len(terms)}.")
    for cat in GROW_CATEGORIES:
        print(f"  {CATEGORIES[cat]:<24} +{summary.get(cat, 0)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
