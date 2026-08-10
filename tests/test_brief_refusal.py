from newsvault.brief import (
    BriefResult,
    _brief_via_hub,
    looks_like_refusal,
)

REAL_BULLETS = [
    "Iran cảnh báo tấn công hạ tầng năng lượng vùng Vịnh nếu Mỹ không nhượng bộ.",
    "Xuất khẩu bền bỉ giúp các nhà máy Trung Quốc tìm đầu ra ngoài thị trường Mỹ.",
    "Đài Loan tăng chi quốc phòng 16% giữa lúc căng thẳng eo biển leo thang.",
    "Sony và TSMC lập liên doanh cảm biến hình ảnh trị giá 6,4 tỷ USD tại Nhật Bản.",
    "Giá dầu hạ nhiệt sau khi thị trường đánh giá lại rủi ro qua eo biển Hormuz.",
]


def test_empty_is_not_refusal():
    assert not looks_like_refusal([])


def test_real_incident_is_refusal():
    bullets = ["Không có mục tin nào được cung cấp để tóm tắt."] * 5
    assert looks_like_refusal(bullets)


def test_real_bullets_are_not_refusal():
    assert not looks_like_refusal(REAL_BULLETS)


def test_repeated_real_bullet_is_refusal():
    assert looks_like_refusal([REAL_BULLETS[0]] * 5)


def test_one_real_bullet_is_not_refusal():
    assert not looks_like_refusal([REAL_BULLETS[0]])


def test_one_refusal_is_below_threshold():
    bullets = ["Không có mục tin nào được cung cấp để tóm tắt."] + REAL_BULLETS[:4]
    assert not looks_like_refusal(bullets)


def test_three_refusals_reach_threshold():
    bullets = ["Không có mục tin nào được cung cấp để tóm tắt."] * 3 + REAL_BULLETS[:2]
    assert looks_like_refusal(bullets)


def test_refusal_matching_is_case_insensitive():
    bullets = ["KHÔNG CÓ MỤC TIN NÀO ĐƯỢC CUNG CẤP."] * 5
    assert looks_like_refusal(bullets)


def test_english_refusal_is_detected():
    assert looks_like_refusal(["No items were provided to summarise."] * 5)


def test_hub_refusal_returns_none(monkeypatch):
    monkeypatch.setattr(
        "newsvault.brief.ai_hub.chat_json",
        lambda *args, **kwargs: {
            "bullets": ["Không có mục tin nào được cung cấp để tóm tắt."] * 5
        },
    )
    assert _brief_via_hub("2026-08-09", [], limit=12) is None


def test_hub_good_brief_returns_aihub_result(monkeypatch):
    monkeypatch.setattr(
        "newsvault.brief.ai_hub.chat_json",
        lambda *args, **kwargs: {"bullets": REAL_BULLETS},
    )
    result = _brief_via_hub("2026-08-10", [], limit=12)
    assert isinstance(result, BriefResult)
    assert result.source == "aihub"
    assert result.bullets == tuple(REAL_BULLETS)
