from newsvault.publish_quality import publishable_text


def test_rejects_empty_too_short_and_chinese_output():
    assert not publishable_text("")
    assert not publishable_text("Tóm tắt ngắn.")
    assert not publishable_text("作者称赞Gehihi 3.8 Flash版本非常好用，尽管有人批评它。" * 3)


def test_accepts_a_useful_vietnamese_summary():
    assert publishable_text(
        "Tác giả phân tích thay đổi mới, nêu bối cảnh, tác động với người dùng và các bước cần theo dõi tiếp theo."
    )
