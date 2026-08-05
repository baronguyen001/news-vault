import sqlite3

from newsvault.videos import (
    connect,
    fallback_thumbnail_url,
    has_column,
    load_all,
    thumbnail_url,
)

_COLUMNS = """
    id TEXT,
    title TEXT,
    channel TEXT,
    url TEXT,
    {is_short}
    success INTEGER,
    error_message TEXT,
    processed_at TEXT,
    run_session TEXT,
    summary TEXT,
    video_type TEXT,
    attempts INTEGER,
    permanent_fail INTEGER,
    upload_date TEXT
"""


def _make_database(path, *, include_is_short=True, rows=()):
    conn = sqlite3.connect(path)
    try:
        is_short = "is_short INTEGER," if include_is_short else ""
        conn.execute(f"CREATE TABLE videos ({_COLUMNS.format(is_short=is_short)})")
        columns = [
            "id",
            "title",
            "channel",
            "url",
        ]
        if include_is_short:
            columns.append("is_short")
        columns.extend(
            [
                "success",
                "error_message",
                "processed_at",
                "run_session",
                "summary",
                "video_type",
                "attempts",
                "permanent_fail",
                "upload_date",
            ]
        )
        placeholders = ", ".join("?" for _ in columns)
        conn.executemany(
            f"INSERT INTO videos ({', '.join(columns)}) VALUES ({placeholders})",
            rows,
        )
        conn.commit()
    finally:
        conn.close()


def _row(video_id, is_short=None, *, include_is_short=True):
    values = [
        video_id,
        "Title",
        "Channel",
        "",
        is_short,
        1,
        "",
        "2024-01-02T03:04:05",
        "",
        "Summary",
        "",
        0,
        0,
        "20240102",
    ]
    if not include_is_short:
        values.pop(4)
    return tuple(values)


def test_thumbnail_urls():
    assert thumbnail_url("abcdefghijk") == "https://i.ytimg.com/vi/abcdefghijk/hqdefault.jpg"
    assert (
        thumbnail_url("abcdefghijk", is_short=True) == "https://i.ytimg.com/vi/abcdefghijk/oar2.jpg"
    )
    assert thumbnail_url("short", is_short=True) == ""


def test_fallback_thumbnail_url():
    assert fallback_thumbnail_url("abcdefghijk") == (
        "https://i.ytimg.com/vi/abcdefghijk/hqdefault.jpg"
    )
    assert fallback_thumbnail_url("short") == ""


def test_has_column(tmp_path):
    path = tmp_path / "videos.sqlite"
    _make_database(path, rows=[_row("abcdefghijk", 0)])
    # The read layer needs sqlite3.Row; connect() is what production uses.
    conn = connect(path)
    try:
        assert has_column(conn, "is_short") is True
        assert has_column(conn, "missing") is False
    finally:
        conn.close()


def test_shorts_and_null_are_coerced(tmp_path):
    path = tmp_path / "videos.sqlite"
    _make_database(
        path,
        rows=[
            _row("abcdefghijk", 1),
            _row("bcdefghijkl", 0),
            _row("cdefghijklm", None),
        ],
    )
    # The read layer needs sqlite3.Row; connect() is what production uses.
    conn = connect(path)
    try:
        videos = {video.id: video for video in load_all(conn)}
    finally:
        conn.close()

    short = videos["abcdefghijk"]
    assert short.is_short is True
    assert short.thumbnail.endswith("/oar2.jpg")
    assert short.thumbnail_fallback.endswith("/hqdefault.jpg")

    ordinary = videos["bcdefghijkl"]
    assert ordinary.is_short is False
    assert ordinary.thumbnail.endswith("/hqdefault.jpg")
    assert ordinary.thumbnail_fallback == ""

    null_short = videos["cdefghijklm"]
    assert null_short.is_short is False
    assert null_short.thumbnail.endswith("/hqdefault.jpg")
    assert null_short.thumbnail_fallback == ""


def test_database_without_is_short_column(tmp_path):
    path = tmp_path / "videos.sqlite"
    _make_database(
        path,
        include_is_short=False,
        rows=[_row("abcdefghijk", include_is_short=False)],
    )
    # The read layer needs sqlite3.Row; connect() is what production uses.
    conn = connect(path)
    try:
        videos = load_all(conn)
    finally:
        conn.close()

    assert len(videos) == 1
    assert videos[0].is_short is False
    assert videos[0].thumbnail_fallback == ""
