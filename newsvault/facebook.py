"""Read layer for the optional :mod:`facebook_digest` ``feed_posts`` table.

The sibling scraper owns this SQLite database.  News-vault only reads completed,
newsworthy summaries from it, so a missing database or table leaves the archive usable.
"""

from __future__ import annotations

import datetime
import sqlite3
from collections.abc import Iterator, Sequence
from dataclasses import dataclass

from .curated import curated_blocks
from .videos import Block, connect

__all__ = [
    "FacebookPost",
    "TABLE",
    "available_days",
    "connect",
    "group_by_day",
    "has_table",
    "load_all",
]

TABLE = "feed_posts"
NO_NEWS_SUMMARY = "Không có nội dung tin tức đáng chú ý."


@dataclass(frozen=True, slots=True)
class FacebookPost:
    id: str
    url: str
    author_name: str
    category: str
    image: str
    day: str
    published_iso: str
    summary: str
    text: str
    blocks: tuple[Block, ...]


def has_table(conn: sqlite3.Connection) -> bool:
    """Return True when facebook-digest has created ``feed_posts``."""
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?", (TABLE,)
    )
    try:
        return cursor.fetchone() is not None
    finally:
        cursor.close()


def available_days(conn: sqlite3.Connection) -> list[str]:
    return sorted({post.day for post in load_all(conn)})


def load_all(conn: sqlite3.Connection) -> list[FacebookPost]:
    """Every completed, newsworthy Facebook summary, newest first."""
    posts = [post for post in _iter_posts(conn) if post is not None]
    posts = sorted(posts, key=lambda post: post.id)
    posts.sort(key=lambda post: (post.day, post.published_iso), reverse=True)
    return posts


def group_by_day(posts: Sequence[FacebookPost]) -> dict[str, list[FacebookPost]]:
    grouped: dict[str, list[FacebookPost]] = {}
    for post in posts:
        grouped.setdefault(post.day, []).append(post)
    return grouped


def _iter_posts(conn: sqlite3.Connection) -> Iterator[FacebookPost | None]:
    if not has_table(conn):
        return
    query = (
        f"SELECT id, category, author_name, post_url, text, image_url, summary_text, scraped_at "
        f"FROM {TABLE} "
        "WHERE summary_text IS NOT NULL AND TRIM(summary_text) <> '' "
        "AND TRIM(summary_text) <> ? ORDER BY id"
    )
    cursor = conn.execute(query, (NO_NEWS_SUMMARY,))
    try:
        for row in cursor:
            yield _post_from_row(row)
    finally:
        cursor.close()


def _post_from_row(row: sqlite3.Row) -> FacebookPost | None:
    post_id = str(row["id"] or "")
    summary = (row["summary_text"] or "").strip()
    scraped_at = row["scraped_at"] or ""
    day = _resolve_day(scraped_at)
    if not post_id or not summary or summary == NO_NEWS_SUMMARY or not day:
        return None
    return FacebookPost(
        id=post_id,
        url=(row["post_url"] or "").strip(),
        author_name=(row["author_name"] or "").strip(),
        category=(row["category"] or "").strip(),
        image=_https_url(row["image_url"]),
        day=day,
        published_iso=_published_iso(scraped_at),
        summary=summary,
        text=(row["text"] or "").strip(),
        blocks=curated_blocks(summary),
    )


def _https_url(raw: object) -> str:
    """Keep an untrusted image URL inert unless facebook-digest supplied HTTPS."""
    return raw.strip() if isinstance(raw, str) and raw.strip().startswith("https://") else ""


def _resolve_day(scraped_at: str) -> str:
    try:
        return datetime.datetime.fromisoformat(scraped_at[:10]).date().isoformat()
    except ValueError:
        return ""


def _published_iso(scraped_at: str) -> str:
    try:
        return datetime.datetime.fromisoformat(scraped_at.replace("Z", "+00:00")).isoformat()
    except ValueError:
        return ""
