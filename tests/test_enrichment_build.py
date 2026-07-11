"""Build-level tests for enrichment, coverage recording, and the gate."""

from __future__ import annotations

from pathlib import Path

import pytest

from scholar_corpus.adapters.arxiv_kaggle import ArxivKaggleAdapter
from scholar_corpus.build import BuildConfig, build_corpus
from scholar_corpus.enrichment.openalex import OpenAlexSnapshotAdapter
from scholar_corpus.errors import CoverageBelowGateError
from scholar_corpus.manifest import read_manifest, verify_corpus
from scholar_corpus.scope import Scope
from tests.conftest import EXPECTED_BY_STRATEGY, EXPECTED_MATCHED


def _config(
    adapter: ArxivKaggleAdapter,
    enrichment: OpenAlexSnapshotAdapter,
    scope: Scope,
    out: Path,
    gate: float = 0.5,
) -> BuildConfig:
    return BuildConfig(
        source=adapter, scope=scope, output_dir=out, enrichment=enrichment, coverage_gate=gate
    )


def test_build_with_enrichment_records_coverage(
    adapter: ArxivKaggleAdapter,
    enrichment: OpenAlexSnapshotAdapter,
    scope: Scope,
    tmp_path: Path,
) -> None:
    result = build_corpus(_config(adapter, enrichment, scope, tmp_path / "c", gate=0.5))
    assert result.coverage is not None
    assert result.coverage["matched"] == EXPECTED_MATCHED
    assert result.coverage["by_strategy"] == EXPECTED_BY_STRATEGY
    assert result.counts["matched"] == EXPECTED_MATCHED

    manifest = read_manifest(result.corpus_dir)
    assert manifest.coverage is not None
    assert manifest.enrichment is not None
    assert manifest.enrichment["name"] == "openalex"
    assert len(manifest.enrichment["snapshot"]["sha256"]) == 64
    assert verify_corpus(result.corpus_dir).ok


def test_coverage_gate_raises_below_floor(
    adapter: ArxivKaggleAdapter,
    enrichment: OpenAlexSnapshotAdapter,
    scope: Scope,
    tmp_path: Path,
) -> None:
    out = tmp_path / "degraded"
    with pytest.raises(CoverageBelowGateError) as exc:
        build_corpus(_config(adapter, enrichment, scope, out, gate=0.8))
    assert exc.value.coverage < 0.8
    # Artifacts are still written so the degraded corpus is inspectable.
    assert (out / "catalogue.db").is_file()
    assert (out / "MANIFEST.json").is_file()


def test_determinism_with_enrichment(
    snapshot_path: Path,
    openalex_snapshot_path: Path,
    scope: Scope,
    tmp_path: Path,
) -> None:
    def once(where: str) -> str:
        result = build_corpus(
            _config(
                ArxivKaggleAdapter(snapshot_path),
                OpenAlexSnapshotAdapter(openalex_snapshot_path),
                scope,
                tmp_path / where,
                gate=0.5,
            )
        )
        return result.content_sha256

    assert once("a") == once("b")
