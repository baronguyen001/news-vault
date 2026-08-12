"""End to end: an x-pulse database attached to a real build.

There was no test that a video-bearing day page actually got built, only that the reader
parsed rows. This covers the equivalent for X posts: the day is built, the payload is
encrypted, and what comes back out of `data.enc` has the section in it.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from newsvault import build, crypto
from tests.make_fixture import build as make_fixture

PASSWORD = "test-password"

_COLUMNS = (
    "id TEXT, url TEXT, author TEXT, author_name TEXT, author_tier REAL, text TEXT, "
    "created_at TEXT, day TEXT, likes INTEGER, retweets INTEGER, replies INTEGER, "
    "views INTEGER, vertical TEXT, topic TEXT, relevance INTEGER, score INTEGER, "
    "is_primary INTEGER, title_vi TEXT, summary_vi TEXT, key_points TEXT, insight TEXT, "
    "impact_level TEXT, processed_at TEXT"
)
_FIELDS = [part.strip().split(" ")[0] for part in _COLUMNS.split(",")]


@pytest.fixture(autouse=True)
def _clear_shell_cache() -> None:
    build._shell_digest.cache_clear()
    yield
    build._shell_digest.cache_clear()


def _make_x_db(path: Path, day: str) -> Path:
    conn = sqlite3.connect(path)
    conn.execute(f"CREATE TABLE raw_posts ({_COLUMNS})")
    rows = [
        {
            "id": f"18000000000000000{index}",
            "url": f"https://x.com/reuters/status/18000000000000000{index}",
            "author": "reuters",
            "author_name": "Reuters",
            "author_tier": 0.85,
            "text": f"Fed policy headline number {index}.",
            "created_at": f"{day}T03:00:00.000Z",
            "day": day,
            "likes": 1200 - index,
            "retweets": 430,
            "replies": 88,
            "views": 90000,
            "vertical": "kinh-te",
            "topic": "Kinh tế/Tài chính",
            "relevance": 9,
            "score": 90 - index,
            "is_primary": 1,
            "title_vi": f"Fed giữ nguyên lãi suất, bản tin số {index}",
            "summary_vi": "Fed giữ lãi suất ở mức 4,25-4,5%.",
            "key_points": json.dumps(["Lạm phát còn 2,4%"], ensure_ascii=False),
            "insight": "Chính sách vẫn thắt chặt.",
            "impact_level": "cao",
            "processed_at": f"{day}T14:05:00",
        }
        for index in (1, 2)
    ]
    placeholders = ", ".join("?" for _ in _FIELDS)
    for row in rows:
        conn.execute(
            f"INSERT INTO raw_posts VALUES ({placeholders})", [row[field] for field in _FIELDS]
        )
    conn.execute("CREATE VIEW x_feed AS SELECT * FROM raw_posts")
    conn.commit()
    conn.close()
    return path


def _build(out: Path, db: Path, x_db: Path | None) -> build.BuildReport:
    return build.build_site(
        build.BuildOptions(
            db_path=db,
            out_dir=out,
            password=PASSWORD,
            backfill=True,
            use_brief=False,
            x_db_path=x_db,
        )
    )


def _decrypt(out: Path, day: str) -> dict[str, object]:
    blob = (out / "d" / day / "data.enc").read_bytes()
    data = crypto.decrypt_payload(blob, PASSWORD)
    assert isinstance(data, dict)
    return data


def test_posts_reach_the_encrypted_day_payload(tmp_path: Path) -> None:
    db = tmp_path / "sample.db"
    make_fixture(db)
    day = "2026-08-04"
    x_db = _make_x_db(tmp_path / "x_pulse.db", day)
    out = tmp_path / "site"

    report = _build(out, db, x_db)

    assert report.posts_included == 2
    data = _decrypt(out, day)
    assert len(data["posts"]) == 2
    # Highest score leads, and the tier travels with the card.
    assert data["posts"][0]["t"].endswith("số 1")
    assert data["posts"][0]["tr"] == 0.85


def test_a_missing_x_database_is_a_warning_not_a_failed_build(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The scraper writes three times a day; the nightly build must survive its absence."""
    db = tmp_path / "sample.db"
    make_fixture(db)
    out = tmp_path / "site"

    with caplog.at_level("WARNING"):
        report = _build(out, db, tmp_path / "khong-ton-tai.db")

    assert report.days_built, "the build must still produce day pages"
    assert report.posts_included == 0
    assert "x-pulse" in caplog.text
    assert _decrypt(out, "2026-08-04")["posts"] == []


def test_no_x_database_configured_leaves_the_key_empty(tmp_path: Path) -> None:
    db = tmp_path / "sample.db"
    make_fixture(db)
    out = tmp_path / "site"

    report = _build(out, db, None)

    assert report.posts_included == 0
    assert _decrypt(out, "2026-08-04")["posts"] == []


def test_a_day_with_only_x_posts_still_gets_a_page(tmp_path: Path) -> None:
    """A quiet news day where X had something is still a day worth publishing."""
    db = tmp_path / "sample.db"
    make_fixture(db)
    quiet_day = "2026-09-20"  # outside the fixture's range
    x_db = _make_x_db(tmp_path / "x_pulse.db", quiet_day)
    out = tmp_path / "site"

    report = _build(out, db, x_db)

    assert quiet_day in report.days_built
    data = _decrypt(out, quiet_day)
    assert data["articles"] == []
    assert len(data["posts"]) == 2
