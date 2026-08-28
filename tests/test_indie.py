"""Reading the x-pulse database's indie_posts table - the build-in-public signal stream."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from newsvault import indie, payload

_COLUMNS = (
    "id TEXT, url TEXT, author TEXT, author_name TEXT, text TEXT, created_at TEXT, "
    "day TEXT, likes INTEGER, retweets INTEGER, replies INTEGER, fetched_at TEXT, "
    "summary_vi TEXT, keep INTEGER, scored_at TEXT"
)

_FIELDS = [part.strip().split(" ")[0] for part in _COLUMNS.split(",")]


def _row(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": "1",
        "url": "https://x.com/levelsio/status/1",
        "author": "levelsio",
        "author_name": "Pieter Levels",
        "text": "Shipped v2, now at $40k MRR",
        "created_at": "2026-08-20T10:00:00+00:00",
        "day": "2026-08-20",
        "likes": 100,
        "retweets": 10,
        "replies": 5,
        "fetched_at": "2026-08-20T12:00:00+07:00",
        "summary_vi": "Đã ra mắt v2, hiện đạt $40k MRR.",
        "keep": 1,
        "scored_at": "2026-08-20T12:05:00+07:00",
    }
    base.update(overrides)
    return base


def _make_db(
    tmp_path: Path, rows: tuple[dict[str, object], ...] = (), *, table: bool = True
) -> Path:
    path = tmp_path / f"x_pulse_{len(list(tmp_path.iterdir()))}.db"
    conn = sqlite3.connect(path)
    if table:
        conn.execute(f"CREATE TABLE indie_posts ({_COLUMNS})")
        for row in rows:
            placeholders = ", ".join("?" for _ in _FIELDS)
            conn.execute(
                f"INSERT INTO indie_posts VALUES ({placeholders})",
                [row[field] for field in _FIELDS],
            )
    else:
        conn.execute("CREATE TABLE other (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()
    return path


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def test_a_database_without_the_table_still_reads_as_empty(tmp_path: Path) -> None:
    conn = _connect(_make_db(tmp_path, table=False))
    assert indie.has_table(conn) is False
    assert indie.load_all(conn) == []


def test_load_all_reads_a_kept_row(tmp_path: Path) -> None:
    conn = _connect(_make_db(tmp_path, rows=(_row(),)))
    posts = indie.load_all(conn)
    assert len(posts) == 1
    post = posts[0]
    assert post.author == "levelsio"
    assert post.text_vi == "Đã ra mắt v2, hiện đạt $40k MRR."
    assert post.day == "2026-08-20"
    assert post.likes == 100


def test_load_all_uses_optional_topic_and_relevance_columns(tmp_path: Path) -> None:
    conn = _connect(_make_db(tmp_path, rows=(_row(),)))
    conn.execute("ALTER TABLE indie_posts ADD COLUMN topic TEXT")
    conn.execute("ALTER TABLE indie_posts ADD COLUMN relevance REAL")
    conn.execute("UPDATE indie_posts SET topic = ?, relevance = ?", ("Công nghệ", 82))
    conn.commit()
    post = indie.load_all(conn)[0]
    assert (post.topic, post.relevance) == ("Công nghệ", 82.0)
    assert payload.compact_indie(post)["sc"] == 82.0
    assert payload.indie_index_items([post])[0]["tp"] == "Công nghệ"


def test_load_all_excludes_dropped_rows(tmp_path: Path) -> None:
    rows = (_row(id="kept", keep=1), _row(id="dropped", keep=0, summary_vi=""))
    conn = _connect(_make_db(tmp_path, rows=rows))
    assert [post.id for post in indie.load_all(conn)] == ["kept"]


def test_load_all_excludes_unscored_rows(tmp_path: Path) -> None:
    """`keep IS NULL` (not yet scored) must not render as "kept"."""
    rows = (_row(id="pending", keep=None, summary_vi=None, scored_at=None),)
    conn = _connect(_make_db(tmp_path, rows=rows))
    assert indie.load_all(conn) == []


def test_load_all_strips_leading_at_sign(tmp_path: Path) -> None:
    conn = _connect(_make_db(tmp_path, rows=(_row(author="@levelsio"),)))
    assert indie.load_all(conn)[0].author == "levelsio"


def test_group_by_day_preserves_order(tmp_path: Path) -> None:
    rows = (
        _row(id="a", created_at="2026-08-20T08:00:00+00:00"),
        _row(id="b", created_at="2026-08-20T09:00:00+00:00"),
    )
    conn = _connect(_make_db(tmp_path, rows=rows))
    grouped = indie.group_by_day(indie.load_all(conn))
    assert [post.id for post in grouped["2026-08-20"]] == ["b", "a"]


def test_available_days_are_sorted_without_duplicates(tmp_path: Path) -> None:
    rows = (
        _row(id="a", day="2026-08-20"),
        _row(id="b", day="2026-08-19"),
        _row(id="c", day="2026-08-20"),
    )
    conn = _connect(_make_db(tmp_path, rows=rows))
    assert indie.available_days(conn) == ["2026-08-19", "2026-08-20"]


def test_compact_indie_omits_scoring_fields(tmp_path: Path) -> None:
    conn = _connect(_make_db(tmp_path, rows=(_row(),)))
    post = indie.load_all(conn)[0]
    compact = payload.compact_indie(post)
    assert compact["vi"] == "Đã ra mắt v2, hiện đạt $40k MRR."
    assert compact["au"] == "levelsio"
    assert "keep" not in compact
    assert "scored_at" not in compact


def test_indie_index_payload_has_total_and_items(tmp_path: Path) -> None:
    rows = (_row(id="a", url="https://x/a"), _row(id="b", url="https://x/b"))
    conn = _connect(_make_db(tmp_path, rows=rows))
    posts = indie.load_all(conn)
    result = payload.indie_index_payload(posts, generated_at="2026-08-26T00:00:00+07:00")
    assert result["kind"] == "indieIndex"
    assert result["total"] == 2
    assert len(result["items"]) == 2


def test_indie_index_payload_orders_newest_first(tmp_path: Path) -> None:
    rows = (
        _row(id="old", url="https://x/old", created_at="2026-08-01T00:00:00+00:00", day="2026-08-01"),
        _row(id="new", url="https://x/new", created_at="2026-08-20T00:00:00+00:00", day="2026-08-20"),
    )
    conn = _connect(_make_db(tmp_path, rows=rows))
    posts = indie.load_all(conn)
    result = payload.indie_index_payload(posts, generated_at="2026-08-26T00:00:00+07:00")
    assert [item["au"] for item in result["items"]] == ["levelsio", "levelsio"]
    assert result["items"][0]["d"] == "2026-08-20"
    assert result["items"][1]["d"] == "2026-08-01"


def test_load_all_without_media_column_defaults_image_to_empty(tmp_path: Path) -> None:
    """A database that predates x-pulse's `media_url` migration must still build."""
    conn = _connect(_make_db(tmp_path, rows=(_row(),)))
    assert indie.load_all(conn)[0].image == ""


def test_load_all_reads_https_media_url(tmp_path: Path) -> None:
    path = _make_db(tmp_path, rows=(_row(),))
    conn = _connect(path)
    conn.execute("ALTER TABLE indie_posts ADD COLUMN media_url TEXT")
    conn.execute("UPDATE indie_posts SET media_url = ?", ("https://pbs.twimg.com/media/x.jpg",))
    conn.commit()
    assert indie.load_all(conn)[0].image == "https://pbs.twimg.com/media/x.jpg"


def test_load_all_rejects_non_https_media_url(tmp_path: Path) -> None:
    path = _make_db(tmp_path, rows=(_row(),))
    conn = _connect(path)
    conn.execute("ALTER TABLE indie_posts ADD COLUMN media_url TEXT")
    conn.execute("UPDATE indie_posts SET media_url = ?", ("http://pbs.twimg.com/media/x.jpg",))
    conn.commit()
    assert indie.load_all(conn)[0].image == ""


def test_compact_indie_includes_image_only_when_present() -> None:
    with_image = indie.IndiePost(
        id="1", url="https://x/1", author="levelsio", author_name="Pieter Levels",
        text_vi="v2", day="2026-08-20", published_iso="", image="https://pbs.twimg.com/x.jpg",
    )
    without_image = indie.IndiePost(
        id="2", url="https://x/2", author="levelsio", author_name="Pieter Levels",
        text_vi="v3", day="2026-08-20", published_iso="",
    )
    assert payload.compact_indie(with_image)["img"] == "https://pbs.twimg.com/x.jpg"
    assert "img" not in payload.compact_indie(without_image)


def test_indie_index_items_use_indie_kind() -> None:
    post = indie.IndiePost(
        id="1",
        url="https://x.com/levelsio/status/1",
        author="levelsio",
        author_name="Pieter Levels",
        text_vi="Đã ra mắt v2, hiện đạt $40k MRR.",
        day="2026-08-20",
        published_iso="2026-08-20T10:00:00+00:00",
        likes=100,
    )
    entries = payload.indie_index_items([post])
    assert entries[0]["k"] == "i"
    assert entries[0]["sk"] == "x"
