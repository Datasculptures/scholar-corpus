"""Stage checkpoints for resumable builds.

A build can die at hour two; completed work must survive. After each pipeline
stage (and within the long scan stage at an interval) the build writes a
checkpoint. On restart it resumes from the last checkpoint by default.

The checkpoint is written atomically (temp file + ``os.replace``) so a crash
mid-write can never leave a truncated checkpoint — the exact failure mode that
motivated this feature. A ``fingerprint`` of the build inputs guards against
resuming into a checkpoint from a different scope or a changed snapshot; on any
mismatch, or any corruption, the checkpoint is ignored and the build starts
clean.

Checkpoints are pickled. They are internal artifacts the tool writes and reads
in the user's own output directory; they are never loaded from untrusted input.
"""

from __future__ import annotations

import os
import pickle
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CHECKPOINT_FILENAME = "checkpoint.pkl"
CHECKPOINT_VERSION = 1


@dataclass
class Checkpoint:
    """Completed-stage payloads for one build, plus an input fingerprint."""

    fingerprint: dict[str, Any]
    stages: dict[str, Any] = field(default_factory=dict)
    version: int = CHECKPOINT_VERSION

    def has(self, stage: str) -> bool:
        return stage in self.stages

    def get(self, stage: str) -> Any:
        return self.stages[stage]

    def set(self, stage: str, payload: Any) -> None:
        self.stages[stage] = payload


def checkpoint_path(corpus_dir: Path) -> Path:
    return Path(corpus_dir) / CHECKPOINT_FILENAME


def save_checkpoint(corpus_dir: Path, checkpoint: Checkpoint) -> None:
    """Write ``checkpoint`` atomically into ``corpus_dir``."""
    path = checkpoint_path(corpus_dir)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("wb") as handle:
        pickle.dump(checkpoint, handle, protocol=pickle.HIGHEST_PROTOCOL)
        handle.flush()
        os.fsync(handle.fileno())
    tmp.replace(path)


def load_checkpoint(corpus_dir: Path, fingerprint: dict[str, Any]) -> Checkpoint | None:
    """Load a checkpoint if present, valid, and matching ``fingerprint``.

    Returns ``None`` (meaning "start clean") when the checkpoint is absent,
    corrupt, an old version, or built from different inputs.
    """
    path = checkpoint_path(corpus_dir)
    if not path.is_file():
        return None
    try:
        with path.open("rb") as handle:
            obj = pickle.load(handle)
    except (pickle.UnpicklingError, EOFError, AttributeError, ValueError, ImportError):
        return None
    if not isinstance(obj, Checkpoint):
        return None
    if obj.version != CHECKPOINT_VERSION:
        return None
    if obj.fingerprint != fingerprint:
        return None
    return obj


def clear_checkpoint(corpus_dir: Path) -> None:
    """Remove any checkpoint (and stray temp file) for ``corpus_dir``."""
    path = checkpoint_path(corpus_dir)
    path.unlink(missing_ok=True)
    path.with_name(path.name + ".tmp").unlink(missing_ok=True)
