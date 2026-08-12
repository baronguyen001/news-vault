"""Tests for newsvault.videos."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from newsvault import videos


def _make_db(
    tmp_path: Path,
    *,
    upload_date: bool = False,
    rows: tuple[dict[str, object], ...] = (),
) -> Path:
    # One file per call: a test that needs both an old-schema and a new-schema database
    # would otherwise try to create the `videos` table twice in the same file.
    path = tmp_path / f"videos-{len(list(tmp_path.glob('videos-*.db')))}.db"
    conn = sqlite3.connect(path)
    columns = [
        "id TEXT PRIMARY KEY",
        "title TEXT",
        "channel TEXT",
        "url TEXT",
        "processed_at TEXT",
        "summary TEXT",
        "video_type TEXT",
        "success INTEGER DEFAULT 0",
    ]
    if upload_date:
        columns.append("upload_date TEXT")
    conn.execute(f"CREATE TABLE videos ({', '.join(columns)})")
    if rows:
        keys = list(rows[0].keys())
        placeholders = ", ".join("?" for _ in keys)
        conn.executemany(
            f"INSERT INTO videos ({', '.join(keys)}) VALUES ({placeholders})",
            [tuple(row[key] for key in keys) for row in rows],
        )
    conn.commit()
    conn.close()
    return path


def test_clean_title_removes_channel_prefix():
    assert (
        videos.clean_title(
            "Tài chính & Kinh doanh uploaded: CPI 7 THÁNG",
            "Tài chính & Kinh doanh",
        )
        == "CPI 7 THÁNG"
    )


def test_clean_title_tolerates_repeated_spaces():
    assert (
        videos.clean_title(
            "Channel   uploaded :   Extra spaces",
            "Channel",
        )
        == "Extra spaces"
    )


def test_clean_title_removes_bare_uploaded_prefix():
    assert videos.clean_title("uploaded:   Bare prefix", "") == "Bare prefix"


def test_clean_title_leaves_clean_title_unchanged():
    assert videos.clean_title("Plain headline", "Channel") == "Plain headline"


def test_clean_title_keeps_original_when_stripped_empty():
    original = "Channel uploaded:    "
    assert videos.clean_title(original, "Channel") == original


def test_thumbnail_url_returns_url_for_valid_id():
    assert videos.thumbnail_url("dQw4w9WgXcQ") == (
        "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg"
    )


def test_thumbnail_url_returns_empty_for_invalid_id():
    assert videos.thumbnail_url("") == ""
    assert videos.thumbnail_url("!!!") == ""
    assert videos.thumbnail_url("a" * 10) == ""
    assert videos.thumbnail_url("a" * 12) == ""


def test_summary_blocks_classifies_heading_paragraph_bullet_and_bold():
    text = (
        "📊 TÌNH HÌNH: CPI tăng\n\n"
        "Đoạn văn bản thường.\n"
        "*   **Nguyên nhân:** giao thông\n"
        "⚡ KHUYẾN NGHỊ: theo dõi"
    )
    blocks = videos.summary_blocks(text)
    assert [block.kind for block in blocks] == ["h", "p", "b", "h"]
    assert blocks[0].runs == (("📊 TÌNH HÌNH: CPI tăng", False),)
    assert blocks[1].runs == (("Đoạn văn bản thường.", False),)
    assert blocks[2].runs == (
        ("Nguyên nhân:", True),
        (" giao thông", False),
    )
    assert blocks[3].runs == (("⚡ KHUYẾN NGHỊ: theo dõi", False),)


def test_summary_blocks_treats_unpaired_bold_as_literal():
    blocks = videos.summary_blocks("Line with ** unpaired marker")
    assert blocks[0].kind == "p"
    assert blocks[0].runs == (("Line with ** unpaired marker", False),)


def test_summary_blocks_gives_bullets_priority_over_headings():
    blocks = videos.summary_blocks("* 📊 Bullet heading: text")
    assert blocks[0].kind == "b"
    assert blocks[0].runs == (("📊 Bullet heading: text", False),)


def test_summary_blocks_drops_blank_lines_and_empty_bullets():
    blocks = videos.summary_blocks("Para.\n\n*   \n\n📊 Heading:\nMore")
    assert [block.kind for block in blocks] == ["p", "h", "p"]


def test_summary_blocks_indented_paragraph_with_colon_is_paragraph():
    blocks = videos.summary_blocks("   This is indented: it stays a paragraph.")
    assert len(blocks) == 1
    assert blocks[0].kind == "p"
    assert blocks[0].runs == (("This is indented: it stays a paragraph.", False),)


def test_summary_blocks_original_example():
    text = (
        "📊 TÌNH HÌNH: Chỉ số CPI (lạm phát) 7 tháng đầu năm tăng 4,39%.\n"
        "📈 PHÂN TÍCH:\n"
        "*   **Nguyên nhân CPI tháng 7 giảm:** Chủ yếu do giá nhóm giao thông giảm.\n"
        "*   **Tác động đến chính sách:** Đà giảm của CPI tháng 7 tạo dư địa.\n"
        "⚡ KHUYẾN NGHỊ:\n"
        "*   Nhà đầu tư nên theo dõi sát diễn biến lạm phát."
    )
    blocks = videos.summary_blocks(text)
    assert [block.kind for block in blocks] == ["h", "h", "b", "b", "h", "b"]
    assert blocks[2].runs[0] == ("Nguyên nhân CPI tháng 7 giảm:", True)


def test_has_upload_date_detects_column_with_pragma(tmp_path: Path):
    path_without = _make_db(tmp_path, upload_date=False)
    path_with = _make_db(tmp_path, upload_date=True)
    with videos.connect(path_without) as conn:
        assert videos.has_upload_date(conn) is False
    with videos.connect(path_with) as conn:
        assert videos.has_upload_date(conn) is True


def test_load_prefers_upload_date_then_falls_back_to_processed_at(tmp_path: Path):
    rows = (
        {
            "id": "a",
            "title": "t",
            "channel": "c",
            "url": "u",
            "processed_at": "2026-08-04T20:00:00.000000",
            "summary": "s",
            "video_type": "tech",
            "success": 1,
            "upload_date": "20260803",
        },
        {
            "id": "b",
            "title": "t",
            "channel": "c",
            "url": "u",
            "processed_at": "2026-08-05T20:00:00.000000",
            "summary": "s",
            "video_type": "tech",
            "success": 1,
            "upload_date": "",
        },
        {
            "id": "c",
            "title": "t",
            "channel": "c",
            "url": "u",
            "processed_at": "2026-08-06T20:00:00.000000",
            "summary": "s",
            "video_type": "tech",
            "success": 1,
            "upload_date": "notadate",
        },
    )
    path = _make_db(tmp_path, upload_date=True, rows=rows)
    with videos.connect(path) as conn:
        loaded = videos.load_all(conn)
    assert [v.day for v in loaded] == ["2026-08-06", "2026-08-05", "2026-08-03"]
    assert loaded[2].published_iso == "2026-08-03T00:00:00+07:00"
    # isoformat() omits a zero microsecond field, which is still valid ISO-8601.
    assert loaded[1].published_iso == "2026-08-05T20:00:00+07:00"


def test_load_uses_processed_at_when_upload_date_column_missing(tmp_path: Path):
    rows = (
        {
            "id": "x",
            "title": "t",
            "channel": "c",
            "url": "u",
            "processed_at": "2026-08-04T12:34:56.789012",
            "summary": "s",
            "video_type": "",
            "success": 1,
        },
    )
    path = _make_db(tmp_path, upload_date=False, rows=rows)
    with videos.connect(path) as conn:
        loaded = videos.load_all(conn)
    assert len(loaded) == 1
    assert loaded[0].day == "2026-08-04"
    assert loaded[0].published_iso == "2026-08-04T12:34:56.789012+07:00"


def test_load_keeps_timezone_aware_processed_at(tmp_path: Path):
    rows = (
        {
            "id": "z",
            "title": "t",
            "channel": "c",
            "url": "u",
            "processed_at": "2026-08-04T12:34:56.789012+00:00",
            "summary": "s",
            "video_type": "",
            "success": 1,
        },
    )
    path = _make_db(tmp_path, upload_date=False, rows=rows)
    with videos.connect(path) as conn:
        loaded = videos.load_all(conn)
    assert len(loaded) == 1
    assert loaded[0].day == "2026-08-04"
    assert loaded[0].published_iso == "2026-08-04T12:34:56.789012+00:00"


def test_load_skips_rows_with_unparseable_dates(tmp_path: Path):
    rows = (
        {
            "id": "bad",
            "title": "t",
            "channel": "c",
            "url": "u",
            "processed_at": "not-a-date",
            "summary": "s",
            "video_type": "",
            "success": 1,
        },
    )
    path = _make_db(tmp_path, upload_date=False, rows=rows)
    with videos.connect(path) as conn:
        assert videos.load_all(conn) == []
        assert videos.available_days(conn) == []
        assert videos.counts_by_day(conn) == {}


def test_load_skips_unsuccessful_and_empty_summaries(tmp_path: Path):
    rows = (
        {
            "id": "fail",
            "title": "t",
            "channel": "c",
            "url": "u",
            "processed_at": "2026-08-04T10:00:00",
            "summary": "s",
            "video_type": "",
            "success": 0,
        },
        {
            "id": "empty",
            "title": "t",
            "channel": "c",
            "url": "u",
            "processed_at": "2026-08-04T10:00:00",
            "summary": "",
            "video_type": "",
            "success": 1,
        },
        {
            "id": "null",
            "title": "t",
            "channel": "c",
            "url": "u",
            "processed_at": "2026-08-04T10:00:00",
            "summary": None,
            "video_type": "",
            "success": 1,
        },
        {
            "id": "good",
            "title": "t",
            "channel": "c",
            "url": "u",
            "processed_at": "2026-08-04T10:00:00",
            "summary": "s",
            "video_type": "",
            "success": 1,
        },
    )
    path = _make_db(tmp_path, upload_date=False, rows=rows)
    with videos.connect(path) as conn:
        loaded = videos.load_all(conn)
    assert [v.id for v in loaded] == ["good"]


def test_load_range_is_inclusive_at_both_boundaries(tmp_path: Path):
    rows = (
        {
            "id": "a",
            "title": "t",
            "channel": "c",
            "url": "u",
            "processed_at": "2026-08-03T10:00:00",
            "summary": "s",
            "video_type": "",
            "success": 1,
        },
        {
            "id": "b",
            "title": "t",
            "channel": "c",
            "url": "u",
            "processed_at": "2026-08-04T10:00:00",
            "summary": "s",
            "video_type": "",
            "success": 1,
        },
        {
            "id": "c",
            "title": "t",
            "channel": "c",
            "url": "u",
            "processed_at": "2026-08-05T10:00:00",
            "summary": "s",
            "video_type": "",
            "success": 1,
        },
    )
    path = _make_db(tmp_path, upload_date=False, rows=rows)
    with videos.connect(path) as conn:
        single = videos.load_range(conn, "2026-08-04", "2026-08-04")
        all_days = videos.load_range(conn, "2026-08-03", "2026-08-05")
    assert [v.id for v in single] == ["b"]
    assert [v.id for v in all_days] == ["c", "b", "a"]


def test_load_ordering_uses_id_tiebreaker(tmp_path: Path):
    rows = (
        {
            "id": "b",
            "title": "t",
            "channel": "c",
            "url": "u",
            "processed_at": "2026-08-04T10:00:00",
            "summary": "s",
            "video_type": "",
            "success": 1,
        },
        {
            "id": "a",
            "title": "t",
            "channel": "c",
            "url": "u",
            "processed_at": "2026-08-04T10:00:00",
            "summary": "s",
            "video_type": "",
            "success": 1,
        },
        {
            "id": "c",
            "title": "t",
            "channel": "c",
            "url": "u",
            "processed_at": "2026-08-04T10:00:00",
            "summary": "s",
            "video_type": "",
            "success": 1,
        },
    )
    path = _make_db(tmp_path, upload_date=False, rows=rows)
    with videos.connect(path) as conn:
        loaded = videos.load_all(conn)
    assert [v.id for v in loaded] == ["a", "b", "c"]


def test_available_days_and_counts_use_archive_rows_only(tmp_path: Path):
    rows = (
        {
            "id": "a1",
            "title": "t",
            "channel": "c",
            "url": "u",
            "processed_at": "2026-08-03T10:00:00",
            "summary": "s",
            "video_type": "",
            "success": 1,
        },
        {
            "id": "a2",
            "title": "t",
            "channel": "c",
            "url": "u",
            "processed_at": "2026-08-03T11:00:00",
            "summary": "s",
            "video_type": "",
            "success": 1,
        },
        {
            "id": "b1",
            "title": "t",
            "channel": "c",
            "url": "u",
            "processed_at": "2026-08-05T10:00:00",
            "summary": "s",
            "video_type": "",
            "success": 1,
        },
    )
    path = _make_db(tmp_path, upload_date=False, rows=rows)
    with videos.connect(path) as conn:
        assert videos.available_days(conn) == ["2026-08-03", "2026-08-05"]
        assert videos.counts_by_day(conn) == {"2026-08-03": 2, "2026-08-05": 1}


def test_load_library_includes_unsummarised_rows_with_retry_status(tmp_path: Path):
    path = _make_db(
        tmp_path,
        rows=(
            {
                "id": "done", "title": "done", "channel": "A", "url": "u",
                "processed_at": "2026-08-04T10:00:00", "summary": "summary",
                "video_type": "", "success": 1,
            },
            {
                "id": "retry", "title": "retry", "channel": "A", "url": "u",
                "processed_at": "2026-08-05T10:00:00", "summary": "",
                "video_type": "", "success": 0,
            },
        ),
    )
    with videos.connect(path) as conn:
        loaded = videos.load_library(conn)

    assert [video.id for video in loaded] == ["retry", "done"]
    assert [video.summary_status for video in loaded] == ["retry", "summarized"]
