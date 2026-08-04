from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from newsvault.text import VI_STOPWORDS, excerpt, fold, slugify

HOUSE_STYLE: str = (
    "Flat modern editorial vector illustration, built from clean geometric shapes "
    "with a subtle paper-grain texture and a single confident line weight. "
    "Colour palette is strictly limited to deep indigo, warm amber, muted teal, "
    "off-white paper, and one signal red used sparingly for emphasis. "
    "Use a single clear focal metaphor, generous negative space, a slight top-down "
    "perspective, wide 16:9 framing, and keep every object fully inside the frame. "
    "Mood: calm, analytical, broadsheet-newspaper seriousness; avoid corporate stock "
    "art, cyberpunk, or sensational visuals. "
    "CRITICAL CONSTRAINT, this outranks everything above: the image must contain ZERO "
    "written characters. No text, no words, no letters of any alphabet, no numerals, no "
    "labels, no captions, no signage, no logos, no watermarks. Any lettering the model "
    "renders comes out as misspelled nonsense and ruins the illustration. Also: no flags "
    "of any country and no recognisable real person's face. Communicate the subject "
    "purely through shape, object and composition."
)
"""The fixed style clause appended to every image prompt."""

NEGATIVE_STYLE: str = (
    "text, letters, numbers, logos, watermarks, flags, faces, portraits, "
    "photorealism, neon, cyberpunk, corporate stock art, cropped objects, "
    "sensational imagery"
)
"""What the illustration must avoid."""

_TOKEN_SPLIT = re.compile(r"[^a-z0-9]+")

# English theme wording per topic slug. Vietnamese label text must NEVER reach the image
# prompt: the model treats any supplied string as a caption to draw, and renders it as
# misspelled gibberish across the illustration.
_THEME_EN: dict[str, str] = {
    "kinh-te-tai-chinh": "the economy and financial markets",
    "cong-nghe-ai": "technology and artificial intelligence",
    "chinh-tri-chinh-sach": "government policy and public administration",
    "xung-dot-chien-tranh": "armed conflict and its aftermath",
    "phap-luat-nghi-dinh": "law and new regulation",
    "van-hoa-xa-hoi": "culture and everyday social life",
    "khac": "the day's mixed news",
}


def theme_phrase(label: str) -> str:
    """English theme wording for a Vietnamese topic label."""
    return _THEME_EN.get(slugify(label), "the day's news")


_CENTRAL_OBJECT: dict[str, str] = {
    "kinh-te-tai-chinh": "a balanced scale beside a gently rising chart",
    "cong-nghe-ai": "a calm neural node connected to quiet circuitry",
    "chinh-tri-chinh-sach": "an open council table with a single document",
    "xung-dot-chien-tranh": "a broken olive branch and distant smoke",
    "phap-luat-nghi-dinh": "a gavel resting on an open book",
    "van-hoa-xa-hoi": "a public square shaded by a single tree",
    "khac": "a compass on an empty map",
}

_TOKEN_OBJECT: dict[str, str] = {
    "lai": "a small interest graph",
    "suat": "a percentage arc",
    "ngan": "a bank column",
    "hang": "a ledger sheet",
    "co": "a rising stock line",
    "phieu": "a paper certificate",
    "dau": "an oil barrel",
    "vang": "a gold bar",
    "bat": "a catching net",
    "dong": "a moving arrow",
    "san": "a factory silhouette",
    "xuat": "an export crate",
    "thue": "a tax ledger",
    "chinh": "a council table",
    "sach": "a policy document",
    "phap": "a scale of justice",
    "luat": "an open legal book",
    "van": "a public square",
    "hoa": "a flowering tree",
    "xa": "a community roofline",
    "hoi": "a gathering circle",
    "cong": "a circuit node",
    "nghe": "a quiet machine gear",
    "tri": "a neural pathway",
    "tue": "a glowing chip",
    "khac": "a compass on an empty map",
}


def _clean_headlines(headlines: Sequence[str]) -> list[str]:
    """Return up to five trimmed headlines, each truncated to 140 characters."""
    return [excerpt(h.strip(), 140) for h in headlines[:5] if h and h.strip()]


def _headline_tokens(headlines: Sequence[str]) -> list[str]:
    """Deterministic, frequency-ordered token list derived from headlines."""
    counts: dict[str, int] = {}
    for line in headlines:
        for token in _TOKEN_SPLIT.split(fold(line)):
            if len(token) > 2 and token not in VI_STOPWORDS:
                counts[token] = counts.get(token, 0) + 1
    return sorted(counts, key=lambda token: (-counts[token], token))[:5]


def _supporting_objects(headlines: Sequence[str]) -> list[str]:
    """Turn headline tokens into a small list of concrete visual objects."""
    seen: list[str] = []
    for token in _headline_tokens(headlines):
        obj = _TOKEN_OBJECT.get(token)
        if obj and obj not in seen:
            seen.append(obj)
            if len(seen) >= 3:
                break
    return seen


def _build_scene(label: str | None, themes: Sequence[str], headlines: Sequence[str]) -> str:
    """Compose a deterministic scene instruction from themes and headlines."""
    if label is not None:
        central = _CENTRAL_OBJECT.get(slugify(label), "a calm central form")
        theme_text = theme_phrase(label)
    elif themes:
        pieces = [_CENTRAL_OBJECT.get(slugify(theme), "a calm symbol") for theme in themes[:3]]
        central = " and ".join(pieces)
        theme_text = " and ".join(dict.fromkeys(theme_phrase(theme) for theme in themes[:3]))
    else:
        central = "a calm central form"
        theme_text = "today's news"

    extras = _supporting_objects(headlines)
    if extras:
        return (
            f"Editorial illustration: {central}, with {', '.join(extras)}, "
            f"as a single calm metaphor about {theme_text}. "
            "Wordless: draw no text, no numbers, no labels, no faces, no flags, no logos."
        )
    return (
        f"Editorial illustration: {central} as a single clear metaphor "
        f"about {theme_text}. "
        "Wordless: draw no text, no numbers, no labels, no faces, no flags, no logos."
    )


def cover_prompt(day: str, headlines: Sequence[str], *, top_topics: Sequence[str]) -> str:
    """Build a deterministic, 16:9 cover prompt from the day's headlines and topics."""
    cleaned = _clean_headlines(headlines)
    scene = _build_scene(None, list(top_topics)[:5], cleaned)
    return f"{scene}\n\n{HOUSE_STYLE}"


def category_prompt(label: str, headlines: Sequence[str]) -> str:
    """Build a deterministic category illustration prompt from its headline set."""
    cleaned = _clean_headlines(headlines)
    scene = _build_scene(label, [label], cleaned)
    return f"{scene}\n\n{HOUSE_STYLE}"


def brief_prompt(day: str, items: Sequence[Mapping[str, object]]) -> str:
    """Build the Vietnamese daily-brief prompt sent to Gemini."""
    lines = [
        f"Write exactly five concise news-bullet points in Vietnamese (tiếng Việt) for {day}.",
        "Base every bullet only on the supplied items. Do not invent facts.",
        "Do not add numbers, dates, or statistics that are not present in the items.",
        "Prefer the consequence, meaning, or likely impact of each event over the raw event.",
        "One sentence per bullet. No emoji. No preamble. No numbering. Return exactly five strings.",
        "",
        "Items:",
    ]
    for i, item in enumerate(items, start=1):
        title = str(item.get("title", "")).replace("\n", " ").strip()
        source = str(item.get("source", "")).strip()
        topic = str(item.get("topic", "")).strip()
        impact = str(item.get("impact", "")).strip()
        summary = str(item.get("summary", "")).replace("\n", " ").strip()[:300]
        lines.append(f"{i}. title: {title}")
        lines.append(f"   source: {source}")
        lines.append(f"   topic: {topic}")
        lines.append(f"   impact: {impact}")
        lines.append(f"   summary: {summary}")
    return "\n".join(lines)
