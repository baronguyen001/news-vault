from __future__ import annotations

from unittest.mock import patch

import pytest

from newsvault.brief import (
    BriefResult,
    brief_provider_issue,
    fallback_brief,
    generate_brief,
    reset_provider_state,
)
from newsvault.model import Article


def _article(**kwargs: object) -> Article:
    defaults = {
        "id": 1,
        "url": "https://example.com/1",
        "source": "VnExpress",
        "source_key": "vnexpress",
        "region": "domestic",
        "title": "Original title",
        "title_vi": "Tiêu đề",
        "published_at": "Wed, 29 Jul 2026 12:00:36 +0700",
        "published_iso": "2026-07-29T12:00:36+07:00",
        "day": "2026-07-29",
        "fetched_at": "2026-07-29T06:09:27.518450+00:00",
        "category": "Kinh tế & Tài chính",
        "topic": "Kinh tế/Tài chính",
        "summary_vi": "Đây là tóm tắt. Câu thứ hai nói thêm chi tiết.",
        "key_points": (),
        "tags": (),
        "analysis": {},
        "impact_level": "cao",
        "is_law_policy": False,
        "relevance": 8,
        "score": 80,
    }
    defaults.update(kwargs)
    return Article(**defaults)


def test_fallback_brief_respects_limit() -> None:
    articles = [_article(id=i, score=i * 10) for i in range(1, 8)]
    result = fallback_brief(articles, limit=5)
    assert isinstance(result, BriefResult)
    assert len(result.bullets) <= 5
    assert result.source == "fallback"
    assert result.error == ""
    assert "VnExpress" in result.bullets[0]


# Tu 2026-08-12 Gemini da bi go han: chi con AI Hub, hong thi roi xuong ban tu sinh.
# Cac test duoi day khoa dung hop dong do.

def test_generate_brief_fallback_when_hub_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Khong co hub = khong con nha cung cap nao -> fallback, VA phai bao su co."""
    reset_provider_state()
    monkeypatch.setattr("newsvault.brief.ai_hub.is_available", lambda: False)
    result = generate_brief("2026-08-04", [_article()])
    assert result.source == "fallback"
    assert result.error == "no ai hub"
    assert brief_provider_issue() is not None


def test_generate_brief_success_via_hub(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_provider_state()
    bullets = ["A", "B", "C", "D", "E"]
    monkeypatch.setattr("newsvault.brief.ai_hub.is_available", lambda: True)
    monkeypatch.setattr("newsvault.brief.ai_hub.chat_json",
                        lambda *a, **k: {"bullets": bullets})
    result = generate_brief("2026-08-04", [_article()])
    assert result.source == "aihub"
    assert result.bullets == tuple(bullets)
    assert result.error == ""
    assert brief_provider_issue() is None


def test_generate_brief_hub_failure_falls_back_and_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hub nem loi -> van co ban tin de xuat ban, nhung phai duoc danh dau la su co."""
    reset_provider_state()

    def _boom(*_a: object, **_k: object) -> dict[str, object]:
        raise RuntimeError("hub 524")

    monkeypatch.setattr("newsvault.brief.ai_hub.is_available", lambda: True)
    monkeypatch.setattr("newsvault.brief.ai_hub.chat_json", _boom)
    result = generate_brief("2026-08-04", [_article()])
    assert result.source == "fallback"
    assert result.error == "ai hub failed"
    assert brief_provider_issue() is not None


def test_generate_brief_never_touches_gemini(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cong chan: khong con bat ky loi goi mang nao ngoai hub."""
    reset_provider_state()
    monkeypatch.setattr("newsvault.brief.ai_hub.is_available", lambda: True)
    monkeypatch.setattr("newsvault.brief.ai_hub.chat_json",
                        lambda *a, **k: {"bullets": ["x", "y", "z", "t", "u"]})
    with patch("requests.post") as mock_post, patch("requests.request") as mock_req:
        generate_brief("2026-08-04", [_article()])
    assert mock_post.called is False
    assert mock_req.called is False


def test_brief_module_has_no_gemini_endpoint() -> None:
    import pathlib
    src = pathlib.Path("newsvault/brief.py").read_text(encoding="utf-8")
    assert "generativelanguage.googleapis.com" not in src
    assert "GEMINI_API_KEY" not in src


# --- Chất lượng brief: cắt fallback, số liệu lạ, guard ký tự ---------------------------

from newsvault.brief import (  # noqa: E402
    _truncate_at_boundary,
    bullet_output_issue,
    unsupported_numbers,
)
from newsvault.prompts import brief_prompt  # noqa: E402


def test_fallback_truncates_at_word_boundary_with_ellipsis() -> None:
    long_summary = " ".join(["thiênhà"] * 80)
    result = fallback_brief([_article(summary_vi=long_summary)], limit=1)
    line = result.bullets[0]
    assert len(line) <= 220
    assert line.endswith("…")
    assert line[:-1].endswith("thiênhà")  # không đứt giữa từ


def test_truncate_prefers_sentence_boundary_and_keeps_short_text() -> None:
    assert _truncate_at_boundary("Ngắn gọn.") == "Ngắn gọn."
    text = ("a" * 150) + ". " + ("b " * 60)
    cut = _truncate_at_boundary(text)
    assert cut.endswith(".") and len(cut) == 151


def test_fallback_is_not_cached_so_next_run_retries(tmp_path, monkeypatch) -> None:
    from newsvault.build import BuildOptions, _brief_for

    reset_provider_state()
    monkeypatch.setattr("newsvault.brief.ai_hub.is_available", lambda: False)
    options = BuildOptions(
        db_path=tmp_path / "x.db", out_dir=tmp_path / "out", password="x",
        cache_dir=tmp_path / "cache",
    )
    first = _brief_for("2026-08-04", [_article()], options)
    assert first.source == "fallback"
    assert not (tmp_path / "cache" / "brief" / "2026-08-04.json").exists()

    monkeypatch.setattr("newsvault.brief.ai_hub.is_available", lambda: True)
    monkeypatch.setattr("newsvault.brief.ai_hub.chat_json",
                        lambda *a, **k: {"bullets": list("ABCDE")})
    second = _brief_for("2026-08-04", [_article()], options)
    assert second.source == "aihub"


def test_prompt_forbids_derived_numbers_and_extra_details() -> None:
    prompt = brief_prompt("2026-08-04", [])
    assert "Không tự tính/suy ra số liệu mới" in prompt
    assert "Không thêm chi tiết không có trong tin" in prompt


def test_unsupported_numbers_flags_only_new_numbers(monkeypatch, caplog) -> None:
    articles = [_article(summary_vi="Lạm phát 2,5% trong 1.200 ngày.")]
    assert unsupported_numbers(["Lạm phát 2,5%", "Sau 1200 ngày"], articles) == []
    assert unsupported_numbers(["Kéo dài 37 tháng"], articles) == ["37"]

    reset_provider_state()
    monkeypatch.setattr("newsvault.brief.ai_hub.is_available", lambda: True)
    monkeypatch.setattr("newsvault.brief.ai_hub.chat_json",
                        lambda *a, **k: {"bullets": ["Tăng 99%", "B", "C", "D", "E"]})
    with caplog.at_level("WARNING"):
        result = generate_brief("2026-08-04", articles)
    assert result.source == "aihub"  # chỉ cảnh báo, không chặn
    assert "99" in caplog.text


@pytest.mark.parametrize("bad", [
    "Giá dầu 上涨 mạnh", "Сбербанк tăng lãi", "Giá tăngFed lãi suất", "FEDtăng lãi suất",
])
def test_bullet_output_issue_detects_bad_text(bad: str) -> None:
    assert bullet_output_issue(bad)


@pytest.mark.parametrize("ok", [
    "Fed giữ nguyên lãi suất, iPhone bán chạy", "Thị trường tăng mạnh nhờ OpenAI", "ChatGPT ra mắt",
])
def test_bullet_output_issue_accepts_good_text(ok: str) -> None:
    assert bullet_output_issue(ok) == ""


def test_guard_regenerates_once_then_drops_bad_bullet(monkeypatch) -> None:
    reset_provider_state()
    calls: list[int] = []
    good = ["Một", "Hai", "Ba", "Bốn"]

    def _hub(*_a: object, **_k: object) -> dict[str, object]:
        calls.append(1)
        return {"bullets": good + ["Năm 上涨"]}

    monkeypatch.setattr("newsvault.brief.ai_hub.is_available", lambda: True)
    monkeypatch.setattr("newsvault.brief.ai_hub.chat_json", _hub)
    result = generate_brief("2026-08-04", [_article()])
    assert len(calls) == 2  # đúng một lần sinh lại
    assert result.source == "aihub"
    assert result.bullets == tuple(good)


def test_guard_accepts_clean_regeneration(monkeypatch) -> None:
    reset_provider_state()
    replies = iter([["A", "B", "C", "D", "Сбер"], list("VWXYZ")])
    monkeypatch.setattr("newsvault.brief.ai_hub.is_available", lambda: True)
    monkeypatch.setattr("newsvault.brief.ai_hub.chat_json",
                        lambda *a, **k: {"bullets": next(replies)})
    result = generate_brief("2026-08-04", [_article()])
    assert result.bullets == tuple("VWXYZ")
