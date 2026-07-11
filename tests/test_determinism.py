"""Determinism is a correctness property: identical inputs, identical hash."""

from __future__ import annotations

from pathlib import Path

from scholar_corpus.adapters.arxiv_kaggle import ArxivKaggleAdapter
from scholar_corpus.build import BuildConfig, build_corpus
from scholar_corpus.scope import Scope


def test_two_builds_produce_identical_sha256(
    snapshot_path: Path, scope: Scope, tmp_path: Path
) -> None:
    first = build_corpus(
        BuildConfig(
            source=ArxivKaggleAdapter(snapshot_path),
            scope=scope,
            output_dir=tmp_path / "a",
        )
    )
    second = build_corpus(
        BuildConfig(
            source=ArxivKaggleAdapter(snapshot_path),
            scope=scope,
            output_dir=tmp_path / "b",
        )
    )
    assert first.content_sha256 == second.content_sha256


def test_snapshot_hash_is_stable(snapshot_path: Path) -> None:
    a = ArxivKaggleAdapter(snapshot_path).snapshot()
    b = ArxivKaggleAdapter(snapshot_path).snapshot()
    assert a == b
