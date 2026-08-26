"""`--finalize-today`: Tóm tắt ngày + Chuyên mục/biểu đồ/xu hướng chỉ chốt 1 lần cuối
ngày thay vì đổi mỗi khi build chạm ngày đó.

16/08/2026 vá "brief đông cứng ở lần dựng đầu tiên" bằng cách so vân tay rồi sinh lại mỗi
khi nội dung đổi - đúng nhưng lại tạo ra chiều ngược: đổi NHIỀU lần/ngày. User chốt
26/08/2026: giữ nguyên bản đã có trong ngày, chỉ chốt lại đúng 1 lần ở lần chạy cuối ngày
(`finalize=True`). Ngày đã đóng (không phải hôm nay) không bị ảnh hưởng - xem cách
`build_site` tính `finalize` trong vòng lặp ngày.
"""

from __future__ import annotations

import json

from newsvault.brief import BriefResult
from newsvault.build import (
    AnalysisResult,
    _analysis_for,
    _brief_fingerprint,
    _brief_for,
)
from tests.test_brief import _article
from tests.test_brief_cache_selfheal import make_options, read_cache, write_cache

GOOD_BULLETS = (
    "Iran cảnh báo tấn công hạ tầng năng lượng vùng Vịnh nếu Mỹ không nhượng bộ.",
    "Xuất khẩu bền bỉ giúp các nhà máy Trung Quốc tìm đầu ra ngoài thị trường Mỹ.",
)
LATER_BULLETS = ("Bản tóm tắt mới, viết sau khi ngày có thêm tin.",)


# --------------------------------------------------------------------- _brief_for


def test_finalize_false_keeps_the_stale_brief_even_when_content_changed(tmp_path, monkeypatch):
    options = make_options(tmp_path)
    day = "2026-08-26"
    first = [_article(id=1)]
    write_cache(options, day, GOOD_BULLETS, fingerprint=_brief_fingerprint(first, []))

    monkeypatch.setattr(
        "newsvault.build.generate_brief",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("finalize=False không được gọi LLM")),
    )

    result = _brief_for(day, [*first, _article(id=2)], options, finalize=False)

    assert result.bullets == GOOD_BULLETS
    assert read_cache(options, day)["bullets"] == list(GOOD_BULLETS)


def test_finalize_true_still_regenerates_on_new_content(tmp_path, monkeypatch):
    """Hành vi 16/08 giữ nguyên khi finalize=True (mặc định)."""
    options = make_options(tmp_path)
    day = "2026-08-26"
    first = [_article(id=1)]
    write_cache(options, day, GOOD_BULLETS, fingerprint=_brief_fingerprint(first, []))

    monkeypatch.setattr(
        "newsvault.build.generate_brief",
        lambda *a, **k: BriefResult(LATER_BULLETS, "aihub", ""),
    )

    result = _brief_for(day, [*first, _article(id=2)], options, finalize=True)

    assert result.bullets == LATER_BULLETS


def test_finalize_false_still_computes_a_first_draft_when_no_cache_exists(tmp_path, monkeypatch):
    """Lần chạy đầu ngày (finalize=False, chưa có cache): vẫn phải tính 1 lần, không để
    trang trống chờ tới cuối ngày."""
    options = make_options(tmp_path)
    day = "2026-08-26"
    articles = [_article(id=1)]

    monkeypatch.setattr(
        "newsvault.build.generate_brief",
        lambda *a, **k: BriefResult(GOOD_BULLETS, "aihub", ""),
    )

    result = _brief_for(day, articles, options, finalize=False)

    assert result.bullets == GOOD_BULLETS
    assert read_cache(options, day)["bullets"] == list(GOOD_BULLETS)


def test_finalize_false_still_self_heals_a_refusal_cache(tmp_path, monkeypatch):
    """Bản ghi rác (câu từ chối) không đáng "giữ nguyên tới cuối ngày" chỉ vì finalize=False."""
    options = make_options(tmp_path)
    day = "2026-08-26"
    write_cache(options, day, ["Không có mục tin nào được cung cấp."] * 5)

    monkeypatch.setattr(
        "newsvault.build.generate_brief",
        lambda *a, **k: BriefResult(GOOD_BULLETS, "aihub", ""),
    )

    result = _brief_for(day, [], options, finalize=False)

    assert result.bullets == GOOD_BULLETS


# --------------------------------------------------------------------- _analysis_for


def _write_analysis_cache_file(options, day, *, fingerprint):
    cache_dir = options.cache_dir / "analysis"
    cache_dir.mkdir(parents=True, exist_ok=True)
    stale = AnalysisResult(
        categories=[{"key": "stale", "label": "Stale", "count": 1, "paid": 0}],
        charts={"topics": "<svg>stale</svg>"},
        trending=[],
        blindspots=[],
    )
    (cache_dir / f"{day}.json").write_text(
        json.dumps(
            {
                "categories": stale.categories,
                "charts": stale.charts,
                "trending": [],
                "blindspots": [],
                "fp": fingerprint,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return stale


def test_analysis_finalize_false_keeps_the_stale_categories(tmp_path):
    options = make_options(tmp_path)
    day = "2026-08-26"
    first = [_article(id=1)]
    stale = _write_analysis_cache_file(options, day, fingerprint=_brief_fingerprint(first, ()))

    result = _analysis_for(day, [*first, _article(id=2)], {}, options, finalize=False)

    assert result.categories == stale.categories
    assert result.charts == stale.charts


def test_analysis_finalize_true_recomputes_on_new_content(tmp_path):
    options = make_options(tmp_path)
    day = "2026-08-26"
    first = [_article(id=1)]
    stale = _write_analysis_cache_file(options, day, fingerprint=_brief_fingerprint(first, ()))

    result = _analysis_for(day, [*first, _article(id=2)], {}, options, finalize=True)

    assert result.categories != stale.categories


def test_analysis_finalize_false_still_computes_a_first_draft_when_no_cache_exists(tmp_path):
    options = make_options(tmp_path)
    day = "2026-08-26"
    articles = [_article(id=1)]

    result = _analysis_for(day, articles, {}, options, finalize=False)

    assert isinstance(result, AnalysisResult)
    cache_file = options.cache_dir / "analysis" / f"{day}.json"
    assert cache_file.exists()
    assert json.loads(cache_file.read_text(encoding="utf-8"))["fp"] == _brief_fingerprint(
        articles, ()
    )


def test_analysis_matching_fingerprint_is_reused_even_when_finalize_true(tmp_path):
    """Vân tay khớp (nội dung không đổi) ⇒ dùng lại cache dù finalize=True - cùng nguyên
    tắc 'ngày không đổi thì không tính lại' của _brief_for."""
    options = make_options(tmp_path)
    day = "2026-08-26"
    articles = [_article(id=1), _article(id=2)]
    stale = _write_analysis_cache_file(options, day, fingerprint=_brief_fingerprint(articles, ()))

    result = _analysis_for(day, articles, {}, options, finalize=True)

    assert result.categories == stale.categories
    assert result.charts == stale.charts
