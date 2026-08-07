"""Tests for the junk filter in newsvault.videos.

The summarizer flags worthless videos with `junk = 1` instead of deleting the row, so the
archive must exclude them at read time. The column is optional: an older summarizer
database has no `junk` column at all and must still build.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from newsvault import videos

BASE_COLUMNS = (
    "id TEXT PRIMARY KEY",
    "title TEXT",
    "channel TEXT",
    "url TEXT",
    "processed_at TEXT",
    "summary TEXT",
    "video_type TEXT",
    "success INTEGER DEFAULT 0",
)

ROW_KEYS = ("id", "title", "channel", "url", "processed_at", "summary", "video_type", "success")


def _make_db(tmp_path: Path, *, junk_column: bool, rows: tuple[dict[str, object], ...]) -> Path:
    # One file per call so a test can create both an old-schema and a new-schema database.
    path = tmp_path / f"videos-{len(list(tmp_path.glob('videos-*.db')))}.db"
    conn = sqlite3.connect(path)
    columns = list(BASE_COLUMNS)
    if junk_column:
        columns.append("junk INTEGER DEFAULT 0")
    conn.execute(f"CREATE TABLE videos ({', '.join(columns)})")
    for row in rows:
        keys = list(row.keys())
        placeholders = ", ".join("?" for _ in keys)
        conn.execute(
            f"INSERT INTO videos ({', '.join(keys)}) VALUES ({placeholders})",
            tuple(row[key] for key in keys),
        )
    conn.commit()
    conn.close()
    return path


def _row(video_id: str, **extra: object) -> dict[str, object]:
    row: dict[str, object] = {
        "id": video_id,
        "title": f"Tiêu đề {video_id}",
        "channel": "Kênh",
        "url": f"https://youtu.be/{video_id}",
        "processed_at": "2026-08-05T20:00:00",
        "summary": "📌 TÓM TẮT: nội dung thật.",
        "video_type": "tech",
        "success": 1,
    }
    row.update(extra)
    return row


def _load(path: Path) -> list[str]:
    conn = videos.connect(path)
    try:
        return [video.id for video in videos.load_all(conn)]
    finally:
        conn.close()


def test_old_schema_without_junk_column_still_builds(tmp_path: Path) -> None:
    path = _make_db(tmp_path, junk_column=False, rows=(_row("a"), _row("b")))
    assert _load(path) == ["a", "b"]


def test_junk_rows_are_excluded(tmp_path: Path) -> None:
    path = _make_db(
        tmp_path,
        junk_column=True,
        rows=(_row("keep", junk=0), _row("drop", junk=1)),
    )
    assert _load(path) == ["keep"]


def test_null_junk_is_treated_as_kept(tmp_path: Path) -> None:
    """COALESCE guards rows written before the column had a default."""
    path = _make_db(tmp_path, junk_column=True, rows=(_row("a", junk=None),))
    assert _load(path) == ["a"]


def test_junk_does_not_override_the_existing_success_filter(tmp_path: Path) -> None:
    path = _make_db(
        tmp_path,
        junk_column=True,
        rows=(
            _row("ok", junk=0),
            _row("failed", success=0, junk=0),
            _row("empty", summary="", junk=0),
        ),
    )
    assert _load(path) == ["ok"]


def test_every_row_junk_yields_empty_archive(tmp_path: Path) -> None:
    path = _make_db(tmp_path, junk_column=True, rows=(_row("a", junk=1), _row("b", junk=1)))
    assert _load(path) == []
