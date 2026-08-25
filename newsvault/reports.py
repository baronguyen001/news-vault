"""Views over analyst-report articles already loaded from the news database."""

from __future__ import annotations

from collections.abc import Sequence

from newsvault.model import Article
from newsvault.sources import is_report


def reports_of(articles: Sequence[Article]) -> list[Article]:
    """Keep only articles published by one of the configured report sources."""
    return [article for article in articles if is_report(article.source_key)]


def group_by_day(reports: Sequence[Article]) -> dict[str, list[Article]]:
    """Group reports by their existing article day, preserving input order."""
    grouped: dict[str, list[Article]] = {}
    for report in reports:
        grouped.setdefault(report.day, []).append(report)
    return grouped
