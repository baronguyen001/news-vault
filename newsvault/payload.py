from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

from newsvault.blindspot import Blindspot
from newsvault.cluster import Cluster
from newsvault.curated import CuratedItem
from newsvault.entities import Entity
from newsvault.indie import IndiePost
from newsvault.model import Article
from newsvault.posts import Post
from newsvault.substack import Essay
from newsvault.text import excerpt, fold
from newsvault.trends import Trend
from newsvault.videos import Video


def _sorted(value: dict[str, object]) -> dict[str, object]:
    """Return a new dict with keys sorted recursively."""
    return {k: _sorted(v) if isinstance(v, dict) else v for k, v in sorted(value.items())}


def _search_snippet(value: str, limit: int = 160) -> str:
    """Return a reader-facing excerpt without splitting a word."""
    value = " ".join(value.split())
    if len(value) <= limit:
        return value
    cut = value[: limit - 1].rsplit(" ", 1)[0]
    return f"{cut or value[: limit - 1]}…"


def _count_values(values: Iterable[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        if not value:
            continue
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


def _trend_dict(trend: Trend) -> dict[str, object]:
    return _sorted(
        {
            "term": trend.term,
            "label": trend.label,
            "today": trend.today,
            "baseline": trend.baseline,
            "z": trend.z,
        }
    )


def _blindspot_dict(blindspot: Blindspot) -> dict[str, object]:
    return _sorted(
        {
            "topic": blindspot.topic,
            "share_today": blindspot.share_today,
            "share_baseline": blindspot.share_baseline,
            "drop": blindspot.drop,
        }
    )


def compact_article(
    article: Article,
    index: int,
    *,
    entities: Mapping[str, Sequence[str]] | None = None,
    with_day: bool = False,
) -> dict[str, object]:
    """Return the compact JSON shape for a single article."""
    if entities is None:
        article_entities: list[str] = []
    else:
        article_entities = list(entities.get(article.url, []))

    summary = article.summary_vi or ""

    data: dict[str, object] = {
        "i": index,
        "t": article.title_vi or article.title or "",
        "to": article.title or "",
        "u": article.url,
        "s": article.source or "",
        "sk": article.source_key or "",
        "tr": article.tier,
        "r": article.region or "",
        "c": article.category or "",
        "tp": article.topic or "",
        "im": article.impact_level or "",
        "sc": article.score,
        "rel": article.relevance,
        "p": article.published_at or "",
        "pi": article.published_iso or "",
        "sum": excerpt(summary, 1200),
        "kp": list(article.key_points),
        "tg": list(article.tags),
        "an": article.analysis or {},
        "law": bool(article.is_law_policy),
        "te": bool(article.is_teaser),
        "img": article.image_url,
        "ents": article_entities,
    }
    if with_day:
        data["d"] = article.day or ""

    return _sorted(data)


def compact_video(video: Video) -> dict[str, object]:
    """Return the compact JSON shape for one summarised video.

    The summary travels as pre-parsed blocks rather than as text with markup in it. The
    front end turns a block's runs into text nodes, so nothing a language model wrote can
    ever be interpreted as markup by the browser.
    """
    return _sorted(
        {
            "id": video.id,
            "t": video.title,
            "c": video.channel,
            "u": video.url,
            "th": video.thumbnail,
            # A Short's thumbnail comes from an endpoint YouTube does not guarantee, so the
            # front end needs somewhere to fall back to. Empty for an ordinary video, whose
            # primary url already is the guaranteed one.
            "thf": video.thumbnail_fallback,
            "sh": 1 if video.is_short else 0,
            "ty": video.video_type,
            "p": video.processed_at,
            "d": video.day,
            "bl": [{"k": b.kind, "r": [[run, bold] for run, bold in b.runs]} for b in video.blocks],
            "st": video.summary_status,
            "er": video.error_message,
            "at": video.attempts,
        }
    )


def video_index_items(videos: Sequence[Video]) -> list[dict[str, object]]:
    """Build search-index items for videos so the whole-archive search reaches them too."""
    items: list[dict[str, object]] = []
    for index, video in enumerate(videos):
        summary = " ".join(run for block in video.blocks for run, _ in block.runs)
        searchable = fold(f"{video.title} {video.channel} {video.video_type} {summary}".strip())
        # Adding `sn` changes every index-shard digest, so the next build rewrites all
        # seven shards (~1.2 MB) once. Day payloads are hashed separately and unaffected.
        items.append(
            _sorted(
                {
                    "d": video.day,
                    "i": index,
                    "k": "v",
                    "t": video.title,
                    "f": searchable,
                    "sn": _search_snippet(summary),
                    "s": video.channel,
                    "sk": "youtube",
                    "tr": "free",
                    "tp": video.video_type,
                    "im": "",
                    "sc": 0,
                    "r": "",
                    "tg": [],
                }
            )
        )
    return items


def video_library_payload(videos: Sequence[Video], *, generated_at: str) -> dict[str, object]:
    """Payload for the private, channel-oriented video library.

    The library intentionally contains only successfully summarised videos.  It is a
    reading surface for the static archive, not a view of the summariser's work queue;
    exposing failed or pending rows would require a live service and would make the
    archive's data model misleading.
    """
    ordered = sorted(videos, key=lambda video: (video.day, video.processed_at, video.id), reverse=True)
    channels = _count_values(video.channel or "Kênh chưa rõ" for video in ordered)
    return _sorted(
        {
            "v": 1,
            "kind": "videoIndex",
            "generated_at": generated_at,
            "total": len(ordered),
            "channels": channels,
            "videos": [compact_video(video) for video in ordered],
        }
    )


def curated_teaser(item: CuratedItem) -> dict[str, object]:
    """Compact shape for a curated analysis: enough for a card, not the article itself.

    The body is deliberately absent. A day page carrying three 1200-word analyses in full
    would triple its payload for text the reader has to open a dedicated page to read
    anyway, so the card links out and only the reading page ships the blocks.
    """
    return _sorted(
        {
            "id": item.id,
            "t": item.title,
            "c": item.channel,
            "u": item.url,
            "th": item.thumbnail,
            "d": item.day,
            "p": item.processed_at,
            "lead": item.lead,
            "w": item.words,
            "m": item.minutes,
            "ns": len(item.sections),
        }
    )


def curated_payload(item: CuratedItem) -> dict[str, object]:
    """Full analysis for its own reading page.

    Like a video summary, the body travels as pre-parsed blocks and never as markup, so no
    text a language model produced can reach the browser as HTML.
    """
    return _sorted(
        {
            "v": 1,
            "kind": "curated",
            "id": item.id,
            "t": item.title,
            "c": item.channel,
            "u": item.url,
            "th": item.thumbnail,
            "d": item.day,
            "p": item.processed_at,
            "pub": item.published_iso,
            "w": item.words,
            "m": item.minutes,
            "toc": [{"a": s.anchor, "l": s.label} for s in item.sections],
            "bl": [{"k": b.kind, "r": [[run, bold] for run, bold in b.runs]} for b in item.blocks],
        }
    )


def curated_index_payload(items: Sequence[CuratedItem], *, generated_at: str) -> dict[str, object]:
    """Payload for the "Phân tích sâu" listing page."""
    return _sorted(
        {
            "v": 1,
            "kind": "curatedIndex",
            "generated_at": generated_at,
            "total": len(items),
            "items": [curated_teaser(item) for item in items],
        }
    )


def curated_index_items(items: Sequence[CuratedItem]) -> list[dict[str, object]]:
    """Search-index entries so whole-archive search reaches the analyses too."""
    out: list[dict[str, object]] = []
    for item in items:
        body = " ".join(run for block in item.blocks for run, _ in block.runs)
        searchable = fold(f"{item.title} {item.channel} {body}".strip())
        out.append(
            _sorted(
                {
                    "d": item.day,
                    # The id, not a positional index: a curated entry is addressed by its
                    # own page, so the front end needs the id to build the link.
                    "i": item.id,
                    "k": "c",
                    "t": item.title,
                    "f": searchable,
                    "sn": _search_snippet(body),
                    "s": item.channel,
                    "sk": "youtube",
                    "tr": "free",
                    "tp": "Phân tích sâu",
                    "im": "",
                    "sc": 0,
                    "r": "",
                    "tg": [],
                }
            )
        )
    return out


def report_index_payload(reports: Sequence[Article], *, generated_at: str) -> dict[str, object]:
    """Payload for the analyst-report listing, newest report first.

    Reports reuse the normal compact-article shape so full reports can render with the
    normal article card. They already enter the archive-search shards through
    :func:`index_items`, therefore this listing must not create duplicate search entries.
    """
    ordered = sorted(
        reports,
        key=lambda article: (article.day, article.published_iso, article.id),
        reverse=True,
    )
    return _sorted(
        {
            "v": 1,
            "kind": "reportsIndex",
            "generated_at": generated_at,
            "total": len(ordered),
            "items": [
                compact_article(article, index, with_day=True)
                for index, article in enumerate(ordered)
            ],
        }
    )


def compact_post(post: Post) -> dict[str, object]:
    """Return the compact JSON shape for one X post.

    Same discipline as :func:`compact_video`: the summary travels as pre-parsed blocks
    and the key points as plain strings, so nothing a language model wrote can reach the
    browser as markup.

    ``tr`` (the author's tier) travels with the card because it is the only thing keeping
    a viral anonymous post from reading like a wire report - the front end shows it as a
    credibility mark, and a reader who cannot see it cannot weigh the source.
    """
    value: dict[str, object] = {
        "id": post.id,
        "t": post.title,
        "u": post.url,
        "au": post.author,
        "an": post.author_name,
        "tr": round(post.author_tier, 2),
        "pr": 1 if post.is_primary else 0,
        "d": post.day,
        "p": post.processed_at,
        "pi": post.published_iso,
        "ve": post.vertical,
        "vl": post.vertical_label,
        "tp": post.topic,
        "im": post.impact,
        "rel": post.relevance,
        "sc": post.score,
        "lk": post.likes,
        "rt": post.retweets,
        "ins": post.insight,
        "bl": [{"k": b.kind, "r": [[run, bold] for run, bold in b.runs]} for b in post.blocks],
        "kp": list(post.points),
    }
    if post.image:
        value["img"] = post.image
    if post.also_by:
        value["ab"] = list(post.also_by)
    if post.impact_reasoning:
        value["ia"] = {
            "ch": post.impact_channel,
            "as": list(post.impact_assets),
            "dir": post.impact_direction,
            "cf": post.impact_confidence,
            "why": post.impact_reasoning,
        }
    return _sorted(value)


def post_index_items(posts: Sequence[Post]) -> list[dict[str, object]]:
    """Search-index entries so whole-archive search reaches X posts too."""
    out: list[dict[str, object]] = []
    for index, post in enumerate(posts):
        body = " ".join(run for block in post.blocks for run, _ in block.runs)
        points = " ".join(post.points)
        # The original English text is folded into the search string as well: a reader
        # hunting for "FOMC" should find the post that used that word, not only the
        # Vietnamese rendering of it.
        searchable = fold(f"{post.title} {post.author} {body} {points} {post.text}".strip())
        out.append(
            _sorted(
                {
                    "d": post.day,
                    "i": index,
                    "k": "x",
                    "t": post.title,
                    "f": searchable,
                    "sn": _search_snippet(f"{body} {points}".strip()),
                    "s": f"@{post.author}",
                    "sk": "x",
                    "tr": "free",
                    "tp": post.topic,
                    "im": post.impact,
                    "sc": post.score,
                    "r": "",
                    "tg": [],
                }
            )
        )
    return out


def substack_teaser(item: Essay) -> dict[str, object]:
    """Compact shape for a Substack essay: enough for a card, not the essay itself.

    Same reasoning as `curated_teaser`: the body is absent so a day page carrying several
    long essays does not triple its payload for text the reader opens a dedicated page for
    anyway.
    """
    return _sorted(
        {
            "id": item.id,
            "t": item.title,
            "c": item.author_name,
            "u": item.url,
            "d": item.day,
            "p": item.published_iso,
            "lead": item.lead,
            "w": item.words,
            "m": item.minutes,
            "ns": len(item.sections),
        }
    )


def substack_payload(item: Essay) -> dict[str, object]:
    """Full essay for its own reading page.

    Like a curated analysis, the body travels as pre-parsed blocks and never as markup, so
    no text a language model produced can reach the browser as HTML.
    """
    return _sorted(
        {
            "v": 1,
            "kind": "substack",
            "id": item.id,
            "t": item.title,
            "c": item.author_name,
            "u": item.url,
            "d": item.day,
            "p": item.published_iso,
            "w": item.words,
            "m": item.minutes,
            "toc": [{"a": s.anchor, "l": s.label} for s in item.sections],
            "bl": [{"k": b.kind, "r": [[run, bold] for run, bold in b.runs]} for b in item.blocks],
        }
    )


def substack_index_payload(items: Sequence[Essay], *, generated_at: str) -> dict[str, object]:
    """Payload for the "Từ Substack" listing page."""
    return _sorted(
        {
            "v": 1,
            "kind": "substackIndex",
            "generated_at": generated_at,
            "total": len(items),
            "items": [substack_teaser(item) for item in items],
        }
    )


def substack_index_items(items: Sequence[Essay]) -> list[dict[str, object]]:
    """Search-index entries so whole-archive search reaches the essays too."""
    out: list[dict[str, object]] = []
    for item in items:
        body = " ".join(run for block in item.blocks for run, _ in block.runs)
        searchable = fold(f"{item.title} {item.author_name} {body}".strip())
        out.append(
            _sorted(
                {
                    "d": item.day,
                    # The id, not a positional index: a Substack essay is addressed by its
                    # own page, so the front end needs the id to build the link.
                    "i": item.id,
                    "k": "e",
                    "t": item.title,
                    "f": searchable,
                    "sn": _search_snippet(body),
                    "s": item.author_name,
                    "sk": "substack",
                    "tr": "free",
                    "tp": "Substack",
                    "im": "",
                    "sc": 0,
                    "r": "",
                    "tg": [],
                }
            )
        )
    return out


def compact_indie(post: IndiePost) -> dict[str, object]:
    """Compact shape for one indie-hacker post: a translated card, no scoring metadata.

    Unlike `compact_post`, there is no tier/vertical/topic/impact here - `xpulse/indie.py`
    scores keep-or-drop only, deliberately simpler than the 5-vertical triage pipeline.
    """
    return _sorted(
        {
            "au": post.author,
            "an": post.author_name,
            "vi": post.text_vi,
            "u": post.url,
            "d": post.day,
            "p": post.published_iso,
            "lk": post.likes,
            "rt": post.retweets,
        }
    )


def indie_index_items(posts: Sequence[IndiePost]) -> list[dict[str, object]]:
    """Search-index entries so whole-archive search reaches indie posts too."""
    out: list[dict[str, object]] = []
    for index, post in enumerate(posts):
        searchable = fold(f"{post.author_name} {post.author} {post.text_vi}".strip())
        out.append(
            _sorted(
                {
                    "d": post.day,
                    "i": index,
                    "k": "i",
                    "t": post.text_vi,
                    "f": searchable,
                    "sn": _search_snippet(post.text_vi),
                    "s": f"@{post.author}",
                    "sk": "x",
                    "tr": "free",
                    "tp": "Indie Hacker",
                    "im": "",
                    "sc": 0,
                    "r": "",
                    "tg": [],
                }
            )
        )
    return out


def day_payload(
    day: str,
    articles: Sequence[Article],
    *,
    clusters: Sequence[Cluster],
    entity_map: Mapping[str, Sequence[str]],
    trending: Sequence[Trend],
    blindspots: Sequence[Blindspot],
    brief: Sequence[str],
    categories: Sequence[Mapping[str, object]],
    charts: Mapping[str, str],
    generated_at: str,
    videos: Sequence[Video] = (),
    curated: Sequence[CuratedItem] = (),
    reports: Sequence[Article] = (),
    posts: Sequence[Post] = (),
    substack: Sequence[Essay] = (),
    indie: Sequence[IndiePost] = (),
) -> dict[str, object]:
    """Build the encrypted JSON payload for a single day page."""
    compact = [compact_article(a, i, entities=entity_map) for i, a in enumerate(articles)]
    url_to_index = {a.url: i for i, a in enumerate(articles)}

    cluster_objs: list[dict[str, object]] = []
    for cluster in clusters:
        lead_idx = url_to_index.get(cluster.lead.url)
        if lead_idx is None:
            continue
        members = {url_to_index[m.url] for m in cluster.members if m.url in url_to_index}
        members.add(lead_idx)
        cluster_objs.append(
            _sorted(
                {
                    "key": cluster.key,
                    "lead": lead_idx,
                    "members": sorted(members),
                    "sources": list(cluster.sources),
                }
            )
        )

    return _sorted(
        {
            "v": 1,
            "kind": "day",
            "day": day,
            "generated_at": generated_at,
            "brief": list(brief),
            "stats": stats_for(articles),
            "charts": dict(charts),
            "trending": [_trend_dict(t) for t in trending],
            "blindspots": [_blindspot_dict(b) for b in blindspots],
            "categories": [_sorted(dict(c)) for c in categories],
            "clusters": cluster_objs,
            "articles": compact,
            "videos": [compact_video(v) for v in videos],
            "curated": [curated_teaser(c) for c in curated],
            # Preserve the original article indices: normal report cards retain their
            # cluster anchors and reader state when rendered in their own section.
            "reports": [
                compact_article(report, url_to_index.get(report.url, -1), entities=entity_map)
                for report in reports
            ],
            "posts": [compact_post(p) for p in posts],
            "substack": [substack_teaser(item) for item in substack],
            "indie": [compact_indie(post) for post in indie],
        }
    )


def entity_payload(
    entity: Entity,
    articles: Sequence[Article],
    *,
    entity_map: Mapping[str, Sequence[str]],
    charts: Mapping[str, str],
) -> dict[str, object]:
    """Build the encrypted JSON payload for an entity page."""
    if articles:
        days = [a.day for a in articles]
        first_day = min(days)
        last_day = max(days)
    else:
        first_day = ""
        last_day = ""

    day_counts: dict[str, int] = {}
    for article in articles:
        day_counts[article.day] = day_counts.get(article.day, 0) + 1

    days_list = [_sorted({"d": d, "n": n}) for d, n in sorted(day_counts.items())]
    compact = [
        compact_article(a, i, entities=entity_map, with_day=True) for i, a in enumerate(articles)
    ]

    return _sorted(
        {
            "v": 1,
            "kind": "entity",
            "slug": entity.slug,
            "label": entity.label,
            "total": len(articles),
            "first_day": first_day,
            "last_day": last_day,
            "charts": dict(charts),
            "days": days_list,
            "articles": compact,
        }
    )


def quality_payload(
    week: str,
    start: str,
    end: str,
    systems: Sequence[Mapping[str, object]],
    *,
    generated_at: str,
) -> dict[str, object]:
    """Build the encrypted JSON payload for a weekly quality page."""
    return _sorted(
        {
            "v": 1,
            "kind": "quality",
            "week": week,
            "start": start,
            "end": end,
            "generated_at": generated_at,
            "systems": [dict(system) for system in systems],
        }
    )


def week_payload(
    week: str,
    start: str,
    end: str,
    articles: Sequence[Article],
    *,
    entity_map: Mapping[str, Sequence[str]],
    trending: Sequence[Trend],
    charts: Mapping[str, str],
    top_n: int = 30,
) -> dict[str, object]:
    """Build the encrypted JSON payload for a week page."""
    day_counts: dict[str, int] = {}
    for article in articles:
        day_counts[article.day] = day_counts.get(article.day, 0) + 1
    days_list = [_sorted({"d": d, "n": n}) for d, n in sorted(day_counts.items())]

    top = sorted(articles, key=lambda a: (-a.score, a.id))[:top_n]
    top_compact = [
        compact_article(a, i, entities=entity_map, with_day=True) for i, a in enumerate(top)
    ]

    return _sorted(
        {
            "v": 1,
            "kind": "week",
            "week": week,
            "start": start,
            "end": end,
            "stats": stats_for(articles),
            "charts": dict(charts),
            "days": days_list,
            "trending": [_trend_dict(t) for t in trending],
            "top": top_compact,
        }
    )


def index_items(day: str, articles: Sequence[Article]) -> list[dict[str, object]]:
    """Build search-index items for one day."""
    items: list[dict[str, object]] = []
    for index, article in enumerate(articles):
        title = article.title_vi or article.title or ""
        tags = " ".join(article.tags)
        snippet = (article.summary_vi or "")[:400]
        topic = f"{article.topic or ''} {article.category or ''}"
        searchable = fold(f"{title} {tags} {snippet} {article.source or ''} {topic}".strip())

        items.append(
            _sorted(
                {
                    "d": day,
                    "i": index,
                    "t": title,
                    "f": searchable,
                    "sn": _search_snippet(article.summary_vi or ""),
                    "s": article.source or "",
                    "sk": article.source_key or "",
                    "tr": article.tier,
                    "tp": article.topic or "",
                    "im": article.impact_level or "",
                    "sc": article.score,
                    "r": article.region or "",
                    "tg": list(article.tags),
                }
            )
        )
    return items


def index_payload(
    month: str,
    days: Sequence[str],
    items: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Build a search-index shard payload."""
    return _sorted(
        {
            "v": 1,
            "kind": "index",
            "month": month,
            "days": list(days),
            "items": [_sorted(dict(item)) for item in items],
        }
    )


def manifest(
    days: Sequence[tuple[str, int]],
    months: Sequence[str],
    entities: Sequence[Entity],
    *,
    weeks: Sequence[tuple[str, str, str]] = (),
    curated: Sequence[str] | None = None,
    substack: Sequence[str] | None = None,
    generated_at: str,
    kdf_iterations: int,
    site: str,
    version: str,
) -> dict[str, object]:
    """Build the plain-text manifest. It must never contain article text."""
    day_objs = [_sorted({"d": d, "n": n, "months": d[:7]}) for d, n in days]
    entity_objs = [_sorted({"slug": e.slug, "label": e.label, "n": e.mentions}) for e in entities]
    # Weeks are listed so the pruner can tell a live week page from an abandoned one; without
    # them it has to leave docs/w alone entirely rather than risk an unrecoverable delete.
    week_objs = [_sorted({"w": label, "s": start, "e": end}) for label, start, end in sorted(weeks)]

    data: dict[str, object] = {
        "v": 1,
        "site": site,
        "version": version,
        "generated_at": generated_at,
        "days": day_objs,
        "months": list(months),
        "kdf_iterations": kdf_iterations,
        "entities": entity_objs,
        "weeks": week_objs,
    }
    # Curated ids are YouTube video ids, which are already public identifiers and carry no
    # archive text. `None` means "this run did not survey them" and is written as an absent
    # key, which the pruner reads as "leave docs/c alone" — the same non-destructive
    # failure mode `weeks` uses. An empty list means "surveyed, and there are none".
    if curated is not None:
        data["curated"] = list(curated)
    # Same non-destructive contract as `curated`: `None` means this run did not survey
    # Substack essays and the pruner must leave docs/sub alone.
    if substack is not None:
        data["substack"] = list(substack)

    return _sorted(data)


def stats_for(articles: Sequence[Article]) -> dict[str, object]:
    """Return aggregate counts for a set of articles, sorted for stability."""
    return _sorted(
        {
            "total": len(articles),
            "sources": len({a.source for a in articles if a.source}),
            "by_topic": _count_values(a.topic for a in articles),
            "by_impact": _count_values(a.impact_level for a in articles),
            "by_region": _count_values(a.region for a in articles),
            "by_tier": _count_values(a.tier for a in articles),
        }
    )
