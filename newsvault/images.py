from __future__ import annotations

import base64
import hashlib
import logging
import os
import shutil
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import requests
from PIL import Image, ImageOps

from newsvault.model import Article
from newsvault.prompts import category_prompt, cover_prompt
from newsvault.text import slugify

PROVIDER_AIHUB: str = "aihub"
PROVIDER_GEMINI: str = "gemini"
# AI Hub draws by default; Gemini is the fallback.
# Known trade-off: `orchestration` is a routing model that rewrites the prompt before
# drawing, so house-style adherence varies run to run - one build gave a clean editorial
# vector, another a tourism poster carrying rendered text. Its ceiling is higher than
# Gemini's, its floor is lower. Set NEWSVAULT_IMAGE_PROVIDER=gemini for the consistent one.
DEFAULT_PROVIDER: str = PROVIDER_AIHUB

AIHUB_DEFAULT_MODEL: str = "orchestration"
AIHUB_DEFAULT_BASE_URL: str = "https://ai-hub.mk1technology.net/v1"
GEMINI_DEFAULT_MODEL: str = "gemini-2.5-flash-image"
DEFAULT_MODEL: str = GEMINI_DEFAULT_MODEL
AIHUB_TIMEOUT: int = 300

COVER_SIZE: tuple[int, int] = (1200, 630)
CATEGORY_SIZE: tuple[int, int] = (800, 450)
WEBP_QUALITY: int = 72

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ImageRequest:
    key: str
    label: str
    prompt: str
    size: tuple[int, int]


@dataclass(frozen=True, slots=True)
class ImageResult:
    key: str
    label: str
    path: Path | None
    cached: bool
    error: str


@dataclass(frozen=True, slots=True)
class ProviderConfig:
    """Credentials and endpoints for both image back-ends."""

    provider: str = DEFAULT_PROVIDER
    aihub_key: str | None = None
    aihub_base_url: str = AIHUB_DEFAULT_BASE_URL
    aihub_model: str = AIHUB_DEFAULT_MODEL
    gemini_key: str | None = None
    gemini_model: str = GEMINI_DEFAULT_MODEL
    fallback: bool = True

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> ProviderConfig:
        """Build a provider config from environment variables."""
        source = os.environ if env is None else env
        provider = (
            source.get("NEWSVAULT_IMAGE_PROVIDER", DEFAULT_PROVIDER).strip().lower()
            or DEFAULT_PROVIDER
        )
        fallback_value = source.get("NEWSVAULT_IMAGE_FALLBACK", "1").strip().lower()
        fallback = fallback_value not in {"0", "false", "no", "off"}
        return cls(
            provider=provider,
            aihub_key=source.get("AI_HUB_KEY") or None,
            aihub_base_url=source.get("AI_HUB_BASE_URL", AIHUB_DEFAULT_BASE_URL).strip()
            or AIHUB_DEFAULT_BASE_URL,
            aihub_model=source.get("NEWSVAULT_AIHUB_IMAGE_MODEL", AIHUB_DEFAULT_MODEL).strip()
            or AIHUB_DEFAULT_MODEL,
            gemini_key=source.get("GEMINI_API_KEY") or None,
            gemini_model=source.get("NEWSVAULT_IMAGE_MODEL", GEMINI_DEFAULT_MODEL).strip()
            or GEMINI_DEFAULT_MODEL,
            fallback=fallback,
        )

    def available(self) -> tuple[str, ...]:
        """Return configured providers with credentials, preferred first."""
        providers: list[str] = []
        if self.provider == PROVIDER_GEMINI:
            if self.gemini_key:
                providers.append(PROVIDER_GEMINI)
            if self.aihub_key:
                providers.append(PROVIDER_AIHUB)
        else:
            if self.aihub_key:
                providers.append(PROVIDER_AIHUB)
            if self.gemini_key:
                providers.append(PROVIDER_GEMINI)
        return tuple(providers)


def plan_images(
    day: str,
    articles: Sequence[Article],
    *,
    mode: str = "all",
    max_categories: int = 4,
) -> list[ImageRequest]:
    """Plan the cover and per-topic illustrations for one archive day.

    Prompts come from :mod:`newsvault.prompts` and nowhere else. That module maps topics
    to English scene wording and never lets article text reach the image API - two
    properties this project depends on:

    * the model treats any supplied string as a caption to draw, and renders Vietnamese
      as misspelled nonsense across the picture;
    * this is a private archive, so its headlines must not be shipped to a third-party
      image endpoint just to decorate a page.
    """
    if not articles:
        return []

    requests_: list[ImageRequest] = []
    topics: Counter[str] = Counter(article.topic or "Khác" for article in articles)

    if mode in {"all", "cover"}:
        headlines = [article.title_vi or article.title for article in articles[:5]]
        top_topics = [topic for topic, _count in topics.most_common(5)]
        requests_.append(
            ImageRequest(
                key="cover",
                label="Trang bìa",
                prompt=cover_prompt(day, headlines, top_topics=top_topics),
                size=COVER_SIZE,
            )
        )

    if mode in {"all", "categories"} and max_categories > 0:
        for topic, _count in topics.most_common(max_categories):
            topic_articles = [a for a in articles if (a.topic or "Khác") == topic]
            headlines = [a.title_vi or a.title for a in topic_articles[:5]]
            requests_.append(
                ImageRequest(
                    key=slugify(topic),
                    label=topic,
                    prompt=category_prompt(topic, headlines),
                    size=CATEGORY_SIZE,
                )
            )

    return requests_


def prompt_hash(prompt: str, size: tuple[int, int]) -> str:
    """Return a stable cache key derived from prompt and requested size."""
    digest = hashlib.sha256()
    digest.update(prompt.encode("utf-8"))
    digest.update(b"\0")
    digest.update(f"{size[0]}x{size[1]}".encode("ascii"))
    return digest.hexdigest()


def to_webp(
    raw: bytes,
    size: tuple[int, int],
    destination: Path,
    *,
    quality: int = WEBP_QUALITY,
) -> None:
    """Convert raw image bytes to a resized WebP file."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(Path("/dev/null") if False else __import__("io").BytesIO(raw)) as image:
        converted = image.convert("RGB")
        fitted = ImageOps.fit(
            converted, size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5)
        )
        fitted.save(destination, format="WEBP", quality=quality, method=6)


def _safe_text(value: object, *, limit: int = 200) -> str:
    text = str(value).replace("\n", " ").replace("\r", " ").strip()
    return text[:limit] if len(text) > limit else text


def _extract_error_message(payload: object) -> str:
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            message = error.get("message")
            if message:
                return _safe_text(message)
        if isinstance(error, str) and error:
            return _safe_text(error)
        message = payload.get("message")
        if isinstance(message, str) and message:
            return _safe_text(message)
    return ""


def _response_json(response: requests.Response) -> object | None:
    try:
        return response.json()
    except ValueError:
        return None


def _http_error(response: requests.Response, default: str) -> str:
    payload = _response_json(response)
    message = _extract_error_message(payload)
    return message or f"{default} ({response.status_code})"


def _call_aihub(
    prompt: str,
    size: tuple[int, int],
    config: ProviderConfig,
    *,
    timeout: int,
) -> tuple[bytes | None, str]:
    """Call the MK1 AI Hub image endpoint."""
    if not config.aihub_key:
        return None, "no api key"

    url = f"{config.aihub_base_url.rstrip('/')}/images/generations"
    headers = {
        "Authorization": f"Bearer {config.aihub_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config.aihub_model,
        "prompt": prompt,
        "n": 1,
        "size": f"{size[0]}x{size[1]}",
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=timeout)
    except requests.RequestException as exc:
        return None, _safe_text(exc, limit=160)

    body = _response_json(response)
    message = _extract_error_message(body)

    if response.status_code >= 400:
        return None, message or f"aihub http {response.status_code}"
    if message:
        return None, message
    if not isinstance(body, dict):
        return None, "invalid response"
    data = body.get("data")
    if not isinstance(data, list) or not data:
        return None, "missing image data"

    first = data[0]
    if not isinstance(first, dict):
        return None, "invalid image payload"

    b64_json = first.get("b64_json")
    if isinstance(b64_json, str) and b64_json:
        try:
            return base64.b64decode(b64_json), ""
        except (ValueError, TypeError) as exc:
            return None, _safe_text(exc, limit=160)

    image_url = first.get("url")
    if isinstance(image_url, str) and image_url:
        try:
            download = requests.get(image_url, timeout=timeout)
        except requests.RequestException as exc:
            return None, _safe_text(exc, limit=160)
        if download.status_code >= 400:
            return None, _http_error(download, "image download failed")
        return download.content, ""

    return None, "missing image data"


def _call_gemini(
    prompt: str,
    size: tuple[int, int],
    config: ProviderConfig,
    *,
    timeout: int,
) -> tuple[bytes | None, str]:
    """Call Gemini image generation."""
    if not config.gemini_key:
        return None, "no api key"

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{config.gemini_model}:generateContent"
    )
    params = {"key": config.gemini_key}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseModalities": ["TEXT", "IMAGE"],
        },
    }

    try:
        response = requests.post(url, params=params, json=payload, timeout=timeout)
    except requests.RequestException as exc:
        return None, _safe_text(exc, limit=160)

    if response.status_code >= 400:
        return None, _http_error(response, "gemini request failed")

    body = _response_json(response)
    message = _extract_error_message(body)
    if message:
        return None, message
    if not isinstance(body, dict):
        return None, "invalid response"

    candidates = body.get("candidates")
    if not isinstance(candidates, list):
        return None, "missing image data"

    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        content = candidate.get("content")
        if not isinstance(content, dict):
            continue
        parts = content.get("parts")
        if not isinstance(parts, list):
            continue
        for part in parts:
            if not isinstance(part, dict):
                continue
            inline = part.get("inlineData")
            if not isinstance(inline, dict):
                continue
            data = inline.get("data")
            if isinstance(data, str) and data:
                try:
                    return base64.b64decode(data), ""
                except (ValueError, TypeError) as exc:
                    return None, _safe_text(exc, limit=160)

    return None, "missing image data"


def generate_one(
    prompt: str,
    size: tuple[int, int],
    config: ProviderConfig,
    *,
    timeout: int,
) -> tuple[bytes | None, str, str]:
    """Generate a single image using the preferred provider with optional fallback."""
    available = config.available()
    if not available:
        return None, config.provider, "no api key"

    primary = available[0]
    fallback_provider = available[1] if config.fallback and len(available) > 1 else None

    def run(provider: str) -> tuple[bytes | None, str]:
        provider_timeout = AIHUB_TIMEOUT if provider == PROVIDER_AIHUB else timeout
        if provider == PROVIDER_AIHUB:
            return _call_aihub(prompt, size, config, timeout=provider_timeout)
        return _call_gemini(prompt, size, config, timeout=provider_timeout)

    raw, error = run(primary)
    if raw is not None:
        return raw, primary, ""

    if fallback_provider is None:
        return None, primary, error or "generation failed"

    raw, fallback_error = run(fallback_provider)
    if raw is not None:
        return raw, fallback_provider, ""

    combined = error or fallback_error or "generation failed"
    return None, fallback_provider, combined


def generate_images(
    requests_: Sequence[ImageRequest],
    out_dir: Path,
    *,
    api_key: str | None,
    cache_dir: Path,
    model: str = DEFAULT_MODEL,
    timeout: int = 120,
    max_calls: int = 8,
    dry_run: bool = False,
    config: ProviderConfig | None = None,
) -> list[ImageResult]:
    """Generate, cache, and copy image assets for one build invocation."""
    provider_config = config if config is not None else ProviderConfig.from_env()
    if api_key and not provider_config.gemini_key:
        provider_config = ProviderConfig(
            provider=provider_config.provider,
            aihub_key=provider_config.aihub_key,
            aihub_base_url=provider_config.aihub_base_url,
            aihub_model=provider_config.aihub_model,
            gemini_key=api_key,
            gemini_model=provider_config.gemini_model or model,
            fallback=provider_config.fallback,
        )
    elif model != DEFAULT_MODEL and provider_config.gemini_model == GEMINI_DEFAULT_MODEL:
        provider_config = ProviderConfig(
            provider=provider_config.provider,
            aihub_key=provider_config.aihub_key,
            aihub_base_url=provider_config.aihub_base_url,
            aihub_model=provider_config.aihub_model,
            gemini_key=provider_config.gemini_key,
            gemini_model=model,
            fallback=provider_config.fallback,
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    results: list[ImageResult] = []
    calls = 0
    available = provider_config.available()

    for request in requests_:
        destination = out_dir / f"{request.key}.webp"
        cached_file = cache_dir / f"{prompt_hash(request.prompt, request.size)}.webp"

        if cached_file.exists():
            shutil.copy2(cached_file, destination)
            results.append(
                ImageResult(
                    key=request.key,
                    label=request.label,
                    path=destination,
                    cached=True,
                    error="",
                )
            )
            continue

        if dry_run:
            LOGGER.info(
                "image dry-run key=%s provider=%s prompt=%s",
                request.key,
                available[:1] or ("none",),
                request.prompt,
            )
            results.append(
                ImageResult(
                    key=request.key,
                    label=request.label,
                    path=None,
                    cached=False,
                    error="dry-run",
                )
            )
            continue

        if not available:
            results.append(
                ImageResult(
                    key=request.key,
                    label=request.label,
                    path=None,
                    cached=False,
                    error="no api key",
                )
            )
            continue

        if calls >= max_calls:
            results.append(
                ImageResult(
                    key=request.key,
                    label=request.label,
                    path=None,
                    cached=False,
                    error="budget",
                )
            )
            continue

        calls += 1
        raw, provider_used, error = generate_one(
            request.prompt,
            request.size,
            provider_config,
            timeout=timeout,
        )
        if raw is None:
            results.append(
                ImageResult(
                    key=request.key,
                    label=request.label,
                    path=None,
                    cached=False,
                    error=_safe_text(error or "generation failed"),
                )
            )
            continue

        try:
            to_webp(raw, request.size, cached_file)
            shutil.copy2(cached_file, destination)
        except Exception as exc:  # pragma: no cover - defensive conversion guard
            results.append(
                ImageResult(
                    key=request.key,
                    label=request.label,
                    path=None,
                    cached=False,
                    error=_safe_text(exc, limit=160),
                )
            )
            continue

        LOGGER.info(
            "generated image key=%s provider=%s path=%s", request.key, provider_used, destination
        )
        results.append(
            ImageResult(
                key=request.key,
                label=request.label,
                path=destination,
                cached=False,
                error="",
            )
        )

    return results
