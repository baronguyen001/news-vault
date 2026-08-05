from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

from newsvault.blindspot import Blindspot
from newsvault.cluster import Cluster
from newsvault.entities import Entity
from newsvault.model import Article
from newsvault.text import excerpt, fold
from newsvault.trends import Trend
from newsvault.videos import Video


def _sorted(value: dict[str, object]) -> dict[str, object]:
    """Return a new dict with keys sorted recursively."""
    return {k: _sorted(v) if isinstance(v, dict) else v for k, v in sorted(value.items())}


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
        }
    )


def video_index_items(videos: Sequence[Video]) -> list[dict[str, object]]:
    """Build search-index items for videos so the whole-archive search reaches them too."""
    items: list[dict[str, object]] = []
    for index, video in enumerate(videos):
        summary = " ".join(run for block in video.blocks for run, _ in block.runs)
        searchable = fold(f"{video.title} {video.channel} {video.video_type} {summary}".strip())
        items.append(
            _sorted(
                {
                    "d": video.day,
                    "i": index,
                    "k": "v",
                    "t": video.title,
                    "f": searchable,
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
    generated_at: str,
    kdf_iterations: int,
    site: str,
    version: str,
) -> dict[str, object]:
    """Build the plain-text manifest. It must never contain article text."""
    day_objs = [_sorted({"d": d, "n": n, "months": d[:7]}) for d, n in days]
    entity_objs = [_sorted({"slug": e.slug, "label": e.label, "n": e.mentions}) for e in entities]

    return _sorted(
        {
            "v": 1,
            "site": site,
            "version": version,
            "generated_at": generated_at,
            "days": day_objs,
            "months": list(months),
            "kdf_iterations": kdf_iterations,
            "entities": entity_objs,
        }
    )


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
