from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from newsvault.model import Article


def _escape_markdown_link_text(text: str) -> str:
    """Escape '[' , ']' and backslashes inside link text."""
    return text.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


def _format_article(article: Article, include_analysis: bool) -> str:
    """Format a single article as a markdown section."""
    title = _escape_markdown_link_text(article.title_vi or article.title)
    link = f"[{title}]({article.url})"
    source = article.source or ""
    impact = article.impact_level or ""
    score = article.score
    summary = article.summary_vi or ""
    key_points = article.key_points

    lines = [
        f"### {link}",
        f"*{source} · {article.category} · tác động {impact} · điểm {score}*",
        "",
        summary,
        "",
    ]
    if key_points:
        for kp in key_points:
            lines.append(f"- {kp}")
        lines.append("")

    if include_analysis and article.analysis:
        analysis = article.analysis
        lines.append("<details><summary>Phân tích</summary>")
        lines.append("")
        if analysis.get("boi_canh"):
            lines.append(f"**Bối cảnh** {analysis['boi_canh']}")
        if analysis.get("nguyen_nhan"):
            lines.append(f"**Nguyên nhân** {analysis['nguyen_nhan']}")
        if analysis.get("muc_dich"):
            lines.append(f"**Mục đích** {analysis['muc_dich']}")
        if analysis.get("lien_he"):
            lines.append(f"**Liên hệ** {analysis['lien_he']}")
        lines.append("</details>")
        lines.append("")

    return "\n".join(lines)


def day_markdown(
    day: str,
    articles: Sequence[Article],
    *,
    brief: Sequence[str] = (),
    site_url: str = "",
    include_analysis: bool = True,
    limit: int | None = None,
) -> str:
    """A complete Vietnamese Markdown document for one day."""
    # Apply limit
    if limit is not None:
        articles = sorted(articles, key=lambda a: a.score, reverse=True)[:limit]
    else:
        articles = sorted(articles, key=lambda a: a.score, reverse=True)

    # Group by category
    categories: dict[str, list[Article]] = {}
    for article in articles:
        cat = article.category or "Khác"
        categories.setdefault(cat, []).append(article)

    # Order categories by count descending then name
    sorted_cats = sorted(categories.items(), key=lambda x: (-len(x[1]), x[0]))

    # Build document
    lines: list[str] = []
    # Header
    day_label = f"{day[8:10]}/{day[5:7]}/{day[:4]}"
    lines.append(f"# Nhật báo {day_label}")
    lines.append("")
    # Stats line (placeholder)
    total = len(articles)
    sources = len({a.source for a in articles if a.source})
    lines.append(f"*{total} tin · {sources} nguồn · cập nhật …*")
    lines.append("")

    # Brief bullets
    if brief:
        lines.append("## Điểm chính")
        for bullet in brief:
            lines.append(f"- {bullet}")
        lines.append("")

    # Categories
    for cat_name, cat_articles in sorted_cats:
        lines.append(f"## {cat_name}")
        lines.append("")
        for article in cat_articles:
            lines.append(_format_article(article, include_analysis))
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def week_markdown(
    week: str,
    start: str,
    end: str,
    by_day: Mapping[str, Sequence[Article]],
    *,
    site_url: str = "",
    top_n: int = 30,
) -> str:
    """A complete Vietnamese Markdown document for one week."""
    lines: list[str] = []
    # Title
    lines.append(f"# Tuần {start} - {end}")
    lines.append("")
    total_articles = sum(len(v) for v in by_day.values())
    lines.append(f"*Tổng số tin: {total_articles}*")
    lines.append("")

    # Sort days
    sorted_days = sorted(by_day.keys(), reverse=True)
    for day in sorted_days:
        articles = by_day[day]
        day_label = f"{day[8:10]}/{day[5:7]}/{day[:4]}"
        lines.append(f"## {day_label} ({len(articles)} tin)")
        lines.append("")
        # Top N articles by score
        top_articles = sorted(articles, key=lambda a: a.score, reverse=True)[:top_n]
        for article in top_articles:
            title = _escape_markdown_link_text(article.title_vi or article.title)
            link = f"[{title}]({article.url})"
            source = article.source or ""
            score = article.score
            lines.append(f"- {link} *{source} · điểm {score}*")
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def write_markdown(path: Path, content: str) -> int:
    """UTF-8, LF line endings, trailing newline; creates parent directories; returns bytes written."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # Ensure LF line endings and trailing newline
    normalized = content.replace("\r\n", "\n").rstrip("\n") + "\n"
    data = normalized.encode("utf-8")
    path.write_bytes(data)
    return len(data)
