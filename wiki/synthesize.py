#!/usr/bin/env python3
"""Grounded synthesis: turn gathered sources into clean, structured page JSON.

Uses the OpenAI API, grounded strictly on the gathered Wikipedia text, to
paraphrase into an encyclopedic page (lead + sections). The infobox comes
deterministically from Wikidata (from gather.py), so figures are never lost.
Links are added later by resolve_links.py (deterministic), so the model is told
NOT to add links.

Writes data-wiki/pages/<qid>.json and sets status "synthesized".

Usage: python wiki/synthesize.py [--limit N]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys

from wutil import PAGES_DIR, cache_path, load_env, load_terms, read_json, save_terms, write_json

try:
    from openai import OpenAI
except ImportError:
    sys.exit("Run: pip install -r requirements.txt (need openai)")

MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

SYSTEM = (
    "You are an editor for a Ukraine-focused encyclopedia. You rewrite source "
    "material into a neutral, factual entry in your own words, preserving every "
    "fact, figure, name, and date exactly, and emphasizing the subject's "
    "relevance to Ukraine. You respond with valid JSON only."
)


def prompt(term: dict, source: dict) -> str:
    return (
        f"Write an encyclopedia entry about: {term['name']} ({term.get('type','topic')}).\n\n"
        "RULES:\n"
        "1. Base it ONLY on the source text below; do not invent facts.\n"
        "2. Paraphrase in original wording; preserve all facts, figures, dates, names.\n"
        "3. Neutral, encyclopedic tone. No first/second person.\n"
        "4. Do NOT include any hyperlinks, URLs, or markup — plain prose only.\n"
        "5. Organize into 3-6 thematic sections with short headings.\n"
        "6. This is a Ukraine-focused encyclopedia: emphasize the subject's "
        "connection to Ukraine and its Ukrainian context.\n\n"
        "Return JSON EXACTLY as:\n"
        "{\n"
        '  "summary": string,   // 1-3 sentence lead defining the subject\n'
        '  "sections": [ { "heading": string, "paragraphs": [string, ...] } ]\n'
        "}\n\n"
        f"SOURCE TEXT:\n\"\"\"\n{source['extract']}\n\"\"\""
    )


def synthesize(client: OpenAI, term: dict, source: dict) -> dict:
    resp = client.chat.completions.create(
        model=MODEL,
        temperature=0.4,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": prompt(term, source)},
        ],
    )
    return json.loads(resp.choices[0].message.content)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="0 = all gathered")
    args = ap.parse_args()

    load_env()
    if not os.environ.get("OPENAI_API_KEY"):
        sys.exit("OPENAI_API_KEY not found.")

    terms = load_terms()
    pending = [t for t in terms if t.get("status") == "gathered"]
    if args.limit:
        pending = pending[: args.limit]
    print(f"Synthesizing {len(pending)} page(s) with {MODEL}…")

    client = OpenAI()
    today = dt.date.today().isoformat()

    for i, term in enumerate(pending, 1):
        qid = term["qid"]
        source = read_json(cache_path(qid, "gather.json"))
        if not source:
            term["status"] = "gather_failed"
            continue
        try:
            result = synthesize(client, term, source)
            page = {
                "qid": qid,
                "slug": term["slug"],
                "title": term["name"],
                "type": term.get("type", "topic"),
                "category": term.get("category", "other"),
                "aliases": term.get("aliases", []),
                "infobox": {"label": term.get("type", ""), "fields": source.get("infobox", [])},
                "summary": result.get("summary", ""),
                "sections": result.get("sections", []),
                "links_out": [],
                "sources": [
                    {
                        "title": f"{source['wp_title']} — Wikipedia",
                        "url": source["url"],
                        "license": "CC BY-SA 4.0",
                    }
                ],
                "updated_at": today,
                "status": "published",
            }
            write_json(PAGES_DIR / f"{qid}.json", page)
            term["status"] = "synthesized"
            print(f"  [{i}/{len(pending)}] {term['name']} ({len(page['sections'])} sections)")
        except Exception as e:  # noqa: BLE001
            print(f"  [{i}/{len(pending)}] FAILED {term['name']}: {e}")
            term["status"] = "synth_failed"

    save_terms(terms)
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
