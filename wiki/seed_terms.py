#!/usr/bin/env python3
"""Seed the term dictionary from Wikidata, ranked by notability.

Combines:
  * a curated high-value core (resolved to QIDs via Wikipedia), and
  * SPARQL top-ups for places, people, and organizations in Ukraine,
    ranked by `wikibase:sitelinks` (a precomputed notability signal).

Writes data-wiki/terms.json (status "queued").

Usage: python wiki/seed_terms.py [--limit N]
"""

from __future__ import annotations

import argparse

from wutil import http_get_json, load_terms, save_terms, slugify

WDQS = "https://query.wikidata.org/sparql"
WD_API = "https://www.wikidata.org/w/api.php"
WP_API = "https://en.wikipedia.org/w/api.php"

# Categories used across the wiki (slug -> display name).
CATEGORIES = {
    "geography": "Land & Geography",
    "people": "People & Society",
    "culture": "Culture & Arts",
    "economy": "Economy & Industry",
    "politics": "Government & Politics",
    "history": "History",
    "war": "Russia\u2013Ukraine War",
    "other": "Other",
}

# Curated core: (Wikipedia title, category). Guarantees a strong, well-rounded
# base spanning history, culture, politics, geography, and the war.
CURATED: list[tuple[str, str]] = [
    # --- Geography (cities, rivers, regions) ---
    ("Ukraine", "geography"),
    ("Kyiv", "geography"),
    ("Crimea", "geography"),
    ("Dnieper", "geography"),
    ("Ukrainian Carpathians", "geography"),
    ("Donbas", "geography"),
    ("Kharkiv", "geography"),
    ("Lviv", "geography"),
    ("Odesa", "geography"),
    ("Dnipro", "geography"),
    ("Zaporizhzhia", "geography"),
    ("Mariupol", "geography"),
    ("Mykolaiv", "geography"),
    ("Kherson", "geography"),
    ("Chernihiv", "geography"),
    ("Poltava", "geography"),
    ("Vinnytsia", "geography"),
    ("Ivano-Frankivsk", "geography"),
    ("Ternopil", "geography"),
    ("Zhytomyr", "geography"),
    ("Sevastopol", "geography"),
    ("Luhansk", "geography"),
    ("Donetsk", "geography"),
    ("Sumy", "geography"),
    ("Chernivtsi", "geography"),
    ("Kryvyi Rih", "geography"),
    ("Dniester", "geography"),
    # --- History ---
    ("Kyivan Rus'", "history"),
    ("Cossacks", "history"),
    ("Zaporozhian Sich", "history"),
    ("Cossack Hetmanate", "history"),
    ("Holodomor", "history"),
    ("Ukrainian War of Independence", "history"),
    ("Orange Revolution", "history"),
    ("Euromaidan", "history"),
    ("Revolution of Dignity", "history"),
    ("Ukrainian Soviet Socialist Republic", "history"),
    ("Chernobyl disaster", "history"),
    ("Khmelnytsky Uprising", "history"),
    ("Pereiaslav Council", "history"),
    ("Ukrainian People's Republic", "history"),
    ("West Ukrainian People's Republic", "history"),
    ("Kingdom of Galicia–Volhynia", "history"),
    ("Trypillia culture", "history"),
    ("Ukrainization", "history"),
    ("Executed Renaissance", "history"),
    ("Bohdan Khmelnytsky", "history"),
    ("Hetman", "history"),
    ("Sich Riflemen", "history"),
    # --- Government & Politics ---
    ("Volodymyr Zelenskyy", "politics"),
    ("Verkhovna Rada", "politics"),
    ("Petro Poroshenko", "politics"),
    ("Viktor Yanukovych", "politics"),
    ("Government of Ukraine", "politics"),
    ("Constitution of Ukraine", "politics"),
    ("President of Ukraine", "politics"),
    ("Prime Minister of Ukraine", "politics"),
    ("Cabinet of Ministers of Ukraine", "politics"),
    ("Security Service of Ukraine", "politics"),
    ("Armed Forces of Ukraine", "politics"),
    ("Servant of the People (political party)", "politics"),
    ("Constitutional Court of Ukraine", "politics"),
    ("Administrative divisions of Ukraine", "politics"),
    ("Foreign relations of Ukraine", "politics"),
    ("Ukraine–NATO relations", "politics"),
    ("Ukraine–European Union relations", "politics"),
    ("Leonid Kuchma", "politics"),
    ("Leonid Kravchuk", "politics"),
    ("Viktor Yushchenko", "politics"),
    ("Yulia Tymoshenko", "politics"),
    ("Denys Shmyhal", "politics"),
    # --- Russia–Ukraine War ---
    ("Russo-Ukrainian War", "war"),
    ("Russian invasion of Ukraine", "war"),
    ("Annexation of Crimea by the Russian Federation", "war"),
    ("Battle of Kyiv (2022)", "war"),
    ("Siege of Mariupol", "war"),
    ("War in Donbas", "war"),
    ("Battle of Ilovaisk", "war"),
    ("Battle of Debaltseve", "war"),
    ("Battle of Bakhmut", "war"),
    ("2022 Kharkiv counteroffensive", "war"),
    ("2022 Kherson counteroffensive", "war"),
    ("Snake Island campaign", "war"),
    ("Russian cruiser Moskva", "war"),
    ("Bucha massacre", "war"),
    ("Minsk agreements", "war"),
    ("Kerch Strait incident", "war"),
    ("Battle of Sievierodonetsk (2022)", "war"),
    ("Kramatorsk railway station attack", "war"),
    ("Mariupol theatre airstrike", "war"),
    # --- Culture & Arts ---
    ("Ukrainian cuisine", "culture"),
    ("Borscht", "culture"),
    ("Pysanka", "culture"),
    ("Vyshyvanka", "culture"),
    ("Bandura", "culture"),
    ("Hopak", "culture"),
    ("Varenyky", "culture"),
    ("Salo (food)", "culture"),
    ("Ukrainian literature", "culture"),
    ("Music of Ukraine", "culture"),
    ("Petrykivka painting", "culture"),
    ("Motanka", "culture"),
    ("Rushnyk", "culture"),
    ("Kutia", "culture"),
    ("Paska (bread)", "culture"),
    ("Holubtsi", "culture"),
    ("Ukrainian Orthodox Church", "culture"),
    ("Ukrainian Greek Catholic Church", "culture"),
    ("Kolomyika", "culture"),
    ("Trembita", "culture"),
    ("Deruny", "culture"),
    # --- Economy & Industry ---
    ("Economy of Ukraine", "economy"),
    ("Hryvnia", "economy"),
    ("Agriculture in Ukraine", "economy"),
    ("Naftogaz", "economy"),
    ("Metinvest", "economy"),
    ("Antonov", "economy"),
    ("Motor Sich", "economy"),
    ("Ukrzaliznytsia", "economy"),
    ("Energoatom", "economy"),
    ("PrivatBank", "economy"),
    ("DTEK", "economy"),
    ("Roshen", "economy"),
    ("Nova Poshta", "economy"),
    ("Kyivstar", "economy"),
    ("Ukrnafta", "economy"),
    ("ArcelorMittal Kryvyi Rih", "economy"),
    ("Ukroboronprom", "economy"),
    ("Interpipe", "economy"),
    ("Oschadbank", "economy"),
    ("National Bank of Ukraine", "economy"),
    # --- People & Society ---
    ("Ukrainians", "people"),
    ("Ukrainian language", "people"),
    ("Ukrainian diaspora", "people"),
    ("Taras Shevchenko", "people"),
    ("Lesya Ukrainka", "people"),
    ("Ivan Franko", "people"),
    ("Mykhailo Hrushevsky", "people"),
]

# Wikidata P31 (instance of) QID -> category.
TYPE_CATEGORY = {
    "Q5": "people",            # human
    "Q515": "geography",       # city
    "Q1549591": "geography",   # big city
    "Q5119": "geography",      # capital
    "Q3957": "geography",      # town
    "Q532": "geography",       # village
    "Q4022": "geography",      # river
    "Q23397": "geography",     # lake
    "Q8502": "geography",      # mountain
    "Q46831": "geography",     # mountain range
    "Q165": "geography",       # sea
    "Q34763": "geography",     # peninsula
    "Q217691": "geography",    # oblast of Ukraine
    "Q6256": "geography",      # country
    "Q198": "war",             # war
    "Q178561": "war",          # battle
    "Q645883": "war",          # military operation
    "Q350604": "war",          # armed conflict
    "Q10931": "history",       # revolution
    "Q41397": "history",       # genocide
    "Q168247": "history",      # famine
    "Q7278": "politics",       # political party
    "Q43229": "politics",      # organization
    "Q11204": "politics",      # legislature
    "Q41710": "people",        # ethnic group
    "Q34770": "people",        # language
    "Q9174": "people",         # religion
    "Q2095": "culture",        # food
    "Q746549": "culture",      # dish
    "Q34379": "culture",       # musical instrument
    "Q8142": "economy",        # currency
    "Q783794": "economy",      # company
}


def sparql(query: str) -> list[dict]:
    data = http_get_json(WDQS, {"query": query, "format": "json"})
    return data["results"]["bindings"]


def qid_from_uri(uri: str) -> str:
    return uri.rsplit("/", 1)[-1]


def resolve_titles(titles: list[str]) -> dict[str, str]:
    """Wikipedia title -> Wikidata QID via pageprops."""
    out: dict[str, str] = {}
    for i in range(0, len(titles), 40):
        chunk = titles[i : i + 40]
        data = http_get_json(
            WP_API,
            {
                "action": "query",
                "prop": "pageprops",
                "ppprop": "wikibase_item",
                "titles": "|".join(chunk),
                "redirects": "1",
                "format": "json",
            },
        )
        pages = data.get("query", {}).get("pages", {})
        norm = {n["to"]: n["from"] for n in data.get("query", {}).get("normalized", [])}
        redir = {r["to"]: r["from"] for r in data.get("query", {}).get("redirects", [])}
        for page in pages.values():
            title = page.get("title", "")
            qid = page.get("pageprops", {}).get("wikibase_item")
            if not qid:
                continue
            original = redir.get(title, title)
            original = norm.get(original, original)
            out[original] = qid
    return out


def sparql_qids(query: str) -> list[str]:
    try:
        rows = sparql(query)
    except Exception as e:  # noqa: BLE001
        print(f"  [warn] SPARQL failed, skipping: {e}")
        return []
    return [qid_from_uri(r["item"]["value"]) for r in rows]


def fetch_entities(qids: list[str]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for i in range(0, len(qids), 50):
        chunk = qids[i : i + 50]
        data = http_get_json(
            WD_API,
            {
                "action": "wbgetentities",
                "ids": "|".join(chunk),
                "props": "labels|aliases|claims|sitelinks",
                "languages": "en",
                "format": "json",
            },
        )
        out.update(data.get("entities", {}))
    return out


def fetch_labels(qids: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    uniq = sorted(set(qids))
    for i in range(0, len(uniq), 50):
        chunk = uniq[i : i + 50]
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


def instance_of(entity: dict) -> str | None:
    try:
        claims = entity["claims"]["P31"]
        return claims[0]["mainsnak"]["datavalue"]["value"]["id"]
    except Exception:  # noqa: BLE001
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=300, help="max terms to keep")
    args = ap.parse_args()

    print("Resolving curated core via Wikipedia…")
    curated_map = resolve_titles([t for t, _ in CURATED])
    category_override: dict[str, str] = {}
    for title, cat in CURATED:
        qid = curated_map.get(title)
        if qid:
            category_override[qid] = cat
    print(f"  resolved {len(category_override)} curated QIDs")

    print("Querying Wikidata (places, people, organizations)…")
    # Kept small so the curated, category-balanced core dominates and the corpus
    # stays evenly distributed (people previously flooded the set).
    places = sparql_qids(
        """SELECT ?item ?count WHERE {
             ?item wdt:P17 wd:Q212 ; wdt:P31/wdt:P279* wd:Q486972 ;
                   wikibase:sitelinks ?count .
           } ORDER BY DESC(?count) LIMIT 20"""
    )
    people = sparql_qids(
        """SELECT ?item ?count WHERE {
             ?item wdt:P27 wd:Q212 ; wdt:P31 wd:Q5 ; wikibase:sitelinks ?count .
           } ORDER BY DESC(?count) LIMIT 18"""
    )
    orgs = sparql_qids(
        """SELECT ?item ?count WHERE {
             ?item wdt:P17 wd:Q212 ; wdt:P31/wdt:P279* wd:Q43229 ;
                   wikibase:sitelinks ?count .
           } ORDER BY DESC(?count) LIMIT 12"""
    )
    print(f"  places={len(places)} people={len(people)} orgs={len(orgs)}")

    all_qids: list[str] = list(category_override.keys()) + places + people + orgs
    # De-dup while preserving order (curated first).
    seen: set[str] = set()
    ordered_qids = [q for q in all_qids if not (q in seen or seen.add(q))]

    print(f"Fetching {len(ordered_qids)} entities from Wikidata…")
    entities = fetch_entities(ordered_qids)

    type_qids = [t for t in (instance_of(e) for e in entities.values()) if t]
    type_labels = fetch_labels(type_qids)

    # Preserve existing statuses so re-seeding doesn't reset progress.
    existing = {t["qid"]: t for t in load_terms()}

    terms: list[dict] = []
    used_slugs: set[str] = set()
    for qid in ordered_qids:
        ent = entities.get(qid)
        if not ent:
            continue
        label = ent.get("labels", {}).get("en", {}).get("value")
        sitelinks = ent.get("sitelinks", {})
        wp = sitelinks.get("enwiki", {}).get("title")
        if not label or not wp:
            continue  # need an English Wikipedia article to ground on
        aliases = [a["value"] for a in ent.get("aliases", {}).get("en", [])]
        t31 = instance_of(ent)
        category = category_override.get(qid) or TYPE_CATEGORY.get(t31 or "", "other")
        slug = slugify(label)
        base, n = slug, 2
        while slug in used_slugs:
            slug, n = f"{base}-{n}", n + 1
        used_slugs.add(slug)
        prev = existing.get(qid, {})
        terms.append(
            {
                "qid": qid,
                "slug": slug,
                "name": label,
                "wp_title": wp,
                "type": type_labels.get(t31 or "", "topic"),
                "category": category,
                "aliases": sorted(set(aliases)),
                "notability": len(sitelinks),
                "status": prev.get("status", "queued"),
            }
        )

    # Curated first, then by notability.
    curated_set = set(category_override)
    terms.sort(key=lambda t: (t["qid"] not in curated_set, -t["notability"]))
    terms = terms[: args.limit]

    save_terms(terms)
    by_cat: dict[str, int] = {}
    for t in terms:
        by_cat[t["category"]] = by_cat.get(t["category"], 0) + 1
    print(f"\nWrote {len(terms)} terms to data-wiki/terms.json")
    for cat, count in sorted(by_cat.items(), key=lambda kv: -kv[1]):
        print(f"  {CATEGORIES.get(cat, cat):<24} {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
