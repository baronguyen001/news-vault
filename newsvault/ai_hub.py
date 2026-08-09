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
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)

# Every setting is read at CALL time, never at import time. `newsvault.cli` imports
# `newsvault.build` (and through it this module) at line 12 but only calls `load_dotenv()`
# inside `main()` at line 244, so anything captured during import sees an environment that
# does not have the keys in it yet. A module-level `os.environ.get` here would leave
# `is_available()` permanently False and send every brief to Gemini in complete silence —
# exactly the failure this change exists to remove.
DEFAULT_MODEL = "planning"
DEFAULT_TIMEOUT = 300

_MAX_RETRIES = 2
_RETRY_STATUS = {429, 500, 502, 503, 504}


class NoRetry(RuntimeError):
    """A failure that a second identical attempt cannot fix."""


def base_url() -> str:
    return os.environ.get("AI_HUB_BASE_URL", "").rstrip("/")


def api_key() -> str:
    return os.environ.get("AI_HUB_KEY", "")


def default_model() -> str:
    return os.environ.get("AI_HUB_MODEL", DEFAULT_MODEL)


def timeout_seconds() -> int:
    try:
        return int(os.environ.get("AI_HUB_TIMEOUT", str(DEFAULT_TIMEOUT)))
    except ValueError:
        return DEFAULT_TIMEOUT


def enabled() -> bool:
    return os.environ.get("AI_HUB_ENABLED", "1") not in ("0", "false", "False", "")


def is_available() -> bool:
    return bool(enabled() and base_url() and api_key())


def _scrub(text: str) -> str:
    """Never let the key reach a log line or an error message."""
    key = api_key()
    return text.replace(key, "***") if key else text


def chat_json(
    prompt: str,
    *,
    max_tokens: int = 8192,
    temperature: float = 0.3,
    model: str | None = None,
    timeout: int | None = None,
) -> dict[str, Any]:
    """Return the parsed JSON object the model produced.

    Raises RuntimeError on any failure so the caller can fall back. Never returns a partial
    or guessed result.
    """
    if not is_available():
        raise RuntimeError("AI Hub not configured")

    payload = {
        "model": model or default_model(),
        "stream": True,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
        "messages": [{"role": "user", "content": prompt}],
    }
    headers = {
        "Authorization": f"Bearer {api_key()}",
        # urllib's and requests' default agents get blocked by Cloudflare with error 1010,
        # which is indistinguishable from an auth failure at the call site.
        "User-Agent": "Mozilla/5.0",
    }

    last_error = ""
    for attempt in range(_MAX_RETRIES + 1):
        try:
            text = _stream_text(payload, headers, timeout or timeout_seconds())
            return _parse_object(text)
        except NoRetry as exc:
            raise RuntimeError(_scrub(str(exc))) from None
        except Exception as exc:  # noqa: BLE001 — network, decode and parse all retry alike
            last_error = _scrub(f"{type(exc).__name__}: {exc}")[:200]
            if attempt < _MAX_RETRIES:
                time.sleep(2 * (attempt + 1))

    raise RuntimeError(f"AI Hub failed after {_MAX_RETRIES + 1} attempts: {last_error}")


def _stream_text(payload: dict[str, Any], headers: dict[str, str], timeout: int) -> str:
    """Read one server-sent-events response and return the concatenated content."""
    response = requests.post(
        f"{base_url()}/chat/completions",
        json=payload,
        headers=headers,
        timeout=timeout,
        stream=True,
    )
    if response.status_code == 524:
        raise NoRetry("AI Hub 524 (Cloudflare cut the request); retrying costs the same wall")
    if response.status_code in _RETRY_STATUS:
        raise RuntimeError(f"AI Hub HTTP {response.status_code}")
    if response.status_code != 200:
        raise NoRetry(f"AI Hub HTTP {response.status_code}: {(response.text or '')[:200]}")

    chunks: list[str] = []
    reasoning_chars = 0
    # decode_unicode=True would use response.encoding, and text/event-stream declares no
    # charset, so HTTP defaults it to ISO-8859-1 and every Vietnamese character comes back
    # as mojibake — silently, with no error anywhere. Decode the bytes ourselves.
    for raw in response.iter_lines(decode_unicode=False):
        if not raw:
            continue
        line = raw.decode("utf-8", errors="replace").strip()
        if not line.startswith("data:"):
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
            reasoning = delta.get("reasoning_content")
            if reasoning:
                reasoning_chars += len(reasoning)

    text = "".join(chunks).strip()
    if not text:
        # Distinguish the two silences: a model that thought hard and emitted nothing has
        # run out of budget, which is a `max_tokens` problem, not a capability problem.
        raise NoRetry(
            f"AI Hub returned no content ({reasoning_chars} reasoning chars) — "
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
