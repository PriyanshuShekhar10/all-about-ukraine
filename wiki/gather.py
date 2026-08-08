#!/usr/bin/env python3
"""Gather grounding sources for each term: Wikipedia text + Wikidata facts.

Caches everything under wiki/cache/<qid>/gather.json so re-runs are free.
Sets term status to "gathered".

Usage: python wiki/gather.py [--limit N]
"""

from __future__ import annotations

import argparse
import time

from wutil import (
    cache_path,
    http_get_json,
    load_terms,
    read_json,
    save_terms,
    write_json,
)

WP_API = "https://en.wikipedia.org/w/api.php"
WD_API = "https://www.wikidata.org/w/api.php"
MAX_EXTRACT_CHARS = 12000

# Wikidata property -> (infobox label, datatype). Order defines display order.
INFOBOX_PROPS: list[tuple[str, str, str]] = [
    ("P571", "Inception", "time"),
    ("P569", "Born", "time"),
    ("P570", "Died", "time"),
    ("P19", "Birthplace", "entity"),
    ("P585", "Date", "time"),
    ("P17", "Country", "entity"),
    ("P36", "Capital", "entity"),
    ("P1082", "Population", "quantity"),
    ("P2046", "Area (km\u00b2)", "quantity"),
    ("P2044", "Elevation (m)", "quantity"),
    ("P6", "Head of government", "entity"),
    ("P39", "Position held", "entity"),
    ("P276", "Location", "entity"),
    ("P159", "Headquarters", "entity"),
    ("P625", "Coordinates", "coord"),
]


def wp_extract(title: str) -> tuple[str, str]:
    """Return (summary, full_plaintext) for a Wikipedia title."""
    data = http_get_json(
        WP_API,
        {
            "action": "query",
            "prop": "extracts",
            "explaintext": "1",
            "redirects": "1",
            "titles": title,
            "format": "json",
        },
    )
    pages = data.get("query", {}).get("pages", {})
    page = next(iter(pages.values()), {})
    text = page.get("extract", "") or ""
    summary = text.split("\n", 1)[0][:600]
    return summary, text[:MAX_EXTRACT_CHARS]


def wd_claims(qid: str) -> dict:
    data = http_get_json(
        WD_API,
        {
            "action": "wbgetentities",
            "ids": qid,
            "props": "claims",
            "format": "json",
        },
    )
    return data.get("entities", {}).get(qid, {}).get("claims", {})


def fmt_time(dv: dict) -> str:
    t = dv.get("time", "")  # e.g. +2022-02-24T00:00:00Z
    prec = dv.get("precision", 11)
    body = t.lstrip("+")
    date = body.split("T", 1)[0]
    y, m, d = (date.split("-") + ["", ""])[:3]
    if prec >= 11:
        return f"{y}-{m}-{d}"
    if prec == 10:
        return f"{y}-{m}"
    return y


def fmt_quantity(dv: dict) -> str:
    amt = dv.get("amount", "").lstrip("+")
    try:
        return f"{int(float(amt)):,}"
    except ValueError:
        return amt


def collect_entity_refs(claims: dict) -> set[str]:
    refs: set[str] = set()
    for prop, _, dtype in INFOBOX_PROPS:
        if dtype != "entity" or prop not in claims:
            continue
        for c in claims[prop][:2]:
            try:
                refs.add(c["mainsnak"]["datavalue"]["value"]["id"])
            except Exception:  # noqa: BLE001
                pass
    return refs


def resolve_labels(qids: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    uniq = sorted(set(qids))
    for i in range(0, len(uniq), 50):
        chunk = uniq[i : i + 50]
        if not chunk:
            break
        data = http_get_json(
            WD_API,
            {
                "action": "wbgetentities",
                "ids": "|".join(chunk),
                "props": "labels",
                "languages": "en",
                "format": "json",
            },
        )
        for qid, ent in data.get("entities", {}).items():
            out[qid] = ent.get("labels", {}).get("en", {}).get("value", qid)
    return out


def build_infobox(claims: dict, labels: dict[str, str]) -> list[dict]:
    fields: list[dict] = []
    for prop, label, dtype in INFOBOX_PROPS:
        if prop not in claims:
            continue
        snaks = claims[prop]
        try:
            dv = snaks[0]["mainsnak"]["datavalue"]["value"]
        except Exception:  # noqa: BLE001
            continue
        if dtype == "time":
            value = fmt_time(dv)
        elif dtype == "quantity":
            value = fmt_quantity(dv)
        elif dtype == "coord":
            value = f"{dv.get('latitude'):.4f}, {dv.get('longitude'):.4f}"
        elif dtype == "entity":
            ids = []
            for c in snaks[:2]:
                try:
                    ids.append(c["mainsnak"]["datavalue"]["value"]["id"])
                except Exception:  # noqa: BLE001
                    pass
            value = ", ".join(labels.get(i, i) for i in ids)
        else:
            value = str(dv)
        if value:
            fields.append({"label": label, "value": value, "source": f"wikidata:{prop}"})
    return fields


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="0 = all pending")
    args = ap.parse_args()

    terms = load_terms()
    pending = [t for t in terms if t.get("status") in (None, "queued")]
    if args.limit:
        pending = pending[: args.limit]
    print(f"Gathering {len(pending)} term(s)…")

    for i, term in enumerate(pending, 1):
        qid = term["qid"]
        out = cache_path(qid, "gather.json")
        if out.exists():
            term["status"] = "gathered"
            continue
        try:
            summary, extract = wp_extract(term["wp_title"])
            claims = wd_claims(qid)
            labels = resolve_labels(list(collect_entity_refs(claims)))
            infobox = build_infobox(claims, labels)
            write_json(
                out,
                {
                    "qid": qid,
                    "wp_title": term["wp_title"],
                    "url": f"https://en.wikipedia.org/wiki/{term['wp_title'].replace(' ', '_')}",
                    "summary": summary,
                    "extract": extract,
                    "infobox": infobox,
                },
            )
            term["status"] = "gathered"
            print(f"  [{i}/{len(pending)}] {term['name']} ({len(extract)} chars, {len(infobox)} facts)")
        except Exception as e:  # noqa: BLE001
            print(f"  [{i}/{len(pending)}] FAILED {term['name']}: {e}")
            term["status"] = "gather_failed"
        time.sleep(0.2)

    save_terms(terms)
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
