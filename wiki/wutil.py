"""Shared helpers for the Ukraine wiki pipeline: env, HTTP, slugify, cache."""

from __future__ import annotations

import json
import os
import random
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parent.parent
DATA_WIKI = ROOT / "data-wiki"
PAGES_DIR = DATA_WIKI / "pages"
CACHE_DIR = ROOT / "wiki" / "cache"
TERMS_JSON = DATA_WIKI / "terms.json"

USER_AGENT = (
    "UkraineWikiBot/0.1 "
    "(+https://github.com/PriyanshuShekhar10/all-about-ukraine)"
)

# HTTP statuses worth retrying (rate limits + transient server errors). Shared
# CI IPs (e.g. GitHub Actions) get 429'd by Wikimedia frequently, so we back off
# and honor Retry-After instead of failing hard.
RETRY_STATUS = {429, 500, 502, 503, 504}


def load_env(path: Path | None = None) -> None:
    path = path or (ROOT / ".env")
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def http_get(url: str, params: dict | None = None, accept: str | None = None,
             retries: int = 6, backoff: float = 2.0) -> str:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url)
            req.add_header("User-Agent", USER_AGENT)
            if accept:
                req.add_header("Accept", accept)
            with urllib.request.urlopen(req, timeout=45) as resp:
                return resp.read().decode("utf-8")
        except HTTPError as e:
            last_err = e
            retryable = e.code in RETRY_STATUS and attempt < retries - 1
            if not retryable:
                raise RuntimeError(f"GET failed (HTTP {e.code}): {url}\n{e}") from e
            retry_after = e.headers.get("Retry-After") if e.headers else None
            if retry_after and str(retry_after).strip().isdigit():
                delay = float(retry_after)
            else:
                delay = backoff * (2 ** attempt)
            time.sleep(min(delay, 60.0) + random.uniform(0, 1.0))
        except URLError as e:
            last_err = e
            if attempt >= retries - 1:
                break
            time.sleep(min(backoff * (2 ** attempt), 60.0) + random.uniform(0, 1.0))
    raise RuntimeError(f"GET failed after {retries} tries: {url}\n{last_err}")


def http_get_json(url: str, params: dict | None = None) -> dict:
    return json.loads(http_get(url, params=params, accept="application/json"))


def slugify(text: str) -> str:
    s = text.strip().lower()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_]+", "-", s)
    return re.sub(r"-{2,}", "-", s).strip("-")


def read_json(path: Path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def cache_path(qid: str, name: str) -> Path:
    return CACHE_DIR / qid / name


def load_terms() -> list[dict]:
    return read_json(TERMS_JSON, default=[]) or []


def save_terms(terms: list[dict]) -> None:
    write_json(TERMS_JSON, terms)
