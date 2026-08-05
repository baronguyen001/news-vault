from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from collections.abc import Mapping, Sequence

import pytest

from newsvault.feeds import FeedDay, atom_feed, json_feed
from newsvault.model import Article


def _make_article(
    id: int = 1,
    title: str = "Test Title",
    title_vi: str = "Tiêu đề kiểm tra",
    day: str = "2026-08-04",
    category: str = "Kinh tế & Tài chính",
    topic: str = "Kinh tế/Tài chính",
    score: int = 80,
    source: str = "VnExpress",
    source_key: str = "vnexpress",
    region: str = "domestic",
    published_at: str = "Wed, 29 Jul 2026 12:00:36 +0700",
    published_iso: str = "2026-07-29T12:00:36+07:00",
    fetched_at: str = "2026-08-04T06:09:27.518450+00:00",
    summary_vi: str = "Tóm tắt bài báo.",
    key_points: tuple[str, ...] = (),
    tags: tuple[str, ...] = (),
    analysis: dict[str, str] | None = None,
    impact_level: str = "cao",
    is_law_policy: bool = False,
    relevance: int = 9,
) -> Article:
    return Article(
        id=id,
        url=f"https://example.com/article/{id}",
        source=source,
        source_key=source_key,
        region=region,
        title=title,
        title_vi=title_vi,
        published_at=published_at,
        published_iso=published_iso,
        day=day,
        fetched_at=fetched_at,
        category=category,
        topic=topic,
        summary_vi=summary_vi,
        key_points=key_points,
        tags=tags,
        analysis=dict(analysis) if analysis else {},
        impact_level=impact_level,
        is_law_policy=is_law_policy,
        relevance=relevance,
        score=score,
    )


class TestAtomFeed:
    def test_default_mode_contains_no_titles(self) -> None:
        """The default feed must not contain any article titles."""
        days = [
            FeedDay(
                day="2026-08-04",
                count=2,
                topics={"Kinh tế/Tài chính": 2},
                url="https://example.com/2026-08-04",
            )
        ]
        articles = [
            _make_article(id=1, title_vi="Tiêu đề bí mật"),
            _make_article(id=2, title_vi="Không được tiết lộ"),
        ]
        entries: Mapping[str, Sequence[Article]] = {"2026-08-04": articles}
        feed = atom_feed(
            days,
            site="Test",
            site_url="https://example.com",
            updated="2026-08-04T18:00:00Z",
            full=False,
            entries=entries,
        )
        # Assert that none of the article titles appear in the feed
        for article in articles:
            assert article.title_vi not in feed
            assert article.title not in feed

    def test_xml_parses(self) -> None:
        days = [
            FeedDay(
                day="2026-08-04",
                count=1,
                topics={"Kinh tế/Tài chính": 1},
                url="https://example.com/2026-08-04",
            )
        ]
        feed = atom_feed(
            days,
            site="Test",
            site_url="https://example.com",
            updated="2026-08-04T18:00:00Z",
        )
        root = ET.fromstring(feed)
        assert root.tag == "{http://www.w3.org/2005/Atom}feed"

    def test_topic_with_ampersand_round_trips(self) -> None:
        days = [
            FeedDay(
                day="2026-08-04",
                count=1,
                topics={"Kinh tế & Tài chính": 1},
                url="https://example.com/2026-08-04",
            )
        ]
        feed = atom_feed(
            days,
            site="Test",
            site_url="https://example.com",
            updated="2026-08-04T18:00:00Z",
        )
        # The ampersand should be escaped in XML
        assert "&amp;" in feed
        # After parsing, the text should contain the original
        root = ET.fromstring(feed)
        entry = root.find("{http://www.w3.org/2005/Atom}entry")
        assert entry is not None
        summary = entry.find("{http://www.w3.org/2005/Atom}summary")
        assert summary is not None
        assert "Kinh tế & Tài chính" in summary.text

    def test_full_true_with_entries_none_raises(self) -> None:
        days = [
            FeedDay(
                day="2026-08-04",
                count=1,
                topics={},
                url="https://example.com/2026-08-04",
            )
        ]
        with pytest.raises(ValueError, match="full=True requires entries mapping"):
            atom_feed(
                days,
                site="Test",
                site_url="https://example.com",
                updated="2026-08-04T18:00:00Z",
                full=True,
                entries=None,
            )

    def test_full_true_contains_titles(self) -> None:
        days = [
            FeedDay(
                day="2026-08-04",
                count=2,
                topics={"Kinh tế/Tài chính": 2},
                url="https://example.com/2026-08-04",
            )
        ]
        articles = [
            _make_article(id=1, title_vi="Tiêu đề công khai 1"),
            _make_article(id=2, title_vi="Tiêu đề công khai 2"),
        ]
        entries: Mapping[str, Sequence[Article]] = {"2026-08-04": articles}
        feed = atom_feed(
            days,
            site="Test",
            site_url="https://example.com",
            updated="2026-08-04T18:00:00Z",
            full=True,
            entries=entries,
        )
        for article in articles:
            assert article.title_vi in feed

    def test_limit_caps_entries(self) -> None:
        days = [
            FeedDay(
                day=f"2026-08-{d:02d}",
                count=1,
                topics={},
                url=f"https://example.com/2026-08-{d:02d}",
            )
            for d in range(1, 10)
        ]
        feed = atom_feed(
            days,
            site="Test",
            site_url="https://example.com",
            updated="2026-08-10T18:00:00Z",
            limit=3,
        )
        root = ET.fromstring(feed)
        entries = root.findall("{http://www.w3.org/2005/Atom}entry")
        assert len(entries) == 3


class TestJsonFeed:
    def test_output_survives_json_dumps(self) -> None:
        days = [
            FeedDay(
                day="2026-08-04",
                count=1,
                topics={"Kinh tế/Tài chính": 1},
                url="https://example.com/2026-08-04",
            )
        ]
        result = json_feed(
            days,
            site="Test",
            site_url="https://example.com",
            updated="2026-08-04T18:00:00Z",
        )
        # Should not raise
        json.dumps(result)

    def test_has_correct_version(self) -> None:
        days = [
            FeedDay(
                day="2026-08-04",
                count=1,
                topics={},
                url="https://example.com/2026-08-04",
            )
        ]
        result = json_feed(
            days,
            site="Test",
            site_url="https://example.com",
            updated="2026-08-04T18:00:00Z",
        )
        assert result["version"] == "https://jsonfeed.org/version/1.1"

    def test_full_true_with_entries_none_raises(self) -> None:
        days = [
            FeedDay(
                day="2026-08-04",
                count=1,
                topics={},
                url="https://example.com/2026-08-04",
            )
        ]
        with pytest.raises(ValueError, match="full=True requires entries mapping"):
            json_feed(
                days,
                site="Test",
                site_url="https://example.com",
                updated="2026-08-04T18:00:00Z",
                full=True,
                entries=None,
            )

    def test_full_true_contains_titles(self) -> None:
        days = [
            FeedDay(
                day="2026-08-04",
                count=2,
                topics={"Kinh tế/Tài chính": 2},
                url="https://example.com/2026-08-04",
            )
        ]
        articles = [
            _make_article(id=1, title_vi="Tiêu đề công khai 1"),
            _make_article(id=2, title_vi="Tiêu đề công khai 2"),
        ]
        entries: Mapping[str, Sequence[Article]] = {"2026-08-04": articles}
        result = json_feed(
            days,
            site="Test",
            site_url="https://example.com",
            updated="2026-08-04T18:00:00Z",
            full=True,
            entries=entries,
        )
        items = result["items"]
        assert len(items) == 1
        summary = items[0]["summary"]
        assert isinstance(summary, str)
        for article in articles:
            assert article.title_vi in summary

    def test_limit_caps_items(self) -> None:
        days = [
            FeedDay(
                day=f"2026-08-{d:02d}",
                count=1,
                topics={},
                url=f"https://example.com/2026-08-{d:02d}",
            )
            for d in range(1, 10)
        ]
        result = json_feed(
            days,
            site="Test",
            site_url="https://example.com",
            updated="2026-08-10T18:00:00Z",
            limit=3,
        )
        assert len(result["items"]) == 3


def _two_days() -> list[FeedDay]:
    return [
        FeedDay(day="2026-08-04", count=3, topics={"Kinh tế/Tài chính": 3}, url="/d/2026-08-04/"),
        FeedDay(day="2026-08-05", count=2, topics={"Công nghệ/AI": 2}, url="/d/2026-08-05/"),
    ]


def test_entry_dates_do_not_move_when_the_build_time_does():
    """Two builds of unchanged content must produce byte-identical feeds.

    Entries used to be stamped with the build time, so the nightly job committed a diff on
    every run and every subscriber saw all sixty entries as newly published each time.
    """
    days = _two_days()
    kwargs = {"site": "Kho tin", "site_url": "https://example.test"}

    morning_xml = atom_feed(days, updated="2026-08-05T04:00:00+00:00", **kwargs)
    evening_xml = atom_feed(days, updated="2026-08-05T14:30:00+00:00", **kwargs)
    morning_json = json_feed(days, updated="2026-08-05T04:00:00+00:00", **kwargs)
    evening_json = json_feed(days, updated="2026-08-05T14:30:00+00:00", **kwargs)

    # The JSON feed carries no build stamp at all, so it must be identical.
    assert morning_json == evening_json

    # The Atom feed keeps one <updated> for the feed itself; every entry stays put.
    def entry_dates(xml: str) -> list[str | None]:
        return [
            el.text
            for el in ET.fromstring(xml).findall(
                "{http://www.w3.org/2005/Atom}entry/{http://www.w3.org/2005/Atom}updated"
            )
        ]

    assert entry_dates(morning_xml) == entry_dates(evening_xml)
    assert entry_dates(morning_xml) == ["2026-08-05T00:00:00+07:00", "2026-08-04T00:00:00+07:00"]
