"""Safe filesystem helpers: traversal guards, size caps, default artifact dir."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from scholar_corpus.errors import InputTooLargeError, PathTraversalError

# Default cap on any single ingested input file (bytes). The full arXiv Kaggle
# snapshot is a few GB; this leaves headroom while still refusing absurd inputs.
DEFAULT_MAX_INPUT_BYTES: int = 8 * 1024 * 1024 * 1024


def resolve_within(base: Path, candidate: Path | str) -> Path:
    """Resolve ``candidate`` and guarantee it stays inside ``base``.

    Raises :class:`PathTraversalError` if the resolved path escapes ``base``
    (via ``..`` segments, absolute reparenting, or symlinks).
    """
    base_resolved = Path(base).resolve()
    combined = Path(candidate)
    target = combined if combined.is_absolute() else base_resolved / combined
    target_resolved = target.resolve()
    if base_resolved != target_resolved and base_resolved not in target_resolved.parents:
        raise PathTraversalError(
            f"path {target_resolved} escapes base directory {base_resolved}"
        )
    return target_resolved


def check_input_size(path: Path, *, max_bytes: int = DEFAULT_MAX_INPUT_BYTES) -> int:
    """Return the size of ``path`` in bytes, raising if it exceeds ``max_bytes``."""
    size = Path(path).stat().st_size
    if size > max_bytes:
        raise InputTooLargeError(
            f"input {path} is {size} bytes, exceeding the cap of {max_bytes} bytes"
        )
    return size


_SYNC_MARKERS: tuple[str, ...] = ("onedrive", "dropbox", "google drive", "icloud")


def looks_like_sync_folder(path: Path) -> bool:
    """Heuristic: does any path segment look like a cloud-sync folder?

    Corpus artifacts should default to a location outside sync folders, because
    a multi-gigabyte, byte-reproducible artifact churning through OneDrive or
    Dropbox is both slow and pointless. Used only to warn, never to block.
    """
    lowered = [part.casefold() for part in Path(path).parts]
    return any(marker in part for part in lowered for marker in _SYNC_MARKERS)


def resolve_artifact_dir(os_name: str, environ: Mapping[str, str], home: Path) -> Path:
    """Pure resolver for the default artifact directory.

    Takes the platform, environment, and home directory as arguments so it is
    testable on any OS without monkeypatching ``os.name`` or ``Path.home()``.
    """
    override = environ.get("SCHOLAR_CORPUS_HOME")
    if override:
        return Path(override).expanduser()
    if os_name == "nt":
        base = environ.get("LOCALAPPDATA") or str(home / "AppData" / "Local")
        return Path(base) / "scholar-corpus" / "corpora"
    xdg = environ.get("XDG_DATA_HOME")
    base_path = Path(xdg) if xdg else home / ".local" / "share"
    return base_path / "scholar-corpus" / "corpora"


def default_artifact_dir() -> Path:
    """Return the default output directory, outside any repo or sync folder.

    Honours ``SCHOLAR_CORPUS_HOME`` if set. Otherwise uses the platform user
    data directory: ``%LOCALAPPDATA%`` on Windows, ``$XDG_DATA_HOME`` (or
    ``~/.local/share``) elsewhere.
    """
    return resolve_artifact_dir(os.name, os.environ, Path.home())
