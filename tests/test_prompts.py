from __future__ import annotations

from newsvault.prompts import brief_prompt


def test_brief_prompt_contains_day_and_vietnamese() -> None:
    day = "2026-08-04"
    prompt = brief_prompt(day, [])
    assert day in prompt
    assert "tiếng Việt" in prompt
    assert "No emoji" in prompt


def test_brief_prompt_lists_every_item_with_its_fields() -> None:
    items = [
        {
            "title": "Fed giữ nguyên lãi suất",
            "source": "Reuters",
            "topic": "Kinh tế/Tài chính",
            "impact": "cao",
            "summary": "Uỷ ban thị trường mở giữ lãi suất điều hành.",
        },
        {"title": "Giá dầu tăng", "source": "Bloomberg", "topic": "", "impact": "", "summary": ""},
    ]
    prompt = brief_prompt("2026-08-04", items)

    for item in items:
        assert item["title"] in prompt
        assert item["source"] in prompt
    assert "1. title:" in prompt
    assert "2. title:" in prompt


def test_brief_prompt_truncates_a_long_summary() -> None:
    summary = "x" * 900
    prompt = brief_prompt("2026-08-04", [{"title": "t", "summary": summary}])
    assert summary not in prompt
    assert "x" * 300 in prompt


def test_module_no_longer_exposes_image_prompts() -> None:
    """The image pipeline is gone; day pages use fixed category icons instead.

    Asserting the absence keeps a later edit from quietly reintroducing a code path that
    sends this archive's headlines to a third-party image endpoint.
    """
    import newsvault.prompts as prompts

    for removed in ("HOUSE_STYLE", "NEGATIVE_STYLE", "cover_prompt", "category_prompt"):
        assert not hasattr(prompts, removed), removed
