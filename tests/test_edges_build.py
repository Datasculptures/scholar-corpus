"""Build-level tests for the citation graph, manifest, hashing, and verify."""

from __future__ import annotations

import gzip
from pathlib import Path

from scholar_corpus.adapters.arxiv_kaggle import ArxivKaggleAdapter
from scholar_corpus.build import BuildConfig, build_corpus
from scholar_corpus.enrichment.openalex import OpenAlexSnapshotAdapter
from scholar_corpus.graph import read_edges
from scholar_corpus.manifest import read_manifest, verify_corpus
from scholar_corpus.scope import Scope
from tests.conftest import (
    EXPECTED_EDGES,
    EXPECTED_OUT_OF_SCOPE_REFS,
    EXPECTED_SELF_REFS,
)


def _build(
    snapshot: Path, oa: Path, scope: Scope, out: Path, edge_format: str = "csv.gz"
) -> object:
    return build_corpus(
        BuildConfig(
            source=ArxivKaggleAdapter(snapshot),
            scope=scope,
            output_dir=out,
            enrichment=OpenAlexSnapshotAdapter(oa),
            edge_format=edge_format,
            coverage_gate=0.5,
        )
    )


def test_graph_counts_and_self_containment(
    snapshot_path: Path, openalex_snapshot_path: Path, scope: Scope, tmp_path: Path
) -> None:
    result = _build(snapshot_path, openalex_snapshot_path, scope, tmp_path / "c")
    assert result.counts["edges"] == EXPECTED_EDGES  # type: ignore[attr-defined]
    assert result.counts["out_of_scope_references"] == EXPECTED_OUT_OF_SCOPE_REFS  # type: ignore[attr-defined]
    assert result.counts["self_references"] == EXPECTED_SELF_REFS  # type: ignore[attr-defined]

    manifest = read_manifest(result.corpus_dir)  # type: ignore[attr-defined]
    assert manifest.graph is not None
    assert manifest.graph["direction"] == "citing_to_cited"
    assert manifest.graph["edges"] == EXPECTED_EDGES

    # Self-containment: every endpoint is a paper in the catalogue.
    edges = read_edges(result.edges_path, edge_format="csv.gz")  # type: ignore[attr-defined]
    catalogue_ids = {"arxiv:2101.00001", "arxiv:2102.00002", "arxiv:2103.00003",
                     "arxiv:2108.00012", "arxiv:hep-ph/9901001"}
    for source, target in edges:
        assert source in catalogue_ids
        assert target in catalogue_ids


def test_verify_ok_with_edges(
    snapshot_path: Path, openalex_snapshot_path: Path, scope: Scope, tmp_path: Path
) -> None:
    result = _build(snapshot_path, openalex_snapshot_path, scope, tmp_path / "c")
    assert verify_corpus(result.corpus_dir).ok  # type: ignore[attr-defined]


def test_verify_fails_when_edges_tampered(
    snapshot_path: Path, openalex_snapshot_path: Path, scope: Scope, tmp_path: Path
) -> None:
    result = _build(snapshot_path, openalex_snapshot_path, scope, tmp_path / "c")
    edges_path = result.edges_path  # type: ignore[attr-defined]
    # Append a fabricated edge to the gzip csv.
    original = read_edges(edges_path, edge_format="csv.gz")
    with gzip.open(edges_path, "wt", encoding="utf-8", newline="") as handle:
        handle.write("source_id,target_id\n")
        for s, t in original:
            handle.write(f"{s},{t}\n")
        handle.write("arxiv:2101.00001,arxiv:2103.00003\n")
    assert verify_corpus(result.corpus_dir).failed  # type: ignore[attr-defined]


def test_verify_fails_when_edges_missing(
    snapshot_path: Path, openalex_snapshot_path: Path, scope: Scope, tmp_path: Path
) -> None:
    result = _build(snapshot_path, openalex_snapshot_path, scope, tmp_path / "c")
    Path(result.edges_path).unlink()  # type: ignore[attr-defined]
    verdict = verify_corpus(result.corpus_dir)  # type: ignore[attr-defined]
    assert verdict.failed
    assert "edge list missing" in verdict.reason


def test_content_hash_is_edge_format_independent(
    snapshot_path: Path, openalex_snapshot_path: Path, scope: Scope, tmp_path: Path
) -> None:
    csv_build = _build(snapshot_path, openalex_snapshot_path, scope, tmp_path / "csv", "csv.gz")
    pq_build = _build(snapshot_path, openalex_snapshot_path, scope, tmp_path / "pq", "parquet")
    assert csv_build.content_sha256 == pq_build.content_sha256  # type: ignore[attr-defined]
    # And the parquet corpus verifies against its own manifest.
    assert verify_corpus(pq_build.corpus_dir).ok  # type: ignore[attr-defined]


def test_determinism_with_edges(
    snapshot_path: Path, openalex_snapshot_path: Path, scope: Scope, tmp_path: Path
) -> None:
    a = _build(snapshot_path, openalex_snapshot_path, scope, tmp_path / "a")
    b = _build(snapshot_path, openalex_snapshot_path, scope, tmp_path / "b")
    assert a.content_sha256 == b.content_sha256  # type: ignore[attr-defined]


def test_catalogue_only_build_has_no_graph(
    snapshot_path: Path, scope: Scope, tmp_path: Path
) -> None:
    result = build_corpus(
        BuildConfig(
            source=ArxivKaggleAdapter(snapshot_path), scope=scope, output_dir=tmp_path / "c"
        )
    )
    assert result.counts["edges"] == 0
    assert result.graph is None
    assert read_manifest(result.corpus_dir).graph is None
    assert verify_corpus(result.corpus_dir).ok
