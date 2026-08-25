"""Read layer for the substack-digest database — long-form essays from followed authors.

A row here is a full essay (usually 800-2000+ words) summarised with the author's own
argument structure, concrete anecdotes and takeaways preserved — a different reading
problem from a 280-character X post or a 5-minute video recap. The summariser was built
to emit the same emoji-led, colon-less heading style as a curated deep dive on purpose, so
this module reuses `curated.py`'s heading/section/lead parsing rather than duplicating it;
what differs is only the source (an essay someone wrote and posted themselves, not a video
someone picked to analyse), so it gets its own table, its own identity and its own
"Từ Substack" section instead of being folded into "Phân tích sâu".

The table is optional: news-vault must still build on a machine that has never run
substack-digest.
"""

from __future__ import annotations

import datetime
import sqlite3
from collections.abc import Iterator, Sequence
from dataclasses import dataclass

from .curated import Section, count_words, curated_blocks, lead_text, reading_minutes, sections_of
from .videos import Block, connect

__all__ = [
    "Essay",
    "TABLE",
    "available_days",
    "connect",
    "group_by_day",
    "has_table",
    "load_all",
]

TABLE = "posts"


@dataclass(frozen=True, slots=True)
class Essay:
    id: str
    title: str
    author_handle: str
    author_name: str
    url: str
    day: str  # "YYYY-MM-DD"
    published_iso: str  # ISO-8601, "" when unknown
    summary: str  # verbatim
    blocks: tuple[Block, ...]
    sections: tuple[Section, ...]
    lead: str  # first paragraph, for the teaser card on the day page
    words: int
    minutes: int


def has_table(conn: sqlite3.Connection) -> bool:
    """Return True when the posts table exists.

    Probed rather than assumed: a machine that has never run substack-digest must still
    build without this section.
    """
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?", (TABLE,)
    )
    try:
        return cursor.fetchone() is not None
    finally:
        cursor.close()


def available_days(conn: sqlite3.Connection) -> list[str]:
    """Every day key with at least one summarised essay, ascending."""
    return sorted({item.day for item in load_all(conn)})


def load_all(conn: sqlite3.Connection) -> list[Essay]:
    """Every summarised essay, newest day first, newest publish time within a day."""
    items = [item for item in _iter_items(conn) if item is not None]
    # Stable sort so id is the final ascending tie-breaker between two same-second rows.
    items = sorted(items, key=lambda item: item.id)
    items.sort(key=lambda item: (item.day, item.published_iso), reverse=True)
    return items


def group_by_day(items: Sequence[Essay]) -> dict[str, list[Essay]]:
    grouped: dict[str, list[Essay]] = {}
    for item in items:
        grouped.setdefault(item.day, []).append(item)
    return grouped


def _iter_items(conn: sqlite3.Connection) -> Iterator[Essay | None]:
    """Yield summarised essays, or None for a row with no usable title/date.

    Only rows the summariser finished: a post still mid-pipeline has no body worth its own
    page yet, same reasoning as `curated._iter_items`'s `success = 1` guard.
    """
    if not has_table(conn):
        return
    query = (
        "SELECT p.id, p.url, p.author_handle, p.title, p.published_at, p.fetched_at, "
        "p.summary_text, f.display_name "
        f"FROM {TABLE} p LEFT JOIN followed_authors f ON f.handle = p.author_handle "
        "WHERE p.summary_text IS NOT NULL AND TRIM(p.summary_text) <> '' ORDER BY p.id"
    )
    cursor = conn.execute(query)
    try:
        for row in cursor:
            yield _item_from_row(row)
    finally:
        cursor.close()


def _item_from_row(row: sqlite3.Row) -> Essay | None:
    title = (row["title"] or "").strip()
    post_id = str(row["id"] or "")
    summary = row["summary_text"] or ""
    if not post_id or not title or not summary.strip():
        return None

    published_at = row["published_at"] or ""
    fetched_at = row["fetched_at"] or ""
    day = _resolve_day(published_at, fetched_at)
    if not day:
        return None

    blocks = curated_blocks(summary)
    words = count_words(summary)
    display_name = (row["display_name"] or "").strip()
    return Essay(
        id=post_id,
        title=title,
        author_handle=row["author_handle"] or "",
        author_name=display_name or (row["author_handle"] or ""),
        url=row["url"] or "",
        day=day,
        published_iso=_published_iso(published_at, fetched_at),
        summary=summary,
        blocks=blocks,
        sections=sections_of(blocks),
        lead=lead_text(blocks),
        words=words,
        minutes=reading_minutes(words),
    )


def _resolve_day(published_at: str, fetched_at: str) -> str:
    """The essay's own publish date wins; the scrape time is only a fallback for the rare
    row where the author's page carried no parseable publish date."""
    for candidate in (published_at, fetched_at):
        if not candidate:
            continue
        try:
            return datetime.datetime.fromisoformat(candidate[:10]).date().isoformat()
        except ValueError:
            continue
    return ""


def _published_iso(published_at: str, fetched_at: str) -> str:
    """ISO-8601 timestamp for the essay; substack-digest already stores UTC-aware values."""
    for candidate in (published_at, fetched_at):
        if not candidate:
            continue
        try:
            parsed = datetime.datetime.fromisoformat(candidate.replace("Z", "+00:00"))
        except ValueError:
            continue
        return parsed.isoformat()
    return ""
