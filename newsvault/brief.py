from __future__ import annotations

import logging
import os
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass

from newsvault import ai_hub
from newsvault.model import Article
from newsvault.posts import Post
from newsvault.prompts import brief_prompt

# How many top-scoring articles the model gets to read, and how many bullets it returns.
BRIEF_ITEMS: int = 12
BRIEF_BULLETS: int = 5

# Bài X đọc kèm, tính RIÊNG với bài báo. Trước 16/08/2026 brief chỉ đọc `articles`, nên
# "Tóm tắt ngày" — thứ nằm trên cùng trang ngày VÀ trên trang chủ — về cấu trúc chưa bao giờ
# nhắc tới một dòng nào từ X, dù x-pulse đổ vào đúng trang đó ba lượt mỗi ngày.
#
# Hạn riêng chứ không gộp chung vào `BRIEF_ITEMS` là có lý do: điểm của bài X (`score` của
# x-pulse) và điểm của bài báo (`score` của news-hunter) là hai thang khác nhau, trộn rồi
# sắp chung sẽ để một thang nuốt hết suất của thang kia. Cắt riêng thì mỗi bên giữ được chỗ.
BRIEF_POST_ITEMS: int = 6

logger = logging.getLogger(__name__)


_brief_provider_issue: str | None = None


@dataclass(frozen=True, slots=True)
class BriefResult:
    bullets: tuple[str, ...]
    source: str  # 'aihub' | legacy 'gemini' | 'fallback'
    error: str  # '' on success


# Sources that mean "a language model actually wrote this". Anything else is the
# score-ordered fallback, which is a quality incident worth reporting, not a real brief.
LLM_SOURCES: frozenset[str] = frozenset({"aihub", "gemini"})


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


FALLBACK_MAX_CHARS: int = 220


def _truncate_at_boundary(text: str, limit: int = FALLBACK_MAX_CHARS) -> str:
    """Cut `text` to at most `limit` chars at a sentence/word boundary, adding an ellipsis.

    Trước đây cắt cứng `[:220]` nên fallback đứt giữa từ ("...ngân hà"). Ưu tiên ranh giới
    câu nếu nó nằm ở nửa sau, ngược lại lùi về khoảng trắng gần nhất.
    """
    text = text.strip()
    if len(text) <= limit:
        return text
    window = text[: limit - 1]
    cut = max(window.rfind(". "), window.rfind("! "), window.rfind("? "))
    if cut >= limit // 2:
        return window[: cut + 1].rstrip()
    space = window.rfind(" ")
    if space >= limit // 2:
        window = window[:space]
    return window.rstrip(" ,;:—–-") + "…"


def fallback_brief(
    articles: Sequence[Article],
    *,
    limit: int = 5,
    posts: Sequence[Post] = (),
) -> BriefResult:
    """Deterministic brief with no network: top `limit` articles by score.

    Bài X chỉ được dùng để ĐỘN CHO ĐỦ khi bài báo không đủ `limit`, không trộn chung rồi sắp
    lại: hai nguồn chấm điểm theo hai thang khác nhau (xem ghi chú ở `BRIEF_POST_ITEMS`).
    Nhưng một ngày chỉ có bài X mà brief trả rỗng thì trang ngày mất hẳn phần trên cùng —
    tệ hơn hẳn so với năm dòng lấy từ X.
    """
    ordered = sorted(articles, key=lambda article: article.score, reverse=True)
    bullets: list[str] = []
    for article in ordered[:limit]:
        sentence = _first_sentence(article.summary_vi)
        line = f"{article.source or 'Nguồn'} — {sentence or article.title_vi}"
        bullets.append(_truncate_at_boundary(line))
    if len(bullets) < limit and posts:
        ranked = sorted(posts, key=lambda post: post.score, reverse=True)
        for post in ranked[: limit - len(bullets)]:
            sentence = _first_sentence(post.summary)
            line = f"@{post.author or 'X'} — {sentence or post.title}"
            bullets.append(_truncate_at_boundary(line))
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


def _post_items(posts: Sequence[Post], limit: int) -> list[dict[str, object]]:
    """The top-scoring X posts, in the same shape `brief_prompt` reads for articles.

    `source` mang dấu "@" để model phân biệt được đây là bài đăng cá nhân/tổ chức trên X chứ
    không phải một toà soạn — sắc thái đó phải giữ, vì độ tin cậy của hai loại khác nhau.
    """
    selected = sorted(posts, key=lambda post: post.score, reverse=True)[:limit]
    return [
        {
            "title": post.title,
            "source": f"@{post.author}" if post.author else "X",
            "topic": post.topic,
            "impact": post.impact,
            "summary": (post.summary or "")[:300],
        }
        for post in selected
    ]


def generate_brief(
    day: str,
    articles: Sequence[Article],
    *,
    limit: int = BRIEF_ITEMS,
    posts: Sequence[Post] = (),
    post_limit: int = BRIEF_POST_ITEMS,
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
        fb = fallback_brief(articles, limit=BRIEF_BULLETS, posts=posts)
        return BriefResult(fb.bullets, "fallback", "no ai hub")

    result = _brief_via_hub(day, articles, limit=limit, posts=posts, post_limit=post_limit)
    if result is not None:
        return result

    _brief_provider_issue = "AI Hub khong tra duoc brief — da dung ban tu sinh thay the"
    fb = fallback_brief(articles, limit=BRIEF_BULLETS, posts=posts)
    return BriefResult(fb.bullets, "fallback", "ai hub failed")


def _brief_max_tokens() -> int:
    try:
        return max(1024, int(os.environ.get("AI_HUB_BRIEF_MAX_TOKENS", "16000")))
    except ValueError:
        return 16000


def _brief_via_hub(
    day: str,
    articles: Sequence[Article],
    *,
    limit: int,
    posts: Sequence[Post] = (),
    post_limit: int = BRIEF_POST_ITEMS,
) -> BriefResult | None:
    """Goi hub. Tra None (khong phai BriefResult) de caller quyet dinh dung fallback."""
    prompt = brief_prompt(
        day, _brief_items(articles, limit) + _post_items(posts, post_limit)
    )
    try:
        # Deliberately roomy: the model burns budget on a hidden reasoning phase before
        # writing a single character, and a tight ceiling yields empty content that looks
        # like a model failure but is really a budget one (8192 failed with 28-31k reasoning
        # chars on 2026-10-31/11-01). Override with AI_HUB_BRIEF_MAX_TOKENS.
        parsed = ai_hub.chat_json(prompt, max_tokens=_brief_max_tokens(), temperature=0.3)
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

    if any(bullet_output_issue(b) for b in cleaned):
        # Output guard: chữ CJK/Cyrillic hoặc tiếng Việt dính liền từ tiếng Anh. Sinh lại ĐÚNG
        # MỘT lần; nếu vẫn lỗi thì bỏ riêng dòng lỗi thay vì vứt cả brief.
        logger.warning("Brief của %s có dòng lỗi ký tự/dính chữ, sinh lại 1 lần", day)
        try:
            retry = ai_hub.chat_json(prompt, max_tokens=_brief_max_tokens(), temperature=0.3)
            retried = _clean_bullets(retry.get("bullets"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Brief regenerate failed for %s: %s", day, str(exc)[:200])
            retried = []
        if retried and not looks_like_refusal(retried):
            bad_before = sum(1 for b in cleaned if bullet_output_issue(b))
            bad_after = sum(1 for b in retried if bullet_output_issue(b))
            if bad_after <= bad_before:
                cleaned = retried
        kept = [b for b in cleaned if not bullet_output_issue(b)]
        if len(kept) < len(cleaned):
            logger.warning(
                "Brief của %s: bỏ %d dòng lỗi ký tự/dính chữ", day, len(cleaned) - len(kept)
            )
        cleaned = kept
        if not cleaned:
            logger.warning("Brief via AI Hub: mọi dòng đều lỗi ký tự cho %s", day)
            return None

    warn_unsupported_numbers(day, cleaned, articles, posts)
    return BriefResult(tuple(cleaned), "aihub", "")


_CJK_CYRILLIC_RE = re.compile(
    "[Ѐ-ӿ぀-ヿ㐀-䶿一-鿿가-힯＀-￯]"
)
# Một "từ" vừa có ký tự Latin có dấu (tiếng Việt) vừa có chỗ chuyển chữ thường -> HOA
# ("tăngFed") hoặc cụm HOA ASCII (>=2) rồi chữ thường ("FEDtăng") là từ bị dính.
_WORD_RE = re.compile(r"[^\W\d_]+")
_GLUE_RES: tuple[re.Pattern[str], ...] = (
    re.compile(r"[a-zÀ-ɏḀ-ỿ][A-Z]"),
    re.compile(r"[A-Z]{2,}[a-zÀ-ɏḀ-ỿ]"),
)


def _is_latin_diacritic(ch: str) -> bool:
    return ord(ch) > 127 and unicodedata.name(ch, "").startswith("LATIN")


def bullet_output_issue(bullet: str) -> str:
    """Return a short reason if the bullet has CJK/Cyrillic or Vietnamese glued to English."""
    if _CJK_CYRILLIC_RE.search(bullet):
        return "cjk_cyrillic"
    for word in _WORD_RE.findall(bullet):
        if any(_is_latin_diacritic(ch) for ch in word) and any(
            pattern.search(word) for pattern in _GLUE_RES
        ):
            return "glued_words"
    return ""


_NUMBER_RE = re.compile(r"\d[\d.,]*\d|\d")


def _number_forms(text: str) -> set[str]:
    forms: set[str] = set()
    for raw in _NUMBER_RE.findall(text):
        forms.add(raw)
        forms.add(re.sub(r"\D", "", raw))
    return forms


def unsupported_numbers(
    bullets: Sequence[str],
    articles: Sequence[Article],
    posts: Sequence[Post] = (),
) -> list[str]:
    """Numbers in `bullets` that appear in no article/post text of the day."""
    source_text: list[str] = []
    for article in articles:
        source_text.extend(
            [article.title, article.title_vi, article.summary_vi, *article.key_points]
        )
    for post in posts:
        source_text.extend([post.title, post.summary])
    known = _number_forms(" ".join(t for t in source_text if t))
    missing: list[str] = []
    for bullet in bullets:
        for raw in _NUMBER_RE.findall(bullet):
            if raw not in known and re.sub(r"\D", "", raw) not in known and raw not in missing:
                missing.append(raw)
    return missing


def warn_unsupported_numbers(
    day: str,
    bullets: Sequence[str],
    articles: Sequence[Article],
    posts: Sequence[Post] = (),
) -> list[str]:
    """Cheap hallucination check: log (never block) numbers absent from the sources."""
    missing = unsupported_numbers(bullets, articles, posts)
    if missing:
        logger.warning(
            "Brief của %s có số không thấy trong tin nguồn: %s", day, ", ".join(missing)
        )
    return missing


def _clean_bullets(raw: object) -> list[str]:
    """Keep the non-empty strings, trimmed, capped at the bullet count."""
    if not isinstance(raw, list):
        return []
    cleaned: list[str] = []
    for item in raw:
        if isinstance(item, str) and item.strip():
            cleaned.append(item.strip())
    return cleaned[:BRIEF_BULLETS]
