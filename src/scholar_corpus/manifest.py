"""Provenance manifest and content hashing.

The content SHA-256 is computed over a canonical serialisation of the corpus
*content* (catalogue rows plus, when present, the citation edge list), read back
through the artifact read paths. It deliberately excludes wall-clock timestamps
and the manifest metadata itself, so the same scope against the same snapshots
yields a byte-identical hash. The edge hash sorts independently of file order and
format, so a parquet build and a csv.gz build of the same corpus share a hash.

``verify_corpus`` re-derives the hash from the artifacts on disk and compares it
to the value recorded in ``MANIFEST.json``.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scholar_corpus.catalogue import iter_rows
from scholar_corpus.graph import Edge, canonical_edges, edges_filename, read_edges

MANIFEST_FILENAME = "MANIFEST.json"
CATALOGUE_FILENAME = "catalogue.db"
MANIFEST_VERSION = 1
TOOL_NAME = "scholar-corpus"


def _canonical_line(mapping: dict[str, Any]) -> bytes:
    return json.dumps(
        mapping, sort_keys=True, ensure_ascii=True, separators=(",", ":")
    ).encode("ascii")


def compute_content_sha256(
    catalogue_path: Path, edges: Iterable[Edge] | None = None
) -> str:
    """Hash the canonical content of a corpus.

    Rows are read in ``paper_id`` order; edges (when supplied) are sorted into a
    canonical order independent of file layout and format. Both are serialised
    with sorted keys and fixed separators, behind domain-separator prefixes.
    """
    digest = hashlib.sha256()
    digest.update(b"scholar-corpus/v1\n")
    digest.update(b"section:papers\n")
    for row in iter_rows(catalogue_path):
        digest.update(_canonical_line(row))
        digest.update(b"\n")
    if edges is not None:
        digest.update(b"section:edges\n")
        for source, target in canonical_edges(edges):
            digest.update(_canonical_line({"s": source, "t": target}))
            digest.update(b"\n")
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class Manifest:
    """The provenance record written alongside a corpus."""

    tool_version: str
    source: dict[str, Any]
    scope: dict[str, Any]
    counts: dict[str, int]
    content_sha256: str
    coverage: dict[str, Any] | None = None
    enrichment: dict[str, Any] | None = None
    graph: dict[str, Any] | None = None
    manifest_version: int = MANIFEST_VERSION
    tool: str = TOOL_NAME

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifest_version": self.manifest_version,
            "tool": self.tool,
            "tool_version": self.tool_version,
            "source": self.source,
            "scope": self.scope,
            "counts": self.counts,
            "coverage": self.coverage,
            "enrichment": self.enrichment,
            "graph": self.graph,
            "content_sha256": self.content_sha256,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, indent=2, ensure_ascii=True)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Manifest:
        return cls(
            tool_version=str(data["tool_version"]),
            source=dict(data["source"]),
            scope=dict(data["scope"]),
            counts={k: int(v) for k, v in dict(data["counts"]).items()},
            content_sha256=str(data["content_sha256"]),
            coverage=data.get("coverage"),
            enrichment=data.get("enrichment"),
            graph=data.get("graph"),
            manifest_version=int(data.get("manifest_version", MANIFEST_VERSION)),
            tool=str(data.get("tool", TOOL_NAME)),
        )


def write_manifest(corpus_dir: Path, manifest: Manifest) -> Path:
    """Write ``MANIFEST.json`` into ``corpus_dir`` and return its path."""
    target = Path(corpus_dir) / MANIFEST_FILENAME
    target.write_text(manifest.to_json() + "\n", encoding="ascii")
    return target


def read_manifest(corpus_dir: Path) -> Manifest:
    """Read ``MANIFEST.json`` from ``corpus_dir``."""
    target = Path(corpus_dir) / MANIFEST_FILENAME
    data = json.loads(target.read_text(encoding="ascii"))
    return Manifest.from_dict(data)


@dataclass(frozen=True, slots=True)
class VerifyResult:
    """Outcome of verifying a corpus against its manifest."""

    ok: bool
    reason: str
    expected_sha256: str
    actual_sha256: str

    @property
    def failed(self) -> bool:
        return not self.ok


def verify_corpus(corpus_dir: Path) -> VerifyResult:
    """Re-hash the corpus at ``corpus_dir`` and compare to its manifest.

    Returns a :class:`VerifyResult`; it does not raise on mismatch, so callers
    decide how to react. The CLI turns a failed result into a non-zero exit. When
    the manifest records a citation graph, the edge list is re-read (in its
    recorded format) and folded into the hash.
    """
    corpus_dir = Path(corpus_dir)
    manifest = read_manifest(corpus_dir)
    catalogue_path = corpus_dir / CATALOGUE_FILENAME

    def fail(reason: str) -> VerifyResult:
        return VerifyResult(
            ok=False,
            reason=reason,
            expected_sha256=manifest.content_sha256,
            actual_sha256="",
        )

    if not catalogue_path.is_file():
        return fail(f"catalogue missing at {catalogue_path}")

    edges: list[Edge] | None = None
    if manifest.graph is not None:
        edge_format = str(manifest.graph.get("format", "csv.gz"))
        filename = str(manifest.graph.get("filename", edges_filename(edge_format)))
        edges_path = corpus_dir / filename
        if not edges_path.is_file():
            return fail(f"edge list missing at {edges_path}")
        edges = read_edges(edges_path, edge_format=edge_format)

    actual = compute_content_sha256(catalogue_path, edges)
    if actual != manifest.content_sha256:
        return VerifyResult(
            ok=False,
            reason="content hash does not match manifest",
            expected_sha256=manifest.content_sha256,
            actual_sha256=actual,
        )
    return VerifyResult(
        ok=True,
        reason="content hash matches manifest",
        expected_sha256=manifest.content_sha256,
        actual_sha256=actual,
    )
