"""Build the whole static site: read the database, analyse, encrypt, render.

This is the orchestration layer. Every step it calls lives in a focused module; the value
here is the wiring, the incremental-rebuild logic and the guarantee that a failure in an
optional feature (illustrations, brief, audio) never stops the site from being generated.
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import json
import logging
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from newsvault import __version__, charts, crypto, db, feeds, payload, render
from newsvault.blindspot import blindspots
from newsvault.brief import BriefResult, fallback_brief, generate_brief
from newsvault.cluster import cluster_articles
from newsvault.entities import Entity, EntityIndex, build_entity_index
from newsvault.exports import day_markdown, write_markdown
from newsvault.images import ImageResult, generate_images, plan_images
from newsvault.model import Article
from newsvault.text import slugify
from newsvault.trends import trending_terms

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
    days: tuple[str, ...] = ()
    backfill: bool = False
    site: str = "Kho tin"
    site_url: str = ""
    min_relevance: int = 0
    images: str = "all"
    image_days: int = 0  # 0 = illustrate every built day
    max_image_calls: int = 8
    dry_run_images: bool = False
    api_key: str | None = None
    cache_dir: Path = Path(".image-cache")
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
    images_generated: int = 0
    images_cached: int = 0
    images_failed: int = 0
    brief_source: dict[str, str] = field(default_factory=dict)
    bytes_written: int = 0

    def summary(self) -> str:
        """One-line human summary."""
        return (
            f"{len(self.days_built)} ngày dựng, {len(self.days_skipped)} bỏ qua (không đổi), "
            f"{self.entity_pages} trang thực thể, {self.week_pages} trang tuần, "
            f"{self.index_shards} shard tìm kiếm, "
            f"ảnh: {self.images_generated} mới / {self.images_cached} cache / {self.images_failed} lỗi"
        )


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


def _digest(data: object) -> str:
    """Stable content hash of a payload, used to skip unchanged pages."""
    blob = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
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
    """The three server-rendered SVG charts shown on a day page."""
    topics: dict[str, int] = {}
    sources: dict[str, int] = {}
    impacts: dict[str, int] = {}
    for article in articles:
        topics[article.topic or "Khác"] = topics.get(article.topic or "Khác", 0) + 1
        sources[article.source or "?"] = sources.get(article.source or "?", 0) + 1
        impacts[article.impact_level or "không rõ"] = (
            impacts.get(article.impact_level or "không rõ", 0) + 1
        )
    return {
        "topics": charts.bar_chart(
            [(k, float(v)) for k, v in topics.items()], title="Tin theo chủ đề"
        ),
        "sources": charts.donut_chart(
            [(k, float(v)) for k, v in sources.items()], title="Tỉ trọng nguồn"
        ),
        "impact": charts.donut_chart(
            [(k, float(v)) for k, v in impacts.items()], title="Mức tác động"
        ),
    }


def _categories(
    articles: Sequence[Article],
    images: Sequence[ImageResult],
    image_dir: Path | None = None,
) -> list[dict[str, object]]:
    """Category cards for the day page, wired to whatever illustrations exist.

    `images` holds only what this run generated. A rebuild with --images none generates
    nothing, so fall back to what is already on disk - otherwise a text-only rebuild
    would quietly strip every illustration off the page.
    """
    by_image = {result.key: result for result in images}

    def has_image(key: str) -> bool:
        result = by_image.get(key)
        if result is not None and result.path:
            return True
        return image_dir is not None and (image_dir / f"{key}.webp").exists()

    counts: dict[str, int] = {}
    labels: dict[str, str] = {}
    for article in articles:
        label = article.topic or "Khác"
        key = slugify(label)
        counts[key] = counts.get(key, 0) + 1
        labels[key] = label

    cards: list[dict[str, object]] = []
    for key, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        cards.append(
            {
                "key": key,
                "label": labels[key],
                "count": count,
                "image": f"img/{key}.webp" if has_image(key) else "",
                # The label is already rendered above it; repeating it reads as a bug.
                "caption": "",
            }
        )
    if has_image("cover"):
        cards.insert(
            0,
            {
                "key": "cover",
                "label": "Toàn cảnh",
                "count": len(articles),
                "image": "img/cover.webp",
                "caption": "Bức tranh chung của ngày",
            },
        )
    return cards


def _brief_for(day: str, articles: Sequence[Article], options: BuildOptions) -> BriefResult:
    """The day's five bullets, cached on disk and degrading to a deterministic fallback.

    The cache is what makes a rebuild free and a re-key lossless: without it, changing the
    site password would silently replace every Gemini brief with the fallback text.
    """
    cache = Path(options.cache_dir) / "brief" / f"{day}.json"
    if cache.exists():
        try:
            stored = json.loads(cache.read_text(encoding="utf-8"))
            bullets = tuple(str(b) for b in stored.get("bullets", ()) if str(b).strip())
            if bullets:
                return BriefResult(
                    bullets=bullets, source=str(stored.get("source", "cache")), error=""
                )
        except (OSError, ValueError):
            logger.warning("brief cache unreadable for %s", day)

    result = (
        fallback_brief(articles)
        if not options.use_brief
        else generate_brief(day, articles, api_key=options.api_key)
    )
    if result.source == "gemini" and result.bullets:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(
            json.dumps(
                {"bullets": list(result.bullets), "source": result.source}, ensure_ascii=False
            ),
            encoding="utf-8",
        )
    return result


# --------------------------------------------------------------------------------------
# the build
# --------------------------------------------------------------------------------------


def select_days(conn, options: BuildOptions) -> list[str]:
    """Resolve which day keys this invocation should build."""
    available = db.available_days(conn)
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

    conn = db.connect(options.db_path)
    try:
        target_days = select_days(conn, options)
        if not target_days:
            logger.warning("nothing to build")
            return report

        all_days = db.available_days(conn)
        counts = db.counts_by_day(conn)

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

        image_days = set(target_days)
        if options.image_days > 0:
            image_days = set(sorted(target_days)[-options.image_days :])

        index_by_month: dict[str, list[dict[str, object]]] = {}
        weeks: dict[str, list[str]] = {}

        for day in target_days:
            articles = by_day.get(day, [])
            if not articles:
                continue

            image_results: list[ImageResult] = []
            if options.images != "none" and day in image_days:
                requests_ = plan_images(day, articles, mode=options.images)
                image_results = generate_images(
                    requests_,
                    out_dir / "d" / day / "img",
                    api_key=options.api_key,
                    cache_dir=Path(options.cache_dir),
                    max_calls=options.max_image_calls,
                    dry_run=options.dry_run_images,
                )
                for result in image_results:
                    if result.path and result.cached:
                        report.images_cached += 1
                    elif result.path:
                        report.images_generated += 1
                    else:
                        report.images_failed += 1

            brief = _brief_for(day, articles, options)
            report.brief_source[day] = brief.source

            history = {k: v for k, v in by_day.items() if k < day}
            data = payload.day_payload(
                day,
                articles,
                clusters=cluster_articles(articles),
                entity_map=entity_map,
                trending=trending_terms(articles, history),
                blindspots=blindspots(articles, history),
                brief=brief.bullets,
                categories=_categories(articles, image_results, out_dir / "d" / day / "img"),
                charts=_day_charts(articles),
                generated_at=_day_anchor(day),
            )

            key = f"day:{day}"
            fresh[key] = _digest(data)
            index_by_month.setdefault(day[:7], []).extend(payload.index_items(day, articles))
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
        report.week_pages = _write_week_pages(
            out_dir, weeks, by_day, entity_map, options, meta, salt, state, fresh
        )
        report.entity_pages = _write_entity_pages(
            out_dir, entity_index, loaded, options, meta, salt, state, fresh
        )
        _write_home(out_dir, all_days, counts, options, meta)
        _write_root_files(out_dir, all_days, counts, entity_index, by_day, options, meta, salt)
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
    """Write the weekly roll-up pages covering the built days."""
    written = 0
    for week, days in sorted(weeks.items()):
        _, start, end = _iso_week(days[0])
        articles = [a for day in sorted(by_day) if start <= day <= end for a in by_day[day]]
        if not articles:
            continue
        articles.sort(key=lambda a: (-a.score, a.title_vi))
        volume = [
            (day, float(len(by_day.get(day, [])))) for day in sorted(by_day) if start <= day <= end
        ]
        topics: dict[str, int] = {}
        for article in articles:
            topics[article.topic or "Khác"] = topics.get(article.topic or "Khác", 0) + 1
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
                "volume": charts.bar_chart(volume, title="Số tin mỗi ngày"),
                "sources": charts.donut_chart(
                    [
                        (source, float(count))
                        for source, count in sorted(
                            {
                                a.source: sum(1 for x in articles if x.source == a.source)
                                for a in articles
                            }.items()
                        )
                    ],
                    title="Tỉ trọng nguồn",
                ),
            },
        )
        key = f"week:{week}"
        fresh[key] = _digest(data)
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
    return written


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
                "timeline": charts.bar_chart(
                    [(day, float(count)) for day, count in sorted(timeline.items())],
                    title=f"Nhắc tới {entity.label} theo ngày",
                )
            },
        )
        key = f"entity:{entity.slug}"
        fresh[key] = _digest(data)
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


def _write_home(
    out_dir: Path,
    all_days: Sequence[str],
    counts: Mapping[str, int],
    options: BuildOptions,
    meta: render.SiteMeta,
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
) -> None:
    """Manifest, feeds, assets and the static root files."""
    generated_at = dt.datetime.now(dt.UTC).isoformat()

    manifest_data = payload.manifest(
        [(day, counts.get(day, 0)) for day in all_days],
        sorted({day[:7] for day in all_days}),
        entity_index.top(MAX_ENTITY_PAGES),
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
