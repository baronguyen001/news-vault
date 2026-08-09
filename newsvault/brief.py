from __future__ import annotations

import json
import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import requests

from newsvault.model import Article
from newsvault.prompts import brief_prompt

DEFAULT_MODEL: str = "gemini-2.5-flash"
API_BASE: str = "https://generativelanguage.googleapis.com/v1beta/models"

BRIEF_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "bullets": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": ["bullets"],
}

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class BriefResult:
    bullets: tuple[str, ...]
    source: str  # 'gemini' | 'fallback'
    error: str  # '' on success


def _error_detail(response: requests.Response, limit: int = 200) -> str:
    """Lý do thật của một phản hồi lỗi: `error.message` nếu là JSON, không thì thân thô.

    Không được ném lỗi trong bất kỳ trường hợp nào — đây là code chạy TRÊN đường lỗi, làm
    hỏng nó thì che mất chính cái lỗi đang cần đọc.
    """
    try:
        payload = response.json()
        if isinstance(payload, dict):
            error = payload.get("error")
            message = error.get("message") if isinstance(error, dict) else None
            if message:
                return str(message)[:limit]
    except Exception:
        pass
    return str(getattr(response, "text", ""))[:limit]


def _first_sentence(text: str) -> str:
    """Return the first sentence or paragraph of a Vietnamese summary."""
    if not text:
        return ""
    first = text
    for marker in (".\n", ". ", "\n\n", "\n", "!\n", "! ", "?\n", "? "):
        if marker in first:
            first = first.split(marker, 1)[0]
            break
    return first.strip()


def fallback_brief(articles: Sequence[Article], *, limit: int = 5) -> BriefResult:
    """Deterministic brief with no network: top `limit` articles by score."""
    ordered = sorted(articles, key=lambda article: article.score, reverse=True)
    bullets: list[str] = []
    for article in ordered[:limit]:
        sentence = _first_sentence(article.summary_vi)
        line = f"{article.source or 'Nguồn'} — {sentence or article.title_vi}"
        if len(line) > 220:
            line = line[:220]
        bullets.append(line)
    if not bullets:
        return BriefResult(tuple(), "fallback", "no articles")
    return BriefResult(tuple(bullets), "fallback", "")


def generate_brief(
    day: str,
    articles: Sequence[Article],
    *,
    api_key: str | None,
    model: str = DEFAULT_MODEL,
    timeout: int = 60,
    limit: int = 12,
) -> BriefResult:
    """Ask Gemini for five Vietnamese bullets about the day; falls back on any failure."""
    if not api_key:
        logger.warning("No Gemini API key for %s brief; using fallback", day)
        fb = fallback_brief(articles, limit=5)
        return BriefResult(fb.bullets, "fallback", "no api key")

    selected = sorted(articles, key=lambda article: article.score, reverse=True)[:limit]
    items = [
        {
            "title": article.title_vi,
            "source": article.source,
            "topic": article.topic,
            "impact": article.impact_level,
            "summary": (article.summary_vi or "")[:300],
        }
        for article in selected
    ]
    prompt = brief_prompt(day, items)
    url = f"{API_BASE}/{model}:generateContent"
    params = {"key": api_key}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.3,
            "thinkingConfig": {"thinkingBudget": 0},
            "responseMimeType": "application/json",
            "responseSchema": BRIEF_SCHEMA,
        },
    }

    for attempt in range(2):
        try:
            response = requests.post(url, params=params, json=payload, timeout=timeout)
        except requests.RequestException as exc:
            logger.warning(
                "Brief request failed for %s (attempt %d): %s",
                day,
                attempt + 1,
                type(exc).__name__,
            )
            if attempt == 0:
                time.sleep(3)
                continue
            fb = fallback_brief(articles, limit=5)
            return BriefResult(fb.bullets, "fallback", "network error")

        if response.status_code in (429, 500, 503):
            logger.warning(
                "Brief API status %s for %s (attempt %d): %s",
                response.status_code,
                day,
                attempt + 1,
                _error_detail(response),
            )
            if attempt == 0:
                time.sleep(3)
                continue
            fb = fallback_brief(articles, limit=5)
            return BriefResult(fb.bullets, "fallback", f"status {response.status_code}")

        if response.status_code != 200:
            # Thân phản hồi PHẢI vào log. Suốt 07-08/08/2026 log chỉ có "Brief API error 400"
            # nên không ai biết lý do thật là `API key not valid` — brief mỗi ngày lặng lẽ
            # tụt xuống bản fallback xếp-theo-điểm mà trang vẫn dựng bình thường.
            logger.warning(
                "Brief API error %s for %s: %s", response.status_code, day, _error_detail(response)
            )
            fb = fallback_brief(articles, limit=5)
            return BriefResult(fb.bullets, "fallback", f"status {response.status_code}")

        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            logger.warning("Brief response not JSON for %s: %s", day, type(exc).__name__)
            fb = fallback_brief(articles, limit=5)
            return BriefResult(fb.bullets, "fallback", "invalid json")

        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError):
            logger.warning("Brief response missing candidates for %s", day)
            fb = fallback_brief(articles, limit=5)
            return BriefResult(fb.bullets, "fallback", "missing candidates")

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            logger.warning("Brief candidate text not JSON for %s: %s", day, type(exc).__name__)
            fb = fallback_brief(articles, limit=5)
            return BriefResult(fb.bullets, "fallback", "invalid candidate json")

        bullets = parsed.get("bullets")
        if not isinstance(bullets, list) or not bullets:
            logger.warning("Brief bullets empty for %s", day)
            fb = fallback_brief(articles, limit=5)
            return BriefResult(fb.bullets, "fallback", "empty bullets")

        cleaned = [str(bullet).strip() for bullet in bullets if str(bullet).strip()]
        if not cleaned:
            fb = fallback_brief(articles, limit=5)
            return BriefResult(fb.bullets, "fallback", "empty bullets")

        return BriefResult(tuple(cleaned), "gemini", "")

    fb = fallback_brief(articles, limit=5)
    return BriefResult(fb.bullets, "fallback", "unknown")
