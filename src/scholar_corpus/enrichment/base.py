"""The enrichment adapter contract.

An enrichment adapter supplies external records that source papers are joined
against: external identifiers (DOI, arXiv id) for matching, and references for
the (Phase 3) citation graph. The interface is deliberately not OpenAlex-shaped,
so a Semantic Scholar adapter can be added without touching the join layer.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from scholar_corpus.adapters.base import SnapshotInfo


@dataclass(frozen=True, slots=True)
class EnrichmentRecord:
    """A normalised external record to join a source paper against.

    ``enrichment_id`` is the external system's stable id (for example an
    OpenAlex work id ``W123``). ``referenced_ids`` lists the enrichment ids this
    record cites; the join ignores it, but Phase 3 uses it to build the citation
    graph.
    """

    enrichment_id: str
    title_normalized: str
    doi: str | None = None
    arxiv_id: str | None = None
    publication_year: int | None = None
    author_surnames: tuple[str, ...] = ()
    referenced_ids: tuple[str, ...] = field(default=())


@runtime_checkable
class EnrichmentAdapter(Protocol):
    """Streaming, offline-friendly source of normalised enrichment records."""

    @property
    def source_name(self) -> str:
        """Stable identifier for the enrichment source, e.g. ``"openalex"``."""
        ...

    def snapshot(self) -> SnapshotInfo:
        """Return the immutable identity of the underlying snapshot."""
        ...

    def iter_records(self) -> Iterator[EnrichmentRecord]:
        """Yield every enrichment record as a normalised ``EnrichmentRecord``."""
        ...
