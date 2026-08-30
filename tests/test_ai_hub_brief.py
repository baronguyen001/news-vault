"""The brief now runs on MK1 AI Hub, with Gemini as the safety net.

These lock the two failures that made the switch necessary and the one that nearly made it
useless: a Gemini key can expire and take every brief down with it; the hub's settings must
be read late enough for the CLI's own `.env` loader to have run; and `response_format`
alone does not make the model emit JSON.
"""

from __future__ import annotations

import pytest

from newsvault import ai_hub
from newsvault.brief import LLM_SOURCES, _clean_bullets, generate_brief
from newsvault.model import Article
from newsvault.prompts import brief_prompt

HUB_ENV = {
    "AI_HUB_BASE_URL": "https://hub.example/v1",
    "AI_HUB_KEY": "sk-test",
}


def _article(**kwargs: object) -> Article:
    defaults: dict[str, object] = {
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


def _enable_hub(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in HUB_ENV.items():
        monkeypatch.setenv(name, value)


# --- settings are read late, not at import ------------------------------------------


def test_hub_settings_are_read_at_call_time(monkeypatch: pytest.MonkeyPatch) -> None:
    """The regression that would have made this whole change a no-op.

    `newsvault.cli` imports `newsvault.build` — and through it this module — at module
    level, but only calls `load_dotenv()` inside `main()`. Anything captured at import time
    therefore sees an environment with no keys in it, `is_available()` stays False forever,
    and every brief goes to Gemini in complete silence.
    """
    assert ai_hub.is_available() is False
    _enable_hub(monkeypatch)
    assert ai_hub.is_available() is True
    assert ai_hub.base_url() == "https://hub.example/v1"


def test_base_url_drops_a_trailing_slash(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_HUB_BASE_URL", "https://hub.example/v1/")
    assert ai_hub.base_url() == "https://hub.example/v1"


def test_hub_is_unavailable_without_a_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_HUB_BASE_URL", "https://hub.example/v1")
    assert ai_hub.is_available() is False


def test_hub_can_be_switched_off(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_hub(monkeypatch)
    monkeypatch.setenv("AI_HUB_ENABLED", "0")
    assert ai_hub.is_available() is False


def test_timeout_falls_back_when_the_value_is_not_a_number(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AI_HUB_TIMEOUT", "not-a-number")
    assert ai_hub.timeout_seconds() == ai_hub.DEFAULT_TIMEOUT


def test_chat_json_refuses_when_not_configured() -> None:
    with pytest.raises(RuntimeError, match="not configured"):
        ai_hub.chat_json("anything")


# --- JSON extraction -----------------------------------------------------------------


def test_parse_object_ignores_prose_after_the_object() -> None:
    """`find("{")`..`rfind("}")` breaks the moment the model adds anything afterwards."""
    parsed = ai_hub._parse_object('{"bullets": ["a"]}\n\nHope that helps! {not json}')
    assert parsed == {"bullets": ["a"]}


def test_parse_object_rejects_text_with_no_object() -> None:
    with pytest.raises(RuntimeError, match="no JSON object"):
        ai_hub._parse_object("- bullet one\n- bullet two")


def test_parse_object_rejects_a_bare_array() -> None:
    with pytest.raises(RuntimeError, match="no JSON object"):
        ai_hub._parse_object('["a", "b"]')


# --- the prompt carries the JSON contract --------------------------------------------


def test_brief_prompt_states_the_json_shape() -> None:
    """`response_format: json_object` was not enough on its own.

    The model wrote five perfectly good Vietnamese bullets as markdown dashes, the parser
    found no object, and every day fell through to the score-ordered fallback.
    """
    prompt = brief_prompt("2026-08-09", [])
    assert '{"bullets":' in prompt
    assert "No markdown code fence" in prompt


# --- engine selection ------------------------------------------------------------------


def test_brief_uses_the_hub_when_it_is_available(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_hub(monkeypatch)
    calls: list[str] = []

    def fake_chat_json(prompt: str, **kwargs: object) -> dict[str, object]:
        calls.append(prompt)
        return {"bullets": ["một", "hai", "ba", "bốn", "năm"]}

    monkeypatch.setattr(ai_hub, "chat_json", fake_chat_json)
    result = generate_brief("2026-08-09", [_article()])

    assert result.source == "aihub"
    assert result.bullets == ("một", "hai", "ba", "bốn", "năm")
    assert result.error == ""
    assert len(calls) == 1


def test_brief_falls_to_the_deterministic_fallback_when_the_hub_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tu 2026-08-12 khong con Gemini o giua: hub nem loi la ra thang fallback,
    va ngoai le KHONG duoc thoat ra ngoai lam vo ca lan dung."""
    _enable_hub(monkeypatch)

    def boom(prompt: str, **kwargs: object) -> dict[str, object]:
        raise RuntimeError("AI Hub 524")

    monkeypatch.setattr(ai_hub, "chat_json", boom)
    result = generate_brief("2026-08-09", [_article()])

    assert result.source == "fallback"
    assert result.error == "ai hub failed"
    assert result.bullets


def test_brief_falls_through_when_the_hub_returns_no_bullets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_hub(monkeypatch)
    monkeypatch.setattr(ai_hub, "chat_json", lambda prompt, **kw: {"bullets": []})
    result = generate_brief("2026-08-09", [_article()])
    assert result.source == "fallback"


def test_brief_falls_through_when_bullets_is_not_a_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_hub(monkeypatch)
    monkeypatch.setattr(ai_hub, "chat_json", lambda prompt, **kw: {"bullets": "một, hai"})
    result = generate_brief("2026-08-09", [_article()])
    assert result.source == "fallback"


def test_brief_skips_the_hub_entirely_when_it_is_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No hub configured means no hub call — not a call that fails slowly."""
    called: list[str] = []
    monkeypatch.setattr(ai_hub, "chat_json", lambda prompt, **kw: called.append(prompt) or {})
    result = generate_brief("2026-08-09", [_article()])
    assert called == []
    assert result.source == "fallback"


# --- bullet cleaning --------------------------------------------------------------------


def test_clean_bullets_drops_blanks_and_non_strings() -> None:
    assert _clean_bullets(["  một  ", "", "   ", 7, None, "hai"]) == ["một", "hai"]


def test_clean_bullets_caps_at_five() -> None:
    assert len(_clean_bullets([f"b{i}" for i in range(9)])) == 5


def test_clean_bullets_rejects_a_non_list() -> None:
    assert _clean_bullets({"bullets": ["a"]}) == []


# --- the label the build reads ------------------------------------------------------------


def test_current_and_legacy_llm_sources_count_as_real_briefs() -> None:
    """The build must not report cached Gemini briefs as deterministic fallbacks."""
    assert frozenset({"aihub", "gemini"}) == LLM_SOURCES
    assert "fallback" not in LLM_SOURCES
