"""MK1 AI Hub client — the primary engine for the daily brief.

Gemini used to be the only engine here, and when its key expired the brief silently fell
back to a score-ordered list on every build for three days running. The hub is an internal
service on a flat cost, so it is now the default and Gemini is the optional safety net.

The API is OpenAI-compatible: `POST {base}/chat/completions`. Two details are not
negotiable and both were learned the hard way in sibling projects:

* **Stream anything that can take more than ~100 seconds.** Cloudflare in front of the hub
  cuts a non-streaming request at roughly 100s with HTTP 524, and retrying an identical
  request just hits the same wall for another 100s. 524 is therefore never retried.
* **`max_tokens` must be generous.** The model spends budget on a hidden reasoning phase
  before emitting any content, so a small ceiling produces an EMPTY `content` alongside
  thousands of reasoning characters — which reads exactly like "the model cannot do this"
  while actually being a budget problem. That case is reported explicitly.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any

import requests

from newsvault import codex_fallback
from newsvault.hub_slots import (
    hub_slot,
    is_concurrency_429,
    is_retired_model,
    reset_after_seconds,
)

logger = logging.getLogger(__name__)

# Every setting is read at CALL time, never at import time. `newsvault.cli` imports
# `newsvault.build` (and through it this module) at line 12 but only calls `load_dotenv()`
# inside `main()` at line 244, so anything captured during import sees an environment that
# does not have the keys in it yet. A module-level `os.environ.get` here would leave
# `is_available()` permanently False and send every brief to Gemini in complete silence —
# exactly the failure this change exists to remove.
# The hub's old providers (antigravity, opencode-go) are permanently gone: only `ollama/*`
# models answer. The ladder is tried in order; a model that errors or returns nothing hands
# over to the next one.
DEFAULT_MODELS = (
    "ollama/glm-5.3",
    "ollama/deepseek-v4.1-flash",
    "ollama/glm-5.3-flash",
)
DEFAULT_MODEL = DEFAULT_MODELS[0]
DEFAULT_TIMEOUT = 300

_MAX_RETRIES = 2
_CONCURRENCY_RETRIES = 3
_RETRY_STATUS = {429, 500, 502, 503, 504}
# 401/403 mean the credential is gone for every model, not that the hub is busy.
_FATAL_STATUS = {401, 403}
_RETRY_AFTER_CAP = 30.0
# Circuit breaker: after this many consecutive failed calls in ONE process the hub is
# treated as down and further calls fail instantly (a backfill can ask for the brief of
# many days; each would otherwise burn its own retries against a dead credential).
# Concurrency-cap 429s never count: that cap is shared by every project on the account.
BREAKER_THRESHOLD = 3
_consecutive_failures = 0
_retired_models: set[str] = set()
# Safety net behind the hub: the same models called directly on Ollama Cloud
# (OpenAI-compatible) with the user's own key. Unset OLLAMA_API_KEY disables it.
_OLLAMA_ALIASES = {"fast": "deepseek-v4.1-flash", "planning": "glm-5.3", "coding": "glm-5.3-flash"}
_ollama_failures = 0


class NoRetry(RuntimeError):
    """A failure that a second identical attempt cannot fix (the next model may)."""


class FatalHub(NoRetry):
    """A failure no other model can fix either (credential gone)."""


class ModelRetired(NoRetry):
    """HTTP 410 "retired": skip this model for the rest of the process."""


class HubBusy(RuntimeError):
    """The account-wide concurrency cap; `wait` is the server's reset time in seconds."""

    def __init__(self, message: str, wait: float = 30.0) -> None:
        super().__init__(message)
        self.wait = wait


class RateLimited(RuntimeError):
    """HTTP 429 that may clear on its own; carries the server's Retry-After hint."""

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


def reset_breaker() -> None:
    global _consecutive_failures, _ollama_failures
    _consecutive_failures = 0
    _ollama_failures = 0
    _retired_models.clear()


def breaker_open() -> bool:
    return _consecutive_failures >= BREAKER_THRESHOLD


def _retry_after_seconds(value: str | None) -> float | None:
    try:
        return max(0.0, min(float(value), _RETRY_AFTER_CAP)) if value else None
    except ValueError:
        return None


def base_url() -> str:
    return os.environ.get("AI_HUB_BASE_URL", "").rstrip("/")


def api_key() -> str:
    return os.environ.get("AI_HUB_KEY", "")


def default_model() -> str:
    return model_ladder()[0]


def model_ladder() -> list[str]:
    """Models to try in order. AI_HUB_MODELS is comma separated; failing that, the older
    single AI_HUB_MODEL goes first, followed by the default ladder."""
    raw = os.environ.get("AI_HUB_MODELS", "")
    models = [m.strip() for m in raw.split(",") if m.strip()]
    if not models:
        single = os.environ.get("AI_HUB_MODEL", "").strip()
        models = [single] if single else []
        models += [m for m in DEFAULT_MODELS if m != single]
    return models


def timeout_seconds() -> int:
    try:
        return int(os.environ.get("AI_HUB_TIMEOUT", str(DEFAULT_TIMEOUT)))
    except ValueError:
        return DEFAULT_TIMEOUT


def enabled() -> bool:
    return os.environ.get("AI_HUB_ENABLED", "1") not in ("0", "false", "False", "")


def ollama_api_key() -> str:
    return os.environ.get("OLLAMA_API_KEY", "")


def ollama_base_url() -> str:
    return os.environ.get("OLLAMA_BASE_URL", "https://ollama.com/v1").rstrip("/")


def _hub_configured() -> bool:
    return bool(enabled() and base_url() and api_key())


def is_available() -> bool:
    """True when at least one route works: the hub, or the direct Ollama safety net."""
    return _hub_configured() or bool(ollama_api_key()) or codex_fallback.is_usable()


def _scrub(text: str) -> str:
    """Never let a key reach a log line or an error message."""
    for key in (api_key(), ollama_api_key()):
        if key:
            text = text.replace(key, "***")
    return text


def _ollama_model(name: str) -> str:
    name = name.strip().removeprefix("ollama/")
    return _OLLAMA_ALIASES.get(name, name)


def chat_json(
    prompt: str,
    *,
    max_tokens: int = 16000,
    temperature: float = 0.3,
    model: str | None = None,
    timeout: int | None = None,
) -> dict[str, Any]:
    """Return the parsed JSON object the model produced.

    Hub first; when it fails (or its circuit is open) the same models are tried directly on
    Ollama Cloud if OLLAMA_API_KEY is set. Raises RuntimeError on any failure so the caller
    can fall back. Never returns a partial or guessed result.
    """
    try:
        return _hub_chat_json(prompt, max_tokens=max_tokens, temperature=temperature,
                              model=model, timeout=timeout)
    except RuntimeError as hub_exc:
        error = _scrub(str(hub_exc))
        if ollama_api_key():
            logger.warning("AI Hub failed (%s); trying Ollama directly", error[:160])
            try:
                return _ollama_chat_json(prompt, max_tokens, temperature, model, timeout)
            except RuntimeError as exc:
                error = f"{error}; Ollama direct: {_scrub(str(exc))[:200]}"
        if not (codex_fallback.enabled() and not codex_fallback.is_disabled()):
            raise RuntimeError(error) from None
        return _codex_chat_json(prompt, error, timeout)


_codex_rescue_logged = False


def _codex_chat_json(prompt: str, prior_error: str, timeout: int | None) -> dict[str, Any]:
    """Last resort: the local Codex CLI. Same prompt, JSON parsed from its text output."""
    global _codex_rescue_logged
    logger.warning("AI Hub/Ollama failed (%s); trying Codex CLI", prior_error[:200])
    full = "Chỉ trả đúng một JSON object, không markdown.\n\n" + prompt
    text = codex_fallback.codex_fallback(full, timeout=max(timeout or 0, 300))
    if not text:
        reason = codex_fallback.disabled_reason() or "no output (see log)"
        raise RuntimeError(f"{prior_error}; Codex CLI: {reason[:200]}")
    cleaned = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", text.strip(), flags=re.IGNORECASE)
    try:
        parsed = _parse_object(cleaned)
    except (RuntimeError, ValueError) as exc:
        raise RuntimeError(f"{prior_error}; Codex CLI: unparsable output ({exc})") from None
    if not _codex_rescue_logged:
        _codex_rescue_logged = True
        logger.warning("Codex CLI rescued an LLM call (hub and Ollama unavailable)")
    return parsed


def _ollama_chat_json(prompt: str, max_tokens: int, temperature: float,
                      model: str | None, timeout: int | None) -> dict[str, Any]:
    global _ollama_failures
    if _ollama_failures >= BREAKER_THRESHOLD:
        raise RuntimeError(f"Ollama circuit open ({_ollama_failures} consecutive failures)")
    headers = {"Authorization": f"Bearer {ollama_api_key()}", "User-Agent": "Mozilla/5.0"}
    names = list(dict.fromkeys(_ollama_model(m) for m in ([model] if model else model_ladder())))
    url = f"{ollama_base_url()}/chat/completions"
    last_error = ""
    for name in names:
        payload = {
            "model": name,
            "stream": True,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "user", "content": prompt}],
        }
        try:
            parsed = _call_model(payload, headers, timeout or timeout_seconds(), url=url)
        except Exception as exc:  # noqa: BLE001 — try the next model
            last_error = _scrub(f"{name}: {exc}")[:200]
            logger.warning("Ollama model %s failed: %s", name, last_error)
            continue
        _ollama_failures = 0
        return parsed
    _ollama_failures += 1
    raise RuntimeError(f"Ollama failed on all models ({', '.join(names)}): {last_error}")


def _hub_chat_json(
    prompt: str,
    *,
    max_tokens: int,
    temperature: float,
    model: str | None,
    timeout: int | None,
) -> dict[str, Any]:
    global _consecutive_failures
    if not _hub_configured():
        raise RuntimeError("AI Hub not configured")
    if breaker_open():
        raise RuntimeError(
            f"AI Hub circuit open ({_consecutive_failures} consecutive failures); skipping call"
        )

    headers = {
        "Authorization": f"Bearer {api_key()}",
        # urllib's and requests' default agents get blocked by Cloudflare with error 1010,
        # which is indistinguishable from an auth failure at the call site.
        "User-Agent": "Mozilla/5.0",
    }
    ladder = [model] if model else model_ladder()
    candidates = [m for m in ladder if m not in _retired_models]
    if not candidates:
        _consecutive_failures += 1
        raise RuntimeError("AI Hub: every configured model is retired")

    last_error = ""
    for name in candidates:
        payload = {
            "model": name,
            "stream": True,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "user", "content": prompt}],
        }
        try:
            parsed = _call_model(payload, headers, timeout or timeout_seconds())
        except HubBusy as exc:
            # Shared cap, not a fault of this client: no breaker, and other models share it.
            raise RuntimeError(_scrub(str(exc))) from None
        except ModelRetired as exc:
            _retired_models.add(name)
            logger.warning("AI Hub model %s retired; skipping it for this process", name)
            last_error = _scrub(str(exc))[:200]
            continue
        except FatalHub as exc:
            _consecutive_failures += 1
            raise RuntimeError(_scrub(str(exc))) from None
        except Exception as exc:  # noqa: BLE001 — try the next model
            last_error = _scrub(f"{name}: {exc}")[:200]
            logger.warning("AI Hub model %s failed: %s", name, last_error)
            continue
        _consecutive_failures = 0
        return parsed

    _consecutive_failures += 1
    raise RuntimeError(f"AI Hub failed on all models ({', '.join(candidates)}): {last_error}")


def _call_model(payload: dict[str, Any], headers: dict[str, str], timeout: int,
                url: str | None = None) -> dict[str, Any]:
    """One model: retry transient errors, wait out the shared concurrency cap.

    `url` set = a direct endpoint (Ollama) that does not take a shared hub slot."""
    busy = 0
    attempt = 0
    while True:
        try:
            if url:
                text = _stream_text_locked(payload, headers, timeout, url=url)
            else:
                text = _stream_text(payload, headers, timeout)
            return _parse_object(text)
        except HubBusy as exc:
            busy += 1
            if busy > _CONCURRENCY_RETRIES:
                raise HubBusy(
                    f"AI Hub concurrency cap still full after {_CONCURRENCY_RETRIES} waits"
                ) from None
            time.sleep(exc.wait)
        except NoRetry:
            raise
        except Exception as exc:  # noqa: BLE001 — network, decode and parse all retry alike
            last_error = _scrub(f"{type(exc).__name__}: {exc}")[:200]
            if attempt >= _MAX_RETRIES:
                raise RuntimeError(
                    f"AI Hub failed after {_MAX_RETRIES + 1} attempts: {last_error}"
                ) from None
            delay = 2.0 * (attempt + 1)
            if isinstance(exc, RateLimited):
                # Honour Retry-After, but never stall a build for minutes on it.
                delay = exc.retry_after if exc.retry_after is not None else delay * 3
                delay = min(delay, _RETRY_AFTER_CAP)
            attempt += 1
            time.sleep(delay)


def _stream_text(payload: dict[str, Any], headers: dict[str, str], timeout: int) -> str:
    """POST once (holding a shared hub slot) and return the model's content text."""
    with hub_slot():
        return _stream_text_locked(payload, headers, timeout)


def _stream_text_locked(payload: dict[str, Any], headers: dict[str, str], timeout: int,
                        url: str | None = None) -> str:
    response = requests.post(
        url or f"{base_url()}/chat/completions",
        json=payload,
        headers=headers,
        timeout=timeout,
        stream=True,
    )
    status = response.status_code
    if status != 200:
        body = (response.text or "")[:300]
        if status == 524:
            raise NoRetry("AI Hub 524 (Cloudflare cut the request); retrying costs the same wall")
        if is_concurrency_429(status, body):
            raise HubBusy("AI Hub concurrency cap", reset_after_seconds(body, cap=60.0))
        if is_retired_model(status, body):
            raise ModelRetired(f"AI Hub HTTP 410: {body[:200]}")
        if status in _FATAL_STATUS or (status == 429 and "no active credentials" in body.lower()):
            raise FatalHub(f"AI Hub HTTP {status}: {body[:200]}")
        if status == 429:
            raise RateLimited(
                "AI Hub HTTP 429", _retry_after_seconds(response.headers.get("Retry-After"))
            )
        if status in _RETRY_STATUS:
            raise RuntimeError(f"AI Hub HTTP {status}")
        raise NoRetry(f"AI Hub HTTP {status}: {body[:200]}")

    chunks: list[str] = []
    plain: list[str] = []
    reasoning_chars = 0
    # decode_unicode=True would use response.encoding, and text/event-stream declares no
    # charset, so HTTP defaults it to ISO-8859-1 and every Vietnamese character comes back
    # as mojibake — silently, with no error anywhere. Decode the bytes ourselves.
    # The hub answers with SSE even when it is not asked to, but a plain JSON body is also
    # handled: any line that is not a `data:` event is kept and parsed as JSON afterwards.
    for raw in response.iter_lines(decode_unicode=False):
        if not raw:
            continue
        line = raw.decode("utf-8", errors="replace").strip()
        if not line.startswith("data:"):
            plain.append(line)
            continue
        body = line[5:].strip()
        if body == "[DONE]":
            break
        try:
            event = json.loads(body)
        except ValueError:
            continue
        for choice in event.get("choices") or []:
            delta = choice.get("delta") or {}
            piece = delta.get("content")
            if piece:
                chunks.append(piece)
            # The hub sends `reasoning_content`; Ollama directly sends `reasoning`.
            reasoning = delta.get("reasoning_content") or delta.get("reasoning")
            if reasoning:
                reasoning_chars += len(reasoning)

    text = "".join(chunks).strip()
    if not text and plain:
        try:
            doc = json.loads("\n".join(plain))
            for choice in doc.get("choices") or []:
                message = choice.get("message") or {}
                text = (message.get("content") or "").strip()
                reasoning_chars += len(message.get("reasoning_content") or "")
                if text:
                    break
        except (ValueError, AttributeError):
            pass
    if not text:
        # Distinguish the two silences: a model that thought hard and emitted nothing has
        # run out of budget, which is a `max_tokens` problem, not a capability problem.
        raise NoRetry(
            f"AI Hub returned empty content ({reasoning_chars} reasoning chars) — "
            "raise max_tokens rather than blaming the model"
        )
    return text


def _parse_object(text: str) -> dict[str, Any]:
    """Extract the first JSON object from the model's text."""
    start = text.find("{")
    if start < 0:
        raise RuntimeError("AI Hub response contains no JSON object")
    # raw_decode stops at the end of the FIRST object. Slicing find("{")..rfind("}")
    # instead breaks the moment the model appends prose or a second object after the one
    # that matters ("Extra data: line 15" — seen for real in a sibling project).
    obj, _end = json.JSONDecoder().raw_decode(text[start:])
    if not isinstance(obj, dict):
        raise RuntimeError("AI Hub response is not a JSON object")
    return obj
