"""Prompt construction for the Gemini daily brief.

Illustration prompts used to live here too. They are gone with the image pipeline: the
day pages now use a fixed per-category icon, which costs no API call and keeps the
archive's headlines - a deliberately private dataset - away from third-party endpoints.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence


def brief_prompt(day: str, items: Sequence[Mapping[str, object]]) -> str:
    """Build the Vietnamese daily-brief prompt sent to the brief model.

    The JSON contract is spelled out in the prompt itself rather than left to the API.
    Gemini is told the shape twice — here and through `responseSchema` — but MK1 AI Hub has
    no schema parameter, and `response_format: {"type": "json_object"}` alone was not
    enough: the model wrote five genuinely good Vietnamese bullets as markdown dashes and
    the parser found no JSON object at all, so every brief fell through to the fallback.
    """
    lines = [
        f"Write exactly five concise news-bullet points in Vietnamese (tiếng Việt) for {day}.",
        "Base every bullet only on the supplied items. Do not invent facts.",
        "Do not add numbers, dates, or statistics that are not present in the items.",
        "Prefer the consequence, meaning, or likely impact of each event over the raw event.",
        "One sentence per bullet. No emoji. No preamble. No numbering. Return exactly five strings.",
        "",
        'Return ONLY a JSON object of the form {"bullets": ["…", "…", "…", "…", "…"]}',
        "containing exactly five strings. No markdown code fence, no leading dash, and no",
        "text of any kind outside the JSON object.",
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
