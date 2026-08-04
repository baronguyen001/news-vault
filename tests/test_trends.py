from __future__ import annotations

from newsvault.model import Article
from newsvault.text import fold
from newsvault.trends import DEFAULT_WINDOW, trending_terms


def make(
    url: str,
    title: str,
    *,
    topic: str = "Kinh tế/Tài chính",
    tags: tuple[str, ...] = (),
    score: int = 50,
    day: str = "2026-08-04",
) -> Article:
    return Article(
        id=abs(hash(url)) % 10_000,
        url=url,
        source="Src",
        source_key="src",
        region="domestic",
        title=title,
        title_vi=title,
        published_at="",
        published_iso="",
        day=day,
        fetched_at=day,
        category="Kinh tế & Tài chính",
        topic=topic,
        summary_vi="",
        key_points=(),
        tags=tags,
        analysis={},
        impact_level="cao",
        is_law_policy=False,
        relevance=8,
        score=score,
    )


def test_trending_terms_spike_ranks_above_flat() -> None:
    spike_tag = "lãi suất"
    flat_tag = "chứng khoán"
    today = [make(f"u{i}", "Tiêu đề", tags=(spike_tag,)) for i in range(8)] + [
        make(f"f{i}", "Tiêu đề", tags=(flat_tag,)) for i in range(4)
    ]
    history: dict[str, list[Article]] = {}
    for day in ("2026-08-01", "2026-08-02", "2026-08-03"):
        history[day] = [make(f"{day}_{i}", "Tiêu đề", day=day, tags=(flat_tag,)) for i in range(4)]

    trends = trending_terms(today, history, window=DEFAULT_WINDOW, top_n=10, min_today=2)

    spike = next(t for t in trends if t.term == fold(spike_tag))
    flat = next(t for t in trends if t.term == fold(flat_tag))
    assert spike.today == 8
    assert spike.baseline == 0.0
    assert spike.z == 8.0
    assert flat.today == 4
    assert flat.baseline == 4.0
    assert abs(flat.z) < 0.001
    assert trends[0].term == fold(spike_tag)


def test_trending_terms_excludes_today_from_baseline() -> None:
    tag = "lãi suất"
    today_key = "2026-08-04"
    today = [make(f"u{i}", "t", tags=(tag,)) for i in range(3)]
    history = {
        today_key: [make(f"h{i}", "t", day=today_key, tags=(tag,)) for i in range(5)],
    }
    trends = trending_terms(today, history, window=7, top_n=5, min_today=2)
    assert len(trends) == 1
    assert trends[0].baseline == 0.0


def test_trending_terms_empty_today() -> None:
    history = {"2026-08-03": [make("h1", "t", day="2026-08-03")]}
    assert trending_terms([], history) == []
