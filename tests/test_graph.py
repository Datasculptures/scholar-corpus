"""Unit tests for citation-graph extraction and the edge-list I/O."""

from __future__ import annotations

from pathlib import Path

import pytest

from scholar_corpus.enrichment.base import EnrichmentRecord
from scholar_corpus.graph import (
    build_edges,
    canonical_edges,
    edges_filename,
    read_edges,
    write_edges,
)
from scholar_corpus.models import PaperRecord


def _paper(pid: str, enrichment_id: str | None, *, matched: bool = True) -> PaperRecord:
    return PaperRecord(
        paper_id=pid,
        source="arxiv",
        source_id=pid.split(":", 1)[1],
        title="t",
        title_normalized="t",
        abstract="",
        authors=(),
        author_surnames=(),
        categories=("cs.LG",),
        primary_category="cs.LG",
        date_published=None,
        date_updated=None,
        version=None,
        matched=matched,
        enrichment_id=enrichment_id,
    )


def _enr(eid: str, refs: tuple[str, ...]) -> EnrichmentRecord:
    return EnrichmentRecord(enrichment_id=eid, title_normalized="t", referenced_ids=refs)


def test_edges_are_in_scope_only_and_counts_are_reported() -> None:
    records = [
        _paper("arxiv:A", "W1"),
        _paper("arxiv:B", "W2"),
        _paper("arxiv:C", "W3"),
        _paper("arxiv:U", None, matched=False),  # unmatched: contributes nothing
    ]
    matched = {
        "W1": _enr("W1", ("W2", "W99")),  # W99 is out of scope
        "W2": _enr("W2", ()),
        "W3": _enr("W3", ("W1", "W3")),  # W3->W3 is a self-loop
    }
    result = build_edges(records, matched)
    assert set(result.edges) == {("arxiv:A", "arxiv:B"), ("arxiv:C", "arxiv:A")}
    assert result.out_of_scope_references == 1
    assert result.self_references == 1
    assert result.node_count == 3
    assert result.edge_count == 2


def test_edges_sorted_by_target_then_source() -> None:
    records = [_paper("arxiv:A", "W1"), _paper("arxiv:B", "W2"), _paper("arxiv:C", "W3")]
    matched = {
        "W1": _enr("W1", ("W3",)),  # A -> C
        "W2": _enr("W2", ("W3",)),  # B -> C
        "W3": _enr("W3", ()),
    }
    result = build_edges(records, matched)
    # Both target C; ordered by source within the same target.
    assert result.edges == [("arxiv:A", "arxiv:C"), ("arxiv:B", "arxiv:C")]


def test_unmatched_paper_with_enrichment_absent_is_ignored() -> None:
    # A matched paper whose enrichment record is missing yields no edges/errors.
    records = [_paper("arxiv:A", "W1")]
    result = build_edges(records, {})
    assert result.edges == []
    assert result.out_of_scope_references == 0


@pytest.mark.parametrize("edge_format", ["csv.gz", "parquet"])
def test_edge_list_round_trips(edge_format: str, tmp_path: Path) -> None:
    edges = [("arxiv:C", "arxiv:A"), ("arxiv:A", "arxiv:B")]
    path = tmp_path / edges_filename(edge_format)
    write_edges(path, edges, edge_format=edge_format)
    assert path.is_file()
    assert read_edges(path, edge_format=edge_format) == edges


def test_canonical_edges_is_source_then_target() -> None:
    edges = [("b", "a"), ("a", "z"), ("a", "b")]
    assert list(canonical_edges(edges)) == [("a", "b"), ("a", "z"), ("b", "a")]
