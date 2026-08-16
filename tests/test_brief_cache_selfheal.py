import json

import pytest

from newsvault.brief import BriefResult
from newsvault.build import BuildOptions, _brief_fingerprint, _brief_for
from tests.test_brief import _article

GOOD_BULLETS = (
    "Iran cảnh báo tấn công hạ tầng năng lượng vùng Vịnh nếu Mỹ không nhượng bộ.",
    "Xuất khẩu bền bỉ giúp các nhà máy Trung Quốc tìm đầu ra ngoài thị trường Mỹ.",
)

LATER_BULLETS = ("Bản tóm tắt mới, viết sau khi ngày có thêm tin.",)


def make_options(tmp_path):
    return BuildOptions(
        db_path=tmp_path / "khong-dung.db",
        out_dir=tmp_path / "docs",
        password="test",
        cache_dir=tmp_path / ".cache",
        use_brief=True,
    )


def write_cache(options, day, bullets, source="aihub", fingerprint=None):
    cache = options.cache_dir / "brief"
    cache.mkdir(parents=True, exist_ok=True)
    payload = {"bullets": list(bullets), "source": source}
    if fingerprint is not None:
        payload["fp"] = fingerprint
    (cache / f"{day}.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )


def read_cache(options, day):
    return json.loads(
        (options.cache_dir / "brief" / f"{day}.json").read_text(encoding="utf-8")
    )


def test_refusal_cache_is_replaced(tmp_path, monkeypatch):
    options = make_options(tmp_path)
    day = "2026-08-09"
    write_cache(options, day, ["Không có mục tin nào được cung cấp."] * 5)

    monkeypatch.setattr(
        "newsvault.build.generate_brief",
        lambda *args, **kwargs: BriefResult(GOOD_BULLETS, "aihub", ""),
    )

    result = _brief_for(day, [], options)
    assert result.bullets == GOOD_BULLETS

    stored = json.loads(
        (options.cache_dir / "brief" / f"{day}.json").read_text(encoding="utf-8")
    )
    assert tuple(stored["bullets"]) == GOOD_BULLETS


def test_good_cache_is_reused(tmp_path, monkeypatch):
    options = make_options(tmp_path)
    day = "2026-08-10"
    write_cache(options, day, GOOD_BULLETS)

    monkeypatch.setattr(
        "newsvault.build.generate_brief",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("không được gọi")),
    )

    result = _brief_for(day, [], options)
    assert result.bullets == GOOD_BULLETS


def test_refusal_result_is_not_cached(tmp_path, monkeypatch):
    options = make_options(tmp_path)
    day = "2026-08-11"

    monkeypatch.setattr(
        "newsvault.build.generate_brief",
        lambda *args, **kwargs: BriefResult(
            ("Không có mục tin nào được cung cấp.",) * 5,
            "aihub",
            "",
        ),
    )

    _brief_for(day, [], options)
    assert not (options.cache_dir / "brief" / f"{day}.json").exists()


# ---------------------------------------------------------------- vân tay nội dung
#
# Sự cố thật, đo trên máy ngày 16/08/2026: một ngày được dựng BA lần (14:00 · 17:26 · 21:15)
# nhưng cache brief chỉ khoá theo NGÀY. Lần dựng 14:00 ghi cache, hai lần sau đọc lại y
# nguyên — trong khi job retry 19:00 của news-hunter và hai khe chiều/tối của x-pulse vẫn
# đang đổ tin vào đúng ngày đó. Kết quả: bài của ngày 14/08 về thêm lúc 17h và 19h chưa bao
# giờ được tóm tắt, và bài X ngày 15/08 tăng 100 → 114 mà "Tóm tắt ngày" không đổi một chữ.


def test_them_bai_trong_ngay_thi_brief_duoc_sinh_lai(tmp_path, monkeypatch):
    """Cùng một ngày, nhiều tin hơn ⇒ phải viết lại brief chứ không đọc lại cache."""
    options = make_options(tmp_path)
    day = "2026-08-15"
    first = [_article(id=1)]
    write_cache(options, day, GOOD_BULLETS, fingerprint=_brief_fingerprint(first, []))

    monkeypatch.setattr(
        "newsvault.build.generate_brief",
        lambda *args, **kwargs: BriefResult(LATER_BULLETS, "aihub", ""),
    )

    result = _brief_for(day, [*first, _article(id=2)], options)

    assert result.bullets == LATER_BULLETS
    assert read_cache(options, day)["bullets"] == list(LATER_BULLETS)


def test_them_bai_X_trong_ngay_cung_lam_brief_sinh_lai(tmp_path, monkeypatch, post_factory):
    """Bài X cũng là tin mới của ngày — x-pulse đổ vào ba khe mỗi ngày."""
    options = make_options(tmp_path)
    day = "2026-08-15"
    articles = [_article(id=1)]
    write_cache(options, day, GOOD_BULLETS, fingerprint=_brief_fingerprint(articles, []))

    monkeypatch.setattr(
        "newsvault.build.generate_brief",
        lambda *args, **kwargs: BriefResult(LATER_BULLETS, "aihub", ""),
    )

    result = _brief_for(day, articles, options, posts=[post_factory("p1")])

    assert result.bullets == LATER_BULLETS


def test_ngay_khong_doi_thi_khong_goi_lai_LLM(tmp_path, monkeypatch):
    """Vân tay khớp ⇒ dựng lại vẫn miễn phí. Đây là lý do cache tồn tại, đừng phá."""
    options = make_options(tmp_path)
    day = "2026-08-15"
    articles = [_article(id=1), _article(id=2)]
    write_cache(options, day, GOOD_BULLETS, fingerprint=_brief_fingerprint(articles, []))

    monkeypatch.setattr(
        "newsvault.build.generate_brief",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("không được gọi")),
    )

    assert _brief_for(day, articles, options).bullets == GOOD_BULLETS


def test_cache_cu_khong_co_van_tay_thi_NHAN_NUOI_chu_khong_sinh_lai(tmp_path, monkeypatch):
    """File từ thời chưa có vân tay: giữ nguyên nội dung, chỉ đóng dấu vân tay.

    Job đêm chạy `--backfill` nên `_brief_for` được gọi cho cả kho (129 ngày ở thời điểm
    viết). Coi mọi file cũ là hỏng sẽ nổ ra 129 lượt gọi LLM ngay lần dựng kế tiếp — đủ để
    build trượt sang cửa sổ của lần chạy sau.
    """
    options = make_options(tmp_path)
    day = "2026-08-10"
    write_cache(options, day, GOOD_BULLETS)  # không có khoá "fp"
    articles = [_article(id=1)]

    monkeypatch.setattr(
        "newsvault.build.generate_brief",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("không được gọi")),
    )

    result = _brief_for(day, articles, options)

    assert result.bullets == GOOD_BULLETS
    assert read_cache(options, day)["fp"] == _brief_fingerprint(articles, [])


def test_van_tay_bo_qua_thu_tu_va_bat_moi_thay_doi() -> None:
    a1, a2 = _article(id=1), _article(id=2)
    assert _brief_fingerprint([a1, a2], []) == _brief_fingerprint([a2, a1], [])
    assert _brief_fingerprint([a1], []) != _brief_fingerprint([a1, a2], [])


@pytest.fixture
def post_factory():
    from newsvault.posts import Post

    def make(post_id: str) -> Post:
        return Post(
            id=post_id,
            url=f"https://x.com/someone/status/{post_id}",
            author="someone",
            author_name="Some One",
            author_tier=1.0,
            title="Tiêu đề bài X",
            summary="Tóm tắt bài X.",
            blocks=(),
            points=(),
            insight="",
            day="2026-08-15",
            processed_at="2026-08-15T10:00:00+07:00",
            published_iso="2026-08-15T09:00:00+07:00",
            vertical="kinh-te",
            topic="Kinh tế/Tài chính",
            impact="trung bình",
            relevance=8,
            score=70,
        )

    return make
