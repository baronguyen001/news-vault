"""Read-only health review used by the weekly Codex improvement automation.

The report intentionally contains evidence and recommended actions, never credentials or
article bodies.  Codex uses it as a stable hand-off before deciding whether a repair is
safe to implement and deploy.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sqlite3
import subprocess
from pathlib import Path
from typing import Any  # noqa: TC003 - part of the public manifest type

ROOTS = {
    "x-pulse": Path("E:/x-pulse"),
    "news-hunter": Path("E:/Indie Hacker/news-hunter"),
    "youtube-summarizer": Path("E:/Indie Hacker/youtube-summarizer"),
    "news-vault": Path("E:/news-vault"),
    "facebook-digest": Path("E:/facebook-digest"),
    "substack-digest": Path("E:/substack-digest"),
}
DATABASES = {
    "x-pulse": ROOTS["x-pulse"] / "x_pulse.db",
    "news-hunter": ROOTS["news-hunter"] / "news_hunter.db",
    "youtube-summarizer": ROOTS["youtube-summarizer"] / "youtube_summarizer.db",
    "facebook-digest": ROOTS["facebook-digest"] / "facebook_digest.db",
    "substack-digest": ROOTS["substack-digest"] / "substack_digest.db",
}


def _connect(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)


def _one(conn: sqlite3.Connection, sql: str, params: tuple[object, ...]) -> tuple[Any, ...]:
    return tuple(conn.execute(sql, params).fetchone() or ())


def _db_health(name: str, path: Path, since: str) -> dict[str, int]:
    if not path.exists():
        return {"database_missing": 1}
    conn = _connect(path)
    try:
        if name == "news-hunter":
            total, missing_image, short, unresolved = _one(
                conn,
                """SELECT (SELECT count(*) FROM articles WHERE fetched_at >= ?),
                          (SELECT count(*) FROM articles WHERE fetched_at >= ? AND trim(coalesce(image_url,''))=''),
                          (SELECT count(*) FROM articles WHERE fetched_at >= ? AND length(trim(coalesce(summary_vi,''))) < 140),
                          (SELECT count(*) FROM retry_queue WHERE resolved=0)""",
                (since, since, since),
            )
            return {"total": total, "missing_image": missing_image, "short_summary": short,
                    "unresolved_retry": unresolved}
        if name == "facebook-digest":
            total, missing_image, short = _one(
                conn,
                """SELECT count(*), sum(trim(coalesce(image_url,''))=''),
                          sum(length(trim(coalesce(summary_text,''))) < 140)
                   FROM feed_posts WHERE scraped_at >= ?""",
                (since,),
            )
            return {"total": total, "missing_image": missing_image or 0, "short_summary": short or 0}
        if name == "substack-digest":
            total, missing_image, missing_summary = _one(
                conn,
                """SELECT count(*), sum(trim(coalesce(image_url,''))=''),
                          sum(trim(coalesce(summary_text,''))='')
                   FROM posts WHERE fetched_at >= ?""",
                (since,),
            )
            return {"total": total, "missing_image": missing_image or 0,
                    "missing_summary": missing_summary or 0}
        if name == "youtube-summarizer":
            total, failed, retryable = _one(
                conn,
                """SELECT count(*), sum(success=0),
                          sum(success=0 AND coalesce(permanent_fail,0)=0)
                   FROM videos WHERE processed_at >= ?""",
                (since,),
            )
            return {"total": total, "failed": failed or 0, "retryable": retryable or 0}
        if name == "x-pulse":
            total, missing_summary, short = _one(
                conn,
                """SELECT count(*), sum(s.post_id IS NULL),
                          sum(length(trim(coalesce(s.summary_vi,''))) < 140)
                   FROM posts p LEFT JOIN post_summaries s ON s.post_id=p.id
                   WHERE p.day >= ? AND p.status='enriched'""",
                (since[:10],),
            )
            return {"total": total, "missing_summary": missing_summary or 0,
                    "short_summary": short or 0}
    finally:
        conn.close()
    return {}


def _git_state(root: Path) -> dict[str, Any]:
    result = subprocess.run(["git", "-C", str(root), "status", "--porcelain"],
                            text=True, capture_output=True, check=False)
    return {"dirty": bool(result.stdout.strip()), "entries": len(result.stdout.splitlines())}


def build_manifest(*, now: dt.datetime | None = None, days: int = 21) -> dict[str, Any]:
    now = now or dt.datetime.now(dt.UTC)
    since = (now - dt.timedelta(days=days)).isoformat()
    repositories: dict[str, Any] = {}
    findings: list[dict[str, Any]] = []
    for name, root in ROOTS.items():
        entry: dict[str, Any] = {"path": str(root), "git": _git_state(root)}
        if name in DATABASES:
            entry["health"] = _db_health(name, DATABASES[name], since)
            health = entry["health"]
            for key in ("unresolved_retry", "retryable", "missing_summary"):
                if health.get(key, 0):
                    findings.append({"fingerprint": f"{name}:{key}", "component": name,
                                     "severity": "high", "evidence": health[key],
                                     "action": "repair-and-verify"})
        repositories[name] = entry
    return {"schema": 1, "generated_at": now.isoformat(), "window_days": days,
            "repositories": repositories, "findings": findings,
            "deployment": {"status": "review-required", "rollback": "not-run"}}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the autonomous news-pipeline review manifest")
    parser.add_argument("--days", type=int, default=21)
    parser.add_argument("--out", type=Path, default=Path("out/autonomous-review.json"))
    args = parser.parse_args(argv)
    manifest = build_manifest(days=max(1, args.days))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"findings": len(manifest["findings"]), "out": str(args.out)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
