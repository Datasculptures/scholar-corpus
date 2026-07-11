"""Tests for path-traversal safety, size caps, and default artifact dir."""

from __future__ import annotations

from pathlib import Path

import pytest

from scholar_corpus.errors import InputTooLargeError, PathTraversalError
from scholar_corpus.paths import (
    check_input_size,
    default_artifact_dir,
    looks_like_sync_folder,
    resolve_artifact_dir,
    resolve_within,
)


def test_resolve_within_allows_child(tmp_path: Path) -> None:
    child = resolve_within(tmp_path, "sub/dir")
    assert str(child).startswith(str(tmp_path.resolve()))


def test_resolve_within_allows_base_itself(tmp_path: Path) -> None:
    assert resolve_within(tmp_path, ".") == tmp_path.resolve()


def test_resolve_within_rejects_parent_escape(tmp_path: Path) -> None:
    with pytest.raises(PathTraversalError):
        resolve_within(tmp_path, "../evil")


def test_resolve_within_rejects_absolute_escape(tmp_path: Path) -> None:
    with pytest.raises(PathTraversalError):
        resolve_within(tmp_path, "/etc/passwd")


def test_check_input_size_ok(tmp_path: Path) -> None:
    f = tmp_path / "f.txt"
    f.write_text("hello")
    assert check_input_size(f, max_bytes=100) == 5


def test_check_input_size_too_large(tmp_path: Path) -> None:
    f = tmp_path / "f.txt"
    f.write_text("hello world")
    with pytest.raises(InputTooLargeError):
        check_input_size(f, max_bytes=3)


def test_looks_like_sync_folder() -> None:
    assert looks_like_sync_folder(Path("/home/u/OneDrive/x"))
    assert looks_like_sync_folder(Path("/home/u/Dropbox/x"))
    assert not looks_like_sync_folder(Path("/home/u/data/x"))


def test_resolve_artifact_dir_env_override() -> None:
    result = resolve_artifact_dir("posix", {"SCHOLAR_CORPUS_HOME": "/tmp/sc-home"}, Path("/home/u"))
    assert result == Path("/tmp/sc-home")


def test_resolve_artifact_dir_posix_default() -> None:
    result = resolve_artifact_dir("posix", {}, Path("/home/u"))
    assert result.as_posix() == "/home/u/.local/share/scholar-corpus/corpora"


def test_resolve_artifact_dir_xdg() -> None:
    result = resolve_artifact_dir("posix", {"XDG_DATA_HOME": "/tmp/xdg"}, Path("/home/u"))
    assert result.as_posix() == "/tmp/xdg/scholar-corpus/corpora"


def test_resolve_artifact_dir_windows() -> None:
    result = resolve_artifact_dir(
        "nt", {"LOCALAPPDATA": "C:/Users/u/AppData/Local"}, Path("C:/Users/u")
    )
    assert result.as_posix().endswith("AppData/Local/scholar-corpus/corpora")


def test_resolve_artifact_dir_windows_no_localappdata() -> None:
    result = resolve_artifact_dir("nt", {}, Path("C:/Users/u"))
    assert result.as_posix().endswith("AppData/Local/scholar-corpus/corpora")


def test_default_artifact_dir_is_wired() -> None:
    assert default_artifact_dir().as_posix().endswith("scholar-corpus/corpora")
