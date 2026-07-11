"""Thin CLI over the library API.

This is the only module permitted to print, read ``argv``, and choose process
exit codes. It contains no build logic; it parses arguments, calls the library,
renders results, and maps outcomes to exit codes.

Exit codes:

* ``0`` success
* ``1`` unexpected error
* ``2`` usage error (argparse)
* ``3`` join coverage below the configured gate
* ``4`` verification failed
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from scholar_corpus import __version__
from scholar_corpus.adapters.arxiv_kaggle import ArxivKaggleAdapter
from scholar_corpus.build import DEFAULT_CHECKPOINT_INTERVAL, BuildConfig, build_corpus
from scholar_corpus.enrichment.base import EnrichmentAdapter
from scholar_corpus.enrichment.openalex import OpenAlexSnapshotAdapter
from scholar_corpus.errors import (
    CoverageBelowGateError,
    ScholarCorpusError,
)
from scholar_corpus.manifest import verify_corpus
from scholar_corpus.paths import (
    DEFAULT_MAX_INPUT_BYTES,
    default_artifact_dir,
    looks_like_sync_folder,
)
from scholar_corpus.report import corpus_report
from scholar_corpus.scope import Scope

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_COVERAGE = 3
EXIT_VERIFY = 4


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="scholar-corpus", description=__doc__)
    parser.add_argument("--version", action="version", version=f"scholar-corpus {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="build a corpus from a source snapshot")
    build.add_argument("--source", choices=["arxiv"], default="arxiv")
    build.add_argument("--snapshot", required=True, type=Path, help="path to the source snapshot")
    build.add_argument("--categories", nargs="*", default=[], help="in-scope categories (OR)")
    build.add_argument("--date-from", type=_parse_date, default=None)
    build.add_argument("--date-to", type=_parse_date, default=None)
    build.add_argument("--enrichment", choices=["none", "openalex"], default="none")
    build.add_argument(
        "--enrichment-snapshot", type=Path, default=None, help="path to the enrichment snapshot"
    )
    build.add_argument("--output", type=Path, default=None, help="corpus output directory")
    build.add_argument("--edge-format", choices=["parquet", "csv.gz"], default="parquet")
    build.add_argument("--coverage-gate", type=float, default=0.80)
    build.add_argument("--max-input-bytes", type=int, default=DEFAULT_MAX_INPUT_BYTES)
    build.add_argument("--restart", action="store_true", help="ignore any checkpoint and rebuild")
    build.add_argument(
        "--log-file", type=Path, default=None, help="build log (default: <output>/build.log)"
    )
    build.add_argument(
        "--checkpoint-interval", type=int, default=DEFAULT_CHECKPOINT_INTERVAL,
        help="records scanned between intra-stage checkpoints",
    )
    build.add_argument("-v", "--verbose", action="store_true")

    verify = sub.add_parser("verify", help="verify a corpus against its manifest")
    verify.add_argument("corpus_dir", type=Path)

    report = sub.add_parser("report", help="print a summary of an existing corpus")
    report.add_argument("corpus_dir", type=Path)
    report.add_argument("--json", action="store_true", help="emit machine-readable JSON")

    sub.add_parser("info", help="print tool version and default paths")
    return parser


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:  # pragma: no cover - argparse wraps the message
        raise argparse.ArgumentTypeError(f"invalid date {value!r}, expected YYYY-MM-DD") from exc


def _make_enrichment(args: argparse.Namespace) -> EnrichmentAdapter | None:
    if args.enrichment == "none":
        return None
    if args.enrichment_snapshot is None:
        raise ValueError("--enrichment openalex requires --enrichment-snapshot")
    return OpenAlexSnapshotAdapter(args.enrichment_snapshot, max_bytes=args.max_input_bytes)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            return _cmd_build(args)
        if args.command == "verify":
            return _cmd_verify(args)
        if args.command == "report":
            return _cmd_report(args)
        if args.command == "info":
            return _cmd_info()
    except CoverageBelowGateError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_COVERAGE
    except (ScholarCorpusError, FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    return EXIT_USAGE  # pragma: no cover - unreachable with required subcommand


def _configure_build_logging(output: Path, log_file: Path | None, verbose: bool) -> logging.Logger:
    """Attach a flushed file handler (and optional console) to the build logger.

    A ``FileHandler`` flushes on every record, so a long build's log survives a
    crash instead of dying in an unflushed buffer.
    """
    output.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("scholar_corpus.build")
    logger.setLevel(logging.INFO)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    logger.propagate = False
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    file_handler = logging.FileHandler(log_file or output / "build.log", encoding="utf-8")
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)
    if verbose:
        console = logging.StreamHandler(sys.stderr)
        console.setFormatter(fmt)
        logger.addHandler(console)
    return logger


def _cmd_build(args: argparse.Namespace) -> int:
    output = Path(args.output) if args.output else default_artifact_dir() / "corpus"
    if looks_like_sync_folder(output):
        print(
            f"warning: output {output} looks like a cloud-sync folder; "
            "large reproducible artifacts do not belong in sync folders",
            file=sys.stderr,
        )
    logger = _configure_build_logging(output, args.log_file, args.verbose)
    adapter = ArxivKaggleAdapter(args.snapshot, max_bytes=args.max_input_bytes)
    scope = Scope(
        source=args.source,
        categories=tuple(args.categories),
        date_from=args.date_from,
        date_to=args.date_to,
    )
    config = BuildConfig(
        source=adapter,
        scope=scope,
        output_dir=output,
        enrichment=_make_enrichment(args),
        edge_format=args.edge_format,
        coverage_gate=args.coverage_gate,
        restart=args.restart,
        checkpoint_interval=args.checkpoint_interval,
    )
    result = build_corpus(config, logger=logger)
    print(f"corpus:   {result.corpus_dir}")
    print(f"records:  {result.counts['records']}")
    print(f"scanned:  {result.counts['scanned']}")
    if result.coverage is not None:
        print(f"coverage: {float(str(result.coverage['coverage'])):.4f}")
        print(f"strategy: {json.dumps(result.coverage['by_strategy'])}")
    print(f"sha256:   {result.content_sha256}")
    return EXIT_OK


def _cmd_verify(args: argparse.Namespace) -> int:
    result = verify_corpus(args.corpus_dir)
    if result.ok:
        print(f"ok: {result.reason}")
        print(f"sha256: {result.actual_sha256}")
        return EXIT_OK
    print(f"FAILED: {result.reason}", file=sys.stderr)
    print(f"expected: {result.expected_sha256}", file=sys.stderr)
    print(f"actual:   {result.actual_sha256}", file=sys.stderr)
    return EXIT_VERIFY


def _cmd_report(args: argparse.Namespace) -> int:
    summary = corpus_report(args.corpus_dir)
    if args.json:
        print(json.dumps(summary, sort_keys=True, indent=2))
        return EXIT_OK
    print(f"corpus:   {summary['corpus_dir']}")
    print(f"scope:    {json.dumps(summary['scope'])}")
    print(f"records:  {summary['records']}")
    print(f"matched:  {summary['matched']}")
    print(f"unmatched:{summary['unmatched']}")
    print(f"edges:    {summary['edges']}")
    coverage = summary["coverage"]
    if isinstance(coverage, dict):
        print(f"coverage: {float(str(coverage['coverage'])):.4f}")
        print(f"strategy: {json.dumps(coverage['by_strategy'])}")
        print(f"ambiguous:{coverage['ambiguous']}")
    graph = summary["graph"]
    if isinstance(graph, dict):
        print(f"out-of-scope refs: {graph['out_of_scope_references']}")
        print(f"self refs:         {graph['self_references']}")
        print(f"nodes:             {graph['nodes']}")
    print(f"sha256:   {summary['content_sha256']}")
    return EXIT_OK


def _cmd_info() -> int:
    print(f"scholar-corpus {__version__}")
    print(f"default artifact dir: {default_artifact_dir()}")
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
