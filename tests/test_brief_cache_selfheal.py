import json

from newsvault.brief import BriefResult
from newsvault.build import BuildOptions, _brief_for

GOOD_BULLETS = (
    "Iran cảnh báo tấn công hạ tầng năng lượng vùng Vịnh nếu Mỹ không nhượng bộ.",
    "Xuất khẩu bền bỉ giúp các nhà máy Trung Quốc tìm đầu ra ngoài thị trường Mỹ.",
)


def make_options(tmp_path):
    return BuildOptions(
        db_path=tmp_path / "khong-dung.db",
        out_dir=tmp_path / "docs",
        password="test",
        cache_dir=tmp_path / ".cache",
        use_brief=True,
        api_key="khoa-gia",
    )


def write_cache(options, day, bullets, source="aihub"):
    cache = options.cache_dir / "brief"
    cache.mkdir(parents=True)
    (cache / f"{day}.json").write_text(
        json.dumps({"bullets": list(bullets), "source": source}, ensure_ascii=False),
        encoding="utf-8",
    )


def test_refusal_cache_is_replaced(tmp_path, monkeypatch):
    options = make_options(tmp_path)
    day = "2026-08-09"
    write_cache(options, day, ["Không có mục tin nào được cung cấp."] * 5)

    monkeypatch.setattr(
        "newsvault.build.generate_brief",
        lambda *args, **kwargs: BriefResult(GOOD_BULLETS, "gemini", ""),
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
