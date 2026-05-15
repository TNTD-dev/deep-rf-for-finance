"""CafeF sitemap URL math + parse + alias tagging.

Network calls are NOT made here. Fixture XML covers the parse path. The
URL generator (`list_sub_sitemaps`) is pure date arithmetic.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from src.data_pipeline.news_scraper import (
    list_sub_sitemaps,
    parse_chunk,
    tag_tickers,
)

FIXTURE = Path(__file__).parent / "fixtures" / "cafef_sitemap_chunk.xml"


def test_list_sub_sitemaps_5day_chunks_in_month() -> None:
    """Jul 2025 (31 days) → 6 chunks: 1-5, 6-10, 11-15, 16-20, 21-25, 26-30."""
    urls = list_sub_sitemaps(date(2025, 7, 1), date(2025, 7, 31))
    assert len(urls) == 6
    assert urls[0].endswith("sitemaps-2025-7-1-5.xml")
    assert urls[-1].endswith("sitemaps-2025-7-26-30.xml")


def test_list_sub_sitemaps_handles_short_months() -> None:
    """Feb 2025 (28 days) → last chunk is 26-28, not 26-30."""
    urls = list_sub_sitemaps(date(2025, 2, 1), date(2025, 2, 28))
    assert urls[-1].endswith("sitemaps-2025-2-26-28.xml")


def test_list_sub_sitemaps_spans_months() -> None:
    """Jul 28 - Aug 7 → covers last chunk of Jul + first 2 of Aug."""
    urls = list_sub_sitemaps(date(2025, 7, 28), date(2025, 8, 7))
    assert any("sitemaps-2025-7-26-30" in u for u in urls)
    assert any("sitemaps-2025-8-1-5" in u for u in urls)
    assert any("sitemaps-2025-8-6-10" in u for u in urls)


def test_list_sub_sitemaps_empty_when_inverted_range() -> None:
    """Start after end → empty (don't blow up)."""
    assert list_sub_sitemaps(date(2025, 8, 1), date(2025, 7, 1)) == []


def test_parse_chunk_extracts_title_and_lastmod() -> None:
    """Fixture has 5 articles — parser returns 5 rows with title/lastmod/url."""
    xml = FIXTURE.read_text(encoding="utf-8")
    rows = parse_chunk(xml)
    assert len(rows) == 5
    assert all({"url", "title", "lastmod"} <= set(r) for r in rows)
    # First row is VCB
    assert "Vietcombank" in rows[0]["title"]
    assert rows[0]["lastmod"] == "2025-07-01T12:00:00+07:00"
    assert rows[0]["url"].endswith(".chn")


def test_tag_tickers_matches_alias_case_insensitive() -> None:
    """Vietnamese title with explicit alias → matched ticker.

    Covers the primary tagging path that the coverage gate depends on.
    """
    assert tag_tickers("Vietcombank công bố lợi nhuận quý 2") == ["VCB"]
    assert tag_tickers("FPT Retail báo lãi tăng 30%") == ["FPT"]


def test_tag_tickers_handles_diacritics() -> None:
    """Diacritic-stripped match: 'Hòa Phát' must match HPG alias 'Hoa Phat'."""
    assert tag_tickers("Hòa Phát hoàn tất phát hành cổ phiếu") == ["HPG"]


def test_tag_tickers_no_false_positive_substring() -> None:
    """VICOSTONE must NOT match VIC. Word-boundary guard is the bug-class here.

    If this fails, the alias regex isn't using the (?<!\\w)...(?!\\w) wrapper
    correctly and ~80 false VIC tags per year would land in the parquet.
    """
    title = "VICOSTONE ra mắt sản phẩm đá thạch anh mới"
    assert "VIC" not in tag_tickers(title)


def test_tag_tickers_returns_multiple_when_multi_company() -> None:
    """Title naming 2 companies tags both, sorted alphabetically."""
    title = "Vingroup và Hòa Phát cùng đầu tư khu công nghiệp"
    assert tag_tickers(title) == ["HPG", "VIC"]


def test_tag_tickers_returns_empty_for_unrelated_news() -> None:
    """Lifestyle article — zero tags, gets filtered out before parquet."""
    assert tag_tickers("10 cung đường trekking đẹp nhất Việt Nam") == []
