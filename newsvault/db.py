"""Read-only data layer over the news-hunter SQLite database."""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from pathlib import Path

from newsvault.model import Article, article_from_row

DEFAULT_MIN_RELEVANCE: int = 0


def connect(db_path: str | Path) -> sqlite3.Connection:
    """Open the news-hunter database strictly read-only (file: URI with mode=ro) and set row_factory."""
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"Database not found: {path}")
    if not path.is_file():
        raise FileNotFoundError(f"Not a database file (is it a directory?): {path}")

    conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def available_days(conn: sqlite3.Connection) -> list[str]:
    """Sorted ascending list of 'YYYY-MM-DD' day keys that have at least one article."""
    cursor = conn.execute(
        "SELECT substr(fetched_at, 1, 10) AS day FROM articles "
        "WHERE COALESCE(is_advertorial, 0) = 0 "
        "GROUP BY day ORDER BY day"
    )
    return [row["day"] for row in cursor.fetchall()]


def counts_by_day(conn: sqlite3.Connection) -> dict[str, int]:
    """Article count per day key."""
    cursor = conn.execute(
        "SELECT substr(fetched_at, 1, 10) AS day, COUNT(*) AS count FROM articles "
        "WHERE COALESCE(is_advertorial, 0) = 0 "
        "GROUP BY day ORDER BY day"
    )
    return {row["day"]: row["count"] for row in cursor.fetchall()}


def _base_query(min_relevance: int) -> tuple[str, list[int]]:
    """Return the advertorial filter and optional relevance filter (parameters are appended)."""
    where = "WHERE substr(fetched_at, 1, 10) = ? AND COALESCE(is_advertorial, 0) = 0"
    params: list[int] = []
    if min_relevance > 0:
        where += " AND COALESCE(relevance, 0) >= ?"
        params.append(min_relevance)
    return where, params


def load_day(
    conn: sqlite3.Connection, day: str, *, min_relevance: int = DEFAULT_MIN_RELEVANCE
) -> list[Article]:
    """All articles for one day, sorted by score descending then title ascending."""
    where, extra_params = _base_query(min_relevance)
    cursor = conn.execute(f"SELECT * FROM articles {where}", [day, *extra_params])

    articles = [article_from_row(row) for row in cursor.fetchall()]
    articles.sort(key=lambda article: (-article.score, article.title_vi))
    return articles


def load_range(
    conn: sqlite3.Connection,
    start: str,
    end: str,
    *,
    min_relevance: int = DEFAULT_MIN_RELEVANCE,
) -> list[Article]:
    """All articles with start <= day <= end (inclusive), sorted by day ascending then score descending."""
    where = "WHERE substr(fetched_at, 1, 10) BETWEEN ? AND ? AND COALESCE(is_advertorial, 0) = 0"
    params: list[str | int] = [start, end]
    if min_relevance > 0:
        where += " AND COALESCE(relevance, 0) >= ?"
        params.append(min_relevance)

    cursor = conn.execute(f"SELECT * FROM articles {where}", params)

    articles = [article_from_row(row) for row in cursor.fetchall()]
    articles.sort(key=lambda article: (article.day, -article.score, article.title_vi))
    return articles


def load_days(
    conn: sqlite3.Connection,
    days: Sequence[str],
    *,
    min_relevance: int = DEFAULT_MIN_RELEVANCE,
) -> dict[str, list[Article]]:
    """Group load for a set of day keys."""
    if not days:
        return {}

    placeholders = ", ".join("?" for _ in days)
    where = (
        f"WHERE substr(fetched_at, 1, 10) IN ({placeholders}) AND COALESCE(is_advertorial, 0) = 0"
    )
    params: list[str | int] = list(days)
    if min_relevance > 0:
        where += " AND COALESCE(relevance, 0) >= ?"
        params.append(min_relevance)

    cursor = conn.execute(f"SELECT * FROM articles {where}", params)

    grouped: dict[str, list[Article]] = {day: [] for day in days}
    for row in cursor.fetchall():
        article = article_from_row(row)
        grouped.setdefault(article.day, []).append(article)

    for group in grouped.values():
        group.sort(key=lambda article: (-article.score, article.title_vi))

    return grouped
