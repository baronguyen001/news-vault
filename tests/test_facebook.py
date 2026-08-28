"""Read and payload behavior for facebook-digest's optional feed_posts table."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from newsvault import facebook, payload

_COLUMNS = (
    "id INTEGER, fingerprint TEXT, category TEXT, target_url TEXT, author_name TEXT, "
    "post_url TEXT, text TEXT, image_url TEXT, summary_text TEXT, scraped_at TEXT, "
    "summarized_at TEXT"
)
_FIELDS = [part.strip().split(" ")[0] for part in _COLUMNS.split(",")]


def _row(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": 1,
        "fingerprint": "one",
        "category": "AI",
        "target_url": "https://facebook.com/source",
        "author_name": "Nguyễn Văn A",
        "post_url": "https://www.facebook.com/story.php?story_fbid=1",
        "text": "Raw scraped Facebook text with UI chrome.",
        "image_url": "https://cdn.example.com/post.jpg",
        "summary_text": "Đây là phần tóm tắt tin tức sạch.",
        "scraped_at": "2026-08-26T09:15:00+07:00",
        "summarized_at": "2026-08-26T09:20:00+07:00",
    }
    base.update(overrides)
    return base


def _make_db(
    tmp_path: Path, rows: tuple[dict[str, object], ...] = (), *, table: bool = True
) -> Path:
    path = tmp_path / f"facebook_{len(list(tmp_path.glob('facebook_*.db')))}.db"
    conn = sqlite3.connect(path)
    if table:
        conn.execute(f"CREATE TABLE feed_posts ({_COLUMNS})")
        for row in rows:
            conn.execute(
                f"INSERT INTO feed_posts VALUES ({', '.join('?' for _ in _FIELDS)})",
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
    assert facebook.has_table(conn) is False
    assert facebook.load_all(conn) == []


def test_load_all_filters_missing_blank_and_deliberately_no_news_summaries(tmp_path: Path) -> None:
    rows = (
        _row(id=1, summary_text=None),
        _row(id=2, summary_text="   "),
        _row(id=3, summary_text=f"  {facebook.NO_NEWS_SUMMARY}  "),
        _row(id=4, summary_text="Tin đáng chú ý."),
    )
    conn = _connect(_make_db(tmp_path, rows))
    assert [post.id for post in facebook.load_all(conn)] == ["4"]


def test_load_all_uses_only_https_images_and_scraped_timestamp(tmp_path: Path) -> None:
    rows = (
        _row(id=1, image_url="http://example.com/insecure.jpg"),
        _row(id=2, image_url="javascript:alert(1)", scraped_at="2026-08-25T23:00:00+07:00"),
        _row(id=3, image_url="https://cdn.example.com/ok.jpg", scraped_at="bad"),
    )
    conn = _connect(_make_db(tmp_path, rows))
    posts = facebook.load_all(conn)
    assert [post.id for post in posts] == ["1", "2"]
    assert posts[0].image == ""
    assert posts[0].day == "2026-08-26"
    assert posts[0].published_iso == "2026-08-26T09:15:00+07:00"
    assert posts[1].image == ""


def test_load_all_uses_optional_topic_and_relevance_columns(tmp_path: Path) -> None:
    conn = _connect(_make_db(tmp_path, (_row(),)))
    conn.execute("ALTER TABLE feed_posts ADD COLUMN topic TEXT")
    conn.execute("ALTER TABLE feed_posts ADD COLUMN relevance REAL")
    conn.execute("UPDATE feed_posts SET topic = ?, relevance = ?", ("Công nghệ", 82))
    conn.commit()
    post = facebook.load_all(conn)[0]
    assert (post.topic, post.relevance) == ("Công nghệ", 82.0)
    assert payload.compact_facebook(post)["sc"] == 82.0
    assert payload.facebook_index_items([post])[0]["tp"] == "Công nghệ"


def test_grouping_available_days_and_order_follow_scraped_at(tmp_path: Path) -> None:
    rows = (
        _row(id=1, scraped_at="2026-08-25T08:00:00+07:00"),
        _row(id=2, scraped_at="2026-08-26T08:00:00+07:00"),
        _row(id=3, scraped_at="2026-08-26T10:00:00+07:00"),
    )
    conn = _connect(_make_db(tmp_path, rows))
    posts = facebook.load_all(conn)
    assert [post.id for post in posts] == ["3", "2", "1"]
    assert facebook.available_days(conn) == ["2026-08-25", "2026-08-26"]
    assert [post.id for post in facebook.group_by_day(posts)["2026-08-26"]] == ["3", "2"]


def test_facebook_payload_and_search_keep_only_clean_summary_but_index_raw_text() -> None:
    post = facebook.FacebookPost(
        id="1",
        url="https://www.facebook.com/post/1",
        author_name="Tác giả",
        category="Kinh tế",
        image="https://cdn.example.com/photo.jpg",
        day="2026-08-26",
        published_iso="2026-08-26T09:15:00+07:00",
        summary="Tóm tắt sạch.",
        text="Raw UI Chrome UniqueSearchTerm",
        blocks=(),
    )
    compact = payload.compact_facebook(post)
    assert compact["img"] == "https://cdn.example.com/photo.jpg"
    assert "text" not in compact
    index = payload.facebook_index_items([post])[0]
    assert index["k"] == "f"
    assert "uniquesearchterm" in index["f"]
    listing = payload.facebook_index_payload([post], generated_at="2026-08-26T00:00:00+07:00")
    assert listing["kind"] == "facebookIndex"
    assert listing["total"] == 1
