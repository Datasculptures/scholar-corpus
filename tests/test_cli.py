"""Tests for the thin CLI: argument handling, rendering, and exit codes."""

from __future__ import annotations

from pathlib import Path

import pytest

from scholar_corpus import cli
from scholar_corpus.errors import CoverageBelowGateError, ScholarCorpusError


def _build_argv(snapshot: Path, out: Path) -> list[str]:
    return [
        "build",
        "--snapshot", str(snapshot),
        "--categories", "cs.LG", "cs.CL", "cs.AI", "stat.ML",
        "--date-from", "2020-01-01",
        "--output", str(out),
    ]


def test_info(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["info"]) == cli.EXIT_OK
    assert "scholar-corpus" in capsys.readouterr().out


def test_version_action(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0


def test_build_verify_report_roundtrip(
    snapshot_path: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "corpus"
    assert cli.main(_build_argv(snapshot_path, out)) == cli.EXIT_OK
    assert "sha256:" in capsys.readouterr().out

    assert cli.main(["verify", str(out)]) == cli.EXIT_OK
    assert "ok:" in capsys.readouterr().out

    assert cli.main(["report", str(out)]) == cli.EXIT_OK
    assert "records:" in capsys.readouterr().out

    assert cli.main(["report", str(out), "--json"]) == cli.EXIT_OK
    assert '"records"' in capsys.readouterr().out


def test_build_verbose(snapshot_path: Path, tmp_path: Path) -> None:
    argv = [*_build_argv(snapshot_path, tmp_path / "c"), "-v"]
    assert cli.main(argv) == cli.EXIT_OK


def test_build_warns_on_sync_folder(
    snapshot_path: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "OneDrive" / "corpus"
    assert cli.main(_build_argv(snapshot_path, out)) == cli.EXIT_OK
    assert "sync folder" in capsys.readouterr().err


def test_verify_tamper_exit_code(
    snapshot_path: Path, tmp_path: Path
) -> None:
    import sqlite3
    from contextlib import closing

    out = tmp_path / "corpus"
    assert cli.main(_build_argv(snapshot_path, out)) == cli.EXIT_OK
    with closing(sqlite3.connect(out / "catalogue.db")) as conn:
        conn.execute("UPDATE papers SET title = 'x' WHERE paper_id = 'arxiv:2101.00001'")
        conn.commit()
    assert cli.main(["verify", str(out)]) == cli.EXIT_VERIFY


def test_build_missing_snapshot_exit_error(tmp_path: Path) -> None:
    argv = ["build", "--snapshot", str(tmp_path / "nope.json"), "--output", str(tmp_path / "o")]
    assert cli.main(argv) == cli.EXIT_ERROR


def test_coverage_gate_exit_code(
    snapshot_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_args: object, **_kwargs: object) -> None:
        raise CoverageBelowGateError(0.5, 0.8)

    monkeypatch.setattr(cli, "build_corpus", boom)
    assert cli.main(_build_argv(snapshot_path, tmp_path / "c")) == cli.EXIT_COVERAGE


def test_generic_error_exit_code(
    snapshot_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_args: object, **_kwargs: object) -> None:
        raise ScholarCorpusError("kaboom")

    monkeypatch.setattr(cli, "build_corpus", boom)
    assert cli.main(_build_argv(snapshot_path, tmp_path / "c")) == cli.EXIT_ERROR


def test_missing_subcommand_is_usage_error() -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main([])
    assert exc.value.code == cli.EXIT_USAGE
