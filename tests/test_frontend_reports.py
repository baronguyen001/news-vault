"""Lightweight contracts for the shipped report and Facebook renderers."""

from __future__ import annotations

from pathlib import Path
from subprocess import run

ASSETS = Path(__file__).resolve().parents[1] / "newsvault" / "assets"


def _source(name: str) -> str:
    return (ASSETS / name).read_text(encoding="utf-8")


def test_report_and_facebook_scripts_are_valid_javascript() -> None:
    for name in ("reports.js", "facebook.js"):
        checked = run(["node", "--check", str(ASSETS / name)], capture_output=True, text=True)
        assert checked.returncode == 0, checked.stderr


def test_report_cards_share_one_component_with_placeholder_and_stable_sorts() -> None:
    reports = _source("reports.js")
    styles = _source("styles.css")

    assert "function reportCard(item)" in reports
    assert "articleCard" not in reports
    assert "videos.thumb(lead, report.img" in reports
    assert "report-card__summary" in reports
    assert "received-newest" in reports
    assert "published-newest" in reports
    assert 'compareTime(a, b, "fi", -1)' in reports
    assert ".report-card__summary" in styles
    assert "-webkit-line-clamp: 2" in styles
    assert '[data-layout="grid"] .report-card' in styles
    assert ".reports__day-list .card__lead" in styles
    assert ".reports__day-list .card__lead .card__thumb" in styles


def test_facebook_cards_keep_a_visible_two_line_preview() -> None:
    facebook = _source("facebook.js")
    styles = _source("styles.css")

    assert 'make("div", "fpost__preview", lead)' in facebook
    assert "content.hidden = true" in facebook
    assert ".fpost__preview" in styles
