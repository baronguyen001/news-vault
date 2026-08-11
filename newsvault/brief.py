from __future__ import annotations

import json
import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import requests

from newsvault import ai_hub
from newsvault.model import Article
from newsvault.prompts import brief_prompt

DEFAULT_MODEL: str = "gemini-2.5-flash"
API_BASE: str = "https://generativelanguage.googleapis.com/v1beta/models"

# How many top-scoring articles the model gets to read, and how many bullets it returns.
BRIEF_ITEMS: int = 12
BRIEF_BULLETS: int = 5

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


_gemini_key_rejection: str | None = None


@dataclass(frozen=True, slots=True)
class BriefResult:
    bullets: tuple[str, ...]
    source: str  # 'aihub' | 'gemini' | 'fallback'
    error: str  # '' on success


# Sources that mean "a language model actually wrote this". Anything else is the
# score-ordered fallback, which is a quality incident worth reporting, not a real brief.
LLM_SOURCES: frozenset[str] = frozenset({"aihub", "gemini"})


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


def _response_body(response: requests.Response) -> str:
    """Return an error response body without allowing error handling to fail."""
    try:
        return json.dumps(response.json(), ensure_ascii=False)
    except Exception:
        return str(getattr(response, "text", ""))


def is_permanently_rejected_gemini_key(status_code: int, body: str) -> bool:
    """Return whether Gemini explicitly says that the configured key cannot be used."""
    normalized = body.casefold()
    return status_code != 200 and (
        "api_key_invalid" in normalized
        or "api key not valid" in normalized
        or (status_code == 403 and "permission_denied" in normalized)
    )


def reset_provider_state() -> None:
    """Clear process-local provider failures so tests and later runs start independently."""
    global _gemini_key_rejection
    _gemini_key_rejection = None


def gemini_provider_issue() -> str | None:
    """Return the Gemini condition that should be shown in the build summary, if any."""
    return _gemini_key_rejection


_REFUSAL_MARKERS: tuple[str, ...] = (
    "không có mục tin",
    "không có tin nào",
    "không có bài viết",
    "không có nội dung",
    "không có dữ liệu",
    "không được cung cấp",
    "chưa được cung cấp",
    "không có thông tin nào được cung cấp",
    "no items",
    "no articles",
    "no content",
    "not provided",
    "no data",
)


def looks_like_refusal(bullets: Sequence[str]) -> bool:
    """Return whether bullets look like a model refusal rather than a real brief.

    Sự cố thật 09/08/2026: ngày đó có 92 bài, `_brief_items` cắt ra đủ 12 mục và prompt dài
    5.220 ký tự — model NHẬN ĐỦ dữ liệu mà vẫn trả về 5 lần "Không có mục tin nào được cung
    cấp để tóm tắt.". `_clean_bullets` chỉ kiểm "chuỗi không rỗng" nên câu từ chối lọt qua
    như một brief thật, rồi bị cache kèm nhãn `aihub` ⇒ mọi lần dựng sau đọc lại rác, không
    bao giờ tự lành.

    Hai luật, cố ý tách riêng:
    - lặp y hệt từ 2 dòng trở lên: một bản tóm tắt thật không bao giờ lặp nguyên một câu;
    - câu từ chối chiếm từ MỘT NỬA trở lên. "Một nửa" chứ không phải "bất kỳ": model đôi khi
      viết 4 gạch tốt rồi thòng một câu thừa, vứt cả brief vì một dòng là quá tay.
    """
    if not bullets:
        return False

    normalized = [bullet.strip().casefold() for bullet in bullets]
    if len(normalized) >= 2 and len(set(normalized)) == 1:
        return True

    refusal_count = sum(
        any(marker in bullet for marker in _REFUSAL_MARKERS)
        for bullet in normalized
    )
    return refusal_count * 2 >= len(normalized)


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


def _brief_items(articles: Sequence[Article], limit: int) -> list[dict[str, object]]:
    """The top-scoring articles, trimmed to what the prompt needs."""
    selected = sorted(articles, key=lambda article: article.score, reverse=True)[:limit]
    return [
        {
            "title": article.title_vi,
            "source": article.source,
            "topic": article.topic,
            "impact": article.impact_level,
            "summary": (article.summary_vi or "")[:300],
        }
        for article in selected
    ]


def generate_brief(
    day: str,
    articles: Sequence[Article],
    *,
    api_key: str | None,
    model: str = DEFAULT_MODEL,
    timeout: int = 60,
    limit: int = BRIEF_ITEMS,
) -> BriefResult:
    """Five Vietnamese bullets about the day: AI Hub first, Gemini second, fallback last.

    The hub leads because it is an internal service on a flat cost while Gemini is metered
    and needs a key that can expire — and when it did expire, every build for three days
    quietly shipped the score-ordered fallback instead of a brief. Gemini is kept as a real
    safety net rather than deleted: two independent engines is the whole point of having a
    fallback at all.
    """
    if ai_hub.is_available():
        result = _brief_via_hub(day, articles, limit=limit)
        if result is not None:
            return result

    return _brief_via_gemini(day, articles, api_key=api_key, model=model, timeout=timeout,
                             limit=limit)


def _brief_via_hub(day: str, articles: Sequence[Article], *, limit: int) -> BriefResult | None:
    """Try the hub. Returns None (not a fallback result) so the caller can try Gemini."""
    prompt = brief_prompt(day, _brief_items(articles, limit))
    try:
        # 8192 is deliberately roomy: the model burns budget on a hidden reasoning phase
        # before writing a single character, and a tight ceiling yields empty content that
        # looks like a model failure but is really a budget one.
        parsed = ai_hub.chat_json(prompt, max_tokens=8192, temperature=0.3)
    except Exception as exc:  # noqa: BLE001 — any hub failure must yield to Gemini
        logger.warning("Brief via AI Hub failed for %s: %s", day, str(exc)[:200])
        return None

    cleaned = _clean_bullets(parsed.get("bullets"))
    if not cleaned:
        logger.warning("Brief via AI Hub returned no usable bullets for %s", day)
        return None
    if looks_like_refusal(cleaned):
        # Trả None chứ KHÔNG trả BriefResult: trả kết quả ở đây sẽ chặn mất đường Gemini,
        # tức là mất luôn lưới đỡ đúng lúc cần nó nhất.
        logger.warning("Brief via AI Hub từ chối trả lời cho %s: %s", day, cleaned[0][:120])
        return None
    return BriefResult(tuple(cleaned), "aihub", "")


def _clean_bullets(raw: object) -> list[str]:
    """Keep the non-empty strings, trimmed, capped at the bullet count."""
    if not isinstance(raw, list):
        return []
    cleaned: list[str] = []
    for item in raw:
        if isinstance(item, str) and item.strip():
            cleaned.append(item.strip())
    return cleaned[:BRIEF_BULLETS]


def _brief_via_gemini(
    day: str,
    articles: Sequence[Article],
    *,
    api_key: str | None,
    model: str,
    timeout: int,
    limit: int,
) -> BriefResult:
    """Ask Gemini for five Vietnamese bullets about the day; falls back on any failure."""
    global _gemini_key_rejection

    if _gemini_key_rejection is not None:
        fb = fallback_brief(articles, limit=BRIEF_BULLETS)
        return BriefResult(fb.bullets, "fallback", "gemini key rejected")

    if not api_key:
        logger.warning("No AI Hub and no Gemini API key for %s brief; using fallback", day)
        fb = fallback_brief(articles, limit=BRIEF_BULLETS)
        return BriefResult(fb.bullets, "fallback", "no api key")

    items = _brief_items(articles, limit)
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

        if response.status_code != 200:
            message = _error_detail(response)
            if is_permanently_rejected_gemini_key(response.status_code, _response_body(response)):
                _gemini_key_rejection = "Gemini: key bị từ chối (API_KEY_INVALID) — mất lưới đỡ"
                logger.error("Gemini API key rejected permanently: %s", message)
                fb = fallback_brief(articles, limit=5)
                return BriefResult(fb.bullets, "fallback", "gemini key rejected")

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
                "Brief API error %s for %s: %s", response.status_code, day, message
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

        if looks_like_refusal(cleaned):
            logger.warning("Brief via Gemini từ chối trả lời cho %s: %s", day, cleaned[0][:120])
            fb = fallback_brief(articles, limit=BRIEF_BULLETS)
            return BriefResult(fb.bullets, "fallback", "refusal")

        return BriefResult(tuple(cleaned), "gemini", "")

    fb = fallback_brief(articles, limit=5)
    return BriefResult(fb.bullets, "fallback", "unknown")
