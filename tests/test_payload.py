from __future__ import annotations

import json
import random
from typing import Any

import pytest

from newsvault.cluster import Cluster
from newsvault.entities import Entity
from newsvault.model import Article
from newsvault.payload import (
    compact_article,
    day_payload,
    manifest,
    stats_for,
    video_library_payload,
)
from newsvault.videos import Video


def make_article(**overrides: Any) -> Article:
    defaults = {
        "id": 1,
        "url": "https://example.com/1",
        "source": "Example",
        "source_key": "example",
        "region": "domestic",
        "title": "Original title",
        "title_vi": "Tiêu đề tiếng Việt",
        "published_at": "Wed, 29 Jul 2026 12:00:36 +0700",
        "published_iso": "2026-07-29T12:00:36+07:00",
        "day": "2026-07-29",
        "fetched_at": "2026-07-29T06:09:27.518450+00:00",
        "category": "Kinh tế & Tài chính",
        "topic": "Kinh tế/Tài chính",
        "summary_vi": "Tóm tắt bài viết.\n\nChi tiết thêm.",
        "key_points": ("ý 1", "ý 2"),
        "tags": ("lãi suất", "ngân hàng"),
        "analysis": {"boi_canh": "a", "nguyen_nhan": "b", "muc_dich": "c", "lien_he": "d"},
        "impact_level": "cao",
        "is_law_policy": False,
        "relevance": 9,
        "score": 86,
    }
    defaults.update(overrides)
    return Article(**defaults)


def test_compact_article_full_key_set_no_none() -> None:
    compact = compact_article(make_article(), 0)
    expected = {
        "i",
        "t",
        "to",
        "u",
        "s",
        "sk",
        "tr",
        "r",
        "c",
        "tp",
        "im",
        "sc",
        "rel",
        "p",
        "pi",
        "sum",
        "kp",
        "tg",
        "an",
        "law",
        "te",
        "img",
        "ents",
    }
    assert set(compact.keys()) == expected
    assert None not in compact.values()
    assert None not in compact["an"].values()
    assert None not in compact["kp"]
    assert None not in compact["tg"]


def test_compact_article_with_entities_and_day() -> None:
    article = make_article(url="https://x/1", day="2026-08-04")
    compact = compact_article(
        article,
        5,
        entities={"https://x/1": ["lai-suat"]},
        with_day=True,
    )
    assert compact["i"] == 5
    assert compact["d"] == "2026-08-04"
    assert compact["ents"] == ["lai-suat"]


def test_day_payload_cluster_indices_resolve() -> None:
    a1 = make_article(id=1, url="https://x/1", score=100)
    a2 = make_article(id=2, url="https://x/2", score=90)
    a3 = make_article(id=3, url="https://x/3", score=80)
    articles = [a1, a2, a3]

    cluster = Cluster(
        key="c1",
        lead=a1,
        members=(a1, a3),
        sources=("Reuters", "VnExpress"),
    )

    payload = day_payload(
        day="2026-07-29",
        articles=articles,
        clusters=[cluster],
        entity_map={},
        trending=[],
        blindspots=[],
        brief=[],
        categories=[],
        charts={},
        generated_at="2026-07-29T18:00:00+07:00",
    )

    assert len(payload["articles"]) == 3
    assert payload["clusters"][0]["lead"] == 0
    assert set(payload["clusters"][0]["members"]) == {0, 2}
    assert payload["articles"][0]["u"] == "https://x/1"
    assert payload["articles"][2]["u"] == "https://x/3"


def test_day_payload_deterministic() -> None:
    a1 = make_article(id=1)
    a2 = make_article(id=2)
    args = {
        "day": "2026-07-29",
        "articles": [a1, a2],
        "clusters": [],
        "entity_map": {},
        "trending": [],
        "blindspots": [],
        "brief": [],
        "categories": [],
        "charts": {},
        "generated_at": "2026-07-29T18:00:00+07:00",
    }
    first = json.dumps(day_payload(**args), ensure_ascii=False)
    second = json.dumps(day_payload(**args), ensure_ascii=False)
    assert first == second


def test_video_library_payload_sorts_videos_and_keeps_channel_names_private() -> None:
    older = Video("older", "Cũ", "raw", "Kênh A", "u", "", "2026-08-01", "2026-08-01T10:00:00", "", "", "", ())
    newest = Video("newest", "Mới", "raw", "Kênh B", "u", "", "2026-08-02", "2026-08-02T10:00:00", "", "", "", ())
    result = video_library_payload([older, newest], generated_at="2026-08-02T23:59:59+07:00")

    assert result["kind"] == "videoIndex"
    assert result["total"] == 2
    assert [video["id"] for video in result["videos"]] == ["newest", "older"]
    assert result["channels"] == {"Kênh A": 1, "Kênh B": 1}


def test_stats_for_is_stable_when_shuffled() -> None:
    articles = [
        make_article(id=i, topic=t, impact_level=im, region=rg, source=f"src{i % 3}")
        for i, (t, im, rg) in enumerate(
            [
                ("A", "cao", "domestic"),
                ("B", "cao", "international"),
                ("A", "trung bình", "domestic"),
                ("B", "thấp", "international"),
                ("A", "cao", "domestic"),
            ],
        )
    ]
    first = stats_for(articles)
    shuffled = articles.copy()
    random.shuffle(shuffled)
    second = stats_for(shuffled)
    assert first == second


def test_manifest_contains_no_article_text() -> None:
    titles = ["Secret Headline", "Another Title", "Even More Secret"]
    urls = [
        "https://example.com/secret-1",
        "https://example.com/secret-2",
        "https://example.com/secret-3",
    ]
    articles = [
        make_article(id=i, title=title, title_vi=title, url=url)
        for i, (title, url) in enumerate(zip(titles, urls, strict=True))
    ]
    entity = Entity(
        slug="x",
        label="y",
        mentions=3,
        days=("2026-07-29",),
        topics=("t",),
    )
    result = manifest(
        days=[(a.day, 1) for a in articles],
        months=["2026-07"],
        entities=[entity],
        generated_at="2026-07-29T18:00:00+07:00",
        kdf_iterations=250000,
        site="site",
        version="1",
    )
    dumped = json.dumps(result, ensure_ascii=False)
    for text in titles + urls:
        assert text not in dumped


def test_manifest_omits_weeks_with_empty_list() -> None:
    result = manifest(
        [],
        [],
        [],
        generated_at="2026-08-01T00:00:00Z",
        kdf_iterations=100000,
        site="example",
        version="1",
    )

    assert result["weeks"] == []


def test_manifest_includes_week_triple() -> None:
    result = manifest(
        [],
        [],
        [],
        weeks=[("2026-W31", "2026-07-27", "2026-08-02")],
        generated_at="2026-08-01T00:00:00Z",
        kdf_iterations=100000,
        site="example",
        version="1",
    )

    assert result["weeks"] == [{"e": "2026-08-02", "s": "2026-07-27", "w": "2026-W31"}]


def test_manifest_sorts_weeks_deterministically() -> None:
    weeks = [
        ("2026-W33", "2026-08-10", "2026-08-16"),
        ("2026-W31", "2026-07-27", "2026-08-02"),
        ("2026-W32", "2026-08-03", "2026-08-09"),
    ]
    kwargs = {
        "generated_at": "2026-08-01T00:00:00Z",
        "kdf_iterations": 100000,
        "site": "example",
        "version": "1",
    }

    ordered = manifest([], [], [], weeks=sorted(weeks), **kwargs)
    shuffled = manifest([], [], [], weeks=weeks, **kwargs)

    assert [week["w"] for week in shuffled["weeks"]] == [
        "2026-W31",
        "2026-W32",
        "2026-W33",
    ]
    assert json.dumps(ordered) == json.dumps(shuffled)


def test_manifest_week_entries_carry_only_label_and_range() -> None:
    """The manifest is the one unencrypted file on the site, so pin its week shape exactly.

    Asserting that some string is absent proves nothing when that string was never an input.
    Whitelisting the keys is what actually catches a future field smuggling article text in.
    """
    result = manifest(
        [],
        [],
        [],
        weeks=[("2026-W31", "2026-07-27", "2026-08-02")],
        generated_at="2026-08-01T00:00:00Z",
        kdf_iterations=100000,
        site="example",
        version="1",
    )

    for week in result["weeks"]:
        assert set(week) == {"w", "s", "e"}
        assert all(isinstance(value, str) for value in week.values())


def test_manifest_weeks_parameter_is_keyword_only() -> None:
    with pytest.raises(TypeError):
        manifest(
            [],
            [],
            [],
            [("2026-W31", "2026-07-27", "2026-08-02")],
            generated_at="2026-08-01T00:00:00Z",
            kdf_iterations=100000,
            site="example",
            version="1",
        )
