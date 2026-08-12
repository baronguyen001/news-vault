from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from newsvault import ai_hub
from newsvault.model import Article
from newsvault.prompts import brief_prompt


# How many top-scoring articles the model gets to read, and how many bullets it returns.
BRIEF_ITEMS: int = 12
BRIEF_BULLETS: int = 5

logger = logging.getLogger(__name__)


_brief_provider_issue: str | None = None


@dataclass(frozen=True, slots=True)
class BriefResult:
    bullets: tuple[str, ...]
    source: str  # 'aihub' | 'fallback'
    error: str  # '' on success


# Sources that mean "a language model actually wrote this". Anything else is the
# score-ordered fallback, which is a quality incident worth reporting, not a real brief.
LLM_SOURCES: frozenset[str] = frozenset({"aihub"})


def reset_provider_state() -> None:
    """Clear process-local provider failures so tests and later runs start independently."""
    global _brief_provider_issue
    _brief_provider_issue = None


def brief_provider_issue() -> str | None:
    """Return the provider condition that should be shown in the build summary, if any."""
    return _brief_provider_issue


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
    limit: int = BRIEF_ITEMS,
) -> BriefResult:
    """Nam gach dau dong tieng Viet ve trong ngay: AI Hub, roi den fallback tinh.

    Truoc 2026-08-12 co them duong Gemini o giua. Da go han theo yeu cau: chi con
    MK1 AI Hub. Hub hong thi ROI THANG xuong `fallback_brief` (top-5 theo diem) —
    van co ban tin de xuat ban, nhung do la SU CO CHAT LUONG chu khong phai brief
    that, nen `BuildReport.summary()` phai keu len (source khong nam trong
    LLM_SOURCES) va `brief_provider_issue()` ghi ro ly do.
    """
    global _brief_provider_issue

    if not ai_hub.is_available():
        _brief_provider_issue = (
            "AI Hub chua cau hinh (AI_HUB_BASE_URL/AI_HUB_KEY) — brief tut xuong ban tu sinh"
        )
        logger.warning("No AI Hub for %s brief; using fallback", day)
        fb = fallback_brief(articles, limit=BRIEF_BULLETS)
        return BriefResult(fb.bullets, "fallback", "no ai hub")

    result = _brief_via_hub(day, articles, limit=limit)
    if result is not None:
        return result

    _brief_provider_issue = "AI Hub khong tra duoc brief — da dung ban tu sinh thay the"
    fb = fallback_brief(articles, limit=BRIEF_BULLETS)
    return BriefResult(fb.bullets, "fallback", "ai hub failed")


def _brief_via_hub(day: str, articles: Sequence[Article], *, limit: int) -> BriefResult | None:
    """Goi hub. Tra None (khong phai BriefResult) de caller quyet dinh dung fallback."""
    prompt = brief_prompt(day, _brief_items(articles, limit))
    try:
        # 8192 is deliberately roomy: the model burns budget on a hidden reasoning phase
        # before writing a single character, and a tight ceiling yields empty content that
        # looks like a model failure but is really a budget one.
        parsed = ai_hub.chat_json(prompt, max_tokens=8192, temperature=0.3)
    except Exception as exc:  # noqa: BLE001 — hub hong thi caller dung fallback
        logger.warning("Brief via AI Hub failed for %s: %s", day, str(exc)[:200])
        return None

    cleaned = _clean_bullets(parsed.get("bullets"))
    if not cleaned:
        logger.warning("Brief via AI Hub returned no usable bullets for %s", day)
        return None
    if looks_like_refusal(cleaned):
        # Trả None để caller ghi nhận đây là sự cố và dùng fallback có cảnh báo,
        # thay vì lặng lẽ coi lời từ chối của model là một brief hợp lệ.
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
