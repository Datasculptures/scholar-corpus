"""Enrichment adapters supply citation edges and external identifiers."""

from __future__ import annotations

from scholar_corpus.enrichment.base import EnrichmentAdapter, EnrichmentRecord
from scholar_corpus.enrichment.openalex import OpenAlexSnapshotAdapter

__all__ = ["EnrichmentAdapter", "EnrichmentRecord", "OpenAlexSnapshotAdapter"]
