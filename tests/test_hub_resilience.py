"""AI Hub resilience (no retry on dead credentials, 429 backoff, breaker), stale-brief
retention and .env loading for the video-freshness alarm. Everything is mocked."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from newsvault import ai_hub, build
from newsvault.brief import BriefResult
from newsvault.build import _brief_for
from tests.test_brief_cache_selfheal import (
    GOOD_BULLETS,
    make_options,
    read_cache,
    write_cache,
)
from tests.test_brief import _article


class FakeResponse:
    def __init__(self, status: int, text: str = "", headers: dict | None = None) -> None:
        self.status_code = status
        self.text = text
        self.headers = headers or {}

    def iter_lines(self, decode_unicode: bool = False):
        return iter(())


@pytest.fixture(autouse=True)
def _hub(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setenv("AI_HUB_SLOT_DIR", str(tmp_path / "slots"))
    monkeypatch.setenv("AI_HUB_MODELS", "ollama/a")
    monkeypatch.setenv("AI_HUB_BASE_URL", "https://hub.example/v1")
    monkeypatch.setenv("AI_HUB_KEY", "sk-test")
    ai_hub.reset_breaker()
    yield
    ai_hub.reset_breaker()


def _patch(monkeypatch, responses):
    calls: list[dict] = []
    sleeps: list[float] = []
    queue = list(responses)

    def post(url, **kwargs):
        calls.append(kwargs)
        return queue.pop(0) if len(queue) > 1 else queue[0]

    monkeypatch.setattr(ai_hub.requests, "post", post)
    monkeypatch.setattr(ai_hub.time, "sleep", sleeps.append)
    return calls, sleeps


@pytest.mark.parametrize("status", [403, 404])
def test_dead_route_is_not_retried(monkeypatch, status) -> None:
    calls, sleeps = _patch(monkeypatch, [FakeResponse(status, "gone")])
    with pytest.raises(RuntimeError):
        ai_hub.chat_json("x")
    assert len(calls) == 1 and sleeps == []


def test_429_no_active_credentials_is_not_retried(monkeypatch) -> None:
    calls, sleeps = _patch(
        monkeypatch, [FakeResponse(429, "No active credentials for provider: antigravity")]
    )
    with pytest.raises(RuntimeError, match="No active credentials"):
        ai_hub.chat_json("x")
    assert len(calls) == 1 and sleeps == []


def test_429_honours_capped_retry_after(monkeypatch) -> None:
    calls, sleeps = _patch(
        monkeypatch, [FakeResponse(429, "slow down", {"Retry-After": "999"})]
    )
    with pytest.raises(RuntimeError):
        ai_hub.chat_json("x")
    assert len(calls) == 3
    assert sleeps == [30.0, 30.0]
    calls, sleeps = _patch(monkeypatch, [FakeResponse(429, "", {"Retry-After": "4"})])
    ai_hub.reset_breaker()
    with pytest.raises(RuntimeError):
        ai_hub.chat_json("x")
    assert sleeps == [4.0, 4.0]


def test_circuit_breaker_opens_after_consecutive_failures(monkeypatch) -> None:
    calls, _ = _patch(monkeypatch, [FakeResponse(404, "gone")])
    for _ in range(ai_hub.BREAKER_THRESHOLD):
        with pytest.raises(RuntimeError):
            ai_hub.chat_json("x")
    assert len(calls) == ai_hub.BREAKER_THRESHOLD
    with pytest.raises(RuntimeError, match="circuit open"):
        ai_hub.chat_json("x")
    assert len(calls) == ai_hub.BREAKER_THRESHOLD  # no further network call


def test_default_max_tokens_is_generous() -> None:
    import inspect

    default = inspect.signature(ai_hub.chat_json).parameters["max_tokens"].default
    assert default >= 16000


def test_brief_max_tokens_env_override(monkeypatch) -> None:
    from newsvault import brief

    assert brief._brief_max_tokens() == 16000
    monkeypatch.setenv("AI_HUB_BRIEF_MAX_TOKENS", "20000")
    assert brief._brief_max_tokens() == 20000


# --- B1a ------------------------------------------------------------------------------


def test_stale_cache_survives_a_failed_regeneration(tmp_path, monkeypatch) -> None:
    options = make_options(tmp_path)
    write_cache(options, "2026-11-01", GOOD_BULLETS, fingerprint="old-fp")
    monkeypatch.setattr(
        build,
        "generate_brief",
        lambda *a, **k: BriefResult(("Tự sinh.",), "fallback", "ai hub failed"),
    )
    result = _brief_for("2026-11-01", [_article()], options, finalize=True)
    assert result.bullets == GOOD_BULLETS
    assert result.source == "aihub"
    cached = read_cache(options, "2026-11-01")
    assert cached["fp"] == "old-fp" and tuple(cached["bullets"]) == GOOD_BULLETS


# --- B1b ------------------------------------------------------------------------------


def test_video_freshness_loads_dotenv(tmp_path, monkeypatch, capsys) -> None:
    script = Path(__file__).parents[1] / "scripts" / "check_video_freshness.py"
    spec = importlib.util.spec_from_file_location("cvf_env", script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    env = tmp_path / ".env"
    env.write_text("NEWSVAULT_VIDEO_DB=" + str(tmp_path / "v.db") + "\n", encoding="utf-8")
    monkeypatch.delenv("NEWSVAULT_VIDEO_DB", raising=False)
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    mod.main([])
    out = capsys.readouterr().out
    assert "thiếu DB" not in out
    import os

    assert os.environ["NEWSVAULT_VIDEO_DB"].endswith("v.db")
    monkeypatch.delenv("NEWSVAULT_VIDEO_DB", raising=False)


# --- ollama-only hub ------------------------------------------------------------------


class SseResponse(FakeResponse):
    def __init__(self, lines: list[str], status: int = 200) -> None:
        super().__init__(status)
        self._lines = lines

    def iter_lines(self, decode_unicode: bool = False):
        return iter(line.encode("utf-8") for line in self._lines)


def _sse(*pieces: str) -> SseResponse:
    import json

    lines = [
        'data: ' + json.dumps({"choices": [{"delta": {"reasoning_content": "nghĩ..."}}]}),
        "",
    ]
    for piece in pieces:
        lines.append("data: " + json.dumps({"choices": [{"delta": {"content": piece}}]},
                                           ensure_ascii=False))
    lines.append("data: [DONE]")
    return SseResponse(lines)


def test_sse_stream_is_parsed_and_reasoning_ignored(monkeypatch) -> None:
    _patch(monkeypatch, [_sse('{"bullets": ["Xin ', 'chào"]}')])
    assert ai_hub.chat_json("x") == {"bullets": ["Xin chào"]}


def test_plain_json_body_is_parsed(monkeypatch) -> None:
    import json

    body = json.dumps(
        {"choices": [{"message": {"content": '{"ok": "được"}'}}]}, ensure_ascii=False
    )
    _patch(monkeypatch, [SseResponse(body.splitlines())])
    assert ai_hub.chat_json("x") == {"ok": "được"}


def test_concurrency_429_sleeps_resets_and_never_opens_breaker(monkeypatch) -> None:
    busy = FakeResponse(429, "too many concurrent requests (reset after 42s)")
    calls, sleeps = _patch(monkeypatch, [busy, busy, _sse('{"a": 1}')])
    assert ai_hub.chat_json("x") == {"a": 1}
    assert sleeps == [43.0, 43.0]
    # Persistent cap: gives up after 3 waits, still no breaker strike.
    ai_hub.reset_breaker()
    calls, sleeps = _patch(monkeypatch, [busy])
    for _ in range(ai_hub.BREAKER_THRESHOLD + 1):
        with pytest.raises(RuntimeError, match="concurrency"):
            ai_hub.chat_json("x")
    assert not ai_hub.breaker_open()
    assert max(sleeps) <= 60.0


def test_retired_model_is_skipped_for_the_rest_of_the_process(monkeypatch) -> None:
    monkeypatch.setenv("AI_HUB_MODELS", "ollama/old,ollama/new")
    seen: list[str] = []
    queue = [FakeResponse(410, "model was retired"), _sse('{"a": 1}'), _sse('{"a": 2}')]

    def post(url, **kwargs):
        seen.append(kwargs["json"]["model"])
        return queue.pop(0)

    monkeypatch.setattr(ai_hub.requests, "post", post)
    monkeypatch.setattr(ai_hub.time, "sleep", lambda s: None)
    assert ai_hub.chat_json("x") == {"a": 1}
    assert ai_hub.chat_json("x") == {"a": 2}
    assert seen == ["ollama/old", "ollama/new", "ollama/new"]


def test_empty_content_falls_to_the_next_model_in_ladder_order(monkeypatch) -> None:
    monkeypatch.delenv("AI_HUB_MODELS")
    monkeypatch.delenv("AI_HUB_MODEL", raising=False)
    assert ai_hub.model_ladder() == [
        "ollama/glm-5.3", "ollama/deepseek-v4.1-flash", "ollama/glm-5.3-flash"
    ]
    seen: list[str] = []
    queue = [SseResponse(["data: [DONE]"]), SseResponse(["data: [DONE]"]), _sse('{"z": 1}')]

    def post(url, **kwargs):
        seen.append(kwargs["json"]["model"])
        return queue.pop(0)

    monkeypatch.setattr(ai_hub.requests, "post", post)
    monkeypatch.setattr(ai_hub.time, "sleep", lambda s: None)
    assert ai_hub.chat_json("x") == {"z": 1}
    assert seen == ai_hub.model_ladder()
