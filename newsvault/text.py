"""Shared text helpers used by every news-vault module."""

from __future__ import annotations

import re
import unicodedata

# Folded stopwords. CAREFUL: folding strips Vietnamese diacritics, so a stopword here also
# removes every homograph that folds to the same string. That is why obvious-looking function
# words are absent: "lại" would delete "lãi" (interest), "nhất" would delete "Nhật" (Japan),
# "đầu"/"tư" would delete "đầu tư" (investment), "đang" would delete "Đảng", "chính" would delete
# "chính sách", "giá", "cao", "nền", "dầu", "tài", "văn", "chi", "cần" are all live news terms.
# Only add a word here when no meaningful term folds to it.
_VI_STOPWORDS: set[str] = {
    # Vietnamese function words with no common homograph
    "va",
    "cua",
    "cho",
    "voi",
    "trong",
    "tren",
    "duoi",
    "khi",
    "se",
    "khong",
    "nhung",
    "cac",
    "nhieu",
    "nay",
    "kia",
    "theo",
    "truoc",
    "boi",
    "neu",
    "hoac",
    "cung",
    "nguoi",
    "viec",
    "duoc",
    "phai",
    "hon",
    "rat",
    "tuy",
    "nhu",
    "roi",
    "nua",
    "ma",
    "them",
    "tung",
    "moi-nguoi",
    "khac",
    "cho-nen",
    "vay",
    "the-nen",
    "ngoai",
    "giua",
    "cho-den",
    "khoang",
    "gan",
    "day",
    "hom",
    "trong-khi",
    "boi-vi",
    "tuy-nhien",
    "ben",
    "cho-biet",
    "duoc-biet",
    "hien",
    "nham",
    "nhu-vay",
    "sau-khi",
    "truoc-khi",
    "cho-thay",
    "dong-thoi",
    "ngay-cang",
    "tro-thanh",
    # English stopwords (international headlines)
    "the",
    "and",
    "for",
    "with",
    "from",
    "that",
    "this",
    "these",
    "those",
    "are",
    "was",
    "were",
    "has",
    "have",
    "had",
    "been",
    "being",
    "will",
    "would",
    "should",
    "could",
    "its",
    "it",
    "on",
    "in",
    "at",
    "to",
    "of",
    "by",
    "an",
    "as",
    "is",
    "be",
    "or",
    "but",
    "not",
    "you",
    "your",
    "we",
    "our",
    "they",
    "their",
    "he",
    "she",
    "his",
    "her",
    "who",
    "what",
    "when",
    "where",
    "which",
    "why",
    "how",
    "all",
    "any",
    "more",
    "most",
    "other",
    "some",
    "such",
    "than",
    "then",
    "there",
    "into",
    "over",
    "after",
    "before",
    "about",
    "up",
    "out",
    "off",
    "also",
    "new",
    "says",
    "said",
}

VI_STOPWORDS: frozenset[str] = frozenset(_VI_STOPWORDS)
"""Folded Vietnamese + English stopwords used by :func:`tokens`."""


def fold(value: str) -> str:
    """Lowercase, strip Vietnamese diacritics (đ -> d), collapse whitespace."""
    value = value.strip().lower()
    value = unicodedata.normalize("NFD", value)
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
    value = value.replace("đ", "d").replace("Đ", "d")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def tokens(value: str) -> set[str]:
    """fold(), split on non-alphanumeric, drop VI_STOPWORDS and tokens shorter than 2 chars."""
    folded = fold(value)
    candidates = re.findall(r"[a-z0-9]+", folded)
    return {token for token in candidates if len(token) >= 2 and token not in VI_STOPWORDS}


def slugify(value: str) -> str:
    """fold(), non-alphanumeric runs -> '-', strip leading/trailing '-'. Never returns ''; use 'x' as fallback."""
    folded = fold(value)
    slug = re.sub(r"[^a-z0-9]+", "-", folded).strip("-")
    return slug if slug else "x"


def excerpt(value: str, limit: int = 400) -> str:
    """Collapse whitespace and cut on a word boundary, appending '…' when truncated."""
    value = re.sub(r"\s+", " ", value.strip())
    if len(value) <= limit:
        return value
    cut = value.rfind(" ", 0, limit + 1)
    if cut <= 0:
        cut = limit
    return value[:cut].rstrip() + "…"
