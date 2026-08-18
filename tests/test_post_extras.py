"""Optional X-feed fields remain compatible with old x-pulse databases."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from newsvault import payload, posts

_BASE_COLUMNS = (
    "id TEXT, url TEXT, author TEXT, author_name TEXT, author_tier REAL, text TEXT, "
    "created_at TEXT, day TEXT, likes INTEGER, retweets INTEGER, replies INTEGER, "
    "views INTEGER, vertical TEXT, topic TEXT, relevance INTEGER, score INTEGER, "
    "is_primary INTEGER, title_vi TEXT, summary_vi TEXT, key_points TEXT, insight TEXT, "
    "impact_level TEXT, processed_at TEXT"
)

_EXTRA_COLUMNS = (
    "media_url TEXT, dup_sources TEXT, impact_channel TEXT, impact_assets TEXT, "
    "impact_direction TEXT, impact_confidence TEXT, impact_reasoning TEXT"
)


def _fields(columns: str) -> list[str]:
    return [part.strip().split(" ")[0] for part in columns.split(",")]


def _row(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": "1800000000000000001",
        "url": "https://x.com/reuters/status/1800000000000000001",
        "author": "reuters",
        "author_name": "Reuters",
        "author_tier": 0.85,
        "text": "Fed holds rates steady at 4.25-4.5%.",
        "created_at": "2026-08-12T03:00:00.000Z",
        "day": "2026-08-12",
        "likes": 1200,
        "retweets": 430,
        "replies": 88,
        "views": 90000,
        "vertical": "kinh-te",
        "topic": "Kinh tế/Tài chính",
        "relevance": 9,
        "score": 88,
        "is_primary": 1,
        "title_vi": "Fed giữ nguyên lãi suất",
        "summary_vi": "Fed giữ lãi suất ở mức 4,25-4,5%.",
        "key_points": json.dumps(["Lạm phát tháng 7 còn 2,4%"], ensure_ascii=False),
        "insight": "Chính sách vẫn thắt chặt.",
        "impact_level": "cao",
        "processed_at": "2026-08-12T14:05:00",
        "media_url": "https://images.example/fed.jpg",
        "dup_sources": json.dumps(["afp", "ft"], ensure_ascii=False),
        "impact_channel": "Lợi suất trái phiếu có thể giảm.",
        "impact_assets": json.dumps(["USD", "VN-Index"], ensure_ascii=False),
        "impact_direction": "giảm",
        "impact_confidence": "trung bình",
        "impact_reasoning": "Kỳ vọng lãi suất ổn định làm giảm áp lực định giá lại.",
    }
    base.update(overrides)
    return base


def _make_db(
    tmp_path: Path, row: dict[str, object], *, include_extras: bool = True
) -> Path:
    # Unique per call, not per shape. Two databases of the SAME shape inside one test is the
    # normal case here - "valid row" against "malformed row" - and naming the file after the
    # shape alone made the second call reopen the first one and fail on CREATE TABLE.
    suffix = "extras" if include_extras else "legacy"
    _make_db.counter = getattr(_make_db, "counter", 0) + 1
    path = tmp_path / f"x_pulse_{suffix}_{_make_db.counter}.db"
    columns = _BASE_COLUMNS + (", " + _EXTRA_COLUMNS if include_extras else "")
    fields = _fields(columns)
    conn = sqlite3.connect(path)
    try:
        conn.execute(f"CREATE TABLE raw_posts ({columns})")
        placeholders = ", ".join("?" for _ in fields)
        conn.execute(
            f"INSERT INTO raw_posts VALUES ({placeholders})",
            [row[field] for field in fields],
        )
        conn.execute("CREATE VIEW x_feed AS SELECT * FROM raw_posts")
        conn.commit()
    finally:
        conn.close()
    return path


def _load_one(path: Path) -> posts.Post:
    conn = posts.connect(path)
    try:
        row = conn.execute("SELECT * FROM x_feed").fetchone()
        assert row is not None
        post = posts._post_from_row(row)
        assert post is not None
        return post
    finally:
        conn.close()


def test_post_from_row_reads_optional_x_feed_extras(tmp_path: Path) -> None:
    post = _load_one(_make_db(tmp_path, _row()),)

    assert post.image == "https://images.example/fed.jpg"
    assert post.also_by == ("afp", "ft")
    assert post.impact_channel == "Lợi suất trái phiếu có thể giảm."
    assert post.impact_assets == ("USD", "VN-Index")
    assert post.impact_direction == "giảm"
    assert post.impact_confidence == "trung bình"
    assert post.impact_reasoning == "Kỳ vọng lãi suất ổn định làm giảm áp lực định giá lại."


def test_post_from_legacy_view_defaults_optional_extras_to_empty(tmp_path: Path) -> None:
    post = _load_one(_make_db(tmp_path, _row(), include_extras=False))

    assert post.image == ""
    assert post.also_by == ()
    assert post.impact_channel == ""
    assert post.impact_assets == ()
    assert post.impact_direction == ""
    assert post.impact_confidence == ""
    assert post.impact_reasoning == ""


def test_invalid_media_and_duplicate_sources_degrade_safely(tmp_path: Path) -> None:
    http_post = _load_one(_make_db(tmp_path, _row(media_url="http://images.example/fed.jpg")))
    assert http_post.image == ""

    invalid_post = _load_one(
        _make_db(
            tmp_path,
            _row(media_url="not a url", dup_sources="{ not json"),
        )
    )
    assert invalid_post.image == ""
    assert invalid_post.also_by == ()


def test_compact_post_only_emits_impact_analysis_when_reasoning_exists(tmp_path: Path) -> None:
    complete = _load_one(_make_db(tmp_path, _row()))
    compact_complete = payload.compact_post(complete)

    assert compact_complete["img"] == "https://images.example/fed.jpg"
    assert compact_complete["ab"] == ["afp", "ft"]
    assert compact_complete["ia"] == {
        "ch": "Lợi suất trái phiếu có thể giảm.",
        "as": ["USD", "VN-Index"],
        "dir": "giảm",
        "cf": "trung bình",
        "why": "Kỳ vọng lãi suất ổn định làm giảm áp lực định giá lại.",
    }

    without_analysis = _load_one(
        _make_db(
            tmp_path,
            _row(
                impact_channel="Lợi suất trái phiếu có thể giảm.",
                impact_assets=json.dumps(["USD"]),
                impact_direction="giảm",
                impact_confidence="trung bình",
                impact_reasoning="",
            ),
        )
    )
    compact_without_analysis = payload.compact_post(without_analysis)

    assert "ia" not in compact_without_analysis
