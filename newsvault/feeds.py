from __future__ import annotations

import xml.sax.saxutils
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from newsvault.model import Article


@dataclass(frozen=True, slots=True)
class FeedDay:
    day: str
    count: int
    topics: dict[str, int]
    url: str


def _day_label(day: str) -> str:
    """Convert 'YYYY-MM-DD' to 'DD/MM/YYYY'."""
    parts = day.split("-")
    return f"{parts[2]}/{parts[1]}/{parts[0]}"


def _metadata_title(day: str, count: int) -> str:
    return f"{_day_label(day)} — {count} tin"


def _metadata_summary(topics: dict[str, int]) -> str:
    """Build a short Vietnamese sentence listing top topic counts."""
    sorted_topics = sorted(topics.items(), key=lambda x: (-x[1], x[0]))
    parts = [f"{topic} {count}" for topic, count in sorted_topics if count > 0]
    return " · ".join(parts)


def _full_summary(articles: Sequence[Article]) -> str:
    """Build a summary listing the day's headlines."""
    headlines = [article.title_vi or article.title for article in articles]
    return "\n".join(headlines)


def _escape_xml(value: str) -> str:
    return xml.sax.saxutils.escape(value)


def _escape_attr(value: str) -> str:
    return xml.sax.saxutils.quoteattr(value)


def _atom_entry(
    day: str,
    count: int,
    topics: dict[str, int],
    url: str,
    updated: str,
    full: bool,
    articles: Sequence[Article] | None,
) -> str:
    entry_id = f"urn:news-vault:day:{day}"
    title = _metadata_title(day, count) if not full else _metadata_title(day, count)
    summary = _metadata_summary(topics) if not full else _full_summary(articles)  # type: ignore[arg-type]
    escaped_title = _escape_xml(title)
    escaped_summary = _escape_xml(summary)
    escaped_url = _escape_xml(url)
    escaped_id = _escape_xml(entry_id)
    escaped_updated = _escape_xml(updated)
    return (
        f"<entry>\n"
        f"  <id>{escaped_id}</id>\n"
        f"  <title>{escaped_title}</title>\n"
        f"  <updated>{escaped_updated}</updated>\n"
        f"  <link href={_escape_attr(escaped_url)}/>\n"
        f"  <summary>{escaped_summary}</summary>\n"
        f"</entry>"
    )


def atom_feed(
    days: Sequence[FeedDay],
    *,
    site: str,
    site_url: str,
    updated: str,
    full: bool = False,
    entries: Mapping[str, Sequence[Article]] | None = None,
    limit: int = 60,
) -> str:
    """Atom 1.0 XML. With `full=False` (the default) each entry's title and summary describe only how
    many articles the day holds and how they split by topic - no headline is published. With
    `full=True` the entry summary lists the day's headlines, which makes them public."""
    if full and entries is None:
        raise ValueError("full=True requires entries mapping")

    sorted_days = sorted(days, key=lambda d: d.day, reverse=True)[:limit]
    entries_xml: list[str] = []
    for day in sorted_days:
        day_articles = entries.get(day.day) if entries else None
        if full:
            if day_articles is None:
                continue
            articles = day_articles
        else:
            articles = None
        entries_xml.append(
            _atom_entry(
                day=day.day,
                count=day.count,
                topics=day.topics,
                url=day.url,
                updated=updated,
                full=full,
                articles=articles,
            )
        )

    escaped_site = _escape_xml(site)
    escaped_site_url = _escape_xml(site_url)
    escaped_updated = _escape_xml(updated)
    feed_id = _escape_xml(site_url)

    entries_str = "\n".join(entries_xml)
    return (
        f'<?xml version="1.0" encoding="utf-8"?>\n'
        f'<feed xmlns="http://www.w3.org/2005/Atom">\n'
        f"  <id>{feed_id}</id>\n"
        f"  <title>{escaped_site}</title>\n"
        f"  <updated>{escaped_updated}</updated>\n"
        f"  <link href={_escape_attr(escaped_site_url)}/>\n"
        f"  {entries_str}\n"
        f"</feed>"
    )


def json_feed(
    days: Sequence[FeedDay],
    *,
    site: str,
    site_url: str,
    updated: str,
    full: bool = False,
    entries: Mapping[str, Sequence[Article]] | None = None,
    limit: int = 60,
) -> dict[str, object]:
    """JSON Feed 1.1 equivalent of `atom_feed`."""
    if full and entries is None:
        raise ValueError("full=True requires entries mapping")

    sorted_days = sorted(days, key=lambda d: d.day, reverse=True)[:limit]
    items: list[dict[str, object]] = []
    for day in sorted_days:
        day_articles = entries.get(day.day) if entries else None
        if full:
            if day_articles is None:
                continue
            articles = day_articles
        else:
            articles = None
        item: dict[str, object] = {
            "id": f"urn:news-vault:day:{day.day}",
            "url": day.url,
            "title": _metadata_title(day.day, day.count)
            if not full
            else _metadata_title(day.day, day.count),
            "summary": _metadata_summary(day.topics) if not full else _full_summary(articles),  # type: ignore[arg-type]
            "date_published": updated,
        }
        items.append(item)

    return {
        "version": "https://jsonfeed.org/version/1.1",
        "title": site,
        "home_page_url": site_url,
        "feed_url": site_url + "/feed.json",
        "items": items,
    }
