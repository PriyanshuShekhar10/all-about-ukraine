#!/usr/bin/env python3
"""Build a properly arranged index of the Ukraine markdown data.

Scans the data folder, uses the OpenAI API to categorize each document into a
fixed set of sections (and to produce a clean title + one-line summary), then
writes an organized `INDEX.md` and a machine-readable `index.json`.

The scrape produced many byte-identical files, so the script is
duplicate-aware: it hashes content, analyzes each *unique* body only once, and
groups files that share content in the final index.

Usage:
    python build_index.py                 # uses ./data-ukraine, writes ./INDEX.md
    DATA_DIR=data-ukraine python build_index.py
    OPENAI_MODEL=gpt-4o-mini python build_index.py
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

# --- Configuration -----------------------------------------------------------

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / os.environ.get("DATA_DIR", "data-ukraine")
INDEX_MD = ROOT / os.environ.get("INDEX_MD", "INDEX.md")
INDEX_JSON = ROOT / os.environ.get("INDEX_JSON", "index.json")
MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
MAX_WORKERS = int(os.environ.get("MAX_WORKERS", "6"))
CONTENT_CHARS = 6000  # how much of each doc to send to the model

# The taxonomy the model must choose from. Fixed so the index is consistently
# arranged into sections. Order here defines the order sections appear in the index.
SECTIONS = [
    "Overview & Quick Facts",
    "Land & Geography",
    "People, Society & Religion",
    "Culture & Arts",
    "Economy & Industry",
    "Government & Politics",
    "History: Early & Medieval",
    "History: Imperial & Soviet Era",
    "History: Independence & Modern",
    "Russia–Ukraine War",
    "Other",
]

# --- Helpers -----------------------------------------------------------------


def load_env(path: Path) -> None:
    """Minimal .env loader so we don't need python-dotenv."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def clean_text(md: str) -> str:
    """Strip boilerplate/marketing noise so the model sees the real content."""
    lines = []
    for line in md.splitlines():
        low = line.lower()
        if any(
            junk in low
            for junk in ("cdn.britannica.com", "premium.britannica.com", "subscribe", "britannica quiz")
        ):
            continue
        lines.append(line)
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def content_hash(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:10]


def github_anchor(heading: str) -> str:
    """Slugify a heading the way GitHub does (for the table of contents)."""
    anchor = heading.strip().lower()
    anchor = re.sub(r"[^\w\s-]", "", anchor)  # drop punctuation (commas, &, :, –)
    anchor = anchor.replace(" ", "-")
    return anchor


def pretty_title(filename: str) -> str:
    name = filename.removesuffix(".md")
    name = name.replace("  Britannica", "").replace(" Britannica", "").strip()
    name = re.sub(r"\s{2,}", " - ", name)
    return name.strip(" -")


# --- OpenAI classification ---------------------------------------------------

SYSTEM_PROMPT = (
    "You are a librarian organizing an encyclopedia about Ukraine. "
    "You classify a document into exactly one section from a fixed list and write "
    "a concise, clean title plus a one-sentence summary. Respond ONLY with JSON."
)


def build_user_prompt(filename: str, body: str) -> str:
    return (
        f"Available sections (choose exactly one, verbatim):\n"
        + "\n".join(f"- {s}" for s in SECTIONS)
        + "\n\n"
        f"Source filename (indicates the intended topic): {filename}\n\n"
        f"Document content (may be truncated):\n\"\"\"\n{body[:CONTENT_CHARS]}\n\"\"\"\n\n"
        "Return JSON with keys:\n"
        '  "section": one of the sections above (verbatim),\n'
        '  "title": a clean human-readable title (<= 70 chars),\n'
        '  "summary": one sentence (<= 180 chars) describing what the document covers,\n'
        '  "tags": array of 3-6 short lowercase keywords.\n'
        "Base the section mainly on the filename topic, using the content to refine."
    )


def classify(client: OpenAI, filename: str, body: str) -> dict:
    resp = client.chat.completions.create(
        model=MODEL,
        temperature=0.2,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(filename, body)},
        ],
    )
    data = json.loads(resp.choices[0].message.content)
    if data.get("section") not in SECTIONS:
        data["section"] = "Other"
    data.setdefault("title", pretty_title(filename))
    data.setdefault("summary", "")
    data.setdefault("tags", [])
    return data


# --- Main --------------------------------------------------------------------


def main() -> int:
    load_env(ROOT / ".env")
    if not os.environ.get("OPENAI_API_KEY"):
        sys.exit("OPENAI_API_KEY not found (checked environment and .env).")
    if not DATA_DIR.is_dir():
        sys.exit(f"Data directory not found: {DATA_DIR}")

    files = sorted(p for p in DATA_DIR.glob("*.md"))
    if not files:
        sys.exit(f"No markdown files found in {DATA_DIR}")

    print(f"Found {len(files)} markdown files in {DATA_DIR.name}/")

    # Group files by unique cleaned content so we only call the API once per body.
    groups: dict[str, dict] = {}
    for f in files:
        body = clean_text(f.read_text(encoding="utf-8"))
        h = content_hash(body)
        grp = groups.setdefault(h, {"body": body, "files": []})
        grp["files"].append(f.name)

    print(f"{len(groups)} unique content group(s) after de-duplication.")

    client = OpenAI()

    # Classify each *file* (filename carries the intended topic), reusing the
    # shared body. Runs concurrently for speed.
    entries: list[dict] = []

    def work(fname: str, body: str, dup_count: int, dup_of: str | None) -> dict:
        info = classify(client, fname, body)
        return {
            "file": fname,
            "path": f"{DATA_DIR.name}/{fname}",
            "section": info["section"],
            "title": info["title"],
            "summary": info["summary"],
            "tags": info["tags"],
            "duplicate_group_size": dup_count,
            "shares_content_with": dup_of,
        }

    tasks = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        for h, grp in groups.items():
            fnames = grp["files"]
            representative = fnames[0]
            for fname in fnames:
                dup_of = representative if len(fnames) > 1 and fname != representative else None
                tasks.append(
                    pool.submit(work, fname, grp["body"], len(fnames), dup_of)
                )
        for i, fut in enumerate(as_completed(tasks), 1):
            entry = fut.result()
            entries.append(entry)
            print(f"  [{i}/{len(tasks)}] {entry['section']:<32} {entry['file']}")

    # Order entries by section (per SECTIONS) then title.
    section_rank = {s: i for i, s in enumerate(SECTIONS)}
    entries.sort(key=lambda e: (section_rank.get(e["section"], 999), e["title"].lower()))

    write_outputs(entries, groups)
    print(f"\nWrote {INDEX_MD.name} and {INDEX_JSON.name}")
    return 0


def write_outputs(entries: list[dict], groups: dict[str, dict]) -> None:
    INDEX_JSON.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")

    by_section: dict[str, list[dict]] = {}
    for e in entries:
        by_section.setdefault(e["section"], []).append(e)

    unique_bodies = len(groups)
    total = len(entries)

    lines: list[str] = []
    lines.append("# All About Ukraine — Data Index")
    lines.append("")
    lines.append(
        f"An organized index of the source material in `{DATA_DIR.name}/`, "
        "generated by `build_index.py` using the OpenAI API."
    )
    lines.append("")
    lines.append(f"- **Files indexed:** {total}")
    lines.append(f"- **Unique articles (by content):** {unique_bodies}")
    lines.append("")

    # Duplication note.
    dup_groups = {h: g for h, g in groups.items() if len(g["files"]) > 1}
    if dup_groups:
        lines.append("> **Note on duplicates:** the scrape produced multiple files that")
        lines.append("> share identical content. They are marked with a ↩︎ below and listed")
        lines.append("> together. Re-scraping is recommended to obtain the distinct sections.")
        lines.append("")

    # Table of contents.
    lines.append("## Sections")
    lines.append("")
    for section in SECTIONS:
        if section in by_section:
            anchor = github_anchor(section)
            lines.append(f"- [{section}](#{anchor}) ({len(by_section[section])})")
    lines.append("")

    for section in SECTIONS:
        items = by_section.get(section)
        if not items:
            continue
        lines.append(f"## {section}")
        lines.append("")
        for e in items:
            dup = " ↩︎" if e["shares_content_with"] else ""
            link = e["path"].replace(" ", "%20")
            lines.append(f"### [{e['title']}]({link}){dup}")
            if e["summary"]:
                lines.append("")
                lines.append(e["summary"])
            if e["tags"]:
                lines.append("")
                lines.append("`" + "` `".join(e["tags"]) + "`")
            if e["shares_content_with"]:
                lines.append("")
                lines.append(f"*Shares content with: {e['shares_content_with']}*")
            lines.append("")
    INDEX_MD.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
