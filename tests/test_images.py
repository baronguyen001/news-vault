from __future__ import annotations

import base64
import io
from pathlib import Path

import pytest
from PIL import Image

from newsvault.images import (
    AIHUB_TIMEOUT,
    CATEGORY_SIZE,
    COVER_SIZE,
    DEFAULT_PROVIDER,
    PROVIDER_AIHUB,
    PROVIDER_GEMINI,
    ImageRequest,
    ProviderConfig,
    generate_images,
    generate_one,
    plan_images,
    prompt_hash,
    to_webp,
)
from newsvault.model import Article


class DummyResponse:
    def __init__(
        self, status_code: int, payload: object | None = None, content: bytes = b""
    ) -> None:
        self.status_code = status_code
        self._payload = payload
        self.content = content

    def json(self) -> object:
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


def make_png_bytes(size: tuple[int, int] = (4, 4), color: str = "red") -> bytes:
    image = Image.new("RGB", size, color=color)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def make_article(article_id: int, *, title: str, topic: str, relevance: int = 5) -> Article:
    return Article(
        id=article_id,
        url=f"https://example.com/{article_id}",
        source="Source",
        source_key="source",
        region="domestic",
        title=title,
        title_vi=title,
        published_at="Wed, 29 Jul 2026 12:00:36 +0700",
        published_iso="2026-07-29T12:00:36+07:00",
        day="2026-07-29",
        fetched_at="2026-07-29T06:09:27.518450+00:00",
        category="Cat",
        topic=topic,
        summary_vi="Summary",
        key_points=(),
        tags=(),
        analysis={},
        impact_level="cao",
        is_law_policy=False,
        relevance=relevance,
        score=80,
    )


def test_provider_config_from_env_reads_all_values() -> None:
    env = {
        "AI_HUB_KEY": "hub-key",
        "AI_HUB_BASE_URL": "https://hub.example/v1",
        "NEWSVAULT_IMAGE_PROVIDER": "gemini",
        "NEWSVAULT_AIHUB_IMAGE_MODEL": "mk1-image",
        "GEMINI_API_KEY": "gem-key",
        "NEWSVAULT_IMAGE_MODEL": "gemini-image",
        "NEWSVAULT_IMAGE_FALLBACK": "false",
    }

    config = ProviderConfig.from_env(env)

    assert config.provider == PROVIDER_GEMINI
    assert config.aihub_key == "hub-key"
    assert config.aihub_base_url == "https://hub.example/v1"
    assert config.aihub_model == "mk1-image"
    assert config.gemini_key == "gem-key"
    assert config.gemini_model == "gemini-image"
    assert config.fallback is False
    assert config.available() == (PROVIDER_GEMINI, PROVIDER_AIHUB)


def test_provider_config_defaults_to_aihub() -> None:
    config = ProviderConfig.from_env({})

    assert config.provider == DEFAULT_PROVIDER
    assert config.available() == ()


def test_generate_one_aihub_returns_b64_image(monkeypatch: pytest.MonkeyPatch) -> None:
    png = make_png_bytes()
    encoded = base64.b64encode(png).decode("ascii")
    seen: dict[str, object] = {}

    def fake_post(
        url: str, *, headers: dict[str, str], json: dict[str, object], timeout: int
    ) -> DummyResponse:
        seen["url"] = url
        seen["headers"] = headers
        seen["json"] = json
        seen["timeout"] = timeout
        return DummyResponse(200, {"data": [{"b64_json": encoded}]})

    monkeypatch.setattr("newsvault.images.requests.post", fake_post)

    config = ProviderConfig(provider=PROVIDER_AIHUB, aihub_key="hub-key", gemini_key=None)
    raw, provider, error = generate_one("prompt", COVER_SIZE, config, timeout=120)

    assert raw == png
    assert provider == PROVIDER_AIHUB
    assert error == ""
    assert seen["url"] == "https://ai-hub.mk1technology.net/v1/images/generations"
    assert seen["timeout"] == AIHUB_TIMEOUT


def test_generate_one_aihub_provider_not_supported_falls_back_to_gemini(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    png = make_png_bytes(color="blue")
    encoded = base64.b64encode(png).decode("ascii")
    calls = {"gemini": 0}

    def fake_post(
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json: dict[str, object] | None = None,
        timeout: int,
        params: dict[str, str] | None = None,
    ) -> DummyResponse:
        if url.endswith("/images/generations"):
            return DummyResponse(
                200,
                {"error": {"message": "Provider 'ollama' does not support image generation"}},
            )
        calls["gemini"] += 1
        assert params == {"key": "gem-key"}
        return DummyResponse(
            200,
            {
                "candidates": [
                    {"content": {"parts": [{"text": "note"}, {"inlineData": {"data": encoded}}]}}
                ]
            },
        )

    monkeypatch.setattr("newsvault.images.requests.post", fake_post)

    config = ProviderConfig(provider=PROVIDER_AIHUB, aihub_key="hub-key", gemini_key="gem-key")
    raw, provider, error = generate_one("prompt", COVER_SIZE, config, timeout=120)

    assert raw == png
    assert provider == PROVIDER_GEMINI
    assert error == ""
    assert calls["gemini"] == 1


def test_generate_one_aihub_429_falls_back_to_gemini(monkeypatch: pytest.MonkeyPatch) -> None:
    png = make_png_bytes(color="green")
    encoded = base64.b64encode(png).decode("ascii")

    def fake_post(
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json: dict[str, object] | None = None,
        timeout: int,
        params: dict[str, str] | None = None,
    ) -> DummyResponse:
        if url.endswith("/images/generations"):
            return DummyResponse(429, {"error": {"message": "rate limited (reset after 1m 6s)"}})
        return DummyResponse(
            200,
            {
                "candidates": [
                    {"content": {"parts": [{"text": "note"}, {"inlineData": {"data": encoded}}]}}
                ]
            },
        )

    monkeypatch.setattr("newsvault.images.requests.post", fake_post)

    config = ProviderConfig(provider=PROVIDER_AIHUB, aihub_key="hub-key", gemini_key="gem-key")
    raw, provider, error = generate_one("prompt", COVER_SIZE, config, timeout=120)

    assert raw == png
    assert provider == PROVIDER_GEMINI
    assert error == ""


def test_generate_one_without_fallback_returns_aihub_error(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"gemini": 0}

    def fake_post(
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json: dict[str, object] | None = None,
        timeout: int,
        params: dict[str, str] | None = None,
    ) -> DummyResponse:
        if url.endswith("/images/generations"):
            return DummyResponse(401, {"error": "API key required for remote API access"})
        calls["gemini"] += 1
        return DummyResponse(500, {"error": {"message": "should not happen"}})

    monkeypatch.setattr("newsvault.images.requests.post", fake_post)

    config = ProviderConfig(
        provider=PROVIDER_AIHUB, aihub_key="hub-key", gemini_key="gem-key", fallback=False
    )
    raw, provider, error = generate_one("prompt", COVER_SIZE, config, timeout=120)

    assert raw is None
    assert provider == PROVIDER_AIHUB
    assert "API key required" in error
    assert calls["gemini"] == 0


def test_generate_one_uses_gemini_when_only_gemini_key_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    png = make_png_bytes(color="yellow")
    encoded = base64.b64encode(png).decode("ascii")
    calls = {"aihub": 0, "gemini": 0}

    def fake_post(
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json: dict[str, object] | None = None,
        timeout: int,
        params: dict[str, str] | None = None,
    ) -> DummyResponse:
        if url.endswith("/images/generations"):
            calls["aihub"] += 1
        else:
            calls["gemini"] += 1
        return DummyResponse(
            200,
            {
                "candidates": [
                    {"content": {"parts": [{"text": "note"}, {"inlineData": {"data": encoded}}]}}
                ]
            },
        )

    monkeypatch.setattr("newsvault.images.requests.post", fake_post)

    config = ProviderConfig(aihub_key=None, gemini_key="gem-key")
    raw, provider, error = generate_one("prompt", COVER_SIZE, config, timeout=120)

    assert raw == png
    assert provider == PROVIDER_GEMINI
    assert error == ""
    assert calls["aihub"] == 0
    assert calls["gemini"] == 1


def test_generate_images_cache_hit_skips_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = ImageRequest(key="cover", label="Cover", prompt="prompt", size=COVER_SIZE)
    cache_dir = tmp_path / "cache"
    out_dir = tmp_path / "out"
    cache_dir.mkdir()
    out_dir.mkdir()

    cached = cache_dir / f"{prompt_hash(request.prompt, request.size)}.webp"
    cached.write_bytes(b"cached-image")

    def fail_post(*args: object, **kwargs: object) -> DummyResponse:
        raise AssertionError("network should not be called")

    def fail_get(*args: object, **kwargs: object) -> DummyResponse:
        raise AssertionError("network should not be called")

    monkeypatch.setattr("newsvault.images.requests.post", fail_post)
    monkeypatch.setattr("newsvault.images.requests.get", fail_get)

    results = generate_images(
        [request],
        out_dir,
        api_key=None,
        cache_dir=cache_dir,
        config=ProviderConfig(provider=PROVIDER_AIHUB, aihub_key="hub-key", gemini_key="gem-key"),
    )

    assert len(results) == 1
    assert results[0].cached is True
    assert results[0].error == ""
    assert results[0].path == out_dir / "cover.webp"
    assert (out_dir / "cover.webp").read_bytes() == b"cached-image"


def test_generate_images_max_calls_zero_yields_budget(tmp_path: Path) -> None:
    requests_ = [
        ImageRequest(key="cover", label="Cover", prompt="p1", size=COVER_SIZE),
        ImageRequest(key="tech", label="Tech", prompt="p2", size=CATEGORY_SIZE),
    ]

    results = generate_images(
        requests_,
        tmp_path / "out",
        api_key=None,
        cache_dir=tmp_path / "cache",
        max_calls=0,
        config=ProviderConfig(provider=PROVIDER_AIHUB, aihub_key="hub-key", gemini_key="gem-key"),
    )

    assert [result.error for result in results] == ["budget", "budget"]


def test_keys_do_not_appear_in_logs_or_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    sentinel = "SENTINEL_KEY_9f3a"

    def fake_post(
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json: dict[str, object] | None = None,
        timeout: int,
        params: dict[str, str] | None = None,
    ) -> DummyResponse:
        if url.endswith("/images/generations"):
            return DummyResponse(401, {"error": "API key required for remote API access"})
        return DummyResponse(401, {"error": {"message": "permission denied"}})

    monkeypatch.setattr("newsvault.images.requests.post", fake_post)

    request = ImageRequest(key="cover", label="Cover", prompt="prompt", size=COVER_SIZE)
    results = generate_images(
        [request],
        tmp_path / "out",
        api_key=None,
        cache_dir=tmp_path / "cache",
        config=ProviderConfig(
            provider=PROVIDER_AIHUB, aihub_key=sentinel, gemini_key=sentinel, fallback=False
        ),
    )

    errors = " ".join(result.error for result in results)
    logs = " ".join(record.getMessage() for record in caplog.records)

    assert sentinel not in errors
    assert sentinel not in logs


def test_to_webp_writes_requested_dimensions(tmp_path: Path) -> None:
    raw = make_png_bytes(size=(4, 4))
    destination = tmp_path / "image.webp"

    to_webp(raw, (120, 63), destination)

    assert destination.exists()
    with Image.open(destination) as image:
        assert image.size == (120, 63)


def test_plan_images_cover_first_and_group_by_topic() -> None:
    articles = [
        make_article(1, title="Economy 1", topic="Kinh tế/Tài chính"),
        make_article(2, title="Economy 2", topic="Kinh tế/Tài chính"),
        make_article(3, title="AI 1", topic="Công nghệ/AI"),
        make_article(4, title="Society 1", topic="Văn hóa/Xã hội"),
    ]

    requests_ = plan_images("2026-08-04", articles, mode="all", max_categories=2)

    assert requests_[0].key == "cover"
    assert requests_[0].size == COVER_SIZE
    assert [request.label for request in requests_[1:]] == ["Kinh tế/Tài chính", "Công nghệ/AI"]
    assert all(request.size == CATEGORY_SIZE for request in requests_[1:])


def test_plan_images_respects_mode_and_category_cap() -> None:
    articles = [
        make_article(1, title="Economy", topic="Kinh tế/Tài chính"),
        make_article(2, title="AI", topic="Công nghệ/AI"),
        make_article(3, title="Policy", topic="Chính trị/Chính sách"),
    ]

    categories_only = plan_images("2026-08-04", articles, mode="categories", max_categories=1)
    cover_only = plan_images("2026-08-04", articles, mode="cover", max_categories=3)

    assert len(categories_only) == 1
    assert categories_only[0].key != "cover"
    assert len(cover_only) == 1
    assert cover_only[0].key == "cover"
