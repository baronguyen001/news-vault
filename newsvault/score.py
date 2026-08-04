"""Scoring logic for archive article ranking."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

SCORE_WEIGHTS: dict[str, float] = {"relevance": 0.5, "impact": 0.3, "source": 0.2}

IMPACT_WEIGHT: dict[str, float] = {
    "cao": 1.0,
    "trung bình": 0.6,
    "thấp": 0.25,
}

DEFAULT_SOURCE_TIER: float = 0.5

SOURCE_TIER: dict[str, float] = {
    # Tier 1.0: top-tier international/wire sources
    "reuters": 1.0,
    "bloomberg": 1.0,
    "ft": 1.0,
    "economist": 1.0,
    "wsj": 1.0,
    "nytimes": 1.0,
    "nikkei": 1.0,
    "scmp": 1.0,
    "straitstimes": 1.0,
    "wapo": 1.0,
    "marketwatch": 1.0,
    # Tier 0.85: reputable official / regional / major outlets
    "chinhphu": 0.85,
    "sbv": 0.85,
    "quochoi": 0.85,
    "vnexpress": 0.85,
    "tuoitre": 0.85,
    "thanhnien": 0.85,
    "cnbc": 0.85,
    "bbc_business": 0.85,
    "aljazeera": 0.85,
    "channelnewsasia": 0.85,
    "guardian": 0.85,
    "politico": 0.85,
    "technologyreview": 0.85,
    # Tier 0.7: trade / local / tech-vertical outlets
    "cafef": 0.7,
    "vneconomy": 0.7,
    "vietstock": 0.7,
    "baodautu": 0.7,
    "dantri": 0.7,
    "vietnamnet": 0.7,
    "laodong": 0.7,
    "nld": 0.7,
    "techcrunch": 0.7,
    "theverge": 0.7,
    "arstechnica": 0.7,
    "wired": 0.7,
    "venturebeat": 0.7,
    "tienphong": 0.7,
    "baotintuc": 0.7,
    "vtc": 0.7,
    "congthuong": 0.7,
}


def compute_score(relevance: int, impact_level: str, source_key: str) -> int:
    """Weighted 0..100 integer score, rounding half-up and clamped to the valid range."""
    rel = max(0, min(10, relevance))
    impact = IMPACT_WEIGHT.get(impact_level, 0.0)
    source = SOURCE_TIER.get(source_key, DEFAULT_SOURCE_TIER)

    weighted = (
        SCORE_WEIGHTS["relevance"] * (rel / 10)
        + SCORE_WEIGHTS["impact"] * impact
        + SCORE_WEIGHTS["source"] * source
    )

    score = Decimal(str(weighted * 100)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return max(0, min(100, int(score)))
