from __future__ import annotations

import sqlite3

from newsvault.model import article_from_row
from newsvault.sources import FREE, PAID, PAID_SOURCE_KEYS, is_paid, tier


def _row(**overrides: object) -> sqlite3.Row:
    """Build a database row with the news-hunter column set."""
    columns = {
        "id": 1,
        "url": "https://example.test/a",
        "source": "Reuters",
        "source_key": "reuters",
        "region": "international",
        "title": "Title",
        "title_vi": "Tiêu đề",
        "published_at": "",
        "category": "Khác",
        "summary_vi": "",
        "key_points": "[]",
        "tags": "[]",
        "is_law_policy": 0,
        "impact_level": "cao",
        "fetched_at": "2026-08-04T01:00:00+00:00",
        "relevance": 8,
        "topic": "Kinh tế/Tài chính",
        "analysis": "{}",
    }
    columns.update(overrides)

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    names = ", ".join(f'"{k}"' for k in columns)
    placeholders = ", ".join("?" for _ in columns)
    conn.execute(f"CREATE TABLE t ({names})")
    conn.execute(f"INSERT INTO t VALUES ({placeholders})", tuple(columns.values()))
    return conn.execute("SELECT * FROM t").fetchone()


def test_known_subscription_sources_are_paid() -> None:
    for key in ("ft", "wsj", "scmp", "nytimes", "economist", "reuters", "bloomberg"):
        assert tier(key) == PAID, key
        assert is_paid(key)


def test_free_and_unknown_sources_are_free() -> None:
    for key in ("vnexpress", "cafef", "techcrunch", "chinhphu", "", "not-a-source"):
        assert tier(key) == FREE, key
        assert not is_paid(key)


def test_tier_ignores_case_and_padding() -> None:
    assert tier("  FT  ") == PAID
    assert tier("Reuters") == PAID


def test_paid_set_matches_the_documented_thirteen() -> None:
    """A subscription starting or lapsing is a deliberate edit, not a drive-by one.

    news-hunter owns the real flag; this set mirrors it, so pinning the size makes an
    accidental deletion visible instead of silently downgrading a source to free.
    """
    assert len(PAID_SOURCE_KEYS) == 13


def test_article_derives_its_tier_from_the_source() -> None:
    paid = article_from_row(_row(source_key="ft", source="Financial Times"))
    free = article_from_row(_row(source_key="vnexpress", source="VnExpress"))
    assert paid.tier == PAID
    assert free.tier == FREE


def test_tier_cannot_drift_from_the_source_key() -> None:
    """`tier` is a property, not a stored field, so no caller can set them apart."""
    article = article_from_row(_row(source_key="wsj", source="Wall Street Journal"))
    assert not hasattr(type(article), "__dataclass_fields__") or (
        "tier" not in type(article).__dataclass_fields__
    )
    assert article.tier == PAID
