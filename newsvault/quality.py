"""Thu số liệu chất lượng tuần từ các đường ống dữ liệu tùy chọn."""

from __future__ import annotations

import contextlib
import datetime as dt
import json
import os
import sqlite3
from collections.abc import Mapping
from pathlib import Path

from newsvault.videos import connect

_NEWS_DB = Path(
    os.environ.get("NEWSVAULT_DB", "E:/Indie Hacker/news-hunter/news_hunter.db")
)
_X_DB = Path(os.environ.get("NEWSVAULT_X_DB", "E:/x-pulse/x_pulse.db"))
_VIDEO_DB = Path(
    os.environ.get(
        "NEWSVAULT_VIDEO_DB",
        "E:/Indie Hacker/youtube-summarizer/youtube_summarizer.db",
    )
)
_QUALITY_JSON = Path(
    os.environ.get(
        "NEWSVAULT_QUALITY_JSON",
        "E:/Indie Hacker/news-hunter/out/quality_audit.json",
    )
)


def _next_day(day: str) -> str:
    """Trả về ngày kế tiếp để lọc an toàn các cột ISO-8601 có giờ."""
    return (dt.date.fromisoformat(day) + dt.timedelta(days=1)).isoformat()


def _number(value: object, places: int = 0) -> str:
    """Định dạng số theo quy ước dấu chấm nghìn, dấu phẩy thập phân tiếng Việt."""
    try:
        numeric = float(value or 0)
    except (TypeError, ValueError):
        numeric = 0.0
    if places == 0:
        return f"{round(numeric):,}".replace(",", ".")
    return f"{numeric:,.{places}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _percent(part: object, total: object) -> str:
    """Định dạng tỷ lệ một chữ số thập phân, kể cả khi mẫu số bằng không."""
    try:
        denominator = float(total or 0)
        numerator = float(part or 0)
    except (TypeError, ValueError):
        denominator = 0.0
        numerator = 0.0
    rate = numerator * 100 / denominator if denominator else 0.0
    return f"{_number(rate, 1)}%"


def _full_tone(part: object, total: object) -> str:
    """Chấm tỷ lệ bài đầy đủ: dưới 75% là lỗi vận hành rõ rệt."""
    rate = float(part or 0) * 100 / float(total or 1)
    # 90% cho phép một ít lỗi nguồn; dưới 75% nghĩa là phần lớn bài không dùng được.
    if rate >= 90:
        return "ok"
    if rate >= 75:
        return "warn"
    return "bad"


def _success_tone(part: object, total: object) -> str:
    """Chấm tỷ lệ xử lý thành công: video hỏng quá 10% cần được theo dõi."""
    rate = float(part or 0) * 100 / float(total or 1)
    # 95% là mức vận hành tốt; 90--95% cần xem log, thấp hơn là sự cố đáng kể.
    if rate >= 95:
        return "ok"
    if rate >= 90:
        return "warn"
    return "bad"


def _image_tone(part: object, total: object) -> str:
    """Chấm độ phủ ảnh, chỉ cảnh báo khi thiếu ảnh trên một nửa bài xuất bản."""
    rate = float(part or 0) * 100 / float(total or 1)
    # 70% đủ tốt cho một nhật báo; dưới 40% làm trang đọc nghèo hình ảnh rõ rệt.
    if rate >= 70:
        return "ok"
    if rate >= 40:
        return "warn"
    return "bad"


# Thang chấm của `scripts/quality_audit.py` là 1--5, KHÔNG phải 0--10.
#
# Đọc thẳng trong prompt của nó: "tu_nhien từ 1 đến 5: 5 = đọc như người Việt viết, 1 = dịch
# máy sượng". Ngưỡng đặt theo thang mười sẽ gọi mọi bản dịch là hỏng: lượt đo thật 18/08/2026
# ra 4,22 và 4,03 — tức khoảng 84% và 81% thang điểm, là tốt — mà thang mười sẽ tô đỏ cả hai.
SCORE_MAX = 5


def _score_tone(value: object) -> str:
    """Chấm điểm kiểm định dịch theo thang 1--5."""
    try:
        score = float(value)
    except (TypeError, ValueError):
        return ""
    # 4/5 trở lên là bản dịch dùng được; 3,5--4 cần rà lại; dưới 3,5 là không đạt.
    if score >= 4:
        return "ok"
    if score >= 3.5:
        return "warn"
    return "bad"


def _drift_tone(value: object) -> str:
    """Chấm độ lệch relevance tuyệt đối giữa hệ và kiểm định."""
    try:
        drift = abs(float(value))
    except (TypeError, ValueError):
        return ""
    # Lệch không quá một điểm là ổn; quá hai điểm làm sai đáng kể thứ tự ưu tiên.
    if drift <= 1:
        return "ok"
    if drift <= 2:
        return "warn"
    return "bad"


def _one(conn: sqlite3.Connection, sql: str, params: tuple[object, ...]) -> sqlite3.Row:
    """Lấy một dòng truy vấn, luôn có dòng rỗng khi bảng không có dữ liệu."""
    row = conn.execute(sql, params).fetchone()
    if row is None:
        raise sqlite3.DatabaseError("query returned no aggregate row")
    return row


def _news_hunter(start: str, end: str) -> dict[str, object]:
    """Thu chỉ số chất lượng thu thập bài viết của news-hunter."""
    upper = _next_day(end)
    # `content_length < 1200` là ngưỡng chẩn đoán thân bài đã được dùng trong vận hành.
    conn = connect(_NEWS_DB)  # Hàm dùng URI file:...?mode=ro, không bao giờ mở CSDL để ghi.
    try:
        totals = _one(
            conn,
            """
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN COALESCE(is_teaser, 0) = 0 THEN 1 ELSE 0 END) AS full,
                   SUM(CASE WHEN is_teaser = 1 THEN 1 ELSE 0 END) AS teaser,
                   SUM(CASE WHEN content_length < 1200 THEN 1 ELSE 0 END) AS short,
                   SUM(CASE WHEN TRIM(COALESCE(image_url, '')) <> '' THEN 1 ELSE 0 END)
                       AS images
            FROM articles
            WHERE fetched_at >= ? AND fetched_at < ?
            """,
            (start, upper),
        )
        total = totals["total"]
        full = totals["full"]
        teaser = totals["teaser"]
        short = totals["short"]
        images = totals["images"]
        missing_rows = conn.execute(
            """
            SELECT COALESCE(NULLIF(TRIM(source_key), ''), '?') AS source_key,
                   COUNT(*) AS total,
                   SUM(CASE WHEN is_teaser = 1 OR content_length < 1200 THEN 1 ELSE 0 END)
                       AS missing
            FROM articles
            WHERE fetched_at >= ? AND fetched_at < ?
            GROUP BY COALESCE(NULLIF(TRIM(source_key), ''), '?')
            HAVING COUNT(*) >= 3 AND missing > 0
            ORDER BY CAST(missing AS REAL) / COUNT(*) DESC, total DESC, source_key
            LIMIT 12
            """,
            (start, upper),
        ).fetchall()
        paywall_rows = conn.execute(
            """
            SELECT COALESCE(NULLIF(TRIM(source_key), ''), '?') AS source_key,
                   COUNT(*) AS count
            FROM retry_queue
            WHERE reason = 'hard_paywall' AND last_attempt_at >= ? AND last_attempt_at < ?
            GROUP BY COALESCE(NULLIF(TRIM(source_key), ''), '?')
            ORDER BY count DESC, source_key
            """,
            (start, upper),
        ).fetchall()
        cost = _one(
            conn,
            """
            SELECT COALESCE(SUM(cost_usd), 0) AS cost
            FROM gemini_usage
            WHERE ts >= ? AND ts < ?
            """,
            (start, upper),
        )["cost"]
        calls = _one(
            conn,
            """
            SELECT COUNT(*) AS calls
            FROM gemini_usage
            WHERE ts >= ? AND ts < ?
            """,
            (start, upper),
        )["calls"]
    finally:
        conn.close()

    return {
        "key": "news-hunter",
        "label": "News Hunter",
        "note": "Thu, lọc và tóm tắt tin từ các nguồn báo chí.",
        "stats": [
            {"label": "Bài thu được", "value": _number(total), "sub": "", "tone": ""},
            {
                "label": "Bài đầy đủ",
                "value": _number(full),
                "sub": _percent(full, total),
                "tone": _full_tone(full, total),
            },
            {"label": "Chỉ có teaser", "value": _number(teaser), "sub": "", "tone": ""},
            {"label": "Thân bài quá ngắn", "value": _number(short), "sub": "", "tone": ""},
            {
                "label": "Có ảnh",
                "value": _number(images),
                "sub": _percent(images, total),
                "tone": _image_tone(images, total),
            },
            # Ô này TỪNG hiện "0,0000 USD" và đó là một lời nói dối tử tế: tuần đo thử
            # 18/08/2026 có 465 lượt gọi mà `cost_usd` toàn 0, vì news-hunter đã chuyển sang
            # MK1 AI Hub — nhà cung cấp này không báo giá theo lượt. Số 0 đọc như "miễn phí",
            # trong khi sự thật là "không đo được". Hiện số lượt gọi, và chỉ nói tiền khi
            # thật sự có tiền.
            {
                "label": "Lượt gọi mô hình",
                "value": _number(calls),
                "sub": (
                    f"{_number(cost, 4)} USD" if float(cost or 0) > 0
                    else "nhà cung cấp không báo giá"
                ),
                "tone": "",
            },
        ],
        "tables": [
            {
                "title": "Nguồn hụt thân bài nhiều nhất",
                "cols": ["Nguồn", "Bài", "Hụt", "Tỉ lệ"],
                "rows": [
                    [
                        str(row["source_key"]),
                        _number(row["total"]),
                        _number(row["missing"]),
                        _percent(row["missing"], row["total"]),
                    ]
                    for row in missing_rows
                ],
            },
            {
                "title": "Tường trả phí cứng",
                "cols": ["Nguồn", "Số lần"],
                "rows": [[str(row["source_key"]), _number(row["count"])] for row in paywall_rows],
            },
        ],
    }


def _x_pulse(start: str, end: str) -> dict[str, object]:
    """Thu chỉ số chất lượng sàng lọc và xuất bản bài X."""
    conn = connect(_X_DB)
    try:
        totals = _one(
            conn,
            """
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN status = 'enriched' AND dup_of = '' THEN 1 ELSE 0 END)
                       AS published,
                   SUM(CASE WHEN dup_of <> '' THEN 1 ELSE 0 END) AS duplicates
            FROM posts
            WHERE day >= ? AND day <= ?
            """,
            (start, end),
        )
        total = totals["total"]
        published = totals["published"]
        duplicates = totals["duplicates"]
        images = _one(
            conn,
            """
            SELECT COUNT(*) AS count
            FROM posts
            WHERE day >= ? AND day <= ? AND status = 'enriched' AND dup_of = ''
              AND TRIM(COALESCE(media_url, '')) <> ''
            """,
            (start, end),
        )["count"]
        impacts = _one(
            conn,
            """
            SELECT COUNT(*) AS count
            FROM post_impact AS impact
            JOIN posts AS post ON post.id = impact.post_id
            WHERE post.day >= ? AND post.day <= ?
            """,
            (start, end),
        )["count"]
        authors = conn.execute(
            """
            SELECT COALESCE(NULLIF(TRIM(author), ''), '?') AS author, COUNT(*) AS count
            FROM posts
            WHERE day >= ? AND day <= ? AND status = 'enriched' AND dup_of = ''
            GROUP BY COALESCE(NULLIF(TRIM(author), ''), '?')
            ORDER BY count DESC, author
            LIMIT 10
            """,
            (start, end),
        ).fetchall()
        silent = conn.execute(
            """
            SELECT kind, ref, empty_streak, last_seen_at
            FROM target_health
            WHERE empty_streak >= 3
            ORDER BY empty_streak DESC, kind, ref
            """
        ).fetchall()
    finally:
        conn.close()

    return {
        "key": "x-pulse",
        "label": "X Pulse",
        "note": "Theo dõi, khử trùng và phân tích các bài đăng X.",
        "stats": [
            {"label": "Bài thu được", "value": _number(total), "sub": "", "tone": ""},
            {
                "label": "Bài xuất bản",
                "value": _number(published),
                "sub": _percent(published, total),
                "tone": _success_tone(published, total),
            },
            {
                "label": "Bị gộp vì trùng",
                "value": _number(duplicates),
                "sub": _percent(duplicates, total),
                "tone": "",
            },
            {
                "label": "Có ảnh",
                "value": _number(images),
                "sub": _percent(images, published),
                "tone": _image_tone(images, published),
            },
            {"label": "Phân tích tác động", "value": _number(impacts), "sub": "", "tone": ""},
        ],
        "tables": [
            {
                "title": "Nguồn cùng đưa tin nhiều nhất",
                "cols": ["Tài khoản", "Bài"],
                "rows": [[str(row["author"]), _number(row["count"])] for row in authors],
            },
            {
                "title": "Đích im lặng",
                "cols": ["Loại", "Đích", "Chuỗi trống", "Thấy lần cuối"],
                "rows": [
                    [
                        str(row["kind"] or ""),
                        str(row["ref"] or ""),
                        _number(row["empty_streak"]),
                        str(row["last_seen_at"] or ""),
                    ]
                    for row in silent
                ],
            },
        ],
    }


def _youtube(start: str, end: str) -> dict[str, object]:
    """Thu chỉ số xử lý video và các lỗi rớt video."""
    upper = _next_day(end)
    conn = connect(_VIDEO_DB)
    try:
        totals = _one(
            conn,
            """
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) AS success,
                   SUM(CASE WHEN junk = 1 THEN 1 ELSE 0 END) AS junk,
                   SUM(CASE WHEN telegram_sent = 1 THEN 1 ELSE 0 END) AS telegram
            FROM videos
            WHERE processed_at >= ? AND processed_at < ?
            """,
            (start, upper),
        )
        total = totals["total"]
        success = totals["success"]
        junk = totals["junk"]
        telegram = totals["telegram"]
        errors = conn.execute(
            """
            SELECT COALESCE(NULLIF(TRIM(error_message), ''), 'không rõ') AS reason,
                   COUNT(*) AS count
            FROM videos
            WHERE processed_at >= ? AND processed_at < ? AND success = 0
            GROUP BY COALESCE(NULLIF(TRIM(error_message), ''), 'không rõ')
            ORDER BY count DESC, reason
            LIMIT 8
            """,
            (start, upper),
        ).fetchall()
    finally:
        conn.close()

    return {
        "key": "youtube",
        "label": "YouTube",
        "note": "Tóm tắt video theo dõi từ các kênh đã chọn.",
        "stats": [
            {"label": "Video xử lý", "value": _number(total), "sub": "", "tone": ""},
            {
                "label": "Thành công",
                "value": _number(success),
                "sub": _percent(success, total),
                "tone": _success_tone(success, total),
            },
            {"label": "Lọc rác", "value": _number(junk), "sub": "", "tone": ""},
            {"label": "Đã gửi Telegram", "value": _number(telegram), "sub": "", "tone": ""},
        ],
        "tables": [
            {
                "title": "Lý do rớt",
                "cols": ["Lý do", "Số video"],
                "rows": [[str(row["reason"]), _number(row["count"])] for row in errors],
            }
        ],
    }


def _translation() -> dict[str, object]:
    """Đọc báo cáo kiểm định dịch do news-hunter xuất ra."""
    raw = json.loads(_QUALITY_JSON.read_text(encoding="utf-8"))
    summary = raw.get("summary")
    if not isinstance(summary, Mapping):
        raise ValueError("quality audit has no summary")

    topics = summary.get("theo_mang", {})
    if not isinstance(topics, Mapping):
        topics = {}
    rows: list[list[str]] = []
    for topic, values in sorted(topics.items()):
        if not isinstance(values, Mapping):
            continue
        rows.append(
            [
                str(topic),
                _number(values.get("tu_nhien"), 1),
                _number(values.get("chinh_xac"), 1),
                _number(values.get("lech"), 1),
            ]
        )

    natural = summary.get("tu_nhien_tb", 0)
    accurate = summary.get("chinh_xac_tb", 0)
    drift = summary.get("lech_tb", 0)
    return {
        "key": "translation",
        "label": "Chất lượng dịch",
        "note": "Kiểm định độc lập độ tự nhiên, chính xác và chấm relevance.",
        "stats": [
            {
                "label": "Tự nhiên trung bình",
                "value": _number(natural, 1),
                "sub": f"/{SCORE_MAX}",
                "tone": _score_tone(natural),
            },
            {
                "label": "Chính xác trung bình",
                "value": _number(accurate, 1),
                "sub": f"/{SCORE_MAX}",
                "tone": _score_tone(accurate),
            },
            {
                "label": "Lệch relevance",
                "value": _number(drift, 1),
                "sub": "âm là nới tay",
                "tone": _drift_tone(drift),
            },
            {"label": "Chấm quá cao", "value": _number(summary.get("cham_qua_cao")), "sub": "", "tone": ""},
            {"label": "Chấm quá thấp", "value": _number(summary.get("cham_qua_thap")), "sub": "", "tone": ""},
            {"label": "Bài kiểm định", "value": _number(summary.get("so_bai")), "sub": "", "tone": ""},
            {"label": "Lỗi kiểm định", "value": _number(summary.get("so_loi")), "sub": "", "tone": ""},
        ],
        "tables": [
            {
                "title": "Theo mảng",
                "cols": ["Mảng", "Tự nhiên", "Chính xác", "Lệch"],
                "rows": rows,
            }
        ],
    }


def collect(start: str, end: str) -> list[dict[str, object]]:
    """Số liệu chất lượng của bốn đường ống trong khoảng ngày [start, end].

    Trả về đúng thứ tự news-hunter, x-pulse, youtube, news-vault. Mỗi nguồn là tùy chọn:
    CSDL đang khóa, thiếu, hỏng hoặc có lược đồ chưa tương thích chỉ làm thiếu khối của nguồn đó.
    """
    systems: list[dict[str, object]] = []
    for reader in (_news_hunter, _x_pulse, _youtube):
        try:
            systems.append(reader(start, end))
        except (FileNotFoundError, OSError, sqlite3.Error, ValueError):
            continue
    with contextlib.suppress(FileNotFoundError, OSError, ValueError, json.JSONDecodeError):
        systems.append(_translation())
    return systems
