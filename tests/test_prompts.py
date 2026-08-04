from __future__ import annotations

from newsvault.prompts import (
    HOUSE_STYLE,
    NEGATIVE_STYLE,
    brief_prompt,
    cover_prompt,
)


def test_house_style_mentions_palette_and_no_text() -> None:
    assert "deep indigo" in HOUSE_STYLE
    assert "warm amber" in HOUSE_STYLE
    assert "muted teal" in HOUSE_STYLE
    assert "no text" in HOUSE_STYLE.lower()
    assert "no letters" in HOUSE_STYLE.lower()
    assert "no flags" in HOUSE_STYLE.lower()


def test_negative_style_contains_prohibitions() -> None:
    assert "text" in NEGATIVE_STYLE
    assert "flags" in NEGATIVE_STYLE
    assert "faces" in NEGATIVE_STYLE


def test_cover_prompt_is_deterministic() -> None:
    headlines = ["Headline one", "Headline two", "Headline three"]
    topics = ["Kinh tế/Tài chính", "Công nghệ/AI"]
    first = cover_prompt("2026-08-04", headlines, top_topics=topics)
    second = cover_prompt("2026-08-04", headlines, top_topics=topics)
    assert first == second
    assert first != cover_prompt("2026-08-04", headlines, top_topics=["Khác"])


def test_cover_prompt_truncates_long_headline() -> None:
    long_headline = "word " * 200
    prompt = cover_prompt("2026-08-04", [long_headline], top_topics=["Kinh tế/Tài chính"])
    assert isinstance(prompt, str)
    assert len(prompt) < len(long_headline) + len(HOUSE_STYLE)
    assert long_headline[:300] not in prompt


def test_brief_prompt_contains_day_and_vietnamese() -> None:
    day = "2026-08-04"
    prompt = brief_prompt(day, [])
    assert day in prompt
    assert "tiếng Việt" in prompt
    assert "No emoji" in prompt
