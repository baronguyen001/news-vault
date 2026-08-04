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


def similarity(left: Article, right: Article) -> float:
    """Jaccard overlap of the significant title tokens, boosted by shared tags."""
    left_tokens = tokens(left.title_vi)
    right_tokens = tokens(right.title_vi)
    if not left_tokens or not right_tokens:
        return 0.0

    union_size = len(left_tokens | right_tokens)
    jaccard = len(left_tokens & right_tokens) / union_size if union_size else 0.0

    left_tags = {fold(tag) for tag in left.tags}
    right_tags = {fold(tag) for tag in right.tags}
    shared_tag_count = len(left_tags & right_tags)

    return min(jaccard + 0.1 * shared_tag_count, 1.0)


class _UnionFind:
    """Simple union-find with path compression and union by rank."""

    __slots__ = ("parent", "rank")

    def __init__(self, size: int) -> None:
        self.parent: list[int] = list(range(size))
        self.rank: list[int] = [0] * size

    def find(self, index: int) -> int:
        parent = self.parent
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(self, left: int, right: int) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root == right_root:
            return
        if self.rank[left_root] < self.rank[right_root]:
            self.parent[left_root] = right_root
        elif self.rank[left_root] > self.rank[right_root]:
            self.parent[right_root] = left_root
        else:
            self.parent[right_root] = left_root
            self.rank[left_root] += 1


def cluster_articles(
    articles: Sequence[Article],
    *,
    threshold: float = DEFAULT_THRESHOLD,
) -> list[Cluster]:
    """Single-link agglomeration over articles from one day.

    Articles with fewer than three significant title tokens are ignored because
    their similarities are unreliable. The returned clusters are sorted by lead
    score descending.
    """
    filtered = [
        (index, article)
        for index, article in enumerate(articles)
        if len(tokens(article.title_vi)) >= 3
    ]
    count = len(filtered)
    if count == 0:
        return []

    union_find = _UnionFind(count)
    for left_pos in range(count):
        left_article = filtered[left_pos][1]
        for right_pos in range(left_pos + 1, count):
            right_article = filtered[right_pos][1]
            if left_article.topic != right_article.topic:
                continue
            if similarity(left_article, right_article) >= threshold:
                union_find.union(left_pos, right_pos)

    groups: dict[int, list[int]] = {}
    for position in range(count):
        root = union_find.find(position)
        groups.setdefault(root, []).append(position)

    clusters: list[Cluster] = []
    for member_positions in groups.values():
        members = tuple(filtered[position][1] for position in member_positions)
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
