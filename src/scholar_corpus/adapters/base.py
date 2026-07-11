"""The source adapter contract.

A source adapter defines the *in-scope paper set*: it streams normalised
:class:`~scholar_corpus.models.PaperRecord` objects and reports an immutable
snapshot identity. It knows nothing about enrichment or the join layer, so a
second source (bioRxiv, a DOI list) can be added without touching either.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from scholar_corpus.models import PaperRecord


@dataclass(frozen=True, slots=True)
class SnapshotInfo:
    """Immutable identity of a source snapshot, for the provenance manifest.

    ``sha256`` is over the raw snapshot bytes and pins the exact input, so a
    rebuild against the same snapshot is reproducible and auditable.
    """

    name: str
    sha256: str
    byte_size: int

    def as_dict(self) -> dict[str, str | int]:
        return {"name": self.name, "sha256": self.sha256, "byte_size": self.byte_size}


@runtime_checkable
class SourceAdapter(Protocol):
    """Streaming, offline-friendly source of normalised paper records."""

    @property
    def source_name(self) -> str:
        """Stable identifier for the source, for example ``"arxiv"``."""
        ...

    def snapshot(self) -> SnapshotInfo:
        """Return the immutable identity of the underlying snapshot."""
        ...

    def iter_records(self) -> Iterator[PaperRecord]:
        """Yield every record in the snapshot as a normalised ``PaperRecord``.

        Scope filtering and deduplication are the build layer's job, not the
        adapter's, so this yields the full snapshot in a streaming fashion.
        """
        ...
