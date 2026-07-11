"""scholar-corpus: reproducible builder for joined, citation-linked scholarly corpora.

The public API is presentation-agnostic: it never prints, never reads ``sys.argv``,
and never calls ``sys.exit``. Callers own all input and output. The thin CLI in
:mod:`scholar_corpus.cli` is the only module permitted to do those things.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from scholar_corpus.build import BuildConfig, BuildResult, build_corpus
from scholar_corpus.enrichment.base import EnrichmentAdapter, EnrichmentRecord
from scholar_corpus.enrichment.openalex import OpenAlexSnapshotAdapter
from scholar_corpus.errors import (
    CoverageBelowGateError,
    InputTooLargeError,
    PathTraversalError,
    ScholarCorpusError,
    VerificationError,
)
from scholar_corpus.graph import GraphResult, build_edges
from scholar_corpus.join import CoverageReport, JoinOutcome, join_records
from scholar_corpus.manifest import Manifest, VerifyResult, verify_corpus
from scholar_corpus.models import PaperRecord
from scholar_corpus.scope import Scope

try:
    __version__ = version("scholar-corpus")
except PackageNotFoundError:  # pragma: no cover - only hit in a non-installed tree
    __version__ = "0.0.0+unknown"

__all__ = [
    "BuildConfig",
    "BuildResult",
    "CoverageBelowGateError",
    "CoverageReport",
    "EnrichmentAdapter",
    "EnrichmentRecord",
    "GraphResult",
    "InputTooLargeError",
    "JoinOutcome",
    "Manifest",
    "OpenAlexSnapshotAdapter",
    "PaperRecord",
    "PathTraversalError",
    "ScholarCorpusError",
    "Scope",
    "VerificationError",
    "VerifyResult",
    "__version__",
    "build_corpus",
    "build_edges",
    "join_records",
    "verify_corpus",
]
