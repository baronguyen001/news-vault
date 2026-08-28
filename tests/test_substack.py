from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

from newsvault import substack
from newsvault.payload import (
    manifest,
    substack_index_items,
    substack_index_payload,
    substack_payload,
    substack_teaser,
)

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import prune_orphans  # noqa: E402

SUMMARY = """\
🎯 LUẬN ĐIỂM CHÍNH

The author argues one clear thing across the whole piece.

📌 BỐI CẢNH

Some concrete anecdote from the author's own experience.

✅ ĐIỀU RÚT RA

1. First actionable takeaway.
2. Second actionable takeaway.
"""


def _make_db(
    tmp_path: Path,
    *,
    posts_table: bool = True,
    image_column: bool = True,
    authors: tuple[dict[str, object], ...] = (),
    rows: tuple[dict[str, object], ...] = (),
) -> Path:
    """Create a temporary substack-digest database.

    `image_column=False` mimics a database from before this column existed, so the
    `_has_image_column` fallback path (news-vault must still build against it) gets real
    coverage rather than only ever seeing the current schema.
    """
    path = tmp_path / f"substack-{len(list(tmp_path.glob('substack-*.db')))}.db"
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE followed_authors (handle TEXT PRIMARY KEY, display_name TEXT)"
    )
    for author in authors:
        conn.execute(
            "INSERT INTO followed_authors (handle, display_name) VALUES (?, ?)",
            (author["handle"], author.get("display_name", "")),
        )
    if posts_table:
        image_col_sql = ",\n                image_url TEXT NULL" if image_column else ""
        conn.execute(
            f"""
            CREATE TABLE posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT UNIQUE NOT NULL,
                author_handle TEXT NOT NULL,
                title TEXT,
                published_at TEXT,
                fetched_at TEXT,
                body_text TEXT,
                summary_text TEXT NULL,
                summarized_at TEXT NULL{image_col_sql}
            )
            """
        )
        for index, row in enumerate(rows):
            values = {
                "url": f"https://example.substack.com/p/post-{index}",
                "author_handle": "author",
                "title": f"Title {index}",
                "published_at": "2026-08-09T09:26:20+00:00",
                "fetched_at": "2026-08-09T10:00:00+00:00",
                "summary_text": SUMMARY,
                "image_url": "",
            }
            values.update(row)
            columns = ["url", "author_handle", "title", "published_at", "fetched_at", "summary_text"]
            if image_column:
                columns.append("image_url")
            conn.execute(
                f"INSERT INTO posts ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
                tuple(values[column] for column in columns),
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


def _one_item(tmp_path: Path, **kwargs: object) -> substack.Essay:
    row = {"url": "https://example.substack.com/p/only"}
    row.update(kwargs)
    path = _make_db(tmp_path, rows=(row,))
    conn = _connect(path)
    item = substack.load_all(conn)[0]
    conn.close()
    return item


# Group A: newsvault.substack read and parsing behavior.


def test_has_table_detects_posts_table(tmp_path: Path) -> None:
    with_table = _connect(_make_db(tmp_path))
    without_table = _connect(_make_db(tmp_path, posts_table=False))
    assert substack.has_table(with_table) is True
    assert substack.has_table(without_table) is False


def test_load_all_filters_unsummarized_and_blank_summaries(tmp_path: Path) -> None:
    rows = (
        {"url": "https://x/p/1", "summary_text": None},
        {"url": "https://x/p/2", "summary_text": ""},
        {"url": "https://x/p/3", "summary_text": "   "},
        {"url": "https://x/p/4", "title": "Good", "summary_text": "Useful summary"},
    )
    conn = _connect(_make_db(tmp_path, rows=rows))
    assert [item.title for item in substack.load_all(conn)] == ["Good"]


def test_load_all_returns_empty_without_table(tmp_path: Path) -> None:
    conn = _connect(_make_db(tmp_path, posts_table=False))
    assert substack.load_all(conn) == []


def test_load_all_drops_empty_title(tmp_path: Path) -> None:
    rows = (
        {"url": "https://x/p/1", "title": ""},
        {"url": "https://x/p/2", "title": "Kept"},
    )
    conn = _connect(_make_db(tmp_path, rows=rows))
    assert [item.title for item in substack.load_all(conn)] == ["Kept"]


def test_load_all_prefers_display_name_over_handle(tmp_path: Path) -> None:
    path = _make_db(
        tmp_path,
        authors=({"handle": "someauthor", "display_name": "Some Author"},),
        rows=({"url": "https://x/p/1", "author_handle": "someauthor"},),
    )
    conn = _connect(path)
    item = substack.load_all(conn)[0]
    assert item.author_name == "Some Author"


def test_load_all_falls_back_to_handle_without_display_name(tmp_path: Path) -> None:
    path = _make_db(tmp_path, rows=({"url": "https://x/p/1", "author_handle": "bare"},))
    conn = _connect(path)
    item = substack.load_all(conn)[0]
    assert item.author_name == "bare"


def test_load_all_orders_by_day_then_published_iso(tmp_path: Path) -> None:
    rows = (
        {
            "url": "https://x/p/old-day",
            "published_at": "2026-08-08T23:00:00+00:00",
        },
        {
            "url": "https://x/p/new-day-old",
            "published_at": "2026-08-09T01:00:00+00:00",
        },
        {
            "url": "https://x/p/new-day-new",
            "published_at": "2026-08-09T09:00:00+00:00",
        },
    )
    conn = _connect(_make_db(tmp_path, rows=rows))
    assert [item.url for item in substack.load_all(conn)] == [
        "https://x/p/new-day-new",
        "https://x/p/new-day-old",
        "https://x/p/old-day",
    ]


def test_resolve_day_prefers_published_at_over_fetched_at() -> None:
    assert substack._resolve_day(
        "2026-08-09T09:26:20+00:00", "2026-08-10T00:00:00+00:00"
    ) == "2026-08-09"


def test_resolve_day_falls_back_to_fetched_at() -> None:
    assert substack._resolve_day("", "2026-08-10T00:00:00+00:00") == "2026-08-10"


def test_resolve_day_returns_empty_for_unparseable_values() -> None:
    assert substack._resolve_day("not-a-date", "also-not-a-date") == ""


def test_load_all_drops_rows_with_no_usable_date(tmp_path: Path) -> None:
    rows = (
        {"url": "https://x/p/bad", "published_at": "bad", "fetched_at": "bad"},
        {"url": "https://x/p/good", "published_at": "2026-08-09T09:00:00+00:00"},
    )
    conn = _connect(_make_db(tmp_path, rows=rows))
    assert [item.url for item in substack.load_all(conn)] == ["https://x/p/good"]


def test_published_iso_normalizes_utc_zulu() -> None:
    assert substack._published_iso("2026-08-09T09:26:20Z", "") == (
        "2026-08-09T09:26:20+00:00"
    )


def test_essay_reuses_curated_block_and_section_parsing(tmp_path: Path) -> None:
    item = _one_item(tmp_path)
    assert any(block.kind == "h" for block in item.blocks)
    assert len(item.sections) >= 1
    assert item.lead


def test_group_by_day_preserves_order(tmp_path: Path) -> None:
    first = _one_item(tmp_path, url="https://x/p/first")
    second = substack.Essay(
        id="999",
        title="Second",
        author_handle="author",
        author_name="author",
        url="https://x/p/second",
        image_url="",
        day=first.day,
        published_iso=first.published_iso,
        summary="second",
        blocks=(),
        sections=(),
        lead="",
        words=1,
        minutes=1,
    )
    grouped = substack.group_by_day([first, second])
    assert [item.id for item in grouped[first.day]] == [first.id, "999"]


def test_load_all_reads_image_url(tmp_path: Path) -> None:
    item = _one_item(tmp_path, image_url="https://substackcdn.com/image/cover.jpg")
    assert item.image_url == "https://substackcdn.com/image/cover.jpg"


def test_load_all_defaults_image_url_to_empty_string(tmp_path: Path) -> None:
    item = _one_item(tmp_path)
    assert item.image_url == ""


def test_load_all_uses_optional_topic_and_relevance_columns(tmp_path: Path) -> None:
    path = _make_db(tmp_path, rows=({"url": "https://x/p/metadata"},))
    conn = _connect(path)
    conn.execute("ALTER TABLE posts ADD COLUMN topic TEXT")
    conn.execute("ALTER TABLE posts ADD COLUMN relevance REAL")
    conn.execute("UPDATE posts SET topic = ?, relevance = ?", ("Công nghệ", 82))
    conn.commit()
    item = substack.load_all(conn)[0]
    assert (item.topic, item.relevance) == ("Công nghệ", 82.0)
    assert substack_payload(item)["sc"] == 82.0
    assert substack_index_items([item])[0]["tp"] == "Công nghệ"


def test_load_all_tolerates_a_database_without_the_image_column(tmp_path: Path) -> None:
    """A reader built against an older substack-digest database - before `image_url`
    existed - must still build rather than crash with "no such column"."""
    path = _make_db(tmp_path, image_column=False, rows=({"url": "https://x/p/only"},))
    conn = _connect(path)
    item = substack.load_all(conn)[0]
    assert item.image_url == ""


def test_available_days_are_sorted_without_duplicates(tmp_path: Path) -> None:
    rows = (
        {"url": "https://x/p/a", "published_at": "2026-08-09T01:00:00+00:00"},
        {"url": "https://x/p/b", "published_at": "2026-08-08T01:00:00+00:00"},
        {"url": "https://x/p/c", "published_at": "2026-08-09T02:00:00+00:00"},
    )
    conn = _connect(_make_db(tmp_path, rows=rows))
    assert substack.available_days(conn) == ["2026-08-08", "2026-08-09"]


# Group B: payload construction.


def test_substack_teaser_omits_blocks(tmp_path: Path) -> None:
    item = _one_item(tmp_path)
    teaser = substack_teaser(item)
    assert "lead" in teaser
    assert "bl" not in teaser


def test_substack_teaser_carries_the_cover_image(tmp_path: Path) -> None:
    item = _one_item(tmp_path, image_url="https://substackcdn.com/image/cover.jpg")
    assert substack_teaser(item)["img"] == "https://substackcdn.com/image/cover.jpg"


def test_substack_payload_has_expected_shape(tmp_path: Path) -> None:
    payload = substack_payload(_one_item(tmp_path))
    assert payload["kind"] == "substack"
    assert isinstance(payload["toc"], list)
    assert isinstance(payload["bl"], list)
    assert all(set(block) == {"k", "r"} for block in payload["bl"])


def test_substack_payload_carries_the_cover_image(tmp_path: Path) -> None:
    item = _one_item(tmp_path, image_url="https://substackcdn.com/image/cover.jpg")
    assert substack_payload(item)["img"] == "https://substackcdn.com/image/cover.jpg"


def test_substack_index_payload_has_total_and_items(tmp_path: Path) -> None:
    first = _one_item(tmp_path, url="https://x/p/first")
    second = _one_item(tmp_path, url="https://x/p/second")
    payload = substack_index_payload([first, second], generated_at="2026-08-09T00:00:00+07:00")
    assert payload["kind"] == "substackIndex"
    assert payload["total"] == 2
    assert len(payload["items"]) == 2


def test_substack_index_items_use_essay_kind_and_ids(tmp_path: Path) -> None:
    item = _one_item(tmp_path)
    entries = substack_index_items([item])
    assert entries[0]["k"] == "e"
    assert entries[0]["i"] == item.id


def test_manifest_omits_substack_when_unsurveyed() -> None:
    data = manifest(
        days=[("2026-08-09", 3)],
        months=["2026-08"],
        entities=[],
        generated_at="2026-08-09T00:00:00+07:00",
        kdf_iterations=250000,
        site="Kho tin",
        version="0.11.0",
    )
    assert "substack" not in data


def test_manifest_includes_substack_ids() -> None:
    data = manifest(
        days=[],
        months=[],
        entities=[],
        substack=["1"],
        generated_at="2026-08-09T00:00:00+07:00",
        kdf_iterations=250000,
        site="Kho tin",
        version="0.11.0",
    )
    assert data["substack"] == ["1"]


# Group C: orphan pruning.


def test_expected_paths_includes_substack_ids() -> None:
    docs = Path("docs")
    expected = prune_orphans.expected_paths({"substack": ["1", "2"]}, docs)
    assert docs / "sub" / "1" in expected
    assert docs / "sub" / "2" in expected


def test_find_orphans_reports_unlisted_substack_directory(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    (docs / "sub" / "orphan").mkdir(parents=True)
    assert prune_orphans.find_orphans({"substack": []}, docs) == [
        docs / "sub" / "orphan"
    ]


def test_find_orphans_keeps_listed_substack_directory(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    (docs / "sub" / "kept").mkdir(parents=True)
    assert prune_orphans.find_orphans({"substack": ["kept"]}, docs) == []


def test_find_orphans_ignores_substack_without_manifest_key(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    (docs / "sub" / "untouched").mkdir(parents=True)
    assert prune_orphans.find_orphans({}, docs) == []
