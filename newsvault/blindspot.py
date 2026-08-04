from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from newsvault.model import Article

DEFAULT_WINDOW: int = 30
DEFAULT_MIN_DROP: float = 0.04


@dataclass(frozen=True, slots=True)
class Blindspot:
    """A topic whose share of coverage dropped today relative to recent history."""

    topic: str
    share_today: float
    share_baseline: float
    drop: float


def _topic_counts(articles: Sequence[Article]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for article in articles:
        counts[article.topic] = counts.get(article.topic, 0) + 1
    return counts


def blindspots(
    today: Sequence[Article],
    history: Mapping[str, Sequence[Article]],
    *,
    window: int = DEFAULT_WINDOW,
    min_drop: float = DEFAULT_MIN_DROP,
    min_baseline_days: int = 5,
) -> list[Blindspot]:
    """Return topics whose share of coverage is unusually low today."""
    if not today:
        return []

    today_key = today[0].day
    baseline_days = sorted(
        (day for day in history if day < today_key),
        reverse=True,
    )[:window]

    if len(baseline_days) < min_baseline_days:
        return []

    today_total = len(today)
    today_counts = _topic_counts(today)

    all_topics: set[str] = set(today_counts)
    daily_counts: list[tuple[int, dict[str, int]]] = []
    for day in baseline_days:
        articles = history[day]
        counts = _topic_counts(articles)
        all_topics.update(counts.keys())
        daily_counts.append((len(articles), counts))

    baseline_shares: dict[str, list[float]] = defaultdict(list)
    for total, counts in daily_counts:
        for topic in all_topics:
            share = counts.get(topic, 0) / total if total else 0.0
            baseline_shares[topic].append(share)

    today_shares = {topic: count / today_total for topic, count in today_counts.items()}

    result: list[Blindspot] = []
    for topic in all_topics:
        share_today = today_shares.get(topic, 0.0)
        shares = baseline_shares[topic]
        share_baseline = sum(shares) / len(shares)
        drop = share_baseline - share_today
        if drop >= min_drop:
            result.append(
                Blindspot(
                    topic=topic,
                    share_today=share_today,
                    share_baseline=share_baseline,
                    drop=drop,
                ),
            )

    result.sort(key=lambda item: -item.drop)
    return result
