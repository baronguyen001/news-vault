from __future__ import annotations

import hashlib
import logging
from collections.abc import Sequence
from dataclasses import dataclass

from newsvault.model import Article
from newsvault.text import fold, tokens

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Cluster:
    """A group of articles covering the same story."""

    key: str
    lead: Article
    members: tuple[Article, ...]
    sources: tuple[str, ...]

    @property
    def size(self) -> int:
        """Number of articles in the cluster."""
        return len(self.members)


DEFAULT_THRESHOLD: float = 0.45
TAG_BOOST_FLOOR: float = 0.25
MAX_TAG_BOOST: float = 0.2
SAME_SOURCE_THRESHOLD: float = 0.7


def similarity(left: Article, right: Article) -> float:
    """Return title similarity, with a limited bonus for shared tags."""
    left_tokens = tokens(left.title_vi)
    right_tokens = tokens(right.title_vi)
    if not left_tokens or not right_tokens:
        return 0.0

    union_size = len(left_tokens | right_tokens)
    jaccard = len(left_tokens & right_tokens) / union_size if union_size else 0.0
    if jaccard < TAG_BOOST_FLOOR:
        return jaccard

    left_tags = {fold(tag) for tag in left.tags}
    right_tags = {fold(tag) for tag in right.tags}
    shared_tag_count = len(left_tags & right_tags)
    tag_boost = min(0.1 * shared_tag_count, MAX_TAG_BOOST)

    return min(jaccard + tag_boost, 1.0)


def _can_join_cluster(article: Article, leader: Article, threshold: float) -> bool:
    if article.topic != leader.topic:
        return False

    title_tokens = tokens(article.title_vi)
    leader_tokens = tokens(leader.title_vi)
    union_size = len(title_tokens | leader_tokens)
    jaccard = len(title_tokens & leader_tokens) / union_size if union_size else 0.0

    if fold(article.source) == fold(leader.source):
        return jaccard >= SAME_SOURCE_THRESHOLD

    return similarity(article, leader) >= threshold


def cluster_articles(
    articles: Sequence[Article],
    *,
    threshold: float = DEFAULT_THRESHOLD,
) -> list[Cluster]:
    """Group sufficiently similar articles from one day without chaining.

    Articles with fewer than three significant title tokens are ignored because
    their similarities are unreliable. The returned clusters are sorted by lead
    score descending.
    """
    filtered = [article for article in articles if len(tokens(article.title_vi)) >= 3]
    ordered = sorted(filtered, key=lambda article: (-article.score, article.url))
    if not ordered:
        return []

    grouped: list[list[Article]] = []
    for article in ordered:
        for group in grouped:
            if _can_join_cluster(article, group[0], threshold):
                group.append(article)
                break
        else:
            grouped.append([article])

    clusters: list[Cluster] = []
    for members in grouped:
        sorted_members = tuple(sorted(members, key=lambda article: (-article.score, article.url)))
        lead = sorted_members[0]
        member_urls = sorted(article.url for article in sorted_members)
        key = hashlib.sha1("\n".join(member_urls).encode("utf-8")).hexdigest()[:10]
        sources = tuple(sorted({article.source for article in sorted_members}))
        clusters.append(
            Cluster(key=key, lead=lead, members=sorted_members, sources=sources),
        )

    clusters.sort(key=lambda cluster: (-cluster.lead.score, cluster.lead.url))
    return clusters


def multi_source_clusters(
    clusters: Sequence[Cluster],
    *,
    min_size: int = 2,
) -> list[Cluster]:
    """Return only clusters reported by at least ``min_size`` distinct sources."""
    return [cluster for cluster in clusters if len(cluster.sources) >= min_size]
