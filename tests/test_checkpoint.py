"""Unit tests for the checkpoint store."""

from __future__ import annotations

from pathlib import Path

from scholar_corpus.checkpoint import (
    Checkpoint,
    checkpoint_path,
    clear_checkpoint,
    load_checkpoint,
    save_checkpoint,
)

FP = {"scope": "x", "edge_format": "csv.gz"}


def test_save_load_round_trip(tmp_path: Path) -> None:
    cp = Checkpoint(fingerprint=FP)
    cp.set("scan", {"records": [1, 2, 3], "complete": True})
    save_checkpoint(tmp_path, cp)
    # Atomic write leaves no temp file behind.
    assert not checkpoint_path(tmp_path).with_name("checkpoint.pkl.tmp").exists()
    loaded = load_checkpoint(tmp_path, FP)
    assert loaded is not None
    assert loaded.has("scan")
    assert loaded.get("scan")["records"] == [1, 2, 3]


def test_load_absent_returns_none(tmp_path: Path) -> None:
    assert load_checkpoint(tmp_path, FP) is None


def test_load_fingerprint_mismatch_returns_none(tmp_path: Path) -> None:
    save_checkpoint(tmp_path, Checkpoint(fingerprint=FP))
    assert load_checkpoint(tmp_path, {"scope": "different"}) is None


def test_load_corrupt_returns_none(tmp_path: Path) -> None:
    checkpoint_path(tmp_path).write_bytes(b"not a pickle at all")
    assert load_checkpoint(tmp_path, FP) is None


def test_load_wrong_version_returns_none(tmp_path: Path) -> None:
    cp = Checkpoint(fingerprint=FP, version=999)
    save_checkpoint(tmp_path, cp)
    assert load_checkpoint(tmp_path, FP) is None


def test_clear_removes_checkpoint(tmp_path: Path) -> None:
    save_checkpoint(tmp_path, Checkpoint(fingerprint=FP))
    clear_checkpoint(tmp_path)
    assert not checkpoint_path(tmp_path).exists()
    # Idempotent.
    clear_checkpoint(tmp_path)
