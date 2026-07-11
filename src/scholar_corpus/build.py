"""Build orchestration (library API).

Presentation-agnostic: never prints, never reads ``sys.argv``, never calls
``sys.exit``. Progress is reported through an optional :class:`logging.Logger`;
results and errors are returned or raised.

The pipeline runs as discrete, checkpointed stages so a build that dies part way
through can resume without losing completed work:

1. **source_snapshot** — hash the source snapshot.
2. **scan** — stream, scope-filter, and de-duplicate source records
   (checkpointed at an interval within the stage, since it is the long one).
3. **enrichment_snapshot** + **join** — hash the enrichment snapshot and run the
   three-strategy join (only when an enrichment source is configured).
4. **graph** — extract the in-scope citation edge list.
5. finalize — write the catalogue, edge list, and manifest, then clear the
   checkpoint.

``build`` resumes from the last checkpoint by default; ``restart=True`` forces a
clean run. Resuming the same inputs produces output identical to an
uninterrupted build.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from scholar_corpus import catalogue
from scholar_corpus.adapters.base import SnapshotInfo, SourceAdapter
from scholar_corpus.checkpoint import (
    Checkpoint,
    clear_checkpoint,
    load_checkpoint,
    save_checkpoint,
)
from scholar_corpus.enrichment.base import EnrichmentAdapter, EnrichmentRecord
from scholar_corpus.errors import CoverageBelowGateError
from scholar_corpus.graph import build_edges, edges_filename, write_edges
from scholar_corpus.join import join_records
from scholar_corpus.manifest import (
    CATALOGUE_FILENAME,
    Manifest,
    compute_content_sha256,
    write_manifest,
)
from scholar_corpus.models import PaperRecord
from scholar_corpus.scope import Scope

VALID_EDGE_FORMATS: frozenset[str] = frozenset({"parquet", "csv.gz"})
DEFAULT_COVERAGE_GATE = 0.80
DEFAULT_CHECKPOINT_INTERVAL = 250_000

_NULL_LOGGER = logging.getLogger("scholar_corpus.build")


@dataclass(frozen=True, slots=True)
class BuildConfig:
    """Everything a build needs, owned by the caller."""

    source: SourceAdapter
    scope: Scope
    output_dir: Path
    enrichment: EnrichmentAdapter | None = None
    edge_format: str = "parquet"
    coverage_gate: float = DEFAULT_COVERAGE_GATE
    restart: bool = False
    checkpoint_interval: int = DEFAULT_CHECKPOINT_INTERVAL

    def __post_init__(self) -> None:
        if self.edge_format not in VALID_EDGE_FORMATS:
            raise ValueError(
                f"edge_format must be one of {sorted(VALID_EDGE_FORMATS)}, "
                f"got {self.edge_format!r}"
            )
        if not 0.0 <= self.coverage_gate <= 1.0:
            raise ValueError(f"coverage_gate must be in [0, 1], got {self.coverage_gate}")
        if self.checkpoint_interval <= 0:
            raise ValueError("checkpoint_interval must be positive")


@dataclass(frozen=True, slots=True)
class BuildResult:
    """The outcome of a successful build."""

    corpus_dir: Path
    catalogue_path: Path
    manifest_path: Path
    content_sha256: str
    counts: dict[str, int] = field(default_factory=dict)
    coverage: dict[str, object] | None = None
    graph: dict[str, object] | None = None
    edges_path: Path | None = None
    resumed: bool = False


def _stat_fingerprint(adapter: object) -> dict[str, Any]:
    name = getattr(adapter, "source_name", "unknown")
    path = getattr(adapter, "path", None)
    if path is None:
        return {"name": name}
    st = Path(path).stat()
    return {"name": name, "path": str(path), "size": st.st_size, "mtime_ns": st.st_mtime_ns}


def _fingerprint(config: BuildConfig) -> dict[str, Any]:
    return {
        "tool_version": _tool_version(),
        "scope": config.scope.as_dict(),
        "edge_format": config.edge_format,
        "source": _stat_fingerprint(config.source),
        "enrichment": (
            _stat_fingerprint(config.enrichment) if config.enrichment is not None else None
        ),
    }


def _scan(
    source: SourceAdapter,
    scope: Scope,
    checkpoint: Checkpoint,
    corpus_dir: Path,
    interval: int,
    log: logging.Logger,
) -> tuple[list[PaperRecord], int, int]:
    """Scan/filter/dedupe with intra-stage checkpointing. Resumable."""
    state = checkpoint.stages.get("scan")
    if state is not None and state.get("complete"):
        log.info("scan stage: reusing checkpoint (%d records)", len(state["records"]))
        return state["records"], state["scanned"], state["duplicates"]

    kept: list[PaperRecord] = list(state["records"]) if state else []
    scanned: int = state["scanned"] if state else 0
    duplicates: int = state["duplicates"] if state else 0
    seen: set[str] = {r.paper_id for r in kept}
    if scanned:
        log.info("scan stage: resuming from %d scanned, %d kept", scanned, len(kept))

    consumed = 0
    for record in source.iter_records():
        consumed += 1
        if consumed <= scanned:
            continue  # already processed in a prior run
        scanned += 1
        if scope.matches(record) and record.paper_id not in seen:
            seen.add(record.paper_id)
            kept.append(record)
        elif scope.matches(record):
            duplicates += 1
        if scanned % interval == 0:
            checkpoint.set(
                "scan",
                {"records": kept, "scanned": scanned, "duplicates": duplicates, "complete": False},
            )
            save_checkpoint(corpus_dir, checkpoint)
            log.info("scan stage: %d scanned, %d kept (checkpointed)", scanned, len(kept))

    checkpoint.set(
        "scan",
        {"records": kept, "scanned": scanned, "duplicates": duplicates, "complete": True},
    )
    save_checkpoint(corpus_dir, checkpoint)
    return kept, scanned, duplicates


def build_corpus(
    config: BuildConfig, *, logger: logging.Logger | None = None
) -> BuildResult:
    """Build a corpus and return its :class:`BuildResult`.

    Resumes from a checkpoint in ``output_dir`` unless ``restart`` is set. Raises
    :class:`~scholar_corpus.errors.CoverageBelowGateError` when enrichment is
    configured and coverage falls below the gate; artifacts are written first, so
    a degraded corpus is inspectable but the build fails loudly.
    """
    log = logger or _NULL_LOGGER
    corpus_dir = Path(config.output_dir)
    corpus_dir.mkdir(parents=True, exist_ok=True)

    fingerprint = _fingerprint(config)
    if config.restart:
        clear_checkpoint(corpus_dir)
        checkpoint = Checkpoint(fingerprint=fingerprint)
        resumed = False
    else:
        existing = load_checkpoint(corpus_dir, fingerprint)
        resumed = existing is not None and bool(existing.stages)
        checkpoint = existing or Checkpoint(fingerprint=fingerprint)
        if resumed:
            log.info("resuming from checkpoint with stages: %s", sorted(checkpoint.stages))

    # Stage: source snapshot hash.
    if checkpoint.has("source_snapshot"):
        snapshot = SnapshotInfo(**checkpoint.get("source_snapshot"))
    else:
        log.info("hashing source snapshot")
        snapshot = config.source.snapshot()
        checkpoint.set("source_snapshot", snapshot.as_dict())
        save_checkpoint(corpus_dir, checkpoint)

    # Stage: scan / filter / dedupe.
    log.info("scanning source and filtering to scope")
    records, scanned, duplicates = _scan(
        config.source, config.scope, checkpoint, corpus_dir, config.checkpoint_interval, log
    )

    coverage_dict: dict[str, object] | None = None
    enrichment_meta: dict[str, object] | None = None
    graph_section: dict[str, object] | None = None
    edges_for_hash: list[tuple[str, str]] | None = None
    edges_path: Path | None = None
    edge_counts = {"edges": 0, "out_of_scope_references": 0, "self_references": 0}

    if config.enrichment is not None:
        # Stage: enrichment snapshot hash.
        if checkpoint.has("enrichment_snapshot"):
            enrichment_snapshot = SnapshotInfo(**checkpoint.get("enrichment_snapshot"))
        else:
            log.info("hashing enrichment snapshot")
            enrichment_snapshot = config.enrichment.snapshot()
            checkpoint.set("enrichment_snapshot", enrichment_snapshot.as_dict())
            save_checkpoint(corpus_dir, checkpoint)
        enrichment_meta = {
            "name": config.enrichment.source_name,
            "snapshot": enrichment_snapshot.as_dict(),
        }

        # Stage: join.
        if checkpoint.has("join"):
            join_state = checkpoint.get("join")
            records = join_state["records"]
            coverage_dict = join_state["coverage"]
            matched_enrichment: dict[str, EnrichmentRecord] = join_state["matched_enrichment"]
            log.info("join stage: reusing checkpoint")
        else:
            log.info("joining against enrichment source")
            outcome = join_records(records, config.enrichment)
            records = outcome.records
            coverage_dict = outcome.coverage.as_dict()
            matched_enrichment = outcome.matched_enrichment
            checkpoint.set(
                "join",
                {
                    "records": records,
                    "coverage": coverage_dict,
                    "matched_enrichment": matched_enrichment,
                },
            )
            save_checkpoint(corpus_dir, checkpoint)
        log.info("join coverage %.4f", float(coverage_dict["coverage"]))  # type: ignore[arg-type]

        # Stage: citation graph.
        if checkpoint.has("graph"):
            graph_state = checkpoint.get("graph")
            edges_for_hash = graph_state["edges"]
            graph_out_of_scope = graph_state["out_of_scope_references"]
            graph_self = graph_state["self_references"]
            log.info("graph stage: reusing checkpoint")
        else:
            log.info("extracting in-scope citation graph")
            graph_result = build_edges(records, matched_enrichment)
            edges_for_hash = graph_result.edges
            graph_out_of_scope = graph_result.out_of_scope_references
            graph_self = graph_result.self_references
            checkpoint.set(
                "graph",
                {
                    "edges": edges_for_hash,
                    "out_of_scope_references": graph_out_of_scope,
                    "self_references": graph_self,
                },
            )
            save_checkpoint(corpus_dir, checkpoint)

        edges_path = corpus_dir / edges_filename(config.edge_format)
        write_edges(edges_path, edges_for_hash, edge_format=config.edge_format)
        edge_counts = {
            "edges": len(edges_for_hash),
            "out_of_scope_references": graph_out_of_scope,
            "self_references": graph_self,
        }
        graph_section = _graph_section(
            edges_for_hash, graph_out_of_scope, graph_self, config.edge_format, edges_path.name
        )

    # Finalize: write catalogue, hash content, write manifest.
    catalogue_path = corpus_dir / CATALOGUE_FILENAME
    log.info("writing catalogue: %d records", len(records))
    written = catalogue.write_catalogue(catalogue_path, records)
    _total, unmatched = catalogue.count_rows(catalogue_path)

    log.info("hashing corpus content")
    content_sha256 = compute_content_sha256(catalogue_path, edges_for_hash)

    counts = {
        "records": written,
        "unmatched": unmatched,
        "matched": written - unmatched,
        "scanned": scanned,
        "duplicates_removed": duplicates,
        "out_of_scope": scanned - written - duplicates,
        **edge_counts,
    }
    manifest = Manifest(
        tool_version=_tool_version(),
        source={"name": config.source.source_name, "snapshot": snapshot.as_dict()},
        scope=config.scope.as_dict(),
        counts=counts,
        content_sha256=content_sha256,
        coverage=coverage_dict,
        enrichment=enrichment_meta,
        graph=graph_section,
    )
    manifest_path = write_manifest(corpus_dir, manifest)
    clear_checkpoint(corpus_dir)
    log.info("build complete: %s", content_sha256)

    result = BuildResult(
        corpus_dir=corpus_dir,
        catalogue_path=catalogue_path,
        manifest_path=manifest_path,
        content_sha256=content_sha256,
        counts=counts,
        coverage=coverage_dict,
        graph=graph_section,
        edges_path=edges_path,
        resumed=resumed,
    )

    if coverage_dict is not None:
        coverage_value = float(coverage_dict["coverage"])  # type: ignore[arg-type]
        if coverage_value < config.coverage_gate:
            raise CoverageBelowGateError(coverage_value, config.coverage_gate)

    return result


def _graph_section(
    edges: list[tuple[str, str]],
    out_of_scope: int,
    self_refs: int,
    edge_format: str,
    filename: str,
) -> dict[str, object]:
    nodes: set[str] = set()
    for source, target in edges:
        nodes.add(source)
        nodes.add(target)
    return {
        "edges": len(edges),
        "nodes": len(nodes),
        "out_of_scope_references": out_of_scope,
        "self_references": self_refs,
        "direction": "citing_to_cited",
        "format": edge_format,
        "filename": filename,
    }


def _tool_version() -> str:
    from scholar_corpus import __version__

    return __version__
