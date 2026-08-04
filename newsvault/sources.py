"""Which sources cost a subscription, and which are free.

news-hunter marks a source `paywall: True` in its own SOURCES config when reading it
needs a paid account, and fetches those through an authenticated browser session. That
flag is a property of the *source*, not of the article, so it never lands in a database
column -- which is why the set is mirrored here rather than read from a row.

Keeping a copy is deliberate. Importing `news_hunter.config` would couple this repo to a
private one that is not installed alongside it, and the list changes roughly once a year.
When a subscription starts or lapses, edit `PAID_SOURCE_KEYS`; nothing else needs to move.
"""

from __future__ import annotations

PAID = "paid"
FREE = "free"

# Mirrors `key for key, cfg in news_hunter.config.SOURCES.items() if cfg["paywall"]`.
PAID_SOURCE_KEYS: frozenset[str] = frozenset(
    {
        "bloomberg",
        "economist",
        "ft",
        "investing",
        "marketwatch",
        "nikkei",
        "nytimes",
        "reuters",
        "scmp",
        "straitstimes",
        "techinasia",
        "wapo",
        "wsj",
    }
)

TIER_LABEL: dict[str, str] = {PAID: "Trả phí", FREE: "Miễn phí"}


def tier(source_key: str) -> str:
    """Return 'paid' or 'free' for a source key; unknown keys count as free."""
    return PAID if (source_key or "").strip().lower() in PAID_SOURCE_KEYS else FREE


def is_paid(source_key: str) -> bool:
    """True when the source needs a paid subscription."""
    return tier(source_key) == PAID
