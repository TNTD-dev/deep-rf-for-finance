"""Scrape CafeF sitemap chunks → ticker-tagged news rows (secondary source).

CafeF sitemap structure (verified 2026-05-15):
    Index:   https://cafef.vn/sitemap.xml
    Chunks:  https://cafef.vn/sitemaps/sitemaps-{Y}-{M}-{D1}-{D2}.xml (5-day)
    Entry:   <url><loc>...</loc><lastmod>ISO+07:00</lastmod>
                  <image:image><image:title>CDATA</image:title></image:image></url>

Pipeline:
    1. Generate sub-sitemap URLs by date range (5-day chunks aligned to
       boundaries 1, 6, 11, 16, 21, 26).
    2. Fetch each (file-cached to data/raw/news_cache/).
    3. Parse: url + title + lastmod.
    4. Keyword-match title against ticker alias map; keep only tagged rows.

Rate limiting: 1s sleep between fetches (~72 fetches for 12mo ≈ 75s total).
Exp backoff (1s, 2s, 4s) on 429/503. Cache + immutable past chunks make re-runs
fast.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import date, timedelta
from pathlib import Path

import httpx
import pandas as pd
from bs4 import BeautifulSoup

from src import config
from src.data_pipeline.news_align import normalize_for_match, to_utc

log = logging.getLogger(__name__)

CACHE_DIR: Path = config.PROJECT_ROOT / "data" / "raw" / "news_cache"
USER_AGENT: str = (
    "deep-rf-finance-research/0.1 (academic; contact: devinnotech1@gmail.com)"
)
CHUNK_BOUNDARIES: tuple[int, ...] = (1, 6, 11, 16, 21, 26)
THROTTLE_SECONDS: float = 1.0

# Alias map. Verify each entry by hand. False positive on "VIC" (3-letter word)
# is most likely vector — alias regex applies word-boundary guard.
_TICKER_ALIASES: dict[str, list[str]] = {
    "VCB": ["VCB", "Vietcombank", "Ngân hàng Ngoại Thương"],
    "FPT": ["FPT"],
    "HPG": ["HPG", "Hòa Phát", "Tập đoàn Hòa Phát"],
    "VIC": ["VIC", "Vingroup", "Tập đoàn Vingroup"],
    "VNM": ["VNM", "Vinamilk", "Sữa Việt Nam"],
}


def _compile_alias_regex(aliases: list[str]) -> re.Pattern:
    """Word-boundary regex on normalized (diacritic-stripped) text."""
    parts = [re.escape(normalize_for_match(a)) for a in aliases]
    pattern = r"(?<!\w)(?:" + "|".join(parts) + r")(?!\w)"
    return re.compile(pattern, re.IGNORECASE)


_TICKER_REGEX: dict[str, re.Pattern] = {
    t: _compile_alias_regex(aliases) for t, aliases in _TICKER_ALIASES.items()
}


def _last_day_of_month(y: int, m: int) -> int:
    nxt_y = y + 1 if m == 12 else y
    nxt_m = 1 if m == 12 else m + 1
    return (date(nxt_y, nxt_m, 1) - timedelta(days=1)).day


def list_sub_sitemaps(start: date, end: date) -> list[str]:
    """Generate CafeF sub-sitemap URLs covering [start, end].

    Format: sitemaps-{Y}-{M}-{D1}-{D2}.xml with D1 ∈ {1,6,11,16,21,26}, D2
    the next boundary minus 1 (or end of month if boundary overruns).
    """
    if start > end:
        return []
    urls: list[str] = []
    cur = date(start.year, start.month, 1)
    while cur <= end:
        last_day = _last_day_of_month(cur.year, cur.month)
        for d1 in CHUNK_BOUNDARIES:
            if d1 > last_day:
                break
            d2 = min(d1 + 4, last_day)
            chunk_start = date(cur.year, cur.month, d1)
            chunk_end = date(cur.year, cur.month, d2)
            if chunk_end < start or chunk_start > end:
                continue
            urls.append(
                f"https://cafef.vn/sitemaps/sitemaps-"
                f"{cur.year}-{cur.month}-{d1}-{d2}.xml"
            )
        # Next month
        cur = date(cur.year + (cur.month == 12), 1 if cur.month == 12 else cur.month + 1, 1)
    return urls


def _fetch_with_retry(
    client: httpx.Client, url: str, attempts: int = 3
) -> str | None:
    """GET with exp backoff. Returns text or None if all attempts fail."""
    for i in range(attempts):
        try:
            r = client.get(url, timeout=15.0)
            if r.status_code == 200:
                return r.text
            if r.status_code in (429, 503):
                log.warning(
                    "rate-limited %s (attempt %d), backing off", url, i + 1
                )
                time.sleep(2**i + 1)
                continue
            log.warning("unexpected status %d for %s", r.status_code, url)
            return None
        except httpx.HTTPError as e:
            log.warning("HTTP error %s for %s: %s", type(e).__name__, url, e)
            time.sleep(2**i)
    return None


def _load_or_fetch(client: httpx.Client, url: str) -> str | None:
    """File-cache wrapper. Past-month chunks are immutable; cache forever."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    fname = url.rsplit("/", 1)[-1]
    cached = CACHE_DIR / fname
    if cached.exists() and cached.stat().st_size > 0:
        return cached.read_text(encoding="utf-8")
    text = _fetch_with_retry(client, url)
    if text is not None:
        cached.write_text(text, encoding="utf-8")
    return text


def parse_chunk(xml: str) -> list[dict]:
    """Parse one sub-sitemap → list of {url, title, lastmod}.

    Public for testability (fixture-driven).
    """
    soup = BeautifulSoup(xml, "lxml-xml")
    out: list[dict] = []
    for url_el in soup.find_all("url"):
        loc = url_el.find("loc")
        lastmod = url_el.find("lastmod")
        img = url_el.find("image:image")
        title_el = img.find("image:title") if img else None
        if not loc or not title_el:
            continue
        out.append(
            {
                "url": loc.text.strip(),
                "title": title_el.text.strip(),
                "lastmod": lastmod.text.strip() if lastmod else None,
            }
        )
    return out


def tag_tickers(title: str) -> list[str]:
    """Apply alias regex on normalized title. Returns sorted matched tickers."""
    norm = normalize_for_match(title)
    return sorted(t for t, pat in _TICKER_REGEX.items() if pat.search(norm))


def scrape_cafef_sitemap_range(start: date, end: date) -> pd.DataFrame:
    """Fetch + parse + ticker-tag CafeF sub-sitemaps in [start, end].

    Only rows with at least one matched ticker are kept. Output lacks
    `available_for_session` — caller computes after providing a calendar.
    """
    out_rows: list[dict] = []
    with httpx.Client(headers={"User-Agent": USER_AGENT}) as client:
        for url in list_sub_sitemaps(start, end):
            xml = _load_or_fetch(client, url)
            if xml is None:
                log.warning("skip %s (fetch failed)", url)
                continue
            for entry in parse_chunk(xml):
                tickers = tag_tickers(entry["title"])
                if not tickers:
                    continue
                out_rows.append(
                    {
                        "published_at_utc": entry["lastmod"],
                        "source": "cafef",
                        "url": entry["url"],
                        "title": entry["title"],
                        "summary": None,
                        "tickers": tickers,
                    }
                )
            time.sleep(THROTTLE_SECONDS)

    if not out_rows:
        return pd.DataFrame(
            columns=["published_at_utc", "source", "url", "title", "summary", "tickers"]
        )
    df = pd.DataFrame(out_rows)
    df["published_at_utc"] = to_utc(df["published_at_utc"])
    return df.sort_values("published_at_utc").reset_index(drop=True)
