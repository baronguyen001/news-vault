"""Read layer for the ``curated_videos`` table of the youtube-summarizer database.

These rows are a different product from the ``videos`` table that :mod:`newsvault.videos`
reads. A row in ``videos`` is a 300-600 word recap produced by an automatic nightly sweep;
a row here is an 800-1200 word analysis of a video the reader picked by hand, with sections
for the argument, the evidence behind it and the counter-argument. Long-form text needs its
own page and its own reading layout, so it gets its own module rather than a flag on
:class:`newsvault.videos.Video`.

The table is optional: a database predating the curated pipeline must still build.
"""

from __future__ import annotations

import datetime
import re
import sqlite3
from collections.abc import Iterator, Sequence
from dataclasses import dataclass

from .videos import Block, clean_title, summary_blocks, thumbnail_url

TABLE = "curated_videos"

# Vietnamese prose averages close to this; used only for the "N phút đọc" hint, so being
# a little off changes nothing that matters.
_WORDS_PER_MINUTE = 200

# Leading emoji/punctuation on a section heading, e.g. "🎯 TL;DR" -> "TL;DR". Kept for the
# table of contents only; the heading itself keeps its emoji so the page still reads well.
_HEADING_LEAD_RE = re.compile(r"^[^\w]+", re.UNICODE)

# A curated heading is short, emoji-led and not a sentence. 60 characters clears the
# longest one this prompt produces ("📊 SỐ LIỆU & DỮ KIỆN ĐÁNG NHỚ") with room to spare
# while still rejecting a paragraph that happens to open with an emoji.
_HEADING_MAX_CHARS = 60
_SENTENCE_END = ".!?…:;,"

# Characters that open a sentence, never a section title. The quotes matter most: the
# prompt asks for one to three verbatim quotations, and a short one like
# `"One quoted line."` is emoji-free, under 60 characters and ends on a quote mark rather
# than a full stop, so every other test here passes it and it lands in the table of
# contents as a phantom section.
_HEADING_BAD_LEAD = frozenset("\"'“”‘’«»([{<-–—*•·#>/\\|")


def _looks_like_heading(text: str) -> bool:
    """True for a curated section heading such as "🎯 TL;DR" or "📌 BỐI CẢNH".

    :func:`newsvault.videos.summary_blocks` only promotes an emoji-led line to a heading
    when it also contains a colon, because that is how the nightly recap prompt writes
    them ("📊 TÌNH HÌNH: ..."). The curated prompt writes the heading on a line of its own
    with NO colon, so every section title fell through to a paragraph: the table of
    contents came out empty and the teaser on the day page read "🎯 TL;DR" instead of the
    actual summary. Detect the colon-less form here rather than change the shared parser,
    which the whole video archive already depends on.
    """
    if not text or text[0].isalnum() or text[0] in _HEADING_BAD_LEAD:
        return False
    if len(text) > _HEADING_MAX_CHARS:
        return False
    return text[-1] not in _SENTENCE_END


def curated_blocks(summary: str) -> tuple[Block, ...]:
    """Parse a curated summary, promoting colon-less emoji headings to headings."""
    return tuple(
        Block(kind="h", runs=block.runs)
        if block.kind == "p" and _looks_like_heading("".join(t for t, _ in block.runs).strip())
        else block
        for block in summary_blocks(summary)
    )


@dataclass(frozen=True, slots=True)
class Section:
    """One heading in the analysis, for the table of contents."""

    anchor: str  # "s1", "s2", ... - stable, and free of Vietnamese diacritics
    label: str  # heading text with the leading emoji stripped


@dataclass(frozen=True, slots=True)
class CuratedItem:
    id: str
    title: str  # cleaned, see videos.clean_title
    raw_title: str
    channel: str
    url: str
    thumbnail: str
    day: str  # "YYYY-MM-DD", from processed_at
    processed_at: str  # verbatim
    published_iso: str  # ISO-8601, "" when unknown
    summary: str  # verbatim
    blocks: tuple[Block, ...]
    sections: tuple[Section, ...]
    lead: str  # first paragraph, for the teaser card on the day page
    words: int
    minutes: int


def has_table(conn: sqlite3.Connection) -> bool:
    """Return True when the curated table exists.

    Probed rather than assumed: the curated pipeline shipped after this site did, so a
    reader still running the older summarizer has a database without this table and must
    keep building.
    """
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?", (TABLE,)
    )
    try:
        return cursor.fetchone() is not None
    finally:
        cursor.close()


def lead_text(blocks: Sequence[Block]) -> str:
    """First paragraph of the analysis, used as the teaser on the day page.

    Falls back to the first block of any kind so a summary written entirely as bullets
    still gets a teaser rather than an empty card.
    """
    paragraphs = [block for block in blocks if block.kind == "p"]
    chosen = paragraphs[0] if paragraphs else (blocks[0] if blocks else None)
    if chosen is None:
        return ""
    return "".join(text for text, _bold in chosen.runs).strip()


def sections_of(blocks: Sequence[Block]) -> tuple[Section, ...]:
    """Build the table of contents from the heading blocks.

    Anchors are positional (``s1``, ``s2``) rather than slugs of the heading text: the
    headings are Vietnamese with diacritics and emoji, and a positional id keeps the URL
    fragment ASCII without needing a transliteration table.
    """
    out: list[Section] = []
    index = 0
    for block in blocks:
        if block.kind != "h":
            continue
        index += 1
        raw = "".join(text for text, _bold in block.runs).strip()
        label = _HEADING_LEAD_RE.sub("", raw).strip() or raw
        out.append(Section(anchor=f"s{index}", label=label))
    return tuple(out)


def count_words(summary: str) -> int:
    return len((summary or "").split())


def reading_minutes(words: int) -> int:
    """Minutes to read, never below 1 so a short piece does not claim '0 phút đọc'."""
    return max(1, round(words / _WORDS_PER_MINUTE))


def available_days(conn: sqlite3.Connection) -> list[str]:
    """Every day key that has at least one published analysis, ascending."""
    return sorted({item.day for item in load_all(conn)})


def load_all(conn: sqlite3.Connection) -> list[CuratedItem]:
    """Return every published analysis, newest first."""
    items = [item for item in _iter_items(conn) if item is not None]
    # Stable sort so id is the final ascending tie-breaker between two same-second rows.
    items = sorted(items, key=lambda item: item.id)
    items.sort(key=lambda item: (item.day, item.processed_at), reverse=True)
    return items


def group_by_day(items: Sequence[CuratedItem]) -> dict[str, list[CuratedItem]]:
    grouped: dict[str, list[CuratedItem]] = {}
    for item in items:
        grouped.setdefault(item.day, []).append(item)
    return grouped


def _iter_items(conn: sqlite3.Connection) -> Iterator[CuratedItem | None]:
    """Yield published analyses, or None for a row with no usable date."""
    if not has_table(conn):
        return
    # telegram_sent is deliberately NOT part of the condition: whether the reader's phone
    # got the message says nothing about whether the analysis is worth publishing here.
    query = (
        f"SELECT id, url, title, channel, summary, processed_at FROM {TABLE} "
        "WHERE success = 1 AND TRIM(summary) <> '' ORDER BY id"
    )
    cursor = conn.execute(query)
    try:
        for row in cursor:
            yield _item_from_row(row)
    finally:
        cursor.close()


def _item_from_row(row: sqlite3.Row) -> CuratedItem | None:
    raw_title = row["title"] or ""
    channel = row["channel"] or ""
    processed_at = row["processed_at"] or ""
    summary = row["summary"] or ""
    item_id = row["id"] or ""

    day = _resolve_day(processed_at)
    if not day or not item_id:
        return None

    blocks = curated_blocks(summary)
    words = count_words(summary)
    return CuratedItem(
        id=item_id,
        title=clean_title(raw_title, channel),
        raw_title=raw_title,
        channel=channel,
        url=row["url"] or "",
        # Always the 4:3 still: curated picks are long-form talks, never 9:16 Shorts, and
        # hqdefault is the one size YouTube guarantees for every video however old.
        thumbnail=thumbnail_url(item_id, is_short=False),
        day=day,
        processed_at=processed_at,
        published_iso=_published_iso(processed_at),
        summary=summary,
        blocks=blocks,
        sections=sections_of(blocks),
        lead=lead_text(blocks),
        words=words,
        minutes=reading_minutes(words),
    )


def _resolve_day(processed_at: str) -> str:
    """Day key from the analysis timestamp, or "" when it cannot be parsed.

    There is no ``upload_date`` here, unlike the ``videos`` table: a curated pick is filed
    under the day it was analysed, which is the day the reader chose to look at it. A talk
    from two years ago read today belongs to today's reading, not to a dead archive day.
    """
    try:
        return datetime.datetime.fromisoformat(processed_at[:10]).date().isoformat()
    except ValueError:
        return ""


def _published_iso(processed_at: str) -> str:
    """ISO-8601 timestamp, assuming Vietnam time for the naive values actually stored."""
    try:
        parsed = datetime.datetime.fromisoformat(processed_at)
    except ValueError:
        return ""
    if parsed.tzinfo is None:
        return f"{parsed.isoformat()}+07:00"
    return parsed.isoformat()
