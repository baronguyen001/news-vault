"""Direct-Ollama safety net behind the AI Hub (added 2026-11-02). Everything is mocked."""

from __future__ import annotations

import json

import pytest

from newsvault import ai_hub


class FakeResponse:
    def __init__(self, status: int, lines: list[str] | None = None, text: str = "") -> None:
        self.status_code = status
        self.text = text
        self.headers: dict = {}
        self._lines = lines or []

    def iter_lines(self, decode_unicode: bool = False):
        return iter(line.encode("utf-8") for line in self._lines)


def _sse(content: str) -> list[str]:
    event = {"choices": [{"delta": {"content": content, "reasoning": "nghĩ"}}]}
    return [f"data: {json.dumps(event)}", "data: [DONE]"]


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setenv("AI_HUB_SLOT_DIR", str(tmp_path / "slots"))
    monkeypatch.setenv("AI_HUB_MODELS", "ollama/glm-5.3,planning")
    monkeypatch.setenv("AI_HUB_BASE_URL", "https://hub.example/v1")
    monkeypatch.setenv("AI_HUB_KEY", "sk-hub")
    monkeypatch.setenv("OLLAMA_API_KEY", "sk-ollama")
    monkeypatch.setattr(ai_hub.time, "sleep", lambda *_: None)
    ai_hub.reset_breaker()
    seen: list[tuple[str, str]] = []

    def fake_post(url, json=None, headers=None, **kwargs):
        seen.append((url, json["model"]))
        if url.startswith("https://hub.example"):
            return FakeResponse(403, text="No active credentials for provider: antigravity")
        assert headers["Authorization"] == "Bearer sk-ollama"
        return FakeResponse(200, _sse('{"ok": true}'))

    monkeypatch.setattr(ai_hub.requests, "post", fake_post)
    yield seen
    ai_hub.reset_breaker()


def test_dead_hub_falls_back_to_ollama_with_bare_model_name(calls):
    assert ai_hub.chat_json("x") == {"ok": True}
    assert calls[0] == ("https://hub.example/v1/chat/completions", "ollama/glm-5.3")
    assert calls[-1] == ("https://ollama.com/v1/chat/completions", "glm-5.3")


def test_alias_maps_to_ollama_model(calls):
    ai_hub.chat_json("x", model="coding")
    assert calls[-1] == ("https://ollama.com/v1/chat/completions", "glm-5.3-flash")


def test_open_hub_circuit_still_reaches_ollama(calls):
    for _ in range(ai_hub.BREAKER_THRESHOLD):
        ai_hub.chat_json("x")
    assert ai_hub.breaker_open()
    hub_calls = sum(1 for url, _ in calls if "hub.example" in url)
    assert ai_hub.chat_json("x") == {"ok": True}
    assert sum(1 for url, _ in calls if "hub.example" in url) == hub_calls


def test_without_key_no_fallback(calls, monkeypatch):
    monkeypatch.delenv("OLLAMA_API_KEY")
    with pytest.raises(RuntimeError):
        ai_hub.chat_json("x")
    assert all("ollama.com" not in url for url, _ in calls)


def test_key_never_leaks_into_error(calls, monkeypatch):
    def all_down(url, json=None, headers=None, **kwargs):
        return FakeResponse(401, text="bad key sk-ollama")

    monkeypatch.setattr(ai_hub.requests, "post", all_down)
    with pytest.raises(RuntimeError) as info:
        ai_hub.chat_json("x")
    assert "sk-ollama" not in str(info.value)
