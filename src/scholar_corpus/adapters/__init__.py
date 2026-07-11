"""Source adapters define the in-scope paper set for a corpus build."""

from __future__ import annotations

from scholar_corpus.adapters.arxiv_kaggle import ArxivKaggleAdapter
from scholar_corpus.adapters.base import SnapshotInfo, SourceAdapter

__all__ = ["ArxivKaggleAdapter", "SnapshotInfo", "SourceAdapter"]
