"""Reading the x-pulse database - the third content stream on a day page."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from newsvault import payload, posts

_COLUMNS = (
    "id TEXT, url TEXT, author TEXT, author_name TEXT, author_tier REAL, text TEXT, "
    "created_at TEXT, day TEXT, likes INTEGER, retweets INTEGER, replies INTEGER, "
    "views INTEGER, vertical TEXT, topic TEXT, relevance INTEGER, score INTEGER, "
    "is_primary INTEGER, title_vi TEXT, summary_vi TEXT, key_points TEXT, insight TEXT, "
    "impact_level TEXT, processed_at TEXT"
)

_FIELDS = [part.strip().split(" ")[0] for part in _COLUMNS.split(",")]


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
        "summary_vi": "Fed giữ lãi suất ở mức 4,25-4,5%.\n* Lạm phát hạ về 2,4%",
        "key_points": json.dumps(["Lạm phát tháng 7 còn 2,4%"], ensure_ascii=False),
        "insight": "Chính sách vẫn thắt chặt.",
        "impact_level": "cao",
        "processed_at": "2026-08-12T14:05:00",
    }
    base.update(overrides)
    return base


def _make_db(
    tmp_path: Path, rows: tuple[dict[str, object], ...] = (), *, view: bool = True
) -> Path:
    path = tmp_path / f"x_pulse_{len(list(tmp_path.iterdir()))}.db"
    conn = sqlite3.connect(path)
    conn.execute(f"CREATE TABLE raw_posts ({_COLUMNS})")
    for row in rows:
        placeholders = ", ".join("?" for _ in _FIELDS)
        conn.execute(
            f"INSERT INTO raw_posts VALUES ({placeholders})", [row[field] for field in _FIELDS]
        )
    if view:
        conn.execute("CREATE VIEW x_feed AS SELECT * FROM raw_posts")
    conn.commit()
    conn.close()
    return path


def test_a_database_without_the_view_still_reads_as_empty(tmp_path: Path) -> None:
    """x-pulse shipped after this site did; an older database must not fail the build."""
    conn = posts.connect(_make_db(tmp_path, view=False))
    try:
        assert posts.has_table(conn) is False
        assert posts.load_all(conn) == []
        assert posts.available_days(conn) == []
    finally:
        conn.close()


def test_the_contract_is_a_view_not_a_table(tmp_path: Path) -> None:
    conn = posts.connect(_make_db(tmp_path, (_row(),)))
    try:
        assert posts.has_table(conn) is True
        assert len(posts.load_all(conn)) == 1
    finally:
        conn.close()


def test_fields_survive_the_read(tmp_path: Path) -> None:
    conn = posts.connect(_make_db(tmp_path, (_row(),)))
    try:
        post = posts.load_all(conn)[0]
    finally:
        conn.close()

    assert post.author == "reuters"
    assert post.author_tier == 0.85
    assert post.title == "Fed giữ nguyên lãi suất"
    assert post.points == ("Lạm phát tháng 7 còn 2,4%",)
    assert post.is_primary is True
    assert post.vertical_label == "Kinh tế"
    assert post.day == "2026-08-12"


def test_the_summary_is_parsed_into_blocks_not_markup(tmp_path: Path) -> None:
    conn = posts.connect(_make_db(tmp_path, (_row(),)))
    try:
        post = posts.load_all(conn)[0]
    finally:
        conn.close()
    kinds = [block.kind for block in post.blocks]
    assert "p" in kinds and "b" in kinds


def test_a_row_without_a_title_is_dropped(tmp_path: Path) -> None:
    conn = posts.connect(_make_db(tmp_path, (_row(title_vi="  "),)))
    try:
        assert posts.load_all(conn) == []
    finally:
        conn.close()


def test_the_stored_day_wins_over_the_utc_timestamp(tmp_path: Path) -> None:
    """x-pulse resolves the Hanoi day at capture; recomputing here would move the post back."""
    conn = posts.connect(
        _make_db(tmp_path, (_row(day="2026-08-12", created_at="2026-08-11T18:30:00.000Z"),))
    )
    try:
        assert posts.load_all(conn)[0].day == "2026-08-12"
    finally:
        conn.close()


def test_a_missing_day_falls_back_to_the_timestamps(tmp_path: Path) -> None:
    conn = posts.connect(_make_db(tmp_path, (_row(day="", created_at="2026-08-10T02:00:00"),)))
    try:
        assert posts.load_all(conn)[0].day == "2026-08-10"
    finally:
        conn.close()


def test_a_row_with_no_usable_date_at_all_is_dropped(tmp_path: Path) -> None:
    conn = posts.connect(_make_db(tmp_path, (_row(day="", created_at="", processed_at=""),)))
    try:
        assert posts.load_all(conn) == []
    finally:
        conn.close()


def test_malformed_key_points_degrade_to_none(tmp_path: Path) -> None:
    """An empty list is a legitimate answer from the summariser, so this is not an error."""
    conn = posts.connect(_make_db(tmp_path, (_row(key_points="{ not json"),)))
    try:
        assert posts.load_all(conn)[0].points == ()
    finally:
        conn.close()


def test_ordering_is_newest_day_then_highest_score(tmp_path: Path) -> None:
    rows = (
        _row(id="1", day="2026-08-11", score=95),
        _row(id="2", day="2026-08-12", score=40),
        _row(id="3", day="2026-08-12", score=90),
    )
    conn = posts.connect(_make_db(tmp_path, rows))
    try:
        loaded = posts.load_all(conn)
    finally:
        conn.close()
    assert [post.id for post in loaded] == ["3", "2", "1"]


def test_group_by_day_and_available_days(tmp_path: Path) -> None:
    rows = (_row(id="1", day="2026-08-11"), _row(id="2", day="2026-08-12"))
    conn = posts.connect(_make_db(tmp_path, rows))
    try:
        grouped = posts.group_by_day(posts.load_all(conn))
        assert set(grouped) == {"2026-08-11", "2026-08-12"}
        assert posts.available_days(conn) == ["2026-08-11", "2026-08-12"]
    finally:
        conn.close()


def test_model_written_text_never_becomes_markup(tmp_path: Path) -> None:
    """The title and summary are model output about a stranger's text - twice untrusted."""
    hostile = "</script><img src=x onerror=alert(1)>"
    conn = posts.connect(
        _make_db(
            tmp_path,
            (_row(title_vi=hostile, summary_vi=hostile, key_points=json.dumps([hostile])),),
        )
    )
    try:
        post = posts.load_all(conn)[0]
    finally:
        conn.close()

    compact = payload.compact_post(post)
    # The payload carries it as data: a title string and block runs, never as HTML.
    assert compact["t"] == hostile
    runs = [run for block in compact["bl"] for run, _bold in block["r"]]
    assert hostile in runs
    assert compact["kp"] == [hostile]


def test_compact_post_carries_the_tier(tmp_path: Path) -> None:
    """Without it the card cannot show who is speaking, which is the whole point."""
    conn = posts.connect(_make_db(tmp_path, (_row(),)))
    try:
        compact = payload.compact_post(posts.load_all(conn)[0])
    finally:
        conn.close()
    assert compact["tr"] == 0.85
    assert compact["pr"] == 1
    assert compact["au"] == "reuters"
    assert compact["vl"] == "Kinh tế"


def test_post_index_items_are_tagged_x_and_include_the_original_text(tmp_path: Path) -> None:
    conn = posts.connect(_make_db(tmp_path, (_row(),)))
    try:
        items = payload.post_index_items(posts.load_all(conn))
    finally:
        conn.close()
    assert len(items) == 1
    assert items[0]["k"] == "x"
    assert items[0]["sk"] == "x"
    assert items[0]["s"] == "@reuters"
    # A reader hunting for "Fed" should find the post that used the word, not only its
    # Vietnamese rendering.
    assert "fed" in items[0]["f"]


def test_day_payload_defaults_posts_to_an_empty_list() -> None:
    data = payload.day_payload(
        "2026-08-12",
        [],
        clusters=[],
        entity_map={},
        trending=[],
        blindspots=[],
        brief=[],
        categories=[],
        charts={},
        generated_at="2026-08-12T23:59:59+07:00",
    )
    assert data["posts"] == []
