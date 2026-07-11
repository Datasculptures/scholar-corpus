"""Resumability: interrupt a build, resume, and match the uninterrupted result."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from scholar_corpus.adapters.arxiv_kaggle import ArxivKaggleAdapter
from scholar_corpus.adapters.base import SnapshotInfo
from scholar_corpus.build import BuildConfig, build_corpus
from scholar_corpus.checkpoint import checkpoint_path
from scholar_corpus.enrichment.openalex import OpenAlexSnapshotAdapter
from scholar_corpus.models import PaperRecord
from scholar_corpus.scope import Scope


class _FailAfter:
    """Wrap a source adapter and raise after yielding ``fail_after`` records."""

    def __init__(self, inner: ArxivKaggleAdapter, fail_after: int) -> None:
        self._inner = inner
        self._fail_after = fail_after

    @property
    def source_name(self) -> str:
        return self._inner.source_name

    @property
    def path(self) -> Path:
        return self._inner.path

    def snapshot(self) -> SnapshotInfo:
        return self._inner.snapshot()

    def iter_records(self) -> Iterator[PaperRecord]:
        for i, record in enumerate(self._inner.iter_records()):
            if i >= self._fail_after:
                raise RuntimeError("simulated crash mid-scan")
            yield record


def _uninterrupted(snapshot: Path, scope: Scope, out: Path) -> str:
    return build_corpus(
        BuildConfig(source=ArxivKaggleAdapter(snapshot), scope=scope, output_dir=out)
    ).content_sha256


def test_resume_after_midscan_crash_matches_uninterrupted(
    snapshot_path: Path, scope: Scope, tmp_path: Path
) -> None:
    full = _uninterrupted(snapshot_path, scope, tmp_path / "full")

    out = tmp_path / "resumed"
    failing = _FailAfter(ArxivKaggleAdapter(snapshot_path), fail_after=6)
    with pytest.raises(RuntimeError, match="mid-scan"):
        build_corpus(
            BuildConfig(source=failing, scope=scope, output_dir=out, checkpoint_interval=3)
        )
    # A partial scan checkpoint survived the crash.
    assert checkpoint_path(out).is_file()

    resumed = build_corpus(
        BuildConfig(source=ArxivKaggleAdapter(snapshot_path), scope=scope, output_dir=out)
    )
    assert resumed.resumed is True
    assert resumed.content_sha256 == full
    # Checkpoint is cleared once the build finishes.
    assert not checkpoint_path(out).is_file()


def test_resume_after_finalize_crash_reuses_all_stages(
    snapshot_path: Path,
    openalex_snapshot_path: Path,
    scope: Scope,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _cfg(out: Path) -> BuildConfig:
        return BuildConfig(
            source=ArxivKaggleAdapter(snapshot_path),
            scope=scope,
            output_dir=out,
            enrichment=OpenAlexSnapshotAdapter(openalex_snapshot_path),
            coverage_gate=0.5,
        )

    full = build_corpus(_cfg(tmp_path / "full")).content_sha256

    def _boom(*_a: object, **_k: object) -> None:
        raise RuntimeError("crash in finalize")

    out = tmp_path / "resumed"
    monkeypatch.setattr("scholar_corpus.build.write_manifest", _boom)
    with pytest.raises(RuntimeError, match="finalize"):
        build_corpus(_cfg(out))
    assert checkpoint_path(out).is_file()

    monkeypatch.undo()
    resumed = build_corpus(_cfg(out))
    assert resumed.resumed is True
    assert resumed.content_sha256 == full


def test_restart_ignores_checkpoint(
    snapshot_path: Path, scope: Scope, tmp_path: Path
) -> None:
    out = tmp_path / "c"
    failing = _FailAfter(ArxivKaggleAdapter(snapshot_path), fail_after=6)
    with pytest.raises(RuntimeError):
        build_corpus(
            BuildConfig(source=failing, scope=scope, output_dir=out, checkpoint_interval=3)
        )
    assert checkpoint_path(out).is_file()

    result = build_corpus(
        BuildConfig(
            source=ArxivKaggleAdapter(snapshot_path), scope=scope, output_dir=out, restart=True
        )
    )
    assert result.resumed is False
    assert result.content_sha256 == _uninterrupted(snapshot_path, scope, tmp_path / "ref")


def test_invalid_checkpoint_interval_rejected(
    snapshot_path: Path, scope: Scope, tmp_path: Path
) -> None:
    with pytest.raises(ValueError, match="checkpoint_interval"):
        BuildConfig(
            source=ArxivKaggleAdapter(snapshot_path),
            scope=scope,
            output_dir=tmp_path,
            checkpoint_interval=0,
        )
