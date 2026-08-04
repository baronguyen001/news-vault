"""Generate a small synthetic news-hunter database for tests and CI smoke builds.

The schema is copied verbatim from news-hunter so the reader is exercised against
the real column layout. All content is invented; no real article text is shipped.

Usage:  python -m tests.make_fixture tests/fixtures/sample.db
"""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

SCHEMA = """
CREATE TABLE articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL UNIQUE,
    source TEXT,
    source_key TEXT,
    region TEXT,
    title TEXT,
    title_vi TEXT,
    published_at TEXT,
    category TEXT,
    summary_vi TEXT,
    key_points TEXT,
    tags TEXT,
    is_law_policy INTEGER DEFAULT 0,
    impact_level TEXT,
    content_hash TEXT,
    content_length INTEGER,
    html_snapshot TEXT,
    fetched_at TEXT,
    summarized_at TEXT,
    sent_telegram INTEGER DEFAULT 0,
    telegram_sent_at TEXT,
    relevance INTEGER,
    topic TEXT,
    is_advertorial INTEGER DEFAULT 0,
    is_teaser INTEGER DEFAULT 0,
    analysis TEXT
)
"""

SOURCES = [
    ("VnExpress", "vnexpress", "domestic"),
    ("Reuters", "reuters", "international"),
    ("CafeF", "cafef", "domestic"),
    ("TechCrunch", "techcrunch", "international"),
    ("Tuoi Tre", "tuoitre", "domestic"),
]

TOPICS = [
    ("Kinh te/Tai chinh", "Kinh te & Tai chinh"),
    ("Cong nghe/AI", "Cong nghe"),
    ("Chinh tri/Chinh sach", "Xa hoi & Chinh tri"),
    ("Phap luat/Nghi dinh", "Phap luat & Chinh sach"),
]

IMPACTS = ["cao", "trung binh", "thap"]

TAG_POOL = [
    ["Ha Noi", "lai suat", "ngan hang"],
    ["OpenAI", "chip", "ban dan"],
    ["Quoc hoi", "nghi dinh", "cai cach"],
    ["ty gia", "xuat khau", "USD"],
    ["Vingroup", "bat dong san"],
]


def build(path: Path, days: int = 6, per_day: int = 14) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(path)
    conn.execute(SCHEMA)

    base = datetime(2026, 8, 4, 6, 0, tzinfo=UTC)
    rows = []
    n = 0
    for d in range(days):
        fetched = base - timedelta(days=d)
        for k in range(per_day):
            n += 1
            source, source_key, region = SOURCES[n % len(SOURCES)]
            topic, category = TOPICS[n % len(TOPICS)]
            impact = IMPACTS[n % len(IMPACTS)]
            tags = TAG_POOL[n % len(TAG_POOL)]
            # every third day repeats a headline across sources so clustering has work to do
            if k < 3:
                title_vi = f"Ngan hang Nha nuoc dieu chinh lai suat dieu hanh ngay {fetched:%d/%m}"
            else:
                title_vi = f"Tin thu {k} ngay {fetched:%d/%m/%Y} ve {tags[0]} va thi truong"
            analysis = ""
            if k == 0:
                analysis = json.dumps(
                    {
                        "boi_canh": "Boi canh gia dinh cho bai test so " + str(n),
                        "nguyen_nhan": "Nguyen nhan gia dinh.",
                        "muc_dich": "Muc dich gia dinh.",
                        "lien_he": "Lien he gia dinh.",
                    },
                    ensure_ascii=False,
                )
            rows.append(
                (
                    f"https://example.test/{source_key}/{n}",
                    source,
                    source_key,
                    region,
                    f"Fixture headline {n}",
                    title_vi,
                    fetched.strftime("%a, %d %b %Y %H:%M:%S +0700"),
                    category,
                    f"Tom tat gia dinh cho bai {n}. Noi dung nhac toi {tags[0]} va {tags[-1]}.",
                    json.dumps(
                        [f"Y chinh {i} cua bai {n}" for i in range(1, 4)], ensure_ascii=False
                    ),
                    json.dumps(tags, ensure_ascii=False),
                    1 if topic.startswith("Phap luat") else 0,
                    impact,
                    f"hash{n}",
                    1200 + n,
                    None,
                    fetched.isoformat(),
                    fetched.isoformat(),
                    0,
                    None,
                    (n % 10) + 1,
                    topic,
                    0,
                    0,
                    analysis,
                )
            )

    conn.executemany(
        """
        INSERT INTO articles (
            url, source, source_key, region, title, title_vi, published_at, category,
            summary_vi, key_points, tags, is_law_policy, impact_level, content_hash,
            content_length, html_snapshot, fetched_at, summarized_at, sent_telegram,
            telegram_sent_at, relevance, topic, is_advertorial, is_teaser, analysis
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        rows,
    )
    conn.commit()
    conn.close()


def main() -> int:
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "tests/fixtures/sample.db")
    build(target)
    print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
