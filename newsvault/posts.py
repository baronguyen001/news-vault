"""Read layer for the x-pulse database - important and trending posts from X.

The third stream on a day page, after articles and videos. A post here is not a news
article: it is 280 characters that a language model scored, translated and summarised,
carrying an author whose credibility was asserted by hand rather than inferred. So it
gets its own card and its own panel rather than being mixed into the article flow, where
its score would be read as comparable to a Reuters wire.

Only one name is read out of that database: the ``x_feed`` view. x-pulse can restructure
its tables freely as long as that view keeps its columns, which is the point of reading a
view rather than a join.

Like :mod:`newsvault.curated`, the source is optional - the view is probed, not assumed,
so a database predating x-pulse still builds.
"""

from __future__ import annotations

import datetime
import json
import sqlite3
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field

from .videos import Block, connect, summary_blocks

__all__ = [
    "Post",
    "TABLE",
    "available_days",
    "connect",
    "group_by_day",
    "has_table",
    "load_all",
]

TABLE = "x_feed"

# Mirrors xpulse/config.py. Kept as a plain dict rather than imported: the two projects
# are separate repositories and news-vault must build with x-pulse absent.
VERTICAL_LABELS: dict[str, str] = {
    "kinh-te": "Kinh tế",
    "chinh-tri": "Chính trị",
    "ai": "AI",
    "chung-khoan": "Chứng khoán",
    "crypto": "Crypto",
}


@dataclass(frozen=True, slots=True)
class Post:
    id: str
    url: str
    author: str  # handle, no "@"
    author_name: str
    author_tier: float  # 0.2 - 1.0, asserted in x-pulse's watchlist
    title: str  # title_vi
    summary: str  # summary_vi, verbatim
    blocks: tuple[Block, ...]  # summary parsed into plain-text runs
    points: tuple[str, ...]  # key_points, already plain strings
    insight: str
    day: str  # "YYYY-MM-DD"
    processed_at: str  # verbatim
    published_iso: str  # ISO-8601, "" when unknown
    vertical: str
    topic: str
    impact: str
    relevance: int
    score: int
    likes: int = 0
    retweets: int = 0
    replies: int = 0
    is_primary: bool = False
    text: str = ""  # the original post, for search only
    vertical_label: str = field(default="")
    image: str = ""  # media_url, only https is accepted
    also_by: tuple[str, ...] = ()
    impact_channel: str = ""
    impact_assets: tuple[str, ...] = ()
    impact_direction: str = ""
    impact_confidence: str = ""
    impact_reasoning: str = ""


def has_table(conn: sqlite3.Connection) -> bool:
    """True when the x_feed view exists.

    Probes for a view as well as a table - x-pulse exposes its contract as a view, and
    the ``type = 'table'`` check the other readers use would silently report an empty
    archive against a perfectly healthy database.
    """
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table', 'view') AND name = ?",
        (TABLE,),
    )
    try:
        return cursor.fetchone() is not None
    finally:
        cursor.close()


def available_days(conn: sqlite3.Connection) -> list[str]:
    """Every day key with at least one publishable post, ascending."""
    return sorted({post.day for post in load_all(conn)})


def load_all(conn: sqlite3.Connection) -> list[Post]:
    """Every publishable post, newest day first, highest score first within a day."""
    posts = [post for post in _iter_posts(conn) if post is not None]
    # Stable sort chain: id ascending is the final tie-break between two equal scores.
    posts = sorted(posts, key=lambda post: post.id)
    posts.sort(key=lambda post: (post.day, post.score), reverse=True)
    return posts


def group_by_day(posts: Sequence[Post]) -> dict[str, list[Post]]:
    grouped: dict[str, list[Post]] = {}
    for post in posts:
        grouped.setdefault(post.day, []).append(post)
    return grouped


def _iter_posts(conn: sqlite3.Connection) -> Iterator[Post | None]:
    if not has_table(conn):
        return
    cursor = conn.execute(f"SELECT * FROM {TABLE}")
    try:
        for row in cursor:
            yield _post_from_row(row)
    finally:
        cursor.close()


def _columns(row: sqlite3.Row) -> set[str]:
    return set(row.keys())


def _post_from_row(row: sqlite3.Row) -> Post | None:
    columns = _columns(row)
    post_id = str(row["id"] or "")
    title = (row["title_vi"] or "").strip()
    if not post_id or not title:
        return None

    day = _resolve_day(
        row["day"] if "day" in columns else "",
        row["created_at"] if "created_at" in columns else "",
        row["processed_at"] if "processed_at" in columns else "",
    )
    if not day:
        return None

    summary = row["summary_vi"] or ""
    return Post(
        id=post_id,
        url=row["url"] or "",
        author=(row["author"] or "").lstrip("@"),
        author_name=row["author_name"] if "author_name" in columns else "",
        author_tier=_as_float(row["author_tier"] if "author_tier" in columns else None),
        title=title,
        summary=summary,
        blocks=summary_blocks(summary),
        points=_key_points(row["key_points"] if "key_points" in columns else ""),
        insight=(row["insight"] or "") if "insight" in columns else "",
        day=day,
        processed_at=row["processed_at"] if "processed_at" in columns else "",
        published_iso=_published_iso(
            row["created_at"] if "created_at" in columns else "",
            row["processed_at"] if "processed_at" in columns else "",
        ),
        vertical=row["vertical"] if "vertical" in columns else "",
        topic=row["topic"] if "topic" in columns else "",
        impact=row["impact_level"] if "impact_level" in columns else "",
        relevance=_as_int(row["relevance"] if "relevance" in columns else 0),
        score=_as_int(row["score"] if "score" in columns else 0),
        likes=_as_int(row["likes"] if "likes" in columns else 0),
        retweets=_as_int(row["retweets"] if "retweets" in columns else 0),
        replies=_as_int(row["replies"] if "replies" in columns else 0),
        is_primary=bool(row["is_primary"]) if "is_primary" in columns else False,
        text=row["text"] if "text" in columns else "",
        vertical_label=VERTICAL_LABELS.get(row["vertical"] if "vertical" in columns else "", ""),
        image=_https_url(row["media_url"] if "media_url" in columns else ""),
        also_by=_json_strings(row["dup_sources"] if "dup_sources" in columns else ""),
        impact_channel=(row["impact_channel"] or "") if "impact_channel" in columns else "",
        impact_assets=_json_strings(row["impact_assets"] if "impact_assets" in columns else ""),
        impact_direction=(row["impact_direction"] or "") if "impact_direction" in columns else "",
        impact_confidence=(row["impact_confidence"] or "") if "impact_confidence" in columns else "",
        impact_reasoning=(row["impact_reasoning"] or "") if "impact_reasoning" in columns else "",
    )


def _key_points(raw: str) -> tuple[str, ...]:
    """key_points arrives as a JSON array; anything else degrades to no points.

    An empty list is a legitimate answer from the summariser - a 280-character post often
    has no two separable facts in it - so a missing or malformed value is not an error,
    it just means the card shows its summary and nothing more.
    """
    return _json_strings(raw)


def _json_strings(raw: str) -> tuple[str, ...]:
    """Return non-empty strings from a JSON array, or no values for bad feed data."""
    if not raw:
        return ()
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return ()
    if not isinstance(parsed, list):
        return ()
    return tuple(item.strip() for item in parsed if isinstance(item, str) and item.strip())


def _https_url(raw: object) -> str:
    """Keep untrusted media URLs inert unless x-pulse supplied HTTPS."""
    return raw.strip() if isinstance(raw, str) and raw.strip().startswith("https://") else ""


def _resolve_day(day: str, created_at: str, processed_at: str) -> str:
    """Prefer the stored day column; it is authoritative.

    x-pulse computes it once, at capture, in Asia/Ho_Chi_Minh - which is the only place
    that conversion can be done correctly, because a post captured at 01:00 Hanoi time
    was published on the previous UTC day. Recomputing here from a UTC timestamp would
    move those posts a page backwards.
    """
    if day and _looks_like_day(day):
        return day
    for candidate in (created_at, processed_at):
        if not candidate:
            continue
        try:
            return datetime.datetime.fromisoformat(candidate[:10]).date().isoformat()
        except ValueError:
            continue
    return ""


def _looks_like_day(value: str) -> bool:
    try:
        datetime.date.fromisoformat(value[:10])
    except ValueError:
        return False
    return True


def _published_iso(created_at: str, processed_at: str) -> str:
    """ISO-8601 timestamp for the post, Vietnam time assumed for naive values."""
    for candidate in (created_at, processed_at):
        if not candidate:
            continue
        try:
            parsed = datetime.datetime.fromisoformat(candidate.replace("Z", "+00:00"))
        except ValueError:
            continue
        if parsed.tzinfo is None:
            return f"{parsed.isoformat()}+07:00"
        return parsed.isoformat()
    return ""


def _as_int(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _as_float(value: object) -> float:
    try:
        return float(value if value is not None else 0.35)
    except (TypeError, ValueError):
        return 0.35
