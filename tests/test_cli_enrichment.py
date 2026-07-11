"""CLI tests for the enrichment path and the coverage-gate exit code."""

from __future__ import annotations

from pathlib import Path

import pytest

from scholar_corpus import cli


def _argv(snapshot: Path, oa: Path, out: Path, gate: str) -> list[str]:
    return [
        "build",
        "--snapshot", str(snapshot),
        "--categories", "cs.LG", "cs.CL", "cs.AI", "stat.ML",
        "--date-from", "2020-01-01",
        "--enrichment", "openalex",
        "--enrichment-snapshot", str(oa),
        "--coverage-gate", gate,
        "--output", str(out),
    ]


def test_build_with_enrichment_ok(
    snapshot_path: Path, openalex_snapshot_path: Path, tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    out = tmp_path / "corpus"
    assert cli.main(_argv(snapshot_path, openalex_snapshot_path, out, "0.5")) == cli.EXIT_OK
    printed = capsys.readouterr().out
    assert "coverage:" in printed
    assert "strategy:" in printed

    assert cli.main(["report", str(out)]) == cli.EXIT_OK
    assert "ambiguous:" in capsys.readouterr().out


def test_coverage_gate_exit_code_real(
    snapshot_path: Path, openalex_snapshot_path: Path, tmp_path: Path,
) -> None:
    out = tmp_path / "corpus"
    rc = cli.main(_argv(snapshot_path, openalex_snapshot_path, out, "0.8"))
    assert rc == cli.EXIT_COVERAGE


def test_enrichment_requires_snapshot(snapshot_path: Path, tmp_path: Path) -> None:
    argv = [
        "build", "--snapshot", str(snapshot_path),
        "--enrichment", "openalex",
        "--output", str(tmp_path / "o"),
    ]
    assert cli.main(argv) == cli.EXIT_ERROR


def test_build_writes_flushed_log_file(
    snapshot_path: Path, openalex_snapshot_path: Path, tmp_path: Path
) -> None:
    out = tmp_path / "corpus"
    assert cli.main(_argv(snapshot_path, openalex_snapshot_path, out, "0.5")) == cli.EXIT_OK
    log = out / "build.log"
    assert log.is_file()
    text = log.read_text(encoding="utf-8")
    assert "scanning source" in text
    assert "build complete" in text
