"""Build the whole static site: read the database, analyse, encrypt, render.

This is the orchestration layer. Every step it calls lives in a focused module; the value
here is the wiring, the incremental-rebuild logic and the guarantee that a failure in an
optional feature (brief, audio) never stops the site from being generated.
"""

from __future__ import annotations

import base64
import datetime as dt
import functools
import hashlib
import json
import logging
import shutil
import sqlite3
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from newsvault import __version__, charts, crypto, db, feeds, payload, render
from newsvault import curated as curated_db
from newsvault import posts as posts_db
from newsvault import videos as videos_db
from newsvault.blindspot import blindspots
from newsvault.brief import (
    LLM_SOURCES,
    BriefResult,
    brief_provider_issue,
    fallback_brief,
    generate_brief,
    looks_like_refusal,
)
from newsvault.cluster import cluster_articles
from newsvault.curated import CuratedItem
from newsvault.entities import Entity, EntityIndex, build_entity_index
from newsvault.exports import day_markdown, write_markdown
from newsvault.model import Article
from newsvault.posts import Post
from newsvault.sources import PAID
from newsvault.text import slugify
from newsvault.trends import trending_terms
from newsvault.videos import Video

logger = logging.getLogger(__name__)

# How much history the trend and blind-spot baselines need behind the first built day.
HISTORY_DAYS = 30

# Entities need a wide window to be meaningful, and entity pages are only worth
# generating for names that actually recur.
ENTITY_MIN_MENTIONS = 3
MAX_ENTITY_PAGES = 150

STATE_FILE = ".build-state.json"


@dataclass(frozen=True, slots=True)
class BuildOptions:
    """Everything one `newsvault build` invocation needs."""

    db_path: Path
    out_dir: Path
    password: str
    video_db_path: Path | None = None
    x_db_path: Path | None = None
    days: tuple[str, ...] = ()
    backfill: bool = False
    site: str = "Kho tin"
    site_url: str = ""
    min_relevance: int = 0
    cache_dir: Path = Path(".cache")
    use_brief: bool = True
    feed_full: bool = False
    export_markdown: bool = False
    force: bool = False


@dataclass
class BuildReport:
    """What a build actually did — printed by the CLI and asserted by tests."""

    days_built: list[str] = field(default_factory=list)
    days_skipped: list[str] = field(default_factory=list)
    entity_pages: int = 0
    week_pages: int = 0
    index_shards: int = 0
    videos_included: int = 0
    curated_pages: int = 0
    posts_included: int = 0
    brief_source: dict[str, str] = field(default_factory=dict)
    provider_issues: list[str] = field(default_factory=list)
    bytes_written: int = 0

    def summary(self) -> str:
        """One-line human summary."""
        line = (
            f"{len(self.days_built)} ngày dựng, {len(self.days_skipped)} bỏ qua (không đổi), "
            f"{self.entity_pages} trang thực thể, {self.week_pages} trang tuần, "
            f"{self.index_shards} shard tìm kiếm, {self.videos_included} video, "
            f"{self.curated_pages} bài phân tích sâu, {self.posts_included} bài X"
        )
        # Brief tụt xuống bản fallback (xếp theo điểm, không qua LLM) là một sự cố CHẤT
        # LƯỢNG chứ không phải lỗi build — trước đây `brief_source` được ghi lại nhưng
        # không in ra đâu cả, nên suốt 07-08/08/2026 brief hỏng mà dòng tổng kết vẫn đẹp.
        degraded = sorted(
            day for day, src in self.brief_source.items() if src not in LLM_SOURCES
        )
        if degraded:
            line += f" | ⚠️ brief fallback {len(degraded)} ngày: {', '.join(degraded[:5])}"
        for issue in self.provider_issues:
            line += f" | ⚠️ {issue}"
        return line


# --------------------------------------------------------------------------------------
# state: incremental rebuilds
# --------------------------------------------------------------------------------------


def _load_state(out_dir: Path) -> dict[str, str]:
    """Read the per-page content hashes from the previous build."""
    path = out_dir / STATE_FILE
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.warning("build state unreadable, rebuilding everything")
        return {}
    hashes = data.get("hashes")
    return hashes if isinstance(hashes, dict) else {}


def _save_state(out_dir: Path, hashes: Mapping[str, str], salt: bytes) -> None:
    """Persist content hashes and the site salt.

    The salt is deliberately stable across builds: a fresh salt would change every
    single .enc byte and turn a daily commit into a full-repository diff. A PBKDF2
    salt is not a secret, it only has to be unique per site.
    """
    body = {
        "v": 1,
        "salt": base64.b64encode(salt).decode("ascii"),
        "hashes": dict(sorted(hashes.items())),
    }
    (out_dir / STATE_FILE).write_text(
        json.dumps(body, ensure_ascii=False, indent=0, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _site_salt(out_dir: Path) -> bytes:
    """Reuse the site salt when one exists, otherwise mint a new one."""
    path = out_dir / STATE_FILE
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8")).get("salt")
            if isinstance(raw, str):
                salt = base64.b64decode(raw)
                if len(salt) == crypto.SALT_BYTES:
                    return salt
        except (OSError, ValueError):
            pass
    return crypto.new_salt()


def _templates_root() -> Path:
    """Where the Jinja templates live. Separate so a test can point it somewhere else."""
    return Path(__file__).parent / "templates"


@functools.cache
def _shell_digest() -> str:
    """Hash of the HTML shell every page is rendered into.

    Hashing the payload alone is not enough to decide a page is unchanged. Edit a template -
    add a script tag, change the gate markup - and every payload still hashes identically, so
    not one already-built page is rewritten and the change silently reaches only whichever
    pages happened to have new content that run. Shipping a gate checkbox this way updated the
    home page and none of the 120 day pages. Folding the shell into the key makes a template
    edit invalidate the whole archive, which is what editing a template means.
    """
    blob = "".join(
        path.name + "\n" + path.read_text(encoding="utf-8")
        for path in sorted(_templates_root().glob("*.j2"))
    )
    # The version is stamped into every page's inline config, so it is part of the rendered
    # HTML too. Without it a release left 209 pages claiming the previous version while the
    # manifest beside them claimed the new one.
    return hashlib.sha256((blob + "\x00" + __version__).encode("utf-8")).hexdigest()[:16]


def _digest(data: object, *, with_shell: bool = False) -> str:
    """Stable content hash of a payload, used to skip unchanged pages.

    Pages that render an `index.html` pass `with_shell=True`; the encrypted-only search shards
    have no HTML and must not churn when a template changes.
    """
    blob = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if with_shell:
        blob += "\x00shell:" + _shell_digest()
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


# --------------------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------------------


def _day_anchor(day: str) -> str:
    """Deterministic 'generated_at' for a day page.

    Using the real clock here would rewrite every backfilled payload on every build.
    """
    return f"{day}T23:59:59+07:00"


def _iso_week(day: str) -> tuple[str, str, str]:
    """Return (week key, monday, sunday) for a 'YYYY-MM-DD' day."""
    date = dt.date.fromisoformat(day)
    year, week, _ = date.isocalendar()
    monday = date - dt.timedelta(days=date.isoweekday() - 1)
    return f"{year}-W{week:02d}", monday.isoformat(), (monday + dt.timedelta(days=6)).isoformat()


def _shift(day: str, delta: int) -> str:
    """Day key shifted by `delta` days."""
    return (dt.date.fromisoformat(day) + dt.timedelta(days=delta)).isoformat()


def _day_charts(articles: Sequence[Article]) -> dict[str, str]:
    """The three server-rendered SVG charts shown on a day page.

    The source chart is a full bar chart rather than a donut on purpose: a donut folds
    everything past its sixth slice into "Khác", and the point of this panel is to show
    every source collected that day, paid ones marked.
    """
    topics: dict[str, int] = {}
    sources: dict[str, int] = {}
    impacts: dict[str, int] = {}
    paid_sources: set[str] = set()
    for article in articles:
        topics[article.topic or "Khác"] = topics.get(article.topic or "Khác", 0) + 1
        source = article.source or "?"
        sources[source] = sources.get(source, 0) + 1
        if article.tier == PAID:
            paid_sources.add(source)
        impacts[article.impact_level or "không rõ"] = (
            impacts.get(article.impact_level or "không rõ", 0) + 1
        )
    return {
        "topics": charts.bar_chart(
            [(k, float(v)) for k, v in topics.items()], title="Tin theo chủ đề"
        ),
        "sources": charts.bar_chart(
            [(k, float(v)) for k, v in sources.items()],
            title=f"Tất cả {len(sources)} nguồn thu thập",
            max_bars=max(1, len(sources)),
            emphasis=paid_sources,
            emphasis_label="Trả phí",
            rest_label="Miễn phí",
        ),
        "impact": charts.donut_chart(
            [(k, float(v)) for k, v in impacts.items()], title="Mức tác động"
        ),
    }


def _categories(articles: Sequence[Article]) -> list[dict[str, object]]:
    """Category cards for the day page.

    The card carries the topic slug as its `key`; the front end maps that to a fixed
    icon. Nothing here is generated per day, so the grid costs no API call and looks the
    same in the archive as it does today.
    """
    counts: dict[str, int] = {}
    paid: dict[str, int] = {}
    labels: dict[str, str] = {}
    for article in articles:
        label = article.topic or "Khác"
        key = slugify(label)
        counts[key] = counts.get(key, 0) + 1
        if article.tier == PAID:
            paid[key] = paid.get(key, 0) + 1
        labels[key] = label

    return [
        {
            "key": key,
            "label": labels[key],
            "count": count,
            "paid": paid.get(key, 0),
        }
        for key, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    ]


def _brief_fingerprint(articles: Sequence[Article], posts: Sequence[Post]) -> str:
    """Vân tay của TOÀN BỘ tin trong ngày mà brief được phép đọc.

    Lấy trên cả ngày chứ không chỉ trên phần lọt vào prompt: nếu chỉ băm top-12 thì một bài
    mới điểm thấp sẽ không đổi vân tay, và ta lại rơi đúng vào cái bẫy "brief không biết có
    tin mới" mà hàm này sinh ra để chặn.

    Chỉ gồm bài báo + bài X vì đó đúng là hai thứ đi vào prompt. Cố tình KHÔNG gồm video và
    bài phân tích sâu: chúng không vào prompt nên không thể làm đổi năm dòng brief, băm kèm
    chỉ tạo ra những lượt gọi LLM sinh lại y hệt bản cũ.
    """
    digest = hashlib.sha256()
    for key in sorted(f"a:{article.id}" for article in articles):
        digest.update(key.encode("utf-8"))
        digest.update(b"\x00")
    for key in sorted(f"p:{post.id}" for post in posts):
        digest.update(key.encode("utf-8"))
        digest.update(b"\x00")
    return digest.hexdigest()[:16]


def _brief_for(
    day: str,
    articles: Sequence[Article],
    options: BuildOptions,
    posts: Sequence[Post] = (),
) -> BriefResult:
    """The day's five bullets, cached on disk and degrading to a deterministic fallback.

    The cache is what makes a rebuild free and a re-key lossless: without it, changing the
    site password would silently replace every real brief with the fallback text.

    ⚠️ Trước 16/08/2026 khoá cache CHỈ là ngày, không có vân tay nội dung. Mà một ngày được
    dựng NHIỀU LẦN: 14:00, 17:26, 21:15 — cộng thêm job retry 19:00 của news-hunter và ba
    khe thu của x-pulse đổ tin vào giữa chừng. Hệ quả đo được: brief ngày 14/08 ghi lúc
    14:00, trong khi 5 bài về lúc 17:00 và 19:00 chưa bao giờ được tóm tắt; bài X của ngày
    15/08 tăng 100 → 114 mà "Tóm tắt ngày" không đổi một chữ. Nói cách khác, phần trên cùng
    của trang đông cứng ở lần dựng ĐẦU TIÊN trong ngày.
    """
    cache = Path(options.cache_dir) / "brief" / f"{day}.json"
    fingerprint = _brief_fingerprint(articles, posts)
    if cache.exists():
        try:
            stored = json.loads(cache.read_text(encoding="utf-8"))
            bullets = tuple(str(b) for b in stored.get("bullets", ()) if str(b).strip())
            cached_fp = str(stored.get("fp", ""))
            if bullets and looks_like_refusal(bullets):
                # ĐÂY là chỗ làm hệ thống tự lành. Ngày 09/08/2026 có một câu từ chối được
                # cache kèm nhãn "aihub"; nếu chỉ chặn ở lúc GHI thì file rác đã nằm trên đĩa
                # vẫn được đọc lại mãi mãi và phải xoá tay. Bỏ qua cache ⇒ lần dựng kế tiếp
                # sinh lại brief thật rồi ghi đè.
                logger.warning("brief cache của %s là câu từ chối, sinh lại", day)
            elif bullets and cached_fp and cached_fp != fingerprint:
                logger.info("brief của %s: ngày đã có thêm tin, sinh lại", day)
            elif bullets:
                if not cached_fp:
                    # File từ thời chưa có vân tay. NHẬN NUÔI thay vì sinh lại: job đêm chạy
                    # `--backfill` nên `_brief_for` được gọi cho cả 129 ngày trong kho, và
                    # coi mọi file cũ là hỏng sẽ nổ ra 129 lượt gọi LLM ngay lần dựng kế
                    # tiếp — đủ để build trượt sang cửa sổ của lần chạy sau. Đóng dấu vân
                    # tay hiện tại rồi đi tiếp; từ lần dựng sau nó so sánh bình thường.
                    _write_brief_cache(cache, list(bullets), str(stored.get("source", "")),
                                       fingerprint)
                return BriefResult(
                    bullets=bullets, source=str(stored.get("source", "cache")), error=""
                )
        except (OSError, ValueError):
            logger.warning("brief cache unreadable for %s", day)

    result = (
        fallback_brief(articles, posts=posts)
        if not options.use_brief
        else generate_brief(day, articles, posts=posts)
    )
    # Cache anything a language model actually wrote, whichever engine wrote it. Pinning
    # this to "gemini" meant a hub-written brief was regenerated on every single build.
    # Thắt lưng lẫn dây đeo: `generate_brief` lẽ ra đã chặn câu từ chối rồi, nhưng cache là
    # thứ sống lâu nhất trong hệ thống — một dòng rác lọt vào đây là hỏng vĩnh viễn.
    if result.source in LLM_SOURCES and result.bullets and not looks_like_refusal(result.bullets):
        _write_brief_cache(cache, list(result.bullets), result.source, fingerprint)
    return result


def _write_brief_cache(cache: Path, bullets: list[str], source: str, fingerprint: str) -> None:
    """Ghi cache brief. Lỗi ghi KHÔNG được làm chết build — brief đã có trong tay rồi."""
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(
            json.dumps(
                {"bullets": bullets, "source": source, "fp": fingerprint},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    except OSError as exc:
        logger.warning("không ghi được brief cache %s: %s", cache.name, exc)


# --------------------------------------------------------------------------------------
# the build
# --------------------------------------------------------------------------------------


def _load_videos(options: BuildOptions) -> dict[str, list[Video]]:
    """Group every summarised video by day, or return nothing at all on any problem.

    The video database belongs to another tool that keeps writing while this build runs.
    It is optional by design: a missing file, a schema this code does not recognise or a
    lock must degrade to an archive without videos, never to a failed nightly build.
    """
    if not options.video_db_path:
        return {}
    try:
        conn = videos_db.connect(options.video_db_path)
    except (FileNotFoundError, sqlite3.Error) as err:
        logger.warning("video database unavailable (%s); building without videos", err)
        return {}
    try:
        grouped: dict[str, list[Video]] = {}
        for video in videos_db.load_all(conn):
            grouped.setdefault(video.day, []).append(video)
        return grouped
    except sqlite3.Error as err:
        logger.warning("video database unreadable (%s); building without videos", err)
        return {}
    finally:
        conn.close()


def _load_posts(options: BuildOptions) -> dict[str, list[Post]]:
    """Group every publishable X post by day, or return nothing at all on any problem.

    Same contract as `_load_videos` and `_load_curated`, and for the same reason: the
    x-pulse database belongs to a scraper that runs three times a day and may be mid-write
    when the nightly build starts. A missing file, a missing view or a lock degrades to an
    archive without the X section, never to a failed build.
    """
    if not options.x_db_path:
        return {}
    try:
        conn = posts_db.connect(options.x_db_path)
    except (FileNotFoundError, sqlite3.Error) as err:
        logger.warning("x-pulse database unavailable (%s); building without X posts", err)
        return {}
    try:
        return posts_db.group_by_day(posts_db.load_all(conn))
    except sqlite3.Error as err:
        logger.warning("x-pulse database unreadable (%s); building without X posts", err)
        return {}
    finally:
        conn.close()


def _load_video_library(options: BuildOptions) -> list[Video]:
    """Load successful and retryable videos for the channel library."""
    if not options.video_db_path:
        return []
    try:
        conn = videos_db.connect(options.video_db_path)
    except (FileNotFoundError, sqlite3.Error) as err:
        logger.warning("video database unavailable (%s); building empty video library", err)
        return []
    try:
        return videos_db.load_library(conn)
    except sqlite3.Error as err:
        logger.warning("video library unreadable (%s); building empty video library", err)
        return []
    finally:
        conn.close()


def _load_curated(options: BuildOptions) -> list[CuratedItem]:
    """Every published deep-dive analysis, newest first, or nothing at all on any problem.

    Same contract as `_load_videos`: the curated table lives in a database another tool
    keeps writing to, and it did not exist at all before the curated pipeline shipped. A
    missing file, a missing table or a lock must degrade to a site without the section,
    never to a failed nightly build.
    """
    if not options.video_db_path:
        return []
    try:
        conn = videos_db.connect(options.video_db_path)
    except (FileNotFoundError, sqlite3.Error) as err:
        logger.warning("curated database unavailable (%s); building without deep dives", err)
        return []
    try:
        return curated_db.load_all(conn)
    except sqlite3.Error as err:
        logger.warning("curated table unreadable (%s); building without deep dives", err)
        return []
    finally:
        conn.close()


def select_days(conn, options: BuildOptions, *, extra_days: Iterable[str] = ()) -> list[str]:
    """Resolve which day keys this invocation should build."""
    available = sorted(set(db.available_days(conn)) | set(extra_days))
    if options.days:
        wanted = [d for d in options.days if d in available]
        missing = sorted(set(options.days) - set(wanted))
        if missing:
            logger.warning("no articles for %s", ", ".join(missing))
        return wanted
    if options.backfill:
        return available
    return available[-1:]


def build_site(options: BuildOptions) -> BuildReport:
    """Build every requested page into `options.out_dir`."""
    report = BuildReport()
    out_dir = Path(options.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    salt = _site_salt(out_dir)
    state = {} if options.force else _load_state(out_dir)
    fresh: dict[str, str] = {}

    meta = render.SiteMeta(
        site=options.site,
        version=__version__,
        kdf_iterations=crypto.DEFAULT_ITERATIONS,
        site_url=options.site_url,
    )

    videos_by_day = _load_videos(options)
    library_videos = _load_video_library(options)
    curated_items = _load_curated(options)
    curated_by_day = curated_db.group_by_day(curated_items)
    posts_by_day = _load_posts(options)

    conn = db.connect(options.db_path)
    try:
        target_days = select_days(
            conn, options, extra_days=set(videos_by_day) | set(curated_by_day) | set(posts_by_day)
        )
        if not target_days:
            logger.warning("nothing to build")
            return report

        # A day exists when it has articles OR videos OR a deep dive: the YouTube archive
        # reaches back months further than the news database, and a curated analysis made
        # on a quiet news day would otherwise have no day page to be linked from.
        all_days = sorted(
            set(db.available_days(conn))
            | set(videos_by_day)
            | set(curated_by_day)
            | set(posts_by_day)
        )
        counts = db.counts_by_day(conn)
        for day, day_videos in videos_by_day.items():
            counts[day] = counts.get(day, 0) + len(day_videos)
        for day, day_curated in curated_by_day.items():
            counts[day] = counts.get(day, 0) + len(day_curated)
        for day, day_posts in posts_by_day.items():
            counts[day] = counts.get(day, 0) + len(day_posts)

        # One wide load covers the built days plus the baseline window behind them.
        history_start = _shift(min(target_days), -HISTORY_DAYS)
        loaded = db.load_range(
            conn, history_start, max(target_days), min_relevance=options.min_relevance
        )
        by_day: dict[str, list[Article]] = {}
        for article in loaded:
            by_day.setdefault(article.day, []).append(article)
        for articles in by_day.values():
            articles.sort(key=lambda a: (-a.score, a.title_vi))

        entity_index = build_entity_index(loaded, min_mentions=ENTITY_MIN_MENTIONS)
        entity_map = entity_index.by_article

        index_by_month: dict[str, list[dict[str, object]]] = {}
        weeks: dict[str, list[str]] = {}

        for day in target_days:
            articles = by_day.get(day, [])
            day_videos = videos_by_day.get(day, [])
            day_curated = curated_by_day.get(day, [])
            day_posts = posts_by_day.get(day, [])
            if not articles and not day_videos and not day_curated and not day_posts:
                continue

            brief = _brief_for(day, articles, options, posts=day_posts)
            report.brief_source[day] = brief.source
            issue = brief_provider_issue()
            if issue is not None and issue not in report.provider_issues:
                report.provider_issues.append(issue)

            history = {k: v for k, v in by_day.items() if k < day}
            data = payload.day_payload(
                day,
                articles,
                clusters=cluster_articles(articles),
                entity_map=entity_map,
                trending=trending_terms(articles, history),
                blindspots=blindspots(articles, history),
                brief=brief.bullets,
                categories=_categories(articles),
                charts=_day_charts(articles),
                generated_at=_day_anchor(day),
                videos=day_videos,
                curated=day_curated,
                posts=day_posts,
            )

            key = f"day:{day}"
            fresh[key] = _digest(data, with_shell=True)
            report.videos_included += len(day_videos)
            report.posts_included += len(day_posts)
            month_items = index_by_month.setdefault(day[:7], [])
            month_items.extend(payload.index_items(day, articles))
            month_items.extend(payload.video_index_items(day_videos))
            month_items.extend(payload.curated_index_items(day_curated))
            month_items.extend(payload.post_index_items(day_posts))
            weeks.setdefault(_iso_week(day)[0], []).append(day)

            if state.get(key) == fresh[key] and (out_dir / "d" / day / "data.enc").exists():
                report.days_skipped.append(day)
                continue

            position = all_days.index(day)
            config = {
                "kind": "day",
                "base": "../../",
                "version": __version__,
                "kdfIterations": crypto.DEFAULT_ITERATIONS,
                "site": options.site,
                "siteUrl": options.site_url,
                "day": day,
                "dataUrl": "data.enc",
                "prev": all_days[position - 1] if position > 0 else "",
                "next": all_days[position + 1] if position + 1 < len(all_days) else "",
                "manifestUrl": "../../manifest.json",
                "indexBase": "../../idx/",
            }
            html = render.render_page(
                kind="day",
                base="../../",
                title=f"{day[8:10]}/{day[5:7]}/{day[:4]} — {options.site}",
                config=config,
                meta=meta,
            )
            render.write_page(out_dir / "d" / day / "index.html", html)
            report.bytes_written += crypto.write_encrypted(
                out_dir / "d" / day / "data.enc", data, options.password, salt=salt
            )
            report.days_built.append(day)

            if options.export_markdown:
                write_markdown(
                    out_dir / "d" / day / "export.md",
                    day_markdown(day, articles, brief=brief.bullets, site_url=options.site_url),
                )

        report.index_shards = _write_index_shards(
            out_dir, index_by_month, options, salt, state, fresh
        )
        report.week_pages, live_weeks = _write_week_pages(
            out_dir, weeks, by_day, entity_map, options, meta, salt, state, fresh
        )
        # `weeks` only covers the days this run targeted. Publishing that partial list would
        # tell the pruner that every week outside it is an orphan, and deleting a week page is
        # not reversible - so a run that did not sweep the whole archive publishes no week list
        # at all, and the pruner's existing "no weeks means hands off docs/w" guard holds.
        manifest_weeks = live_weeks if set(target_days) >= set(all_days) else []
        report.entity_pages = _write_entity_pages(
            out_dir, entity_index, loaded, options, meta, salt, state, fresh
        )
        report.curated_pages = _write_curated_pages(
            out_dir, curated_items, options, meta, salt, state, fresh
        )
        _write_video_library(
            out_dir,
            library_videos,
            options,
            meta,
            salt,
            state,
            fresh,
        )
        _write_home(out_dir, all_days, counts, options, meta, curated_total=len(curated_items))
        _write_root_files(
            out_dir,
            all_days,
            counts,
            entity_index,
            by_day,
            options,
            meta,
            salt,
            manifest_weeks,
            # Always the full list, unlike `weeks`: `_load_curated` reads every row and
            # `_write_curated_pages` writes every page on every run regardless of which
            # days were targeted, so this can never be the partial list that would make
            # the pruner delete live analyses.
            curated_ids=[item.id for item in curated_items],
        )
    finally:
        conn.close()

    _save_state(out_dir, fresh, salt)
    return report


def _write_index_shards(
    out_dir: Path,
    index_by_month: Mapping[str, Sequence[dict[str, object]]],
    options: BuildOptions,
    salt: bytes,
    state: Mapping[str, str],
    fresh: dict[str, str],
) -> int:
    """Write one encrypted search shard per month, skipping unchanged ones."""
    written = 0
    for month, items in sorted(index_by_month.items()):
        days = sorted({str(item["d"]) for item in items})
        data = payload.index_payload(month, days, items)
        key = f"idx:{month}"
        fresh[key] = _digest(data)
        target = out_dir / "idx" / f"{month}.enc"
        if state.get(key) == fresh[key] and target.exists():
            continue
        crypto.write_encrypted(target, data, options.password, salt=salt)
        written += 1
    return written


def _write_week_pages(
    out_dir: Path,
    weeks: Mapping[str, Sequence[str]],
    by_day: Mapping[str, Sequence[Article]],
    entity_map: Mapping[str, Sequence[str]],
    options: BuildOptions,
    meta: render.SiteMeta,
    salt: bytes,
    state: Mapping[str, str],
    fresh: dict[str, str],
) -> int:
    """Write the weekly roll-up pages covering the built days.

    Returns the number of pages written and the label and date range of every week that has a
    live page - written now or written earlier and unchanged. The manifest needs the second
    list, because "what exists" and "what this run rebuilt" are not the same set.
    """
    written = 0
    live: list[tuple[str, str, str]] = []
    for week, days in sorted(weeks.items()):
        _, start, end = _iso_week(days[0])
        articles = [a for day in sorted(by_day) if start <= day <= end for a in by_day[day]]
        if not articles:
            continue
        live.append((week, start, end))
        articles.sort(key=lambda a: (-a.score, a.title_vi))
        volume = [
            (day, float(len(by_day.get(day, [])))) for day in sorted(by_day) if start <= day <= end
        ]
        topics: dict[str, int] = {}
        week_sources: dict[str, int] = {}
        week_paid: set[str] = set()
        for article in articles:
            topics[article.topic or "Khác"] = topics.get(article.topic or "Khác", 0) + 1
            source = article.source or "?"
            week_sources[source] = week_sources.get(source, 0) + 1
            if article.tier == PAID:
                week_paid.add(source)
        data = payload.week_payload(
            week,
            start,
            end,
            articles,
            entity_map=entity_map,
            trending=trending_terms(articles, dict(by_day)),
            charts={
                "topics": charts.bar_chart(
                    [(k, float(v)) for k, v in topics.items()], title="Chủ đề trong tuần"
                ),
                "volume": charts.bar_chart(
                    volume, title="Số tin mỗi ngày", max_bars=max(1, len(volume))
                ),
                "sources": charts.bar_chart(
                    [(source, float(count)) for source, count in sorted(week_sources.items())],
                    title=f"Tất cả {len(week_sources)} nguồn trong tuần",
                    max_bars=max(1, len(week_sources)),
                    emphasis=week_paid,
                    emphasis_label="Trả phí",
                    rest_label="Miễn phí",
                ),
            },
        )
        key = f"week:{week}"
        fresh[key] = _digest(data, with_shell=True)
        target = out_dir / "w" / week
        if state.get(key) == fresh[key] and (target / "data.enc").exists():
            continue
        config = {
            "kind": "week",
            "base": "../../",
            "version": __version__,
            "kdfIterations": crypto.DEFAULT_ITERATIONS,
            "site": options.site,
            "siteUrl": options.site_url,
            "week": week,
            "dataUrl": "data.enc",
            "manifestUrl": "../../manifest.json",
            "indexBase": "../../idx/",
        }
        render.write_page(
            target / "index.html",
            render.render_page(
                kind="week",
                base="../../",
                title=f"Tuần {week} — {options.site}",
                config=config,
                meta=meta,
            ),
        )
        crypto.write_encrypted(target / "data.enc", data, options.password, salt=salt)
        written += 1
    return written, live


def _write_entity_pages(
    out_dir: Path,
    entity_index: EntityIndex,
    articles: Sequence[Article],
    options: BuildOptions,
    meta: render.SiteMeta,
    salt: bytes,
    state: Mapping[str, str],
    fresh: dict[str, str],
) -> int:
    """Write a page per recurring entity, newest coverage first."""
    written = 0
    by_slug: dict[str, list[Article]] = {}
    for article in articles:
        for slug in entity_index.by_article.get(article.url, ()):
            by_slug.setdefault(slug, []).append(article)

    top: Sequence[Entity] = entity_index.top(MAX_ENTITY_PAGES)
    for entity in top:
        related = sorted(
            by_slug.get(entity.slug, []), key=lambda a: (a.day, -a.score), reverse=True
        )
        if not related:
            continue
        timeline: dict[str, int] = {}
        for article in related:
            timeline[article.day] = timeline.get(article.day, 0) + 1
        data = payload.entity_payload(
            entity,
            related,
            entity_map=entity_index.by_article,
            charts={
                # A timeline must show every day it covers; folding the tail into a
                # "Khác" bar would turn dates into a meaningless bucket.
                "timeline": charts.bar_chart(
                    [(day, float(count)) for day, count in sorted(timeline.items())],
                    title=f"Nhắc tới {entity.label} theo ngày",
                    max_bars=max(1, len(timeline)),
                )
            },
        )
        key = f"entity:{entity.slug}"
        fresh[key] = _digest(data, with_shell=True)
        target = out_dir / "e" / entity.slug
        if state.get(key) == fresh[key] and (target / "data.enc").exists():
            continue
        config = {
            "kind": "entity",
            "base": "../../",
            "version": __version__,
            "kdfIterations": crypto.DEFAULT_ITERATIONS,
            "site": options.site,
            "siteUrl": options.site_url,
            "slug": entity.slug,
            "label": entity.label,
            "dataUrl": "data.enc",
            "manifestUrl": "../../manifest.json",
            "indexBase": "../../idx/",
        }
        render.write_page(
            target / "index.html",
            render.render_page(
                kind="entity",
                base="../../",
                # The label is a public tag name, not article text, but keep the page
                # title generic so a crawler learns nothing from the <title>.
                title=f"Chủ đề — {options.site}",
                config=config,
                meta=meta,
            ),
        )
        crypto.write_encrypted(target / "data.enc", data, options.password, salt=salt)
        written += 1
    return written


def _write_curated_pages(
    out_dir: Path,
    items: Sequence[CuratedItem],
    options: BuildOptions,
    meta: render.SiteMeta,
    salt: bytes,
    state: Mapping[str, str],
    fresh: dict[str, str],
) -> int:
    """Write the deep-dive listing plus one reading page per analysis.

    A page per item, rather than one long scroll: these run 800-1200 words with a table of
    contents, so each needs its own URL to be shareable and its own scroll position to be
    resumable.
    """
    written = 0

    for item in items:
        data = payload.curated_payload(item)
        key = f"curated:{item.id}"
        fresh[key] = _digest(data, with_shell=True)
        target = out_dir / "c" / item.id
        if state.get(key) == fresh[key] and (target / "data.enc").exists():
            continue
        config = {
            "kind": "curated",
            "base": "../../",
            "version": __version__,
            "kdfIterations": crypto.DEFAULT_ITERATIONS,
            "site": options.site,
            "siteUrl": options.site_url,
            "curatedId": item.id,
            "day": item.day,
            "dataUrl": "data.enc",
            "manifestUrl": "../../manifest.json",
            "indexBase": "../../idx/",
        }
        render.write_page(
            target / "index.html",
            render.render_page(
                kind="curated",
                base="../../",
                # Generic title on purpose: the analysis title is private archive text and
                # must not leak to a crawler through <title>, same rule as entity pages.
                title=f"Phân tích sâu — {options.site}",
                config=config,
                meta=meta,
            ),
        )
        crypto.write_encrypted(target / "data.enc", data, options.password, salt=salt)
        written += 1

    # The listing is written even with zero items so the menu link never lands on a 404.
    index_data = payload.curated_index_payload(
        items, generated_at=_day_anchor(items[0].day) if items else _day_anchor(_today())
    )
    index_key = "curated:index"
    fresh[index_key] = _digest(index_data, with_shell=True)
    index_target = out_dir / "c"
    if not (state.get(index_key) == fresh[index_key] and (index_target / "data.enc").exists()):
        config = {
            "kind": "curatedIndex",
            "base": "../",
            "version": __version__,
            "kdfIterations": crypto.DEFAULT_ITERATIONS,
            "site": options.site,
            "siteUrl": options.site_url,
            "dataUrl": "data.enc",
            "manifestUrl": "../manifest.json",
            "indexBase": "../idx/",
        }
        render.write_page(
            index_target / "index.html",
            render.render_page(
                kind="curatedIndex",
                base="../",
                title=f"Phân tích sâu — {options.site}",
                config=config,
                meta=meta,
            ),
        )
        crypto.write_encrypted(index_target / "data.enc", index_data, options.password, salt=salt)
        written += 1

    return written


def _write_video_library(
    out_dir: Path,
    videos: Sequence[Video],
    options: BuildOptions,
    meta: render.SiteMeta,
    salt: bytes,
    state: Mapping[str, str],
    fresh: dict[str, str],
) -> None:
    """Write the one private screen that groups every summary by YouTube channel."""
    newest = max((video.day for video in videos), default=_today())
    data = payload.video_library_payload(videos, generated_at=_day_anchor(newest))
    key = "videos:index"
    fresh[key] = _digest(data, with_shell=True)
    target = out_dir / "videos"
    if state.get(key) == fresh[key] and (target / "data.enc").exists():
        return
    config = {
        "kind": "videoIndex",
        "base": "../",
        "version": __version__,
        "kdfIterations": crypto.DEFAULT_ITERATIONS,
        "site": options.site,
        "siteUrl": options.site_url,
        "dataUrl": "data.enc",
        "manifestUrl": "../manifest.json",
        "indexBase": "../idx/",
    }
    render.write_page(
        target / "index.html",
        render.render_page(
            kind="videoIndex",
            base="../",
            title=f"Video YouTube — {options.site}",
            config=config,
            meta=meta,
        ),
    )
    crypto.write_encrypted(target / "data.enc", data, options.password, salt=salt)


def _today() -> str:
    return dt.datetime.now(dt.UTC).date().isoformat()


def _write_home(
    out_dir: Path,
    all_days: Sequence[str],
    counts: Mapping[str, int],
    options: BuildOptions,
    meta: render.SiteMeta,
    curated_total: int = 0,
) -> None:
    """Write the landing page. Its calendar reads from the plain manifest."""
    latest = all_days[-1] if all_days else ""
    config = {
        "kind": "home",
        "base": "",
        "version": __version__,
        "kdfIterations": crypto.DEFAULT_ITERATIONS,
        "site": options.site,
        "siteUrl": options.site_url,
        "latest": latest,
        "dataUrl": f"d/{latest}/data.enc" if latest else "",
        "manifestUrl": "manifest.json",
        "indexBase": "idx/",
        "days": len(all_days),
        "articles": sum(counts.values()),
        "curatedTotal": curated_total,
    }
    render.write_page(
        out_dir / "index.html",
        render.render_page(kind="home", base="", title=options.site, config=config, meta=meta),
    )


def _write_root_files(
    out_dir: Path,
    all_days: Sequence[str],
    counts: Mapping[str, int],
    entity_index: EntityIndex,
    by_day: Mapping[str, Sequence[Article]],
    options: BuildOptions,
    meta: render.SiteMeta,
    salt: bytes,
    weeks: Sequence[tuple[str, str, str]] = (),
    curated_ids: Sequence[str] | None = None,
) -> None:
    """Manifest, feeds, assets and the static root files."""
    # Anchored to the newest day, not to the clock, for the same reason `_day_anchor` exists:
    # a wall-clock stamp rewrites manifest.json and feed.xml on every single build, so the
    # nightly job commits a diff even when not one article has changed. With the job running
    # twice a day that is two empty commits daily. Sorted ascending, so [-1] is the newest.
    generated_at = (
        _day_anchor(all_days[-1])
        if all_days
        else _day_anchor(dt.datetime.now(dt.UTC).date().isoformat())
    )

    manifest_data = payload.manifest(
        [(day, counts.get(day, 0)) for day in all_days],
        sorted({day[:7] for day in all_days}),
        entity_index.top(MAX_ENTITY_PAGES),
        weeks=weeks,
        curated=curated_ids,
        generated_at=generated_at,
        kdf_iterations=crypto.DEFAULT_ITERATIONS,
        site=options.site,
        version=__version__,
    )
    manifest_data["salt"] = base64.b64encode(salt).decode("ascii")
    render.write_json(out_dir / "manifest.json", manifest_data)

    site_url = options.site_url.rstrip("/")
    feed_days = [
        feeds.FeedDay(
            day=day,
            count=counts.get(day, 0),
            topics=_topic_counts(by_day.get(day, ())),
            url=f"{site_url}/d/{day}/" if site_url else f"d/{day}/",
        )
        for day in reversed(all_days)
    ]
    entries = {day: list(by_day.get(day, ())) for day in all_days} if options.feed_full else None
    (out_dir / "feed.xml").write_text(
        feeds.atom_feed(
            feed_days,
            site=options.site,
            site_url=site_url,
            updated=generated_at,
            full=options.feed_full,
            entries=entries,
        ),
        encoding="utf-8",
    )
    render.write_json(
        out_dir / "feed.json",
        feeds.json_feed(
            feed_days,
            site=options.site,
            site_url=site_url,
            updated=generated_at,
            full=options.feed_full,
            entries=entries,
        ),
    )

    render.write_static(out_dir, meta)
    render.copy_assets(out_dir)
    shutil.copyfile(
        Path(__file__).parent / "assets" / "sw.js",
        out_dir / "sw.js",
    )


def _topic_counts(articles: Sequence[Article]) -> dict[str, int]:
    """Topic histogram used by the metadata feed."""
    counts: dict[str, int] = {}
    for article in articles:
        counts[article.topic or "Khác"] = counts.get(article.topic or "Khác", 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))
