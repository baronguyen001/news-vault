"""Tests for newsvault.score."""

from __future__ import annotations

from newsvault.score import DEFAULT_SOURCE_TIER, SOURCE_TIER, compute_score


def test_source_tier_values() -> None:
    assert SOURCE_TIER["reuters"] == 1.0
    assert SOURCE_TIER["cafef"] == 0.7
    assert SOURCE_TIER["vnexpress"] == 0.85
    assert "unknown_source" not in SOURCE_TIER


def test_default_source_tier() -> None:
    assert DEFAULT_SOURCE_TIER == 0.5


def test_compute_score_golden_cases() -> None:
    assert compute_score(10, "cao", "reuters") == 100
    assert compute_score(0, "", "unknown-source") == 10
    assert compute_score(8, "trung bình", "cafef") == 72
    assert compute_score(99, "cao", "reuters") == 100


def test_compute_score_clamping_and_unknown_impact() -> None:
    assert compute_score(-5, "cao", "reuters") == 50  # negative relevance clamps to 0
    assert compute_score(5, "unknown-impact", "unknown-source") == 35
    assert compute_score(0, "unknown-impact", "unknown-source") == 10
