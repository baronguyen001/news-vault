from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from newsvault.model import Article
from newsvault.text import fold

DEFAULT_WINDOW: int = 7


@dataclass(frozen=True, slots=True)
class Trend:
    """A tag-derived term whose frequency spiked today."""

    term: str
    label: str
    today: int
    baseline: float
    stdev: float
    z: float


def _article_terms(article: Article) -> set[str]:
    """Return the folded tag-derived terms for an article."""
    return {fold(tag) for tag in article.tags}


def _label_for_term(term: str, labels: dict[str, Counter]) -> str:
    """Choose the most common original spelling for a folded term."""
    counter = labels[term]
    highest = max(counter.values())
    candidates = [spelling for spelling, count in counter.items() if count == highest]
    return min(candidates)


def trending_terms(
    today: Sequence[Article],
    history: Mapping[str, Sequence[Article]],
    *,
    window: int = DEFAULT_WINDOW,
    top_n: int = 15,
    min_today: int = 2,
) -> list[Trend]:
    """Rank today's tag-derived terms by how far they exceed their recent baseline."""
    if not today:
        return []

    today_key = today[0].day
    baseline_days = sorted(
        (day for day in history if day < today_key),
        reverse=True,
    )[:window]

    today_counts: dict[str, int] = defaultdict(int)
    term_labels: dict[str, Counter] = defaultdict(Counter)

    for article in today:
        seen: set[str] = set()
        for tag in article.tags:
            term = fold(tag)
            term_labels[term][tag] += 1
            if term not in seen:
                seen.add(term)
                today_counts[term] += 1

    baseline_counts: dict[str, list[int]] = {
        term: [0] * len(baseline_days) for term in today_counts
    }
    for day_index, day in enumerate(baseline_days):
        for article in history[day]:
            for term in _article_terms(article):
                if term in baseline_counts:
                    baseline_counts[term][day_index] += 1

    trends: list[Trend] = []
    for term, today_value in today_counts.items():
        if today_value < min_today:
            continue

        counts = baseline_counts.get(term, [])
        if counts:
            baseline = sum(counts) / len(counts)
            variance = sum((count - baseline) ** 2 for count in counts) / len(counts)
            stdev = math.sqrt(variance)
        else:
            baseline = 0.0
            stdev = 0.0

        z_score = (today_value - baseline) / max(stdev, 1.0)

        trends.append(
            Trend(
                term=term,
                label=_label_for_term(term, term_labels),
                today=today_value,
                baseline=baseline,
                stdev=stdev,
                z=z_score,
            ),
        )

    trends.sort(key=lambda trend: (-trend.z, -trend.today, trend.term))
    return trends[:top_n]
