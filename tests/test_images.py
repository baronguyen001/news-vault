from __future__ import annotations

from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import requests
from PIL import Image

from newsvault.images import (
    CATEGORY_SIZE,
    COVER_SIZE,
    ImageRequest,
    generate_images,
    plan_images,
    prompt_hash,
    to_webp,
)
from newsvault.model import Article
from newsvault.text import slugify


def _article(**kwargs: object) -> Article:
    defaults = {
        "id": 1,
        "url": "https://example.com/1",
        "source": "VnExpress",
        "source_key": "vnexpress",
        "region": "domestic",
        "title": "Original title",
        "title_vi": "Tiêu đề",
        "published_at": "Wed, 29 Jul 2026 12:00:36 +0700",
        "published_iso": "2026-07-29T12:00:36+07:00",
        "day": "2026-07-29",
        "fetched_at": "2026-07-29T06:09:27.518450+00:00",
        "category": "Kinh tế & Tài chính",
        "topic": "Kinh tế/Tài chính",
        "summary_vi": "Tóm tắt.",
        "key_points": (),
        "tags": (),
        "analysis": {},
        "impact_level": "cao",
        "is_law_policy": False,
        "relevance": 8,
        "score": 80,
    }
    defaults.update(kwargs)
    return Article(**defaults)


def test_plan_images_none_is_empty() -> None:
    assert plan_images("2026-08-04", [_article()], mode="none") == []


def test_plan_images_cover_only() -> None:
    requests = plan_images("2026-08-04", [_article()], mode="cover")
    assert len(requests) == 1
    assert requests[0].key == "cover"
    assert requests[0].size == COVER_SIZE


def test_plan_images_all_includes_top_categories() -> None:
    """The cover plus the `max_categories` busiest topics, ranked by article count."""
    articles = (
        [_article(id=i, topic="Kinh tế/Tài chính") for i in range(1, 6)]
        + [_article(id=i, topic="Công nghệ/AI") for i in range(6, 10)]
        + [_article(id=i, topic="Chính trị/Chính sách") for i in range(10, 13)]
        + [_article(id=i, topic="Pháp luật/Nghị định") for i in range(13, 15)]
        + [_article(id=15, topic="Văn hóa/Xã hội")]
    )
    requests = plan_images("2026-08-04", articles, mode="all", max_categories=4)

    assert len(requests) == 5
    assert requests[0].key == "cover"
    keys = [r.key for r in requests[1:]]
    assert keys == [
        slugify("Kinh tế/Tài chính"),
        slugify("Công nghệ/AI"),
        slugify("Chính trị/Chính sách"),
        slugify("Pháp luật/Nghị định"),
    ]
    # The quietest topic falls outside max_categories and gets no illustration.
    assert slugify("Văn hóa/Xã hội") not in keys


def test_prompt_hash_is_stable_and_size_sensitive() -> None:
    prompt = "a stable prompt"
    assert prompt_hash(prompt, COVER_SIZE) == prompt_hash(prompt, COVER_SIZE)
    assert prompt_hash(prompt, COVER_SIZE) != prompt_hash(prompt, CATEGORY_SIZE)


def test_to_webp_writes_exact_dimensions(tmp_path: Path) -> None:
    buf = BytesIO()
    Image.new("RGB", (100, 80), color=(255, 0, 0)).save(buf, format="PNG")
    destination = tmp_path / "out.webp"
    to_webp(buf.getvalue(), (80, 40), destination)
    assert destination.exists()
    with Image.open(destination) as img:
        assert img.size == (80, 40)
        assert img.mode == "RGB"


def test_cache_hit_avoids_network(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    cache_dir = tmp_path / "cache"
    out_dir.mkdir()
    cache_dir.mkdir()
    request = ImageRequest(key="cover", label="Cover", prompt="cache test prompt", size=COVER_SIZE)
    cache_path = cache_dir / f"{prompt_hash(request.prompt, request.size)}.webp"
    Image.new("RGB", COVER_SIZE, color=(0, 0, 255)).save(cache_path, "WEBP")

    with patch("newsvault.images.requests.post") as mock_post:
        results = generate_images([request], out_dir, api_key="secret", cache_dir=cache_dir)

    assert mock_post.called is False
    assert len(results) == 1
    assert results[0].cached is True
    assert results[0].path == out_dir / "cover.webp"
    assert (out_dir / "cover.webp").exists()


def test_max_calls_zero_returns_budget(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    cache_dir = tmp_path / "cache"
    request = ImageRequest(key="cover", label="Cover", prompt="budget prompt", size=COVER_SIZE)
    with patch("newsvault.images.requests.post") as mock_post:
        results = generate_images(
            [request], out_dir, api_key="secret", cache_dir=cache_dir, max_calls=0
        )
    assert all(result.error == "budget" for result in results)
    assert all(result.path is None for result in results)
    assert mock_post.called is False


def test_network_failure_does_not_raise(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    cache_dir = tmp_path / "cache"
    request = ImageRequest(key="cover", label="Cover", prompt="failure prompt", size=COVER_SIZE)
    with patch("newsvault.images.requests.post", side_effect=requests.RequestException("boom")):
        results = generate_images([request], out_dir, api_key="secret", cache_dir=cache_dir)
    assert len(results) == 1
    assert results[0].path is None
    assert results[0].error
