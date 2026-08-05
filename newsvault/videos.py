"""Read layer for the youtube-summarizer database."""

from __future__ import annotations

import datetime
import re
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

_CONNECT_TIMEOUT = 30.0

# YouTube video ids are exactly 11 characters from this alphabet.
_YOUTUBE_ID_RE = re.compile(r"[A-Za-z0-9_-]{11}")

# Bare "uploaded :" prefix, with any amount of whitespace around the words.
_BARE_UPLOADED_RE = re.compile(r"^uploaded\s*:\s*", re.IGNORECASE)

# Bullet marker is *, - or • followed by whitespace.
_BULLET_RE = re.compile(r"^[ \t]*[*\-•]\s+(.*)$")

# What a content-free bullet line collapses to once whitespace is stripped.
_EMPTY_BULLETS = frozenset({"*", "-", "•"})


@dataclass(frozen=True, slots=True)
class Block:
    kind: str  # "h" heading | "p" paragraph | "b" bullet
    runs: tuple[tuple[str, bool], ...]  # (text, is_bold) in document order


@dataclass(frozen=True, slots=True)
class Video:
    id: str
    title: str  # cleaned, see clean_title
    raw_title: str  # exactly as stored
    channel: str
    url: str
    thumbnail: str  # see thumbnail_url
    day: str  # "YYYY-MM-DD"
    processed_at: str  # verbatim
    published_iso: str  # ISO-8601, "" when unknown
    video_type: str  # may be ""
    summary: str  # verbatim
    blocks: tuple[Block, ...]


def clean_title(title: str, channel: str) -> str:
    """Remove a leading ``<channel> uploaded:`` or ``uploaded:`` prefix from a video title."""
    if not title:
        return title
    rest = title
    if channel:
        # Match the literal channel name, case-insensitively, with flexible spacing.
        channel_pattern = re.compile(
            rf"^{re.escape(channel)}\s+uploaded\s*:\s*",
            re.IGNORECASE,
        )
        match = channel_pattern.match(title)
        if match:
            rest = title[match.end() :]
    bare_match = _BARE_UPLOADED_RE.match(rest)
    if bare_match:
        rest = rest[bare_match.end() :]
    cleaned = rest.strip()
    # Do not return an empty string when the original title contained only the prefix.
    return cleaned if cleaned else title


def thumbnail_url(video_id: str) -> str:
    """Return YouTube's guaranteed thumbnail URL, or an empty string for an invalid id."""
    if _YOUTUBE_ID_RE.fullmatch(video_id or ""):
        return f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
    return ""


def summary_blocks(summary: str) -> tuple[Block, ...]:
    """Turn a raw summary into plain-text blocks; no markup reaches the browser."""
    blocks: list[Block] = []
    for raw_line in summary.splitlines():
        stripped = raw_line.strip()
        # A bullet marker with nothing after it ("*   ") strips down to a bare "*", which
        # no longer matches the bullet pattern and would otherwise be emitted as a
        # paragraph whose entire text is an asterisk.
        if not stripped or stripped in _EMPTY_BULLETS:
            continue
        bullet_match = _BULLET_RE.match(stripped)
        if bullet_match:
            kind = "b"
            text = bullet_match.group(1).strip()
        elif not (stripped[0].isalpha() or stripped[0].isdigit()) and ":" in stripped[:40]:
            # Emoji/punctuation-led lines with an early colon are section headings.
            kind = "h"
            text = stripped
        else:
            kind = "p"
            text = stripped
        runs = _parse_runs(text)
        if runs:
            blocks.append(Block(kind=kind, runs=runs))
    return tuple(blocks)


def _parse_runs(text: str) -> tuple[tuple[str, bool], ...]:
    """Split text on paired ``**`` markers; unpaired markers stay literal."""
    parts = text.split("**")
    # An odd number of ``**`` delimiters means the last one has no closing pair.
    if len(parts) % 2 == 0:
        parts[-2] = parts[-2] + "**" + parts[-1]
        parts.pop()
    runs: list[tuple[str, bool]] = []
    for index, part in enumerate(parts):
        if not part:
            continue
        runs.append((part, index % 2 == 1))
    return tuple(runs)


def connect(path: Path | str) -> sqlite3.Connection:
    """Open the youtube-summarizer database read-only."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"database not found: {path}")
    uri = f"file:{path.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=_CONNECT_TIMEOUT)
    conn.row_factory = sqlite3.Row
    return conn


def has_upload_date(conn: sqlite3.Connection) -> bool:
    """Return True when the ``videos`` table has an ``upload_date`` column."""
    cursor = conn.execute("PRAGMA table_info(videos)")
    try:
        return any(row["name"] == "upload_date" for row in cursor)
    finally:
        cursor.close()


def available_days(conn: sqlite3.Connection) -> list[str]:
    """Return every day key that has archive content, ascending."""
    return sorted({video.day for video in _iter_videos(conn) if video is not None})


def counts_by_day(conn: sqlite3.Connection) -> dict[str, int]:
    """Return row counts per day key for archive content."""
    counts: dict[str, int] = {}
    for video in _iter_videos(conn):
        if video is None:
            continue
        counts[video.day] = counts.get(video.day, 0) + 1
    return counts


def load_range(conn: sqlite3.Connection, start: str, end: str) -> list[Video]:
    """Return archive videos whose resolved day falls inside the inclusive range."""
    return [video for video in load_all(conn) if start <= video.day <= end]


def load_all(conn: sqlite3.Connection) -> list[Video]:
    """Return every archive video, newest day first and newest timestamp first within a day."""
    videos = [video for video in _iter_videos(conn) if video is not None]
    # Stable sort so id is the final ascending tie-breaker.
    videos = sorted(videos, key=lambda video: video.id)
    videos.sort(key=lambda video: (video.day, video.processed_at), reverse=True)
    return videos


def _iter_videos(conn: sqlite3.Connection) -> Iterator[Video | None]:
    """Yield archive videos, or None for rows that cannot be filed under a day."""
    columns = [
        "id",
        "title",
        "channel",
        "url",
        "processed_at",
        "summary",
        "video_type",
        "success",
    ]
    upload_date_present = has_upload_date(conn)
    if upload_date_present:
        columns.append("upload_date")
    query = (
        f"SELECT {', '.join(columns)} FROM videos WHERE success = 1 AND summary <> '' ORDER BY id"
    )
    cursor = conn.execute(query)
    try:
        for row in cursor:
            yield _video_from_row(row, has_upload_date=upload_date_present)
    finally:
        cursor.close()


def _video_from_row(row: sqlite3.Row, *, has_upload_date: bool) -> Video | None:
    """Build a Video, returning None when the row cannot be placed on a calendar day."""
    raw_title = row["title"] or ""
    channel = row["channel"] or ""
    processed_at = row["processed_at"] or ""
    summary = row["summary"] or ""
    upload_date = row["upload_date"] if has_upload_date else None
    day, source = _resolve_day(processed_at, upload_date)
    if not day:
        return None
    return Video(
        id=row["id"] or "",
        title=clean_title(raw_title, channel),
        raw_title=raw_title,
        channel=channel,
        url=row["url"] or "",
        thumbnail=thumbnail_url(row["id"] or ""),
        day=day,
        processed_at=processed_at,
        published_iso=_published_iso(day, source, processed_at),
        video_type=row["video_type"] or "",
        summary=summary,
        blocks=summary_blocks(summary),
    )


def _resolve_day(processed_at: str, upload_date: str | None) -> tuple[str, str]:
    """Return (day, source) or ("", "") when no usable date exists.

    ``upload_date`` wins because yt-dlp reports the real publish date.
    """
    if upload_date:
        try:
            parsed = datetime.datetime.strptime(upload_date, "%Y%m%d")
            return (parsed.date().isoformat(), "upload_date")
        except ValueError:
            pass
    date_part = processed_at[:10]
    try:
        parsed = datetime.datetime.fromisoformat(date_part)
        return (parsed.date().isoformat(), "processed_at")
    except ValueError:
        return ("", "")


def _published_iso(day: str, source: str, processed_at: str) -> str:
    """Return an ISO-8601 timestamp with the original or Vietnam timezone."""
    if source == "upload_date":
        return f"{day}T00:00:00+07:00"
    return _normalise_processed_at(processed_at) or ""


def _normalise_processed_at(processed_at: str) -> str:
    """Convert a local ISO timestamp into an ISO-8601 string.

    If the timestamp already carries an offset, keep it unchanged; only assume +07:00
    for naive values, which is what the summarizer actually stores.
    """
    try:
        dt = datetime.datetime.fromisoformat(processed_at)
    except ValueError:
        return ""
    if dt.tzinfo is None:
        return f"{dt.isoformat()}+07:00"
    return dt.isoformat()
