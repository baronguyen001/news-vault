"""Cảnh báo khi số video YouTube tăng ít bất thường vào buổi tối."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# Cho phép chạy trực tiếp bằng ``python scripts/check_video_freshness.py``.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from newsvault.videos import connect  # noqa: E402

STATE_LIMIT = 30
BASELINE_DELTAS = 14


def _vietnam_timezone() -> timezone | ZoneInfo:
    """Trả về múi giờ Việt Nam, kể cả trên Windows chưa cài tzdata."""
    try:
        return ZoneInfo("Asia/Ho_Chi_Minh")
    except ZoneInfoNotFoundError:
        return timezone(timedelta(hours=7))


def _parse_now(value: str | None, vietnam_tz: timezone | ZoneInfo) -> datetime:
    """Đọc thời điểm test, hoặc lấy thời điểm hiện tại theo giờ Việt Nam."""
    if value is None:
        return datetime.now(vietnam_tz)
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=vietnam_tz)
    return parsed.astimezone(vietnam_tz)


def _load_state(path: Path) -> list[dict[str, int | str]]:
    """Đọc các mẫu hợp lệ theo thứ tự ngày tăng dần."""
    if not path.exists():
        return []
    data: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("state phải là danh sách mẫu")

    samples: list[dict[str, int | str]] = []
    for item in data:
        if not isinstance(item, dict):
            raise ValueError("state chứa mẫu không hợp lệ")
        day, total = item.get("date"), item.get("total")
        if not isinstance(day, str) or isinstance(total, bool) or not isinstance(total, int):
            raise ValueError("state chứa mẫu không hợp lệ")
        datetime.strptime(day, "%Y-%m-%d")
        samples.append({"date": day, "total": total})
    return sorted(samples, key=lambda sample: str(sample["date"]))[-STATE_LIMIT:]


def _save_state(path: Path, samples: list[dict[str, int | str]]) -> None:
    """Ghi state nhỏ, dễ xem và chỉ giữ lịch sử cần thiết."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(samples[-STATE_LIMIT:], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _upsert_sample(
    samples: list[dict[str, int | str]], day: str, total: int
) -> list[dict[str, int | str]]:
    """Ghi đè mẫu cùng ngày rồi trả danh sách theo thứ tự thời gian."""
    updated = [sample for sample in samples if sample["date"] != day]
    updated.append({"date": day, "total": total})
    return sorted(updated, key=lambda sample: str(sample["date"]))[-STATE_LIMIT:]


def _count_videos(db_path: Path) -> int:
    """Đếm mọi dòng trong bảng videos qua kết nối chỉ đọc của newsvault."""
    with connect(db_path) as conn:
        row = conn.execute("SELECT COUNT(*) FROM videos").fetchone()
    return int(row[0])


def _signed_delta(delta: int) -> str:
    """Hiển thị dấu cộng cho số không âm, không tạo chuỗi ``+-N``."""
    return f"{delta:+d}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", help="đường dẫn youtube_summarizer.db")
    parser.add_argument(
        "--state",
        type=Path,
        default=REPO_ROOT / "logs" / "video_freshness_state.json",
        help="file JSON lưu lịch sử đo",
    )
    parser.add_argument("--now", help="ISO datetime, chỉ dùng để test")
    return parser


def _configure_stdout() -> None:
    """Giữ thông báo tiếng Việt ghi được vào stdout Windows cũ."""
    with contextlib.suppress(AttributeError, OSError):
        sys.stdout.reconfigure(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    _configure_stdout()
    try:
        args = build_parser().parse_args(argv)
    except SystemExit:
        # Đây là tác vụ cảnh báo phụ; cả tham số sai cũng không được làm hỏng build.
        return 0
    db_value = args.db or os.environ.get("NEWSVAULT_VIDEO_DB")
    if not db_value:
        print("[video-freshness] bỏ qua — thiếu DB")
        return 0

    try:
        now = _parse_now(args.now, _vietnam_timezone())
    except ValueError as exc:
        print(f"[video-freshness] lỗi: {exc}")
        return 0

    if now.hour < 20:
        print("[video-freshness] chưa tới khung tối, bỏ qua")
        return 0

    try:
        total = _count_videos(Path(db_value))
        prior_samples = _load_state(args.state)
        today = now.date().isoformat()
        samples = _upsert_sample(prior_samples, today, total)
        _save_state(args.state, samples)
    except (OSError, ValueError, sqlite3.Error) as exc:
        print(f"[video-freshness] lỗi: {exc}")
        return 0

    earlier = [sample for sample in prior_samples if str(sample["date"]) < today]
    if not earlier:
        print("[video-freshness] chưa đủ lịch sử để so sánh (0 mẫu)")
        return 0

    previous_total = int(earlier[-1]["total"])
    delta_today = total - previous_total
    historic_deltas = [
        int(current["total"]) - int(previous["total"])
        for previous, current in zip(earlier, earlier[1:], strict=False)
    ][-BASELINE_DELTAS:]
    if len(historic_deltas) < 3:
        print(f"[video-freshness] chưa đủ lịch sử để so sánh ({len(historic_deltas)} mẫu)")
        return 0

    average = sum(historic_deltas) / len(historic_deltas)
    if average <= 0:
        print("[video-freshness] trung bình không dương, bỏ qua so sánh")
        return 0
    if delta_today < 0.5 * average:
        print(
            "[video-freshness-warn] "
            f"Tối nay chỉ {_signed_delta(delta_today)} video (trung bình {average:.0f}/tối gần đây) "
            "— kiểm tra youtube-summarizer có treo không."
        )
        return 0

    print(
        f"[video-freshness] ổn — {_signed_delta(delta_today)} video (trung bình {average:.0f})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
