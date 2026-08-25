"""Kiểm thử script cảnh báo độ mới video YouTube buổi tối."""

from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path

SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "check_video_freshness.py"
SPEC = importlib.util.spec_from_file_location("check_video_freshness", SCRIPT_PATH)
assert SPEC and SPEC.loader
freshness = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(freshness)


def _make_db(tmp_path: Path, total: int) -> Path:
    path = tmp_path / "videos.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE videos (id INTEGER PRIMARY KEY)")
        conn.executemany("INSERT INTO videos DEFAULT VALUES", [()] * total)
    return path


def _write_state(path: Path, totals: list[int]) -> None:
    samples = [
        {"date": f"2026-08-{day:02d}", "total": total}
        for day, total in enumerate(totals, start=1)
    ]
    path.write_text(json.dumps(samples), encoding="utf-8")


def test_skips_before_evening_without_reading_db_or_writing_state(tmp_path: Path, capsys):
    state = tmp_path / "state.json"

    code = freshness.main(
        ["--db", str(tmp_path / "missing.db"), "--state", str(state), "--now", "2026-08-05T14:15:00"]
    )

    assert code == 0
    assert capsys.readouterr().out == "[video-freshness] chưa tới khung tối, bỏ qua\n"
    assert not state.exists()


def test_records_sample_without_enough_history(tmp_path: Path, capsys):
    db_path = _make_db(tmp_path, 10)
    state = tmp_path / "state.json"

    code = freshness.main(["--db", str(db_path), "--state", str(state), "--now", "2026-08-05T21:15:00"])

    assert code == 0
    assert "chưa đủ lịch sử" in capsys.readouterr().out
    assert json.loads(state.read_text(encoding="utf-8")) == [{"date": "2026-08-05", "total": 10}]


def test_reports_normal_evening_instead_of_warning(tmp_path: Path, capsys):
    db_path = _make_db(tmp_path, 140)
    state = tmp_path / "state.json"
    _write_state(state, [100, 110, 120, 130])

    code = freshness.main(["--db", str(db_path), "--state", str(state), "--now", "2026-08-05T21:15:00"])

    assert code == 0
    output = capsys.readouterr().out
    assert output.startswith("[video-freshness] ổn — +10 video")
    assert "[video-freshness-warn] " not in output


def test_warns_when_evening_video_growth_is_unusually_low(tmp_path: Path, capsys):
    db_path = _make_db(tmp_path, 130)
    state = tmp_path / "state.json"
    _write_state(state, [100, 110, 120, 130])

    code = freshness.main(["--db", str(db_path), "--state", str(state), "--now", "2026-08-05T21:15:00"])

    assert code == 0
    assert capsys.readouterr().out.startswith("[video-freshness-warn] ")


def test_second_run_same_day_overwrites_existing_sample(tmp_path: Path, capsys):
    db_path = _make_db(tmp_path, 140)
    state = tmp_path / "state.json"
    _write_state(state, [100, 110, 120, 130])

    freshness.main(["--db", str(db_path), "--state", str(state), "--now", "2026-08-05T21:15:00"])
    with sqlite3.connect(db_path) as conn:
        conn.executemany("INSERT INTO videos DEFAULT VALUES", [()] * 3)
    freshness.main(["--db", str(db_path), "--state", str(state), "--now", "2026-08-05T21:30:00"])

    samples = json.loads(state.read_text(encoding="utf-8"))
    today = [sample for sample in samples if sample["date"] == "2026-08-05"]
    assert today == [{"date": "2026-08-05", "total": 143}]
    assert len(samples) == 5
