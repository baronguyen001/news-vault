from __future__ import annotations

from newsvault.cluster import Cluster, cluster_articles, multi_source_clusters, similarity
from newsvault.model import Article


def make(
    url: str,
    title: str,
    *,
    topic: str = "Kinh tế/Tài chính",
    tags: tuple[str, ...] = (),
    score: int = 50,
    day: str = "2026-08-04",
    source: str = "Src",
    source_key: str = "src",
) -> Article:
    return Article(
        id=abs(hash(url)) % 10_000,
        url=url,
        source=source,
        source_key=source_key,
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


def test_similarity_empty_token_set() -> None:
    left = make("http://l", "A B")
    right = make("http://r", "C D E")
    assert similarity(left, right) == 0.0


def test_similarity_boosted_by_shared_tags() -> None:
    left = make("http://l", "Lãi suất tăng mạnh", tags=("lãi suất", "ngân hàng"))
    right = make("http://r", "Lãi suất tăng mạnh", tags=("lãi suất", "ngân hàng"))
    assert similarity(left, right) == 1.0


def test_near_identical_headlines_cluster_together() -> None:
    a1 = make(
        "http://a/1",
        "Ngân hàng trung ương tăng lãi suất điều hành",
        topic="Kinh tế/Tài chính",
        tags=("lãi suất", "ngân hàng"),
        score=80,
        source="VnExpress",
    )
    a2 = make(
        "http://a/2",
        "Ngân hàng trung ương tăng lãi suất điều hành mạnh",
        topic="Kinh tế/Tài chính",
        tags=("lãi suất", "ngân hàng"),
        score=70,
        source="Reuters",
    )
    a3 = make(
        "http://a/3",
        "Bão số ba gây ngập lụt nghiêm trọng ở miền Trung",
        topic="Văn hóa/Xã hội",
        tags=("bão", "miền trung"),
        score=60,
        source="VnExpress",
    )
    clusters = cluster_articles([a1, a2, a3])
    assert len(clusters) == 2
    cluster0 = clusters[0]
    assert cluster0.size == 2
    assert cluster0.lead == a1
    assert {article.url for article in cluster0.members} == {"http://a/1", "http://a/2"}
    assert set(cluster0.sources) == {"VnExpress", "Reuters"}
    singleton = [c for c in clusters if c.size == 1][0]
    assert singleton.lead == a3


def test_cross_topic_never_clusters() -> None:
    a = make(
        "http://a",
        "Ngân hàng trung ương tăng lãi suất",
        topic="Kinh tế/Tài chính",
        tags=("lãi suất",),
    )
    b = make(
        "http://b",
        "Ngân hàng trung ương tăng lãi suất",
        topic="Công nghệ/AI",
        tags=("lãi suất",),
    )
    clusters = cluster_articles([a, b])
    assert len(clusters) == 2
    assert all(c.size == 1 for c in clusters)


def test_cluster_keys_stable_across_order() -> None:
    a1 = make("http://z", "Lãi suất tiếp tục tăng", score=80)
    a2 = make("http://y", "Lãi suất tiếp tục tăng cao", score=70)
    a3 = make("http://x", "Thị trường chứng khoán rung lắc", score=60)
    keys_forward = {c.key for c in cluster_articles([a1, a2, a3])}
    keys_reverse = {c.key for c in cluster_articles([a3, a2, a1])}
    assert keys_forward == keys_reverse
    assert len(keys_forward) == 2


def test_multi_source_clusters() -> None:
    a1 = make(
        "http://a/1",
        "Lãi suất tăng",
        tags=("lãi suất",),
        score=80,
        source="A",
    )
    a2 = make(
        "http://a/2",
        "Lãi suất tăng mạnh",
        tags=("lãi suất",),
        score=70,
        source="B",
    )
    a3 = make(
        "http://a/3",
        "Giá vàng giảm",
        tags=("vàng",),
        score=60,
        source="A",
    )
    clusters = cluster_articles([a1, a2, a3])
    multi = multi_source_clusters(clusters)
    assert len(multi) == 1
    assert multi[0].size == 2
    assert set(multi[0].sources) == {"A", "B"}


def test_multi_source_respects_min_size() -> None:
    cluster = Cluster(
        key="abc",
        lead=make("http://l", "Title", source="A"),
        members=(make("http://l", "Title", source="A"),),
        sources=("A",),
    )
    assert multi_source_clusters([cluster], min_size=2) == []
    assert multi_source_clusters([cluster], min_size=1) == [cluster]
