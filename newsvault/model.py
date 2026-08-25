"""Article dataclass and row normalisation helpers."""

from __future__ import annotations

import email.utils
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from newsvault.score import compute_score
from newsvault.sources import tier as source_tier
from newsvault.text import fold

_VI_DATE_RE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})(?:[,\s]*(\d{1,2}):(\d{2}))?")


@dataclass(frozen=True, slots=True)
class Article:
    """Normalised representation of one article row from the news-hunter database."""

    id: int
    url: str
    source: str
    source_key: str
    region: str
    title: str
    title_vi: str
    published_at: str
    published_iso: str
    day: str
    fetched_at: str
    category: str
    topic: str
    summary_vi: str
    key_points: tuple[str, ...]
    tags: tuple[str, ...]
    analysis: dict[str, str]
    impact_level: str
    is_law_policy: bool
    relevance: int
    score: int
    image_url: str = ""
    is_teaser: bool = False

    @property
    def tier(self) -> str:
        """'paid' or 'free', derived from the source rather than stored.

        The database has no tier column - whether a source costs a subscription is a
        property of the source, not of the row - so deriving it here means the answer
        can never drift from :mod:`newsvault.sources`, and no caller can construct an
        Article whose tier disagrees with its source.
        """
        return source_tier(self.source_key)


def parse_json_list(raw: str | None) -> tuple[str, ...]:
    """Parse a JSON list column into a tuple of non-empty stripped strings; never raises."""
    if not raw:
        return ()
    try:
        data = json.loads(raw)
    except Exception:
        return ()
    if not isinstance(data, list):
        return ()
    return tuple(item.strip() for item in data if isinstance(item, str) and item.strip())


def parse_analysis(raw: str | None) -> dict[str, str]:
    """Parse the analysis JSON object; keep only the four known keys with non-empty string values."""
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}

    known_keys = ("boi_canh", "nguyen_nhan", "muc_dich", "lien_he")
    return {
        key: data[key] for key in known_keys if isinstance(data.get(key), str) and data[key].strip()
    }


def normalise_impact(raw: str | None) -> str:
    """Map any casing/diacritic variant to 'cao' | 'trung bình' | 'thấp', else ''."""
    if not raw:
        return ""

    folded = fold(raw)
    if folded == "cao":
        return "cao"
    if folded == "trung binh":
        return "trung bình"
    if folded == "thap":
        return "thấp"

    return ""


def parse_published(raw: str | None) -> str:
    """Best-effort ISO-8601 for a published_at string; '' when unparseable."""
    if not raw:
        return ""

    # RFC-2822 form, e.g. "Wed, 29 Jul 2026 12:00:36 +0700"
    try:
        return email.utils.parsedate_to_datetime(raw).isoformat()
    except Exception:
        pass

    # Already-ISO form, e.g. "2026-07-29T06:09:27.518450+00:00"
    try:
        return datetime.fromisoformat(raw).isoformat()
    except Exception:
        pass

    # Vietnamese form, e.g. "Thứ hai, 20/7/2026, 09:37 (GMT+7)"
    match = _VI_DATE_RE.search(raw)
    if match:
        try:
            day, month, year = (int(match.group(i)) for i in range(1, 4))
            hour = int(match.group(4)) if match.group(4) else 0
            minute = int(match.group(5)) if match.group(5) else 0
            tz = timezone(timedelta(hours=7))
            return datetime(year, month, day, hour, minute, tzinfo=tz).isoformat()
        except Exception:
            pass

    return ""


def _image_url(row: sqlite3.Row) -> str:
    """Read the article's representative image, tolerating a database without the column.

    news-hunter adds `image_url` in its own release cycle, and this project must keep
    building against a database that predates it — a missing column is a normal state
    here, not an error worth crashing a nightly build over. Only http(s) survives: the
    value is scraped from an arbitrary page and ends up in an <img src> in the browser.
    """
    # Bind the key list first. `"image_url" not in row` looks equivalent and is not:
    # sqlite3.Row.__contains__ searches the row's *values*, so that form would answer a
    # different question and happen to be right most of the time.
    columns = row.keys()
    if "image_url" not in columns:
        return ""
    value = (row["image_url"] or "").strip()
    return value if value.startswith(("http://", "https://")) else ""


def _is_teaser(row: sqlite3.Row) -> bool:
    """Read the optional teaser flag without requiring a newly migrated database."""
    # row.keys() is deliberate, not row itself — see _image_url's note on why
    # sqlite3.Row.__contains__ (searching values) is the wrong check here.
    return bool(row["is_teaser"] or 0) if "is_teaser" in row.keys() else False  # noqa: SIM118


def article_from_row(row: sqlite3.Row) -> Article:
    """Build an Article from a raw database row, applying every normalisation above."""
    title_vi_raw = row["title_vi"] or ""
    title_raw = row["title"] or ""
    title_vi = title_vi_raw if title_vi_raw.strip() else title_raw

    source_key = row["source_key"] or ""
    relevance = int(row["relevance"] or 0)
    impact_level = normalise_impact(row["impact_level"])
    score = compute_score(relevance, impact_level, source_key)

    return Article(
        id=int(row["id"] or 0),
        url=row["url"] or "",
        source=row["source"] or "",
        source_key=source_key,
        region=row["region"] or "",
        title=title_raw,
        title_vi=title_vi,
        published_at=row["published_at"] or "",
        published_iso=parse_published(row["published_at"]),
        day=(row["fetched_at"] or "")[:10],
        fetched_at=row["fetched_at"] or "",
        category=row["category"] or "",
        topic=row["topic"] or "Khác",
        summary_vi=row["summary_vi"] or "",
        key_points=parse_json_list(row["key_points"]),
        tags=parse_json_list(row["tags"]),
        analysis=parse_analysis(row["analysis"]),
        impact_level=impact_level,
        is_law_policy=bool(row["is_law_policy"] or 0),
        relevance=relevance,
        score=score,
        image_url=_image_url(row),
        is_teaser=_is_teaser(row),
    )
