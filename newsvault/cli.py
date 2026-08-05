"""Command line interface for news-vault."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from newsvault import __version__, crypto, db
from newsvault.build import BuildOptions, build_site
from newsvault.exports import day_markdown, write_markdown

logger = logging.getLogger("newsvault")

DEFAULT_SITE = "Kho tin"
ENV_FILE = ".env"


def load_dotenv(path: Path = Path(ENV_FILE)) -> None:
    """Populate os.environ from a .env file without overwriting real environment values.

    Deliberately tiny: the project must never grow a dependency just to read five keys,
    and the secrets in this file are the reason it is git-ignored.
    """
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _resolve_password(explicit: str | None) -> str:
    """The site password, from the flag or NEWSVAULT_PASSWORD."""
    password = explicit or os.environ.get("NEWSVAULT_PASSWORD", "")
    if not password:
        raise SystemExit(
            "Thiếu mật khẩu: đặt NEWSVAULT_PASSWORD trong .env hoặc truyền --password."
        )
    return password


def _resolve_video_db(explicit: str | None) -> Path | None:
    """Path to the youtube-summarizer database, or None when the archive has no videos.

    Optional on purpose: news-vault has to keep building on a machine that only runs the
    news crawler, so an unset variable means "no videos", not a configuration error.
    """
    raw = explicit or os.environ.get("NEWSVAULT_VIDEO_DB", "")
    return Path(raw) if raw else None


def _resolve_db(explicit: str | None) -> Path:
    """Path to the news-hunter database."""
    raw = explicit or os.environ.get("NEWSVAULT_DB", "")
    if not raw:
        raise SystemExit("Thiếu đường dẫn CSDL: đặt NEWSVAULT_DB trong .env hoặc truyền --db.")
    return Path(raw)


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--db", help="đường dẫn news_hunter.db (mặc định: NEWSVAULT_DB)")
    parser.add_argument(
        "--video-db",
        help="đường dẫn youtube_summarizer.db (mặc định: NEWSVAULT_VIDEO_DB; bỏ trống = không có video)",
    )
    parser.add_argument(
        "--out", default=None, help="thư mục đầu ra (mặc định: NEWSVAULT_OUT hoặc docs)"
    )
    parser.add_argument("--password", help="mật khẩu site (mặc định: NEWSVAULT_PASSWORD)")


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        prog="newsvault",
        description="Dựng kho tin tĩnh có mật khẩu từ CSDL news-hunter.",
    )
    parser.add_argument("--version", action="version", version=f"news-vault {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true", help="log chi tiết")
    sub = parser.add_subparsers(dest="command", required=True)

    build_cmd = sub.add_parser("build", help="dựng site")
    _add_common(build_cmd)
    build_cmd.add_argument(
        "--date", action="append", default=[], help="dựng đúng ngày YYYY-MM-DD (lặp lại được)"
    )
    build_cmd.add_argument("--backfill", action="store_true", help="dựng mọi ngày có trong CSDL")
    build_cmd.add_argument("--force", action="store_true", help="bỏ qua cache, dựng lại tất cả")
    build_cmd.add_argument(
        "--no-brief", action="store_true", help="bỏ qua Gemini, dùng brief tự sinh"
    )
    build_cmd.add_argument(
        "--min-relevance", type=int, default=0, help="lọc bài dưới ngưỡng relevance"
    )
    build_cmd.add_argument("--site", default=None, help="tên site hiển thị")
    build_cmd.add_argument("--site-url", default=None, help="URL gốc của site")
    build_cmd.add_argument("--export-markdown", action="store_true", help="kèm export.md mỗi ngày")
    build_cmd.add_argument(
        "--feed-full",
        action="store_true",
        help="CẢNH BÁO: đưa tiêu đề bài vào RSS/JSON feed — feed là công khai, ai cũng đọc được.",
    )

    rekey_cmd = sub.add_parser("rekey", help="đổi mật khẩu: mã hoá lại toàn bộ (không gọi API)")
    _add_common(rekey_cmd)
    rekey_cmd.add_argument("--site", default=None)
    rekey_cmd.add_argument("--site-url", default=None)

    export_cmd = sub.add_parser("export", help="xuất một ngày ra Markdown")
    _add_common(export_cmd)
    export_cmd.add_argument("--date", required=True, help="ngày YYYY-MM-DD")
    export_cmd.add_argument("--to", help="ghi ra file (mặc định: stdout)")

    days_cmd = sub.add_parser("days", help="liệt kê các ngày có trong CSDL")
    _add_common(days_cmd)

    verify_cmd = sub.add_parser("verify", help="giải mã lại một ngày đã dựng để kiểm tra")
    verify_cmd.add_argument("--out", default=None)
    verify_cmd.add_argument("--date", required=True)
    verify_cmd.add_argument("--password")

    return parser


def _options_from(args: argparse.Namespace, *, force: bool, use_brief: bool) -> BuildOptions:
    out = args.out or os.environ.get("NEWSVAULT_OUT", "docs")
    return BuildOptions(
        db_path=_resolve_db(args.db),
        out_dir=Path(out),
        password=_resolve_password(args.password),
        days=tuple(getattr(args, "date", []) or ()),
        backfill=getattr(args, "backfill", False),
        site=args.site or os.environ.get("NEWSVAULT_SITE", DEFAULT_SITE),
        site_url=args.site_url or os.environ.get("NEWSVAULT_SITE_URL", ""),
        min_relevance=getattr(args, "min_relevance", 0),
        video_db_path=_resolve_video_db(getattr(args, "video_db", None)),
        api_key=os.environ.get("GEMINI_API_KEY") or None,
        cache_dir=Path(os.environ.get("NEWSVAULT_CACHE", ".cache")),
        use_brief=use_brief,
        feed_full=getattr(args, "feed_full", False),
        export_markdown=getattr(args, "export_markdown", False),
        force=force,
    )


def cmd_build(args: argparse.Namespace) -> int:
    """Run a normal build."""
    options = _options_from(args, force=args.force, use_brief=not args.no_brief)
    if options.feed_full:
        logger.warning("--feed-full bật: tiêu đề bài sẽ công khai trong feed.xml và feed.json")
    report = build_site(options)
    print(report.summary())
    return 0


def cmd_rekey(args: argparse.Namespace) -> int:
    """Re-encrypt every page with the current password, touching no external API."""
    args.backfill = True
    options = _options_from(args, force=True, use_brief=False)
    report = build_site(options)
    print("Đã mã hoá lại bằng mật khẩu mới.")
    print(report.summary())
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    """Write one day as Markdown."""
    conn = db.connect(_resolve_db(args.db))
    try:
        articles = db.load_day(conn, args.date)
    finally:
        conn.close()
    if not articles:
        raise SystemExit(f"Không có bài nào cho ngày {args.date}.")
    text = day_markdown(args.date, articles, site_url=os.environ.get("NEWSVAULT_SITE_URL", ""))
    if args.to:
        written = write_markdown(Path(args.to), text)
        print(f"Đã ghi {written} byte vào {args.to}")
    else:
        sys.stdout.write(text)
    return 0


def cmd_days(args: argparse.Namespace) -> int:
    """List the day keys present in the database."""
    conn = db.connect(_resolve_db(args.db))
    try:
        counts = db.counts_by_day(conn)
    finally:
        conn.close()
    for day in sorted(counts):
        print(f"{day}\t{counts[day]}")
    print(f"Tổng: {len(counts)} ngày, {sum(counts.values())} bài")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    """Decrypt a built day and report what is inside it."""
    out = Path(args.out or os.environ.get("NEWSVAULT_OUT", "docs"))
    target = out / "d" / args.date / "data.enc"
    if not target.exists():
        raise SystemExit(f"Chưa dựng ngày {args.date}: không thấy {target}")
    try:
        data = crypto.decrypt_payload(target.read_bytes(), _resolve_password(args.password))
    except crypto.DecryptionError as exc:
        raise SystemExit(f"Không giải mã được: {exc}. Sai mật khẩu?") from None
    if not isinstance(data, dict):
        raise SystemExit("Payload không đúng định dạng.")
    articles = data.get("articles", [])
    print(f"ngày      : {data.get('day')}")
    print(f"số bài    : {len(articles)}")
    print(f"brief     : {len(data.get('brief', []))} gạch đầu dòng")
    print(f"luồng tin : {len(data.get('clusters', []))}")
    print(f"chuyên mục: {len(data.get('categories', []))}")
    if articles:
        print(f"bài đầu   : {articles[0].get('t', '')[:80]}")
    return 0


def _force_utf8_output() -> None:
    """Make Vietnamese output survive a legacy Windows console.

    The default cp1252 console encoding raises UnicodeEncodeError on the first accented
    character, which would kill the nightly scheduled build after it had already done all
    of its work.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    _force_utf8_output()
    load_dotenv()
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    handlers = {
        "build": cmd_build,
        "rekey": cmd_rekey,
        "export": cmd_export,
        "days": cmd_days,
        "verify": cmd_verify,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
