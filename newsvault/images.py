from __future__ import annotations

import base64
import hashlib
import logging
import shutil
from collections.abc import Sequence
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image

from newsvault.model import Article
from newsvault.prompts import category_prompt, cover_prompt
from newsvault.text import slugify

DEFAULT_MODEL: str = "gemini-2.5-flash-image"
API_BASE: str = "https://generativelanguage.googleapis.com/v1beta/models"
COVER_SIZE: tuple[int, int] = (1200, 630)
CATEGORY_SIZE: tuple[int, int] = (800, 450)
WEBP_QUALITY: int = 72

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ImageRequest:
    key: str  # 'cover' or a category slug
    label: str  # Vietnamese label for the alt text
    prompt: str
    size: tuple[int, int]


@dataclass(frozen=True, slots=True)
class ImageResult:
    key: str
    label: str
    path: Path | None  # None when generation was skipped or failed
    cached: bool
    error: str


def plan_images(
    day: str,
    articles: Sequence[Article],
    *,
    mode: str = "all",
    max_categories: int = 4,
) -> list[ImageRequest]:
    """Build the request list for the cover and/or top categories of the day."""
    if mode == "none":
        return []

    requests: list[ImageRequest] = []
    if mode in ("cover", "all"):
        top_articles = sorted(articles, key=lambda article: article.score, reverse=True)[:5]
        headlines = [article.title_vi or article.title for article in top_articles]

        topic_counts: dict[str, int] = {}
        for article in articles:
            topic = article.topic or "Khác"
            topic_counts[topic] = topic_counts.get(topic, 0) + 1
        top_topics = sorted(topic_counts, key=lambda topic: (-topic_counts[topic], topic))[:5]

        requests.append(
            ImageRequest(
                key="cover",
                label="Trang bìa",
                prompt=cover_prompt(day, headlines, top_topics=top_topics),
                size=COVER_SIZE,
            )
        )

    if mode == "all":
        # Group by `topic`, not `category`: the source database leaves `category` as
        # "Khác" for most rows, and the day page builds its category cards from `topic`.
        category_counts: dict[str, int] = {}
        for article in articles:
            category = article.topic or "Khác"
            category_counts[category] = category_counts.get(category, 0) + 1

        top_categories = sorted(
            category_counts.items(),
            key=lambda item: (-item[1], item[0]),
        )[:max_categories]

        for label, _count in top_categories:
            cat_articles = [article for article in articles if (article.topic or "Khác") == label]
            cat_articles.sort(key=lambda article: article.score, reverse=True)
            cat_headlines = [article.title_vi or article.title for article in cat_articles[:5]]

            requests.append(
                ImageRequest(
                    key=slugify(label) or "x",
                    label=label,
                    prompt=category_prompt(label, cat_headlines),
                    size=CATEGORY_SIZE,
                )
            )

    return requests


def prompt_hash(prompt: str, size: tuple[int, int]) -> str:
    """Stable sha256[:16] of the prompt and size — the cache key."""
    data = f"{prompt}\n{size[0]}x{size[1]}".encode()
    return hashlib.sha256(data).hexdigest()[:16]


def to_webp(
    raw: bytes,
    size: tuple[int, int],
    destination: Path,
    *,
    quality: int = WEBP_QUALITY,
) -> None:
    """Decode, convert to RGB, cover-crop to `size`, and save as WebP."""
    with Image.open(BytesIO(raw)) as img:
        rgb = img.convert("RGB")
        src_w, src_h = rgb.size
        tgt_w, tgt_h = size
        scale = max(tgt_w / src_w, tgt_h / src_h)
        new_w = int(src_w * scale)
        new_h = int(src_h * scale)
        resized = rgb.resize((new_w, new_h), Image.Resampling.LANCZOS)
        left = (new_w - tgt_w) // 2
        top = (new_h - tgt_h) // 2
        cropped = resized.crop((left, top, left + tgt_w, top + tgt_h))
        destination.parent.mkdir(parents=True, exist_ok=True)
        cropped.save(destination, "WEBP", quality=quality, method=6)


def _call_gemini_image(prompt: str, api_key: str, model: str, timeout: int) -> str | None:
    """Return the first base64 image payload, or None on any failure."""
    url = f"{API_BASE}/{model}:generateContent"
    params = {"key": api_key}
    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    try:
        response = requests.post(url, params=params, json=payload, timeout=timeout)
    except requests.RequestException:
        return None

    if response.status_code != 200:
        return None

    try:
        data = response.json()
    except Exception:  # noqa: BLE001
        return None

    candidates = data.get("candidates") or []
    if not candidates:
        return None

    parts = candidates[0].get("content", {}).get("parts", [])
    for part in parts:
        inline = part.get("inlineData")
        if inline:
            return inline.get("data")

    return None


def _save_from_inline(
    request: ImageRequest,
    b64: str,
    out_path: Path,
    cache_path: Path,
) -> ImageResult:
    """Decode a base64 image, convert to WebP, cache it, and return the result."""
    try:
        raw = base64.b64decode(b64, validate=True)
    except Exception as exc:
        logger.warning("Could not decode image data for %s: %s", request.key, type(exc).__name__)
        return ImageResult(request.key, request.label, None, False, "decode error")

    try:
        to_webp(raw, request.size, out_path)
    except Exception as exc:
        logger.warning("Could not convert image for %s: %s", request.key, type(exc).__name__)
        return ImageResult(request.key, request.label, None, False, f"convert error: {exc}")

    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(out_path, cache_path)
    except Exception as exc:
        logger.warning("Could not cache image for %s: %s", request.key, type(exc).__name__)

    return ImageResult(request.key, request.label, out_path, False, "")


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
) -> list[ImageResult]:
    """Generate every requested image into out_dir as .webp, reusing the cache. Never raises."""
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    results: list[ImageResult] = []
    calls = 0

    for request in requests_:
        out_path = out_dir / f"{request.key}.webp"
        cache_key = prompt_hash(request.prompt, request.size)
        cache_path = cache_dir / f"{cache_key}.webp"

        if cache_path.exists():
            try:
                shutil.copy2(cache_path, out_path)
                results.append(ImageResult(request.key, request.label, out_path, True, ""))
                continue
            except Exception as exc:
                logger.warning("Cache copy failed for %s: %s", request.key, type(exc).__name__)

        if dry_run:
            logger.info(
                "Dry-run image prompt for %s (%dx%d):\n%s",
                request.key,
                request.size[0],
                request.size[1],
                request.prompt,
            )
            results.append(ImageResult(request.key, request.label, None, False, "dry-run"))
            continue

        if not api_key:
            logger.warning("No API key for image %s; skipping", request.key)
            results.append(ImageResult(request.key, request.label, None, False, "no api key"))
            continue

        if calls >= max_calls:
            results.append(ImageResult(request.key, request.label, None, False, "budget"))
            continue

        b64 = _call_gemini_image(request.prompt, api_key, model, timeout)
        calls += 1

        if b64 is None:
            logger.warning("Image generation failed for %s", request.key)
            results.append(
                ImageResult(request.key, request.label, None, False, "generation failed")
            )
            continue

        results.append(_save_from_inline(request, b64, out_path, cache_path))

    return results
