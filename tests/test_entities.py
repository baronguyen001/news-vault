from __future__ import annotations

from newsvault.entities import EntityIndex, build_entity_index
from newsvault.model import Article
from newsvault.text import VI_STOPWORDS, slugify


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


def test_entity_index_picks_most_common_label() -> None:
    articles = [
        make("u1", "t1", tags=("lãi suất",)),
        make("u2", "t2", tags=("lãi suất",)),
        make("u3", "t3", tags=("lãi suất",)),
        make("u4", "t4", tags=("lai suat",)),
    ]
    index = build_entity_index(articles, min_mentions=2)
    entity = index.get("lai-suat")
    assert entity is not None
    assert entity.label == "lãi suất"
    assert entity.mentions == 4


def test_entity_index_respects_min_mentions() -> None:
    articles = [
        make("u1", "t1", tags=("hiếm",)),
        make("u2", "t2", tags=("hiếm",)),
    ]
    index = build_entity_index(articles, min_mentions=3)
    assert index.get("hiem") is None
    assert index.entities == ()
    assert index.by_article == {}


def test_entity_index_drops_stopwords_and_short_labels() -> None:
    stop_tag = next(iter(VI_STOPWORDS)) if VI_STOPWORDS else "và"
    articles = [
        make("u1", "t1", tags=(stop_tag,)),
        make("u2", "t2", tags=("x",)),
    ]
    index = build_entity_index(articles, min_mentions=1)
    assert index.get(slugify(stop_tag)) is None
    assert index.get("x") is None


def test_entity_index_by_article_mapping() -> None:
    articles = [
        make("u1", "t1", tags=("lãi suất", "chứng khoán")),
        make("u2", "t2", tags=("lãi suất",)),
    ]
    index = build_entity_index(articles, min_mentions=1)
    assert index.by_article["u1"] == ("chung-khoan", "lai-suat")
    assert index.by_article["u2"] == ("lai-suat",)


def test_entity_index_top_and_get() -> None:
    articles = [
        make("u1", "t1", tags=("lãi suất",)),
        make("u2", "t2", tags=("lãi suất",)),
        make("u3", "t3", tags=("vàng",)),
    ]
    index = build_entity_index(articles, min_mentions=1)
    assert index.top(1)[0].slug == "lai-suat"
    assert index.top(0) == ()
    assert index.get("khong-tai") is None
    assert isinstance(index, EntityIndex)
