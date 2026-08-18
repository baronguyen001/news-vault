from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from newsvault import payload, quality


def _database(path: Path, sql: str) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(sql)
    finally:
        conn.close()


def _set_paths(monkeypatch, tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    news = tmp_path / "news.db"
    posts = tmp_path / "posts.db"
    videos = tmp_path / "videos.db"
    audit = tmp_path / "quality.json"
    monkeypatch.setattr(quality, "_NEWS_DB", news)
    monkeypatch.setattr(quality, "_X_DB", posts)
    monkeypatch.setattr(quality, "_VIDEO_DB", videos)
    monkeypatch.setattr(quality, "_QUALITY_JSON", audit)
    return news, posts, videos, audit


def _sources(monkeypatch, tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    news, posts, videos, audit = _set_paths(monkeypatch, tmp_path)
    _database(
        news,
        """
        CREATE TABLE articles (
            fetched_at TEXT, is_teaser INTEGER, content_length INTEGER,
            image_url TEXT, source_key TEXT
        );
        CREATE TABLE retry_queue (
            source_key TEXT, reason TEXT, last_attempt_at TEXT
        );
        CREATE TABLE gemini_usage (cost_usd REAL, ts TEXT);
        INSERT INTO articles VALUES
            ('2026-08-17T10:00:00', 0, 2000, 'image', 'source-a'),
            ('2026-08-17T10:00:00', 0, 2000, '', 'source-a'),
            ('2026-08-17T10:00:00', 0, 2000, '', 'source-a'),
            ('2026-08-17T10:00:00', 1, 100, '', 'source-a'),
            ('2026-08-17T10:00:00', 0, 2000, '', 'source-b'),
            ('2026-08-17T10:00:00', 0, 2000, '', 'source-b'),
            ('2026-08-17T10:00:00', 0, 2000, '', 'source-b'),
            ('2026-08-17T10:00:00', 0, 2000, '', 'source-b'),
            ('2026-08-17T10:00:00', 0, 2000, '', 'source-b'),
            ('2026-08-17T10:00:00', 0, 2000, '', 'source-b'),
            ('2026-08-17T10:00:00', 0, 2000, '', 'source-b'),
            ('2026-08-17T10:00:00', 0, 2000, '', 'source-b'),
            ('2026-08-17T10:00:00', 0, 2000, '', 'source-b'),
            ('2026-08-17T10:00:00', 0, 2000, '', 'source-b'),
            ('2026-08-17T10:00:00', 0, 2000, '', 'source-b'),
            ('2026-08-17T10:00:00', 0, 2000, '', 'source-b');
        INSERT INTO retry_queue VALUES ('source-a', 'hard_paywall', '2026-08-17T10:00:00');
        INSERT INTO gemini_usage VALUES (0.12345, '2026-08-17T10:00:00');
        """,
    )
    _database(
        posts,
        """
        CREATE TABLE posts (
            id INTEGER, day TEXT, status TEXT, dup_of TEXT, media_url TEXT, author TEXT
        );
        CREATE TABLE post_impact (post_id INTEGER);
        CREATE TABLE target_health (
            kind TEXT, ref TEXT, empty_streak INTEGER, last_seen_at TEXT
        );
        INSERT INTO posts VALUES (1, '2026-08-17', 'enriched', '', 'image', 'alice');
        INSERT INTO posts VALUES (2, '2026-08-17', 'dropped', '1', '', 'bob');
        INSERT INTO post_impact VALUES (1);
        INSERT INTO target_health VALUES ('tài khoản', 'lost', 3, '2026-08-16');
        """,
    )
    _database(
        videos,
        """
        CREATE TABLE videos (
            processed_at TEXT, success INTEGER, junk INTEGER, telegram_sent INTEGER,
            error_message TEXT
        );
        INSERT INTO videos VALUES ('2026-08-17T10:00:00', 1, 0, 1, '');
        INSERT INTO videos VALUES ('2026-08-17T10:00:00', 0, 1, 0, '');
        """,
    )
    audit.write_text(
        json.dumps(
            {
                "summary": {
                    "so_bai": 45,
                    "so_loi": 0,
                    "tu_nhien_tb": 8.6,
                    "chinh_xac_tb": 9.1,
                    "lech_tb": 0.8,
                    "cham_qua_cao": 2,
                    "cham_qua_thap": 1,
                    "theo_mang": {
                        "Kinh tế/Tài chính": {
                            "tu_nhien": 8.7,
                            "chinh_xac": 9.2,
                            "lech": 0.6,
                        }
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    return news, posts, videos, audit


def test_collect_returns_all_optional_systems(monkeypatch, tmp_path: Path) -> None:
    _sources(monkeypatch, tmp_path)

    systems = quality.collect("2026-08-17", "2026-08-23")

    assert [system["key"] for system in systems] == [
        "news-hunter",
        "x-pulse",
        "youtube",
        "translation",
    ]
    news = systems[0]
    assert news["stats"][1]["sub"] == "93,8%"
    assert news["stats"][0]["value"] == "16"


def test_collect_skips_missing_x_database(monkeypatch, tmp_path: Path) -> None:
    _, posts, _, _ = _sources(monkeypatch, tmp_path)
    posts.unlink()

    systems = quality.collect("2026-08-17", "2026-08-23")

    assert [system["key"] for system in systems] == [
        "news-hunter",
        "youtube",
        "translation",
    ]


def test_full_article_tones_cover_bad_and_ok(monkeypatch, tmp_path: Path) -> None:
    news, _, _, _ = _set_paths(monkeypatch, tmp_path)
    _database(
        news,
        """
        CREATE TABLE articles (
            fetched_at TEXT, is_teaser INTEGER, content_length INTEGER,
            image_url TEXT, source_key TEXT
        );
        CREATE TABLE retry_queue (
            source_key TEXT, reason TEXT, last_attempt_at TEXT
        );
        CREATE TABLE gemini_usage (cost_usd REAL, ts TEXT);
        INSERT INTO articles VALUES ('2026-08-17T10:00:00', 1, 100, '', 'a');
        """,
    )

    assert quality.collect("2026-08-17", "2026-08-23")[0]["stats"][1]["tone"] == "bad"

    # Chín bài đầy đủ, không phải hai. Một teaser cộng hai bài đầy đủ là 66,7% — dưới ngưỡng
    # 75%, nên "bad" mới là câu trả lời đúng cho tình huống đó. Muốn chạm "ok" thì tỷ lệ phải
    # từ 90% trở lên, tức 1 teaser đi kèm ít nhất chín bài đầy đủ.
    conn = sqlite3.connect(news)
    try:
        for _ in range(9):
            conn.execute(
                "INSERT INTO articles VALUES ('2026-08-17T10:00:00', 0, 2000, '', 'a')"
            )
        conn.commit()
    finally:
        conn.close()

    assert quality.collect("2026-08-17", "2026-08-23")[0]["stats"][1]["tone"] == "ok"


def test_quality_payload_keeps_contract_keys() -> None:
    data = payload.quality_payload(
        "2026-W34",
        "2026-08-17",
        "2026-08-23",
        [],
        generated_at="2026-08-23T23:59:59+07:00",
    )

    assert set(data) == {"v", "kind", "week", "start", "end", "generated_at", "systems"}
    assert data["kind"] == "quality"
