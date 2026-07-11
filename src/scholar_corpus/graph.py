"""Citation graph: a self-contained, in-scope edge list.

Edges are directed **citing -> cited** and restricted to papers within scope, so
the graph has no dangling references and can be fed to graph algorithms without
special-casing missing endpoints. References that point outside the scope are
counted and reported rather than silently discarded, and self-citations are
dropped and counted.

Edges are derived from the enrichment records' ``referenced_ids``: for a matched
source paper whose enrichment record cites enrichment id ``R``, an edge is
emitted only when ``R`` is itself a matched, in-scope paper. The enrichment
records are indexed once (``enrichment_id -> paper_id``) and looked up per
reference, so extraction is O(references), never a nested scan.

The written edge list is ordered by ``(target_id, source_id)`` so that the
"citers of a paper" are contiguous — the index downstream consumers most often
need. The content hash (see :mod:`scholar_corpus.manifest`) sorts independently,
so it depends only on the edge set, not on file order or format.
"""

from __future__ import annotations

import csv
import gzip
import io
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scholar_corpus.enrichment.base import EnrichmentRecord
from scholar_corpus.models import PaperRecord

EDGE_DIRECTION = "citing_to_cited"
EDGE_COLUMNS = ("source_id", "target_id")
Edge = tuple[str, str]


@dataclass(frozen=True, slots=True)
class GraphResult:
    """The in-scope edge list plus self-containment bookkeeping."""

    edges: list[Edge]
    out_of_scope_references: int
    self_references: int

    @property
    def edge_count(self) -> int:
        return len(self.edges)

    @property
    def node_count(self) -> int:
        nodes: set[str] = set()
        for source, target in self.edges:
            nodes.add(source)
            nodes.add(target)
        return len(nodes)

    def as_manifest_section(self, *, edge_format: str, filename: str) -> dict[str, object]:
        return {
            "edges": self.edge_count,
            "nodes": self.node_count,
            "out_of_scope_references": self.out_of_scope_references,
            "self_references": self.self_references,
            "direction": EDGE_DIRECTION,
            "format": edge_format,
            "filename": filename,
        }


def build_edges(
    records: Iterable[PaperRecord],
    matched_enrichment: Mapping[str, EnrichmentRecord],
) -> GraphResult:
    """Build the self-contained, in-scope citation edge list.

    ``matched_enrichment`` maps each matched paper's enrichment id to its
    enrichment record (the only records whose references can produce in-scope
    edges). Only papers with an ``enrichment_id`` participate; unmatched and
    ambiguous papers contribute no edges.
    """
    id_to_paper: dict[str, str] = {
        r.enrichment_id: r.paper_id
        for r in records
        if r.matched and r.enrichment_id is not None
    }

    edges: set[Edge] = set()
    out_of_scope = 0
    self_refs = 0
    for enrichment_id, paper_id in id_to_paper.items():
        record = matched_enrichment.get(enrichment_id)
        if record is None:
            continue
        for ref in record.referenced_ids:
            target = id_to_paper.get(ref)
            if target is None:
                out_of_scope += 1
            elif target == paper_id:
                self_refs += 1
            else:
                edges.add((paper_id, target))

    ordered = sorted(edges, key=lambda e: (e[1], e[0]))
    return GraphResult(
        edges=ordered,
        out_of_scope_references=out_of_scope,
        self_references=self_refs,
    )


def edges_filename(edge_format: str) -> str:
    return "edges.parquet" if edge_format == "parquet" else "edges.csv.gz"


def write_edges(path: Path, edges: Iterable[Edge], *, edge_format: str) -> Path:
    """Write ``edges`` to ``path`` in the requested format. Returns ``path``."""
    path = Path(path)
    materialised = list(edges)
    if edge_format == "parquet":
        _write_parquet(path, materialised)
    elif edge_format == "csv.gz":
        _write_csv_gz(path, materialised)
    else:  # pragma: no cover - guarded by BuildConfig validation
        raise ValueError(f"unknown edge_format {edge_format!r}")
    return path


def read_edges(path: Path, *, edge_format: str) -> list[Edge]:
    """Read an edge list previously written by :func:`write_edges`."""
    path = Path(path)
    if edge_format == "parquet":
        return _read_parquet(path)
    if edge_format == "csv.gz":
        return _read_csv_gz(path)
    raise ValueError(f"unknown edge_format {edge_format!r}")  # pragma: no cover


def _write_csv_gz(path: Path, edges: list[Edge]) -> None:
    # mtime=0 keeps the gzip container byte-reproducible across runs.
    with gzip.GzipFile(filename=str(path), mode="wb", mtime=0) as raw:
        text = io.TextIOWrapper(raw, encoding="utf-8", newline="")
        writer = csv.writer(text)
        writer.writerow(EDGE_COLUMNS)
        writer.writerows(edges)
        text.flush()
        text.detach()


def _read_csv_gz(path: Path) -> list[Edge]:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        rows = iter(reader)
        next(rows, None)  # header
        return [(row[0], row[1]) for row in rows if len(row) >= 2]


def _write_parquet(path: Path, edges: list[Edge]) -> None:
    pa, pq = _import_pyarrow()
    table = pa.table(
        {
            "source_id": pa.array([s for s, _ in edges], type=pa.string()),
            "target_id": pa.array([t for _, t in edges], type=pa.string()),
        }
    )
    pq.write_table(table, str(path))


def _read_parquet(path: Path) -> list[Edge]:
    _pa, pq = _import_pyarrow()
    table = pq.read_table(str(path), columns=list(EDGE_COLUMNS))
    data = table.to_pydict()
    return list(zip(data["source_id"], data["target_id"], strict=True))


def _import_pyarrow() -> tuple[Any, Any]:
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ModuleNotFoundError as exc:  # pragma: no cover - exercised via message only
        raise ModuleNotFoundError(
            "the parquet edge format requires pyarrow; install "
            "'scholar-corpus[parquet]' or use --edge-format csv.gz"
        ) from exc
    return pa, pq


def canonical_edges(edges: Iterable[Edge]) -> Iterator[Edge]:
    """Yield edges in a canonical, format-independent order for hashing."""
    yield from sorted(edges, key=lambda e: (e[0], e[1]))
