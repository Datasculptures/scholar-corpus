# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.0] — 2026-07-10

First feature-complete release across the build pipeline (roadmap phases 1–4).

### Added

- **Resumability and hardening (phase 4).** The build runs as discrete
  checkpointed stages (source-snapshot hash, scan/filter/dedupe, enrichment
  join, citation graph) with intra-stage checkpoints in the long scan stage at a
  configurable interval (`--checkpoint-interval`). Checkpoints are written
  atomically (temp file + rename); a corrupt or mismatched checkpoint is ignored
  rather than trusted. `build` resumes by default; `--restart` forces a clean
  rebuild. Every run writes a flushed, timestamped `build.log`.
- **Citation graph (phase 3).** Self-contained, in-scope edge list directed
  citing → cited, with out-of-scope references and self-citations counted and
  reported. Configurable edge format: `parquet` (default) or `csv.gz`. The
  content hash folds the edge set in independently of file order and format.
- **Enrichment and join (phase 2).** OpenAlex snapshot adapter and a three-
  strategy join (DOI → external arXiv id → guarded normalised title) with a
  per-pair strategy and confidence, ambiguity and many-to-one flagging, a
  coverage report, and a coverage gate (default 0.80, exit code 3 when below).
- **Source adapter and catalogue (phase 1).** arXiv Kaggle JSONL adapter, scope
  filtering, explicit normalisation, a Datasette-compatible SQLite catalogue,
  a provenance `MANIFEST.json`, and a `verify` command.

### Notes

- Deterministic output is treated and tested as a correctness property: the same
  scope against the same snapshots yields an identical content SHA-256.
- Python 3.11+. Core has no third-party runtime dependencies; the `parquet`
  extra pulls in `pyarrow` only for the Parquet edge format.

[Unreleased]: https://github.com/datasculptures/scholar-corpus/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/datasculptures/scholar-corpus/releases/tag/v0.4.0
