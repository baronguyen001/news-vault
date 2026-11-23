from __future__ import annotations

import pytest

from newsvault import ai_hub, codex_fallback


@pytest.fixture(autouse=True)
def _codex_on(monkeypatch):
    monkeypatch.setenv("NEWSVAULT_CODEX_FALLBACK", "1")
    codex_fallback.reset_disabled()
    ai_hub.reset_breaker()
    monkeypatch.setattr(ai_hub, "_codex_rescue_logged", False)

    def hub_fail(*a, **k):
        raise RuntimeError("AI Hub HTTP 429")

    monkeypatch.setattr(ai_hub, "_hub_chat_json", hub_fail)
    yield
    codex_fallback.reset_disabled()


def _fake_codex(monkeypatch, output, calls=None):
    def fake(prompt, timeout=300):
        if calls is not None:
            calls.append(prompt)
        return output

    monkeypatch.setattr(codex_fallback, "codex_fallback", fake)


def test_rescue_returns_parsed_dict(monkeypatch):
    calls: list[str] = []
    _fake_codex(monkeypatch, '{"ok": 1}', calls)
    assert ai_hub.chat_json("hello", max_tokens=100) == {"ok": 1}
    assert len(calls) == 1 and "hello" in calls[0]


def test_rescue_after_ollama_failure(monkeypatch):
    monkeypatch.setenv("OLLAMA_API_KEY", "k")

    def ollama_fail(*a, **k):
        raise RuntimeError("Ollama HTTP 429")

    monkeypatch.setattr(ai_hub, "_ollama_chat_json", ollama_fail)
    _fake_codex(monkeypatch, '{"ok": 2}')
    assert ai_hub.chat_json("x", max_tokens=100) == {"ok": 2}


def test_fenced_json_parsed(monkeypatch):
    _fake_codex(monkeypatch, '```json\n{"bullets": ["a"]}\n```')
    assert ai_hub.chat_json("x", max_tokens=100) == {"bullets": ["a"]}


def test_codex_failure_raises_with_both_errors(monkeypatch):
    _fake_codex(monkeypatch, None)
    with pytest.raises(RuntimeError) as err:
        ai_hub.chat_json("x", max_tokens=100)
    assert "AI Hub HTTP 429" in str(err.value) and "Codex CLI" in str(err.value)


def test_flag_off_no_codex_call(monkeypatch):
    monkeypatch.setenv("NEWSVAULT_CODEX_FALLBACK", "0")
    calls: list[str] = []
    _fake_codex(monkeypatch, '{"ok": 1}', calls)
    with pytest.raises(RuntimeError, match="429"):
        ai_hub.chat_json("x", max_tokens=100)
    assert calls == []


def test_disabled_by_quota_raises(monkeypatch):
    monkeypatch.setattr(codex_fallback, "_DISABLED_REASON", "usage limit")
    calls: list[str] = []
    _fake_codex(monkeypatch, '{"ok": 1}', calls)
    with pytest.raises(RuntimeError, match="429"):
        ai_hub.chat_json("x", max_tokens=100)
    assert calls == []


def test_is_available_reflects_codex(monkeypatch):
    monkeypatch.setattr(codex_fallback, "_find_codex_executable", lambda: object())
    assert ai_hub.is_available()
    monkeypatch.setenv("NEWSVAULT_CODEX_FALLBACK", "0")
    assert not ai_hub.is_available()
