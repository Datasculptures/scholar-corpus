"""Tests for the build orchestration and catalogue output."""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

import pytest

from scholar_corpus.adapters.arxiv_kaggle import ArxivKaggleAdapter
from scholar_corpus.build import BuildConfig, build_corpus
from scholar_corpus.catalogue import count_rows, iter_rows
from scholar_corpus.manifest import read_manifest
from scholar_corpus.report import corpus_report
from scholar_corpus.scope import Scope
from tests.conftest import EXPECTED_DUPLICATES, EXPECTED_IN_SCOPE, EXPECTED_SCANNED


def test_build_counts_match_fixture(built_corpus: object) -> None:
    result = built_corpus
    assert result.counts["records"] == EXPECTED_IN_SCOPE  # type: ignore[attr-defined]
    assert result.counts["scanned"] == EXPECTED_SCANNED  # type: ignore[attr-defined]
    assert result.counts["duplicates_removed"] == EXPECTED_DUPLICATES  # type: ignore[attr-defined]
    assert result.counts["out_of_scope"] == EXPECTED_SCANNED - EXPECTED_IN_SCOPE  # type: ignore[attr-defined]
    assert result.counts["edges"] == 0  # type: ignore[attr-defined]


def test_build_writes_catalogue_and_manifest(built_corpus: object) -> None:
    result = built_corpus
    assert result.catalogue_path.is_file()  # type: ignore[attr-defined]
    assert result.manifest_path.is_file()  # type: ignore[attr-defined]
    total, unmatched = count_rows(result.catalogue_path)  # type: ignore[attr-defined]
    assert total == EXPECTED_IN_SCOPE
    # Phase 1 has no join, so every record is unmatched but retained.
    assert unmatched == EXPECTED_IN_SCOPE


def test_catalogue_rows_sorted_and_flagged(built_corpus: object) -> None:
    rows = list(iter_rows(built_corpus.catalogue_path))  # type: ignore[attr-defined]
    ids = [r["paper_id"] for r in rows]
    assert ids == sorted(ids)
    assert all(r["matched"] == 0 for r in rows)
    assert all(r["match_strategy"] is None for r in rows)


def test_manifest_records_provenance(built_corpus: object) -> None:
    manifest = read_manifest(built_corpus.corpus_dir)  # type: ignore[attr-defined]
    assert manifest.source["name"] == "arxiv"
    assert len(manifest.source["snapshot"]["sha256"]) == 64
    assert manifest.scope["categories"] == ["cs.AI", "cs.CL", "cs.LG", "stat.ML"]
    assert manifest.counts["records"] == EXPECTED_IN_SCOPE
    assert manifest.coverage is None
    assert manifest.content_sha256 == built_corpus.content_sha256  # type: ignore[attr-defined]


def test_report_matches_manifest(built_corpus: object) -> None:
    summary = corpus_report(built_corpus.corpus_dir)  # type: ignore[attr-defined]
    assert summary["records"] == EXPECTED_IN_SCOPE
    assert summary["matched"] == 0
    assert summary["unmatched"] == EXPECTED_IN_SCOPE
    assert summary["coverage"] is None


def test_build_accepts_logger(
    adapter: ArxivKaggleAdapter, scope: Scope, tmp_path: Path
) -> None:
    logger = logging.getLogger("test.build")
    config = BuildConfig(source=adapter, scope=scope, output_dir=tmp_path / "c")
    result = build_corpus(config, logger=logger)
    assert result.content_sha256


def test_invalid_edge_format_rejected(
    adapter: ArxivKaggleAdapter, scope: Scope, tmp_path: Path
) -> None:
    with pytest.raises(ValueError, match="edge_format"):
        BuildConfig(source=adapter, scope=scope, output_dir=tmp_path, edge_format="xml")


def test_invalid_coverage_gate_rejected(
    adapter: ArxivKaggleAdapter, scope: Scope, tmp_path: Path
) -> None:
    with pytest.raises(ValueError, match="coverage_gate"):
        BuildConfig(source=adapter, scope=scope, output_dir=tmp_path, coverage_gate=1.5)


def test_empty_scope_when_nothing_matches(
    adapter: ArxivKaggleAdapter, tmp_path: Path
) -> None:
    scope = Scope(source="arxiv", categories=("q.ZZ",), date_from=date(2020, 1, 1))
    config = BuildConfig(source=adapter, scope=scope, output_dir=tmp_path / "empty")
    result = build_corpus(config)
    assert result.counts["records"] == 0
