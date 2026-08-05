from __future__ import annotations

import pytest

from newsvault.cluster import TAG_BOOST_FLOOR, cluster_articles, similarity
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


def test_shared_tags_do_not_merge_low_overlap_same_source_articles() -> None:
    tags = ("ai", "chinh phu", "lam phat")
    left = make(
        "http://left",
        "lam phat kinh te",
        tags=tags,
    )
    right = make(
        "http://right",
        "lam thue phi",
        tags=tags,
    )

    # One shared token of six in the union = 1/6 = 0.1667.
    assert len(cluster_articles([left, right])) == 2


def test_many_shared_tags_do_not_override_same_source_requirement() -> None:
    tags = ("a", "b", "c", "d", "e", "f", "g")
    left = make(
        "http://left",
        "ngan hang dieu hanh tien te",
        tags=tags,
    )
    right = make(
        "http://right",
        "ngan quyen cong cu tien te",
        tags=tags,
    )

    # Three shared tokens of nine in the union = 3/9 = 0.3333.
    assert len(cluster_articles([left, right])) == 2


def test_tag_bonus_merges_overlapping_different_source_headlines_at_floor() -> None:
    left = make(
        "http://left",
        "bezos startup material investment",
        source="CNBC",
        tags=("ai", "startup"),
    )
    right = make(
        "http://right",
        "bezos startup government policy britain funding",
        source="The Guardian",
        tags=("ai", "startup"),
    )

    # Two shared tokens of eight in the union = 2/8 = 0.25.
    assert len(cluster_articles([left, right])) == 1


def test_near_duplicate_same_source_headlines_merge() -> None:
    left = make(
        "http://left",
        "phat hien quan the lo nung cham co",
    )
    right = make(
        "http://right",
        "phat hien quan the lo nung cham co 1800",
    )

    # Seven shared tokens of eight in the union = 7/8 = 0.875.
    assert len(cluster_articles([left, right])) == 1


def test_same_source_headlines_below_near_duplicate_threshold_stay_apart() -> None:
    left = make("http://left", "lai suat ngan hang tang manh")
    right = make("http://right", "lai suat ngan hang giam nhe")

    # Four shared tokens of eight in the union = 4/8 = 0.5.
    assert len(cluster_articles([left, right])) == 2


def test_assignment_compares_each_article_only_with_cluster_leader() -> None:
    # Three different outlets: same-source pairs are held to 0.7, which would block the
    # merge this test is about before the chaining rule ever came into play.
    a = make("http://a", "alpha beta gamma delta", score=3, source="One")
    b = make("http://b", "alpha beta gamma epsilon", score=2, source="Two")
    c = make("http://c", "alpha beta epsilon zeta", score=1, source="Three")

    # A-B = 3/5 = 0.60 and B-C = 3/5 = 0.60 both clear 0.45, but A-C = 2/6 = 0.3333 does
    # not. Under the old single-link union-find C reached A through B; now C is compared
    # against the leader only, so it stays out.
    clusters = cluster_articles([a, b, c])

    assert len(clusters) == 2
    assert any(
        {article.url for article in cluster.members} == {"http://a", "http://b"}
        for cluster in clusters
    )


def test_tag_bonus_is_capped_and_cannot_carry_low_overlap() -> None:
    tags = tuple(f"tag-{index}" for index in range(10))
    left = make("http://left", "lam phat kinh te", tags=tags, source="One")
    right = make("http://right", "cong nghe y te", tags=tags, source="Two")

    # "te" is shared, so 1 of 6 in the union = 0.1667 - below TAG_BOOST_FLOOR, which is the
    # point: ten shared tags add nothing, and the score stays the bare title overlap.
    assert similarity(left, right) == pytest.approx(1 / 6)
    assert similarity(left, right) < TAG_BOOST_FLOOR
    assert len(cluster_articles([left, right])) == 2


def test_cluster_keys_are_independent_of_input_order() -> None:
    articles = [
        make("http://a", "bezos startup material investment", source="One", score=3),
        make(
            "http://b",
            "bezos startup government policy britain funding",
            source="Two",
            score=2,
        ),
        make("http://c", "thi truong chung khoan hom nay tang diem", source="Three", score=1),
    ]

    forward = cluster_articles(articles)
    reversed_order = cluster_articles(list(reversed(articles)))

    assert [cluster.key for cluster in forward] == [cluster.key for cluster in reversed_order]
