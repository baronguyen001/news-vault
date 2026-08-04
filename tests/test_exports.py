from __future__ import annotations

import tempfile
from pathlib import Path

from newsvault.exports import day_markdown, write_markdown
from newsvault.model import Article


def _make_article(
    id: int = 1,
    title: str = "Test Title",
    title_vi: str = "Tiêu đề kiểm tra",
    day: str = "2026-08-04",
    category: str = "Kinh tế & Tài chính",
    topic: str = "Kinh tế/Tài chính",
    score: int = 80,
    source: str = "VnExpress",
    source_key: str = "vnexpress",
    region: str = "domestic",
    published_at: str = "Wed, 29 Jul 2026 12:00:36 +0700",
    published_iso: str = "2026-07-29T12:00:36+07:00",
    fetched_at: str = "2026-08-04T06:09:27.518450+00:00",
    summary_vi: str = "Tóm tắt bài báo.",
    key_points: tuple[str, ...] = ("Ý chính 1", "Ý chính 2"),
    tags: tuple[str, ...] = (),
    analysis: dict[str, str] | None = None,
    impact_level: str = "cao",
    is_law_policy: bool = False,
    relevance: int = 9,
) -> Article:
    return Article(
        id=id,
        url=f"https://example.com/article/{id}",
        source=source,
        source_key=source_key,
        region=region,
        title=title,
        title_vi=title_vi,
        published_at=published_at,
        published_iso=published_iso,
        day=day,
        fetched_at=fetched_at,
        category=category,
        topic=topic,
        summary_vi=summary_vi,
        key_points=key_points,
        tags=tags,
        analysis=dict(analysis) if analysis else {},
        impact_level=impact_level,
        is_law_policy=is_law_policy,
        relevance=relevance,
        score=score,
    )


class TestDayMarkdown:
    def test_starts_with_header(self) -> None:
        articles = [_make_article()]
        md = day_markdown("2026-08-04", articles)
        assert md.startswith("# Nhật báo 04/08/2026")

    def test_contains_one_heading_per_article(self) -> None:
        articles = [
            _make_article(id=1, title_vi="Bài 1"),
            _make_article(id=2, title_vi="Bài 2"),
        ]
        md = day_markdown("2026-08-04", articles)
        assert md.count("### ") == 2

    def test_groups_by_category(self) -> None:
        articles = [
            _make_article(id=1, category="Kinh tế & Tài chính", title_vi="Bài Kinh tế"),
            _make_article(id=2, category="Công nghệ", title_vi="Bài Công nghệ"),
        ]
        md = day_markdown("2026-08-04", articles)
        assert "## Kinh tế & Tài chính" in md
        assert "## Công nghệ" in md

    def test_includes_analysis_when_true(self) -> None:
        articles = [_make_article(analysis={"boi_canh": "Bối cảnh"})]
        md = day_markdown("2026-08-04", articles, include_analysis=True)
        assert "<details>" in md
        assert "Bối cảnh" in md

    def test_excludes_analysis_when_false(self) -> None:
        articles = [_make_article(analysis={"boi_canh": "Bối cảnh"})]
        md = day_markdown("2026-08-04", articles, include_analysis=False)
        assert "<details>" not in md
        assert "Bối cảnh" not in md

    def test_escapes_brackets_in_title(self) -> None:
        articles = [_make_article(id=1, title_vi="Tiêu đề [có] dấu ngoặc")]
        md = day_markdown("2026-08-04", articles)
        # The title should be escaped in the link text
        assert "\\[có\\]" in md
        assert "\\] dấu ngoặc" in md

    def test_limit_truncates_articles(self) -> None:
        articles = [_make_article(id=i, title_vi=f"Bài {i}", score=100 - i) for i in range(1, 6)]
        md = day_markdown("2026-08-04", articles, limit=3)
        # Should have exactly 3 ### headings
        assert md.count("### ") == 3
        # The highest scored articles should be present
        assert "Bài 1" in md
        assert "Bài 2" in md
        assert "Bài 3" in md
        assert "Bài 4" not in md
        assert "Bài 5" not in md


class TestWriteMarkdown:
    def test_creates_parent_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "sub" / "test.md"
            content = "# Hello\n"
            write_markdown(path, content)
            assert path.exists()

    def test_writes_lf_endings(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.md"
            content = "Line1\r\nLine2\nLine3"
            write_markdown(path, content)
            with open(path, "rb") as f:
                data = f.read()
            # Should have LF only
            assert b"\r\n" not in data
            assert data.endswith(b"\n")

    def test_returns_bytes_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.md"
            content = "Hello\n"
            result = write_markdown(path, content)
            assert result == len(content.encode("utf-8"))
