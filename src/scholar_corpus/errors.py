"""Exception hierarchy for scholar-corpus.

Library code raises these; it never calls ``sys.exit``. The CLI maps them to
process exit codes (see :mod:`scholar_corpus.cli`).
"""

from __future__ import annotations


class ScholarCorpusError(Exception):
    """Base class for every error raised by this package."""


class PathTraversalError(ScholarCorpusError):
    """A user-supplied path escaped its permitted base directory."""


class InputTooLargeError(ScholarCorpusError):
    """An ingested input file exceeded the configured size cap."""


class VerificationError(ScholarCorpusError):
    """A corpus failed verification against its manifest."""


class CoverageBelowGateError(ScholarCorpusError):
    """Join coverage fell below the configured minimum (Phase 2+)."""

    def __init__(self, coverage: float, gate: float) -> None:
        self.coverage = coverage
        self.gate = gate
        super().__init__(
            f"join coverage {coverage:.4f} is below the gate {gate:.4f}",
        )
