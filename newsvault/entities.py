from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field

from newsvault.model import Article
from newsvault.text import VI_STOPWORDS, slugify

DEFAULT_MIN_MENTIONS: int = 3
MIN_LABEL_LENGTH: int = 2


@dataclass(frozen=True, slots=True)
class Entity:
    """A recurring named thing derived from article tags."""

    slug: str
    label: str
    mentions: int
    days: tuple[str, ...]
    topics: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EntityIndex:
    """A collection of recurring entities with article-level lookups."""

    entities: tuple[Entity, ...]
    by_article: dict[str, tuple[str, ...]] = field(repr=False)
    _by_slug: dict[str, Entity] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_by_slug", {entity.slug: entity for entity in self.entities})

    def top(self, limit: int) -> tuple[Entity, ...]:
        """Return the ``limit`` most-mentioned entities."""
        if limit <= 0:
            return ()
        return self.entities[:limit]

    def get(self, slug: str) -> Entity | None:
        """Return the entity with the given slug, if any."""
        return self._by_slug.get(slug)


def build_entity_index(
    articles: Sequence[Article],
    *,
    min_mentions: int = DEFAULT_MIN_MENTIONS,
) -> EntityIndex:
    """Aggregate article tags into recurring entities.

    Tags are grouped by slug. The most common original spelling becomes the
    label. Entities that are stopwords, have very short labels, or fall below
    the mention threshold are dropped.
    """
    spellings: dict[str, Counter] = defaultdict(Counter)
    mentions: dict[str, int] = defaultdict(int)
    days: dict[str, set[str]] = defaultdict(set)
    topics: dict[str, set[str]] = defaultdict(set)

    for article in articles:
        for tag in article.tags:
            slug = slugify(tag)
            if not slug:
                continue
            spellings[slug][tag] += 1
            mentions[slug] += 1
            days[slug].add(article.day)
            topics[slug].add(article.topic)

    kept_slugs: set[str] = set()
    entities: list[Entity] = []
    for slug, counter in spellings.items():
        if slug in VI_STOPWORDS:
            continue
        highest_count = max(counter.values())
        candidate_labels = [label for label, count in counter.items() if count == highest_count]
        label = min(candidate_labels)
        if len(label) < MIN_LABEL_LENGTH:
            continue
        mention_count = mentions[slug]
        if mention_count < min_mentions:
            continue
        kept_slugs.add(slug)
        entities.append(
            Entity(
                slug=slug,
                label=label,
                mentions=mention_count,
                days=tuple(sorted(days[slug])),
                topics=tuple(sorted(topics[slug])),
            ),
        )

    entities.sort(key=lambda entity: (-entity.mentions, entity.slug))

    by_article: dict[str, list[str]] = defaultdict(list)
    for article in articles:
        seen: set[str] = set()
        for tag in article.tags:
            slug = slugify(tag)
            if slug in kept_slugs and slug not in seen:
                seen.add(slug)
                by_article[article.url].append(slug)

    by_article_sorted = {url: tuple(sorted(slugs)) for url, slugs in by_article.items()}

    return EntityIndex(entities=tuple(entities), by_article=by_article_sorted)
