from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

from newsvault import curated
from newsvault.curated import _WORDS_PER_MINUTE
from newsvault.payload import (
    curated_index_items,
    curated_index_payload,
    curated_payload,
    curated_teaser,
    manifest,
)

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import prune_orphans  # noqa: E402

SUMMARY = """\
🎯 TL;DR

Video presents a model where one agent coordinates the rest.

📌 BỐI CẢNH

The topic surfaced after a **major** release.

🔑 LUẬN ĐIỂM CHÍNH

1. First claim in one sentence.
• Lập luận: the reasoning chain.
• Bằng chứng: the numbers offered.

💬 TRÍCH DẪN ĐÁNG CHÚ Ý

"One quoted line."
"""


def _make_db(
    tmp_path: Path,
    *,
    table: bool = True,
    rows: tuple[dict[str, object], ...] = (),
) -> Path:
    """Create a temporary curated-videos database."""
    path = tmp_path / f"curated-{len(list(tmp_path.glob('curated-*.db')))}.db"
    conn = sqlite3.connect(path)
    if table:
        conn.execute(
            """
            CREATE TABLE curated_videos (
              id TEXT PRIMARY KEY, url TEXT, title TEXT DEFAULT '',
              channel TEXT DEFAULT '', summary TEXT DEFAULT '', success INTEGER DEFAULT 0,
              error_message TEXT DEFAULT '', attempts INTEGER DEFAULT 0,
              permanent_fail INTEGER DEFAULT 0, telegram_sent INTEGER DEFAULT 0,
              source TEXT DEFAULT 'sheet', first_seen_at TEXT, processed_at TEXT
            )
            """
        )
        for index, row in enumerate(rows):
            values = {
                "id": f"video-{index}",
                "url": f"https://youtu.be/video-{index}",
                "title": f"Title {index}",
                "channel": "Channel",
                "summary": SUMMARY,
                "success": 1,
                "processed_at": "2026-08-09T09:26:20.321740",
            }
            values.update(row)
            conn.execute(
                """
                INSERT INTO curated_videos
                (id, url, title, channel, summary, success, processed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    values["id"],
                    values["url"],
                    values["title"],
                    values["channel"],
                    values["summary"],
                    values["success"],
                    values["processed_at"],
                ),
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


def _one_item(tmp_path: Path, *, summary: str = SUMMARY) -> curated.CuratedItem:
    path = _make_db(
        tmp_path,
        rows=({"id": "abc", "summary": summary},),
    )
    conn = _connect(path)
    item = curated.load_all(conn)[0]
    conn.close()
    return item


# Group A: newsvault.curated read and parsing behavior.


def test_has_table_detects_curated_table(tmp_path: Path) -> None:
    with_table = _connect(_make_db(tmp_path))
    without_table = _connect(_make_db(tmp_path, table=False))
    assert curated.has_table(with_table) is True
    assert curated.has_table(without_table) is False


def test_load_all_filters_unpublished_and_blank_summaries(tmp_path: Path) -> None:
    rows = (
        {"id": "failed", "success": 0},
        {"id": "empty", "summary": ""},
        {"id": "spaces", "summary": "   "},
        {"id": "good", "summary": "Useful summary"},
    )
    conn = _connect(_make_db(tmp_path, rows=rows))
    assert [item.id for item in curated.load_all(conn)] == ["good"]


def test_load_all_orders_by_day_then_processed_at(tmp_path: Path) -> None:
    rows = (
        {"id": "old-day", "processed_at": "2026-08-08T23:00:00"},
        {"id": "new-day-old", "processed_at": "2026-08-09T01:00:00"},
        {"id": "new-day-new", "processed_at": "2026-08-09T09:00:00"},
    )
    conn = _connect(_make_db(tmp_path, rows=rows))
    assert [item.id for item in curated.load_all(conn)] == [
        "new-day-new",
        "new-day-old",
        "old-day",
    ]


def test_load_all_returns_empty_without_table(tmp_path: Path) -> None:
    conn = _connect(_make_db(tmp_path, table=False))
    assert curated.load_all(conn) == []


def test_load_all_drops_unparseable_processed_at(tmp_path: Path) -> None:
    conn = _connect(
        _make_db(
            tmp_path,
            rows=(
                {"id": "bad", "processed_at": "not-a-date"},
                {"id": "good", "processed_at": "2026-08-09T09:00:00"},
            ),
        )
    )
    assert [item.id for item in curated.load_all(conn)] == ["good"]


def test_load_all_drops_empty_id(tmp_path: Path) -> None:
    conn = _connect(
        _make_db(
            tmp_path,
            rows=(
                {"id": "", "processed_at": "2026-08-09T09:00:00"},
                {"id": "kept", "processed_at": "2026-08-09T08:00:00"},
            ),
        )
    )
    assert [item.id for item in curated.load_all(conn)] == ["kept"]


def test_load_all_uses_optional_topic_and_relevance_columns(tmp_path: Path) -> None:
    conn = _connect(_make_db(tmp_path, rows=({"id": "metadata"},)))
    conn.execute("ALTER TABLE curated_videos ADD COLUMN topic TEXT")
    conn.execute("ALTER TABLE curated_videos ADD COLUMN relevance REAL")
    conn.execute("UPDATE curated_videos SET topic = ?, relevance = ?", ("Công nghệ", 82))
    conn.commit()
    item = curated.load_all(conn)[0]
    assert (item.topic, item.relevance) == ("Công nghệ", 82.0)
    assert curated_payload(item)["sc"] == 82.0
    assert curated_index_items([item])[0]["tp"] == "Công nghệ"


def test_resolve_day_parses_timestamp() -> None:
    assert curated._resolve_day("2026-08-09T09:26:20.321740") == "2026-08-09"


def test_resolve_day_returns_empty_for_invalid_value() -> None:
    assert curated._resolve_day("not-a-date") == ""


def test_published_iso_adds_vietnam_offset_to_naive_value() -> None:
    assert curated._published_iso("2026-08-09T09:26:20") == (
        "2026-08-09T09:26:20+07:00"
    )


def test_published_iso_preserves_aware_value() -> None:
    value = "2026-08-09T09:26:20+02:00"
    assert curated._published_iso(value) == value


@pytest.mark.parametrize("text", ["🎯 TL;DR", "📌 BỐI CẢNH"])
def test_looks_like_heading_accepts_curated_headings(text: str) -> None:
    assert curated._looks_like_heading(text) is True


def test_looks_like_heading_rejects_non_heading_lines() -> None:
    assert curated._looks_like_heading("A paragraph") is False
    assert curated._looks_like_heading("🎯 " + "x" * 60) is False
    assert curated._looks_like_heading("🎯 A sentence.") is False


def test_looks_like_heading_rejects_quoted_line() -> None:
    assert curated._looks_like_heading('"One quoted line."') is False


def test_looks_like_heading_rejects_curly_quoted_line() -> None:
    assert curated._looks_like_heading("“Một câu trích”") is False


def test_looks_like_heading_rejects_bullet_line() -> None:
    assert curated._looks_like_heading("• A bullet without a marker strip") is False


def test_looks_like_heading_keeps_emoji_heading() -> None:
    assert curated._looks_like_heading("🎯 TL;DR") is True


def test_curated_blocks_promotes_colonless_emoji_heading() -> None:
    blocks = curated.curated_blocks(SUMMARY)
    assert any(
        block.kind == "h"
        and "TL;DR" in "".join(text for text, _bold in block.runs)
        for block in blocks
    )


def test_curated_blocks_keeps_bullets_and_bold_runs() -> None:
    blocks = curated.curated_blocks(SUMMARY)
    assert any(block.kind == "b" for block in blocks)
    assert any(bold for block in blocks for _text, bold in block.runs)


def test_sections_of_strips_emoji_and_numbers_anchors() -> None:
    sections = curated.sections_of(curated.curated_blocks(SUMMARY))
    assert sections[0].anchor == "s1"
    assert not sections[0].label.startswith("🎯")
    assert [section.anchor for section in sections] == [
        "s1",
        "s2",
        "s3",
        "s4",
    ]


def test_sections_of_does_not_promote_bare_quotation() -> None:
    summary = """\
🎯 TL;DR

A short introduction.

📌 BỐI CẢNH

The context is described here.

🔑 LUẬN ĐIỂM CHÍNH

The main point is stated here.

💬 TRÍCH DẪN ĐÁNG CHÚ Ý

“Una frase citada”
"""
    sections = curated.sections_of(curated.curated_blocks(summary))
    assert [section.anchor for section in sections] == [
        "s1",
        "s2",
        "s3",
        "s4",
    ]


def test_lead_text_uses_first_paragraph() -> None:
    blocks = curated.curated_blocks(SUMMARY)
    assert curated.lead_text(blocks) == (
        "Video presents a model where one agent coordinates the rest."
    )
    assert curated.lead_text(blocks) != "🎯 TL;DR"


def test_lead_text_handles_empty_and_bullet_only_blocks() -> None:
    assert curated.lead_text(()) == ""
    blocks = curated.curated_blocks("• Only bullet text")
    assert curated.lead_text(blocks) == "Only bullet text"


def test_reading_minutes_never_returns_zero() -> None:
    assert curated.reading_minutes(1) == 1
    assert curated.reading_minutes(_WORDS_PER_MINUTE * 5) == 5


def test_count_words_handles_empty_summary() -> None:
    assert curated.count_words("") == 0


def test_group_by_day_preserves_order(tmp_path: Path) -> None:
    first = _one_item(tmp_path, summary="first")
    second = curated.CuratedItem(
        id="second",
        title="Second",
        raw_title="Second",
        channel="Channel",
        url="",
        thumbnail="",
        day=first.day,
        processed_at=first.processed_at,
        published_iso="",
        summary="second",
        blocks=(),
        sections=(),
        lead="",
        words=1,
        minutes=1,
    )
    grouped = curated.group_by_day([first, second])
    assert [item.id for item in grouped[first.day]] == ["abc", "second"]


def test_available_days_are_sorted_without_duplicates(tmp_path: Path) -> None:
    path = _make_db(
        tmp_path,
        rows=(
            {"id": "a", "processed_at": "2026-08-09T01:00:00"},
            {"id": "b", "processed_at": "2026-08-08T01:00:00"},
            {"id": "c", "processed_at": "2026-08-09T02:00:00"},
        ),
    )
    conn = _connect(path)
    assert curated.available_days(conn) == ["2026-08-08", "2026-08-09"]


# Group B: payload construction.


def test_curated_teaser_omits_blocks(tmp_path: Path) -> None:
    item = _one_item(tmp_path)
    teaser = curated_teaser(item)
    assert "lead" in teaser
    assert "bl" not in teaser


def test_curated_payload_has_expected_shape(tmp_path: Path) -> None:
    payload = curated_payload(_one_item(tmp_path))
    assert payload["kind"] == "curated"
    assert isinstance(payload["toc"], list)
    assert isinstance(payload["bl"], list)
    assert all(set(block) == {"k", "r"} for block in payload["bl"])


def test_curated_payload_preserves_script_as_plain_run_data(tmp_path: Path) -> None:
    item = _one_item(tmp_path, summary="🎯 Heading\n\nText <script>alert(1)</script>")
    payload = curated_payload(item)
    runs = [run for block in payload["bl"] for run, _bold in block["r"]]
    assert "<script>alert(1)</script>" in "".join(runs)
    assert all(
        isinstance(run, str)
        for block in payload["bl"]
        for run, _bold in block["r"]
    )
    assert "<script>" in json.dumps(payload)


def test_curated_index_payload_has_total_and_items(tmp_path: Path) -> None:
    first = _one_item(tmp_path)
    second = curated.CuratedItem(
        **{field: getattr(first, field) for field in first.__slots__}
    )
    items = [first, second]
    payload = curated_index_payload(items, generated_at="2026-08-09T00:00:00+07:00")
    assert payload["kind"] == "curatedIndex"
    assert payload["total"] == 2
    assert len(payload["items"]) == 2


def test_curated_index_items_use_curated_kind_and_ids(tmp_path: Path) -> None:
    item = _one_item(tmp_path)
    entries = curated_index_items([item])
    assert entries[0]["k"] == "c"
    assert entries[0]["i"] == "abc"


def test_manifest_omits_curated_when_unsurveyed() -> None:
    data = manifest(
        days=[("2026-08-09", 3)],
        months=["2026-08"],
        entities=[],
        generated_at="2026-08-09T00:00:00+07:00",
        kdf_iterations=250000,
        site="Kho tin",
        version="0.11.0",
    )
    assert "curated" not in data


def test_manifest_includes_empty_curated_list() -> None:
    data = manifest(
        days=[("2026-08-09", 3)],
        months=["2026-08"],
        entities=[],
        curated=[],
        generated_at="2026-08-09T00:00:00+07:00",
        kdf_iterations=250000,
        site="Kho tin",
        version="0.11.0",
    )
    assert data["curated"] == []


def test_manifest_includes_curated_ids() -> None:
    data = manifest(
        days=[],
        months=[],
        entities=[],
        curated=["abc"],
        generated_at="2026-08-09T00:00:00+07:00",
        kdf_iterations=250000,
        site="Kho tin",
        version="0.11.0",
    )
    assert data["curated"] == ["abc"]


# Group C: orphan pruning.


def test_expected_paths_includes_curated_ids(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    expected = prune_orphans.expected_paths({"curated": ["abc", "def"]}, docs)
    assert docs / "c" / "abc" in expected
    assert docs / "c" / "def" in expected


def test_find_orphans_reports_unlisted_curated_directory(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    (docs / "c" / "orphan").mkdir(parents=True)
    assert prune_orphans.find_orphans({"curated": []}, docs) == [
        docs / "c" / "orphan"
    ]


def test_find_orphans_keeps_listed_curated_directory(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    (docs / "c" / "kept").mkdir(parents=True)
    assert prune_orphans.find_orphans({"curated": ["kept"]}, docs) == []


def test_find_orphans_ignores_curated_without_manifest_key(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    (docs / "c" / "untouched").mkdir(parents=True)
    assert prune_orphans.find_orphans({}, docs) == []


def test_find_orphans_ignores_curated_index_file(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    curated_dir = docs / "c"
    curated_dir.mkdir(parents=True)
    (curated_dir / "index.html").write_text("listing")
    assert prune_orphans.find_orphans({"curated": []}, docs) == []
