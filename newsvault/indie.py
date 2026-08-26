"""Read layer for the x-pulse `indie_posts` table - build-in-public / SaaS-launch signal
from a small, hand-picked list of indie-hacker accounts.

Deliberately separate from :mod:`newsvault.posts`, which reads the 5-vertical `x_feed`
view: `indie_posts` is a different table in the same `x_pulse.db`, filled by
`xpulse/indie.py`'s own scraper that never touches `sources.tsv` or `x_feed` (see that
module's docstring for why the two stay apart). Only rows the model marked worth keeping
(`keep = 1`, a non-empty Vietnamese translation) are read here - a card with no translation
would just show raw English in what is otherwise a Vietnamese archive.
"""

from __future__ import annotations

import datetime
import sqlite3
from collections.abc import Iterator, Sequence
from dataclasses import dataclass

from .videos import connect

__all__ = [
    "IndiePost",
    "TABLE",
    "available_days",
    "connect",
    "group_by_day",
    "has_table",
    "load_all",
]

TABLE = "indie_posts"


@dataclass(frozen=True, slots=True)
class IndiePost:
    id: str
    url: str
    author: str  # handle, no "@"
    author_name: str
    text_vi: str
    day: str  # "YYYY-MM-DD"
    published_iso: str  # ISO-8601, "" when unknown
    likes: int = 0
    retweets: int = 0
    replies: int = 0
    image: str = ""  # media_url, only https is accepted - see posts.py's same guard


def has_table(conn: sqlite3.Connection) -> bool:
    """Return True when the indie_posts table exists.

    Probed rather than assumed: a machine that has never run `xpulse.cli indie` must still
    build without this section - same contract as :func:`newsvault.posts.has_table`.
    """
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?", (TABLE,)
    )
    try:
        return cursor.fetchone() is not None
    finally:
        cursor.close()


def available_days(conn: sqlite3.Connection) -> list[str]:
    return sorted({post.day for post in load_all(conn)})


def load_all(conn: sqlite3.Connection) -> list[IndiePost]:
    """Every kept, translated post, newest day first, newest within a day."""
    posts = [post for post in _iter_posts(conn) if post is not None]
    posts = sorted(posts, key=lambda post: post.id)
    posts.sort(key=lambda post: (post.day, post.published_iso), reverse=True)
    return posts


def group_by_day(posts: Sequence[IndiePost]) -> dict[str, list[IndiePost]]:
    grouped: dict[str, list[IndiePost]] = {}
    for post in posts:
        grouped.setdefault(post.day, []).append(post)
    return grouped


def _has_media_column(conn: sqlite3.Connection) -> bool:
    """True once x-pulse has migrated `indie_posts` to carry `media_url`.

    A reader built against an older x-pulse database (before this column existed) must
    still build - same reasoning as :func:`newsvault.substack._has_image_column`.
    """
    cursor = conn.execute(f"PRAGMA table_info({TABLE})")
    try:
        return any(row["name"] == "media_url" for row in cursor)
    finally:
        cursor.close()


def _https_url(raw: object) -> str:
    """Keep untrusted media URLs inert unless x-pulse supplied HTTPS - same guard posts.py uses."""
    return raw.strip() if isinstance(raw, str) and raw.strip().startswith("https://") else ""


def _iter_posts(conn: sqlite3.Connection) -> Iterator[IndiePost | None]:
    if not has_table(conn):
        return
    media_column = ", media_url" if _has_media_column(conn) else ""
    query = (
        f"SELECT id, url, author, author_name, text, created_at, day, likes, retweets, "
        f"replies, summary_vi{media_column} FROM {TABLE} "
        "WHERE keep = 1 AND summary_vi IS NOT NULL AND TRIM(summary_vi) <> '' ORDER BY id"
    )
    cursor = conn.execute(query)
    try:
        for row in cursor:
            yield _post_from_row(row)
    finally:
        cursor.close()


def _post_from_row(row: sqlite3.Row) -> IndiePost | None:
    post_id = str(row["id"] or "")
    text_vi = (row["summary_vi"] or "").strip()
    day = row["day"] or ""
    if not post_id or not text_vi or not day:
        return None
    # row.keys(), not row itself - sqlite3.Row.__contains__ searches values, not columns.
    image = _https_url(row["media_url"]) if "media_url" in row.keys() else ""  # noqa: SIM118
    return IndiePost(
        id=post_id,
        url=row["url"] or "",
        author=(row["author"] or "").lstrip("@"),
        author_name=row["author_name"] or "",
        text_vi=text_vi,
        day=day,
        published_iso=_published_iso(row["created_at"] or ""),
        likes=int(row["likes"] or 0),
        retweets=int(row["retweets"] or 0),
        replies=int(row["replies"] or 0),
        image=image,
    )


def _published_iso(created_at: str) -> str:
    if not created_at:
        return ""
    try:
        parsed = datetime.datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError:
        return ""
    return parsed.isoformat()
