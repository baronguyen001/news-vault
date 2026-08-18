from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from newsvault import build, payload
from newsvault.model import Article
from newsvault.render import SiteMeta


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
        "summary_vi": "Tóm tắt tiếng Việt có dấu. " * 20,
        "key_points": ("ý 1",),
        "tags": ("lãi suất",),
        "analysis": {"boi_canh": "a", "nguyen_nhan": "b", "muc_dich": "c", "lien_he": "d"},
        "impact_level": "cao",
        "is_law_policy": False,
        "relevance": 9,
        "score": 86,
    }
    defaults.update(overrides)
    return Article(**defaults)


def test_index_items_include_reader_facing_vietnamese_snippet() -> None:
    item = payload.index_items("2026-07-29", [make_article()])[0]

    assert "sn" in item
    assert len(str(item["sn"])) <= 160
    assert "Tóm tắt tiếng Việt có dấu" in str(item["sn"])
    assert str(item["sn"]) != str(item["f"])


def test_index_items_use_empty_snippet_without_summary() -> None:
    item = payload.index_items("2026-07-29", [make_article(summary_vi="")])[0]

    assert item["sn"] == ""


def test_write_search_page_writes_search_shell(tmp_path: Path) -> None:
    options = SimpleNamespace(site="Kho tin", site_url="https://example.com")
    meta = SiteMeta(
        site="Kho tin",
        version="0.1.0",
        kdf_iterations=250000,
        site_url="https://example.com",
    )

    build._write_search_page(
        tmp_path,
        ["2026-07-29", "2026-08-01"],
        options,
        meta,
        ["2026-07", "2026-08"],
    )

    html = (tmp_path / "s" / "index.html").read_text(encoding="utf-8")
    assert '"kind": "search"' in html
    assert '"indexBase": "../idx/"' in html
