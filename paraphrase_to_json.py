#!/usr/bin/env python3
"""Paraphrase every markdown file and emit clean, website-ready JSON.

For each file in the data folder this script:
  1. Strips markdown/HTML links, images, and any Britannica references/boilerplate.
  2. Uses the OpenAI API to paraphrase the text in fresh wording while keeping
     every fact, figure, name, and date intact.
  3. Stores the result as structured JSON (title, summary, sections/paragraphs).

The scrape contains many byte-identical files, so paraphrasing is
duplicate-aware: each unique body is sent to the API only once and the result is
reused for every file that shares it (saving time and tokens). Every source file
still gets its own entry in the output.

Output: content.json

Usage:
    python paraphrase_to_json.py
    OPENAI_MODEL=gpt-4o-mini python paraphrase_to_json.py
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

try:
    from openai import OpenAI
except ImportError:
    sys.exit("The 'openai' package is required. Run: pip install -r requirements.txt")

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / os.environ.get("DATA_DIR", "data-ukraine")
INDEX_JSON = ROOT / "index.json"          # optional metadata (section/title/tags)
OUT_JSON = ROOT / os.environ.get("OUT_JSON", "content.json")
MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
MAX_WORKERS = int(os.environ.get("MAX_WORKERS", "4"))

# --- .env loader ------------------------------------------------------------


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


# --- Pre-cleaning (deterministic, before the model) -------------------------

MD_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
MD_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
BARE_URL = re.compile(r"https?://\S+")
HTML_TAG = re.compile(r"<[^>]+>")

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
    "britannica",
)


def strip_links_and_boilerplate(md: str) -> str:
    """Remove images, links, URLs, HTML, and Britannica-specific lines."""
    text = MD_IMAGE.sub("", md)
    text = MD_LINK.sub(r"\1", text)          # keep link text, drop the URL
    text = BARE_URL.sub("", text)
    text = HTML_TAG.sub("", text)

    kept: list[str] = []
    for line in text.splitlines():
        low = line.strip().lower()
        if not low:
            kept.append("")
            continue
        if any(j in low for j in JUNK_SUBSTRINGS):
            continue
        if low in ("news \u2022", "## news \u2022", "top questions"):
            continue
        kept.append(line)
    out = "\n".join(kept)
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    return out


def content_hash(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:10]


def slugify(text: str) -> str:
    s = re.sub(r"[^\w\s-]", "", text.strip().lower())
    s = re.sub(r"[\s_]+", "-", s)
    return re.sub(r"-{2,}", "-", s).strip("-")


# --- OpenAI paraphrasing ----------------------------------------------------

SYSTEM_PROMPT = (
    "You are an expert encyclopedia editor. You rewrite source text in fresh, "
    "original wording while preserving every fact with perfect accuracy. "
    "You respond with valid JSON only."
)


def user_prompt(title_hint: str, body: str) -> str:
    return (
        "Paraphrase the article below for a public archive website.\n\n"
        "STRICT RULES:\n"
        "1. Rewrite everything in your own words (no copying sentences verbatim).\n"
        "2. Preserve ALL information exactly: every fact, figure, statistic, name, "
        "date, place, and quantity must remain accurate and complete. Do not add, "
        "omit, or invent anything.\n"
        "3. Remove every reference to Britannica, its quizzes, subscriptions, "
        "editors, and any AI-notice/marketing text.\n"
        "4. Do NOT include any hyperlinks, URLs, or markdown link syntax.\n"
        "5. Keep the same overall structure/topics and logical order.\n\n"
        f"Suggested title hint (you may refine): {title_hint}\n\n"
        "Return JSON with EXACTLY this shape:\n"
        "{\n"
        '  "title": string,\n'
        '  "summary": string,            // 1-3 sentence overview\n'
        '  "sections": [\n'
        '    { "heading": string, "paragraphs": [string, ...] }\n'
        "  ]\n"
        "}\n\n"
        "ARTICLE:\n\"\"\"\n" + body + "\n\"\"\""
    )


def paraphrase(client: OpenAI, title_hint: str, body: str) -> dict:
    resp = client.chat.completions.create(
        model=MODEL,
        temperature=0.4,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt(title_hint, body)},
        ],
    )
    data = json.loads(resp.choices[0].message.content)
    data.setdefault("title", title_hint)
    data.setdefault("summary", "")
    data.setdefault("sections", [])
    return data


# --- Main -------------------------------------------------------------------


def title_from_filename(name: str) -> str:
    t = name.removesuffix(".md").replace("  Britannica", "").replace(" Britannica", "")
    t = re.sub(r"\s{2,}", " - ", t).strip(" -")
    return t


def load_metadata() -> dict[str, dict]:
    if not INDEX_JSON.exists():
        return {}
    meta = {}
    for e in json.loads(INDEX_JSON.read_text(encoding="utf-8")):
        meta[e["file"]] = {
            "section": e.get("section", ""),
            "title": e.get("title", ""),
            "tags": e.get("tags", []),
        }
    return meta


def main() -> int:
    load_env(ROOT / ".env")
    if not os.environ.get("OPENAI_API_KEY"):
        sys.exit("OPENAI_API_KEY not found (checked environment and .env).")
    if not DATA_DIR.is_dir():
        sys.exit(f"Data directory not found: {DATA_DIR}")

    files = sorted(DATA_DIR.glob("*.md"))
    if not files:
        sys.exit(f"No markdown files found in {DATA_DIR}")

    meta = load_metadata()
    print(f"Found {len(files)} markdown files. Cleaning and grouping...")

    # Clean each file and group by unique cleaned body.
    per_file: dict[str, str] = {}   # filename -> cleaned body
    groups: dict[str, list[str]] = {}
    for f in files:
        cleaned = strip_links_and_boilerplate(f.read_text(encoding="utf-8"))
        per_file[f.name] = cleaned
        groups.setdefault(content_hash(cleaned), []).append(f.name)

    print(f"{len(groups)} unique article body(ies) -> {len(groups)} API call(s).")

    client = OpenAI()

    # Paraphrase each unique body once, concurrently.
    def work(h: str, fnames: list[str]) -> tuple[str, dict]:
        rep = fnames[0]
        hint = (meta.get(rep, {}) or {}).get("title") or title_from_filename(rep)
        result = paraphrase(client, hint, per_file[rep])
        return h, result

    paraphrased: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futs = [pool.submit(work, h, fns) for h, fns in groups.items()]
        for i, fut in enumerate(as_completed(futs), 1):
            h, result = fut.result()
            paraphrased[h] = result
            print(f"  [{i}/{len(groups)}] paraphrased: {result.get('title', '')[:60]}")

    # Build one entry per source file, reusing the shared paraphrase.
    used_slugs: set[str] = set()
    entries: list[dict] = []
    for f in files:
        h = content_hash(per_file[f.name])
        content = paraphrased[h]
        m = meta.get(f.name, {})
        base_slug = slugify(m.get("title") or content.get("title") or title_from_filename(f.name))
        slug, n = base_slug, 2
        while slug in used_slugs:
            slug, n = f"{base_slug}-{n}", n + 1
        used_slugs.add(slug)
        entries.append(
            {
                "id": slug,
                "source_file": f.name,
                "section": m.get("section", ""),
                "tags": m.get("tags", []),
                "title": content.get("title", ""),
                "summary": content.get("summary", ""),
                "sections": content.get("sections", []),
                "body_group": h,
            }
        )

    output = {
        "title": "All About Ukraine \u2014 Content",
        "generated_with": f"openai:{MODEL}",
        "counts": {"entries": len(entries), "unique_articles": len(groups)},
        "entries": entries,
    }
    OUT_JSON.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {OUT_JSON.name} ({len(entries)} entries).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
