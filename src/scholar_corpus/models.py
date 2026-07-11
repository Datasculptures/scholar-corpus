"""Core record types.

:class:`PaperRecord` is the normalised, source-agnostic unit that flows through
the whole pipeline. Source adapters emit these; the catalogue persists them; the
join layer annotates them with match metadata.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from typing import Any

# Sentinel used for the join columns while a paper has not been matched.
UNMATCHED_STRATEGY: str | None = None

# match_strategy value stored for records the join could not confidently resolve
# (multiple candidates, or a title collapse). They stay unmatched and retained.
AMBIGUOUS_STRATEGY = "ambiguous"


@dataclass(frozen=True, slots=True)
class PaperRecord:
    """A single paper, normalised into a stable, source-agnostic shape.

    ``paper_id`` is the stable primary key (for example ``arxiv:2103.00001``).
    The trailing block of fields carries join metadata: ``matched`` is ``True``
    only for a confident match, ``match_strategy`` names the strategy (or
    ``"ambiguous"`` for a flagged non-match), and unmatched records are always
    retained rather than dropped.
    """

    paper_id: str
    source: str
    source_id: str
    title: str
    title_normalized: str
    abstract: str
    authors: tuple[str, ...]
    author_surnames: tuple[str, ...]
    categories: tuple[str, ...]
    primary_category: str
    date_published: str | None
    date_updated: str | None
    version: str | None
    doi: str | None = None
    # Join metadata.
    matched: bool = False
    match_strategy: str | None = None
    match_confidence: float | None = None
    enrichment_id: str | None = None
    published_year: int | None = field(default=None)

    def as_row(self) -> dict[str, Any]:
        """Return a flat, JSON/SQLite-friendly mapping with deterministic keys.

        Sequence fields are rendered as canonical JSON strings so the row is a
        pure scalar mapping suitable for both SQLite columns and content hashing.
        """
        return {
            "paper_id": self.paper_id,
            "source": self.source,
            "source_id": self.source_id,
            "doi": self.doi,
            "title": self.title,
            "title_normalized": self.title_normalized,
            "abstract": self.abstract,
            "authors_json": json.dumps(list(self.authors), ensure_ascii=True),
            "author_surnames_json": json.dumps(
                list(self.author_surnames), ensure_ascii=True
            ),
            "categories_json": json.dumps(list(self.categories), ensure_ascii=True),
            "primary_category": self.primary_category,
            "date_published": self.date_published,
            "date_updated": self.date_updated,
            "published_year": self.published_year,
            "version": self.version,
            "matched": int(self.matched),
            "match_strategy": self.match_strategy,
            "match_confidence": self.match_confidence,
            "enrichment_id": self.enrichment_id,
        }

    def with_match(
        self,
        *,
        strategy: str,
        confidence: float | None,
        enrichment_id: str | None,
    ) -> PaperRecord:
        """Return a copy annotated as a confident match by the given strategy."""
        return replace(
            self,
            matched=True,
            match_strategy=strategy,
            match_confidence=confidence,
            enrichment_id=enrichment_id,
        )

    def flag_ambiguous(self) -> PaperRecord:
        """Return a copy flagged ambiguous: retained, unmatched, no enrichment id."""
        return replace(
            self,
            matched=False,
            match_strategy=AMBIGUOUS_STRATEGY,
            match_confidence=None,
            enrichment_id=None,
        )


# The ordered column list is the single source of truth for the catalogue schema
# and for the canonical content serialisation. Keep row keys in this exact order.
CATALOGUE_COLUMNS: tuple[str, ...] = (
    "paper_id",
    "source",
    "source_id",
    "doi",
    "title",
    "title_normalized",
    "abstract",
    "authors_json",
    "author_surnames_json",
    "categories_json",
    "primary_category",
    "date_published",
    "date_updated",
    "published_year",
    "version",
    "matched",
    "match_strategy",
    "match_confidence",
    "enrichment_id",
)
