from __future__ import annotations

import sqlite3
from typing import Any

from newsvault.model import Article, article_from_row
from newsvault.payload import day_payload, report_index_payload
from newsvault.reports import group_by_day, reports_of
from newsvault.sources import REPORT_SOURCE_KEYS, is_report


def _article(**overrides: Any) -> Article:
    defaults = {
        "id": 1,
        "url": "https://example.test/report",
        "source": "McKinsey",
        "source_key": "mckinsey",
        "region": "international",
        "title": "Original report",
        "title_vi": "Báo cáo thử nghiệm",
        "published_at": "2026-08-09T10:00:00+07:00",
        "published_iso": "2026-08-09T10:00:00+07:00",
        "day": "2026-08-09",
        "fetched_at": "2026-08-09T10:00:00+07:00",
        "category": "Kinh tế",
        "topic": "Kinh tế/Tài chính",
        "summary_vi": "Đây là phần tóm tắt của báo cáo.",
        "key_points": ("Điểm chính",),
        "tags": ("kinh tế",),
        "analysis": {"boi_canh": "Bối cảnh"},
        "impact_level": "cao",
        "is_law_policy": False,
        "relevance": 8,
        "score": 80,
    }
    defaults.update(overrides)
    return Article(**defaults)


def _row(*, with_teaser: bool, value: int = 0) -> sqlite3.Row:
    conn = sqlite3.connect(":memory:")
    columns = "is_teaser INTEGER, " if with_teaser else ""
    conn.execute(
        f"""
        CREATE TABLE articles (
            id INTEGER, url TEXT, source TEXT, source_key TEXT, region TEXT, title TEXT,
            title_vi TEXT, published_at TEXT, fetched_at TEXT, category TEXT, topic TEXT,
            summary_vi TEXT, key_points TEXT, tags TEXT, analysis TEXT, impact_level TEXT,
            is_law_policy INTEGER, relevance INTEGER, {columns} ignored TEXT
        )
        """
    )
    names = "id, url, source, source_key, region, title, title_vi, published_at, fetched_at, category, topic, summary_vi, key_points, tags, analysis, impact_level, is_law_policy, relevance"
    values: list[object] = [
        1,
        "https://example.test/report",
        "McKinsey",
        "mckinsey",
        "international",
        "Original report",
        "Báo cáo thử nghiệm",
        "2026-08-09T10:00:00+07:00",
        "2026-08-09T10:00:00+07:00",
        "Kinh tế",
        "Kinh tế/Tài chính",
        "Tóm tắt",
        "[]",
        "[]",
        "{}",
        "cao",
        0,
        8,
    ]
    if with_teaser:
        names += ", is_teaser"
        values.append(value)
    conn.execute(
        f"INSERT INTO articles ({names}) VALUES ({', '.join('?' for _ in values)})",
        values,
    )
    conn.row_factory = sqlite3.Row
    return conn.execute("SELECT * FROM articles").fetchone()


def test_report_source_membership_is_authoritative() -> None:
    assert len(REPORT_SOURCE_KEYS) == 26
    assert is_report("GARTNER") is True
    assert is_report("marginalrevolution") is True
    assert is_report("aspistrategist") is True
    assert is_report("reuters") is False
    assert is_report("") is False


def test_article_from_row_reads_optional_teaser_flag() -> None:
    assert article_from_row(_row(with_teaser=True, value=1)).is_teaser is True
    assert article_from_row(_row(with_teaser=True, value=0)).is_teaser is False
    assert article_from_row(_row(with_teaser=False)).is_teaser is False


def test_reports_of_and_group_by_day_preserve_article_order() -> None:
    first = _article(id=1, day="2026-08-09")
    regular = _article(id=2, source_key="reuters")
    second = _article(id=3, day="2026-08-08")
    reports = reports_of([first, regular, second])
    assert [report.id for report in reports] == [1, 3]
    assert [report.id for report in group_by_day(reports)["2026-08-09"]] == [1]


def test_report_payload_keeps_teaser_flag_and_day_card_index() -> None:
    teaser = _article(id=1, is_teaser=True)
    full = _article(id=2, url="https://example.test/full", is_teaser=False)
    index = report_index_payload([teaser, full], generated_at="2026-08-10T00:00:00+07:00")
    assert index["kind"] == "reportsIndex"
    assert index["total"] == 2
    teaser_item = next(item for item in index["items"] if item["u"] == teaser.url)
    assert teaser_item["te"] is True
    assert teaser_item["d"] == "2026-08-09"

    day = day_payload(
        "2026-08-09",
        [full, teaser],
        clusters=[],
        entity_map={},
        trending=[],
        blindspots=[],
        brief=[],
        categories=[],
        charts={},
        generated_at="2026-08-09T18:00:00+07:00",
        reports=[teaser, full],
    )
    assert [item["i"] for item in day["reports"]] == [1, 0]
    assert day["reports"][0]["te"] is True
