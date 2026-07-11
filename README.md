# scholar-corpus

Reproducible, provenance-stamped builder for joined, citation-linked scholarly
corpora. Given a scope (source, categories, date range), it produces a
deduplicated paper catalogue, a multi-strategy join to a citation-data source
with an honest coverage report, and a `MANIFEST.json` that lets any corpus be
traced and reproduced.

The corpus artifacts stay on your disk. This package is the *build code*: a
pipeline that turns a source scope into a joined citation corpus with an honest
coverage report. It does **not** embed papers, fetch full text, or do analysis —
those belong to downstream tools that read the catalogue.

> **Status:** Phase 5 (publish prep). Feature-complete across build phases 1–4:
> arXiv catalogue, OpenAlex enrichment join with coverage report and gate,
> self-contained citation graph, and resumable, checkpointed, logged builds. The
> distributions are built and validated (`twine check` clean, wheel smoke-tested
> from a clean venv); TestPyPI dry-run and PyPI upload are operator steps — see
> [RELEASE.md](RELEASE.md). See [Roadmap](#roadmap).

## Install

```bash
pip install scholar-corpus
```

Python 3.11+. The core has no third-party runtime dependencies. The `parquet`
extra (`pip install "scholar-corpus[parquet]"`) is needed only for the Parquet
edge format (`--edge-format parquet`, the default); `--edge-format csv.gz` writes
edges with no extra dependency.

## Worked example

Download the [Kaggle arXiv metadata snapshot][kaggle] (a single JSONL file) and,
optionally, an [OpenAlex works snapshot][openalex] (newline-delimited JSON). Then
build a catalogue scoped to the machine-learning categories and join it to
OpenAlex for citation data:

```bash
scholar-corpus build \
  --source arxiv \
  --snapshot ~/data/arxiv-metadata-oai-snapshot.json \
  --categories cs.LG cs.CL cs.AI stat.ML \
  --date-from 2007-01-01 \
  --enrichment openalex \
  --enrichment-snapshot ~/data/openalex-works.jsonl \
  --coverage-gate 0.80 \
  --output ~/corpora/arxiv-ml
```

Drop the two `--enrichment*` flags to build a catalogue only (Phase 1 behaviour:
no join, no coverage, no gate). This writes into the output directory:

- `catalogue.db` — a Datasette-compatible SQLite catalogue, one `papers` row per
  deduplicated paper, keyed by a stable `paper_id` (for example
  `arxiv:2103.00001`). Matched rows carry `match_strategy` (`doi`, `arxiv_id`, or
  `title`), a `match_confidence`, and the `enrichment_id`; unmatched rows are
  retained with a null strategy, and records the join could not resolve
  confidently are flagged `ambiguous` — never dropped, never collapsed silently.
- `edges.parquet` (or `edges.csv.gz`) — the citation edge list, present when an
  enrichment source is supplied. Columns `source_id,target_id`, directed
  citing → cited, restricted to papers in scope, ordered by `target_id` so the
  "citers of a paper" are contiguous.
- `MANIFEST.json` — tool version, exact scope, source and enrichment snapshot
  names + SHA-256s, record/edge counts, the coverage report, the graph summary
  (edges, nodes, out-of-scope references, self-references), and the content
  SHA-256.
- `build.log` — a flushed, timestamped log of the run. A transient
  `checkpoint.pkl` also lives here while a build is in progress and is removed on
  success.

Inspect and check it:

```bash
scholar-corpus report ~/corpora/arxiv-ml     # summary incl. coverage + by-strategy
scholar-corpus verify ~/corpora/arxiv-ml     # re-hash against the manifest
scholar-corpus info                          # tool version and default artifact dir
```

By default, artifacts are written under a per-user data directory
(`%LOCALAPPDATA%` on Windows, `$XDG_DATA_HOME` or `~/.local/share` elsewhere),
deliberately outside your repository and outside cloud-sync folders. Override
with `--output` or the `SCHOLAR_CORPUS_HOME` environment variable.

## The join

The join is the hard part, so it is explicit and auditable. Strategies run in
order of decreasing reliability, and every matched pair records which strategy
matched it and a confidence indicator:

1. **DOI** — exact, when the source record carries a DOI (confidence 1.0).
2. **External arXiv id** — the enrichment source's own arXiv id field
   (confidence 0.99).
3. **Normalised title** — guarded against false positives by requiring agreement
   on author surname or publication year (confidence 0.9 when both agree, 0.8
   when one does).

Safeguards: unmatched records are retained and flagged; a title match with more
than one guarded candidate is reported as *ambiguous* rather than guessed; and a
title match is never allowed to collapse two source papers onto one enrichment
record without flagging and counting it. The coverage report states overall
coverage and the breakdown by strategy.

## The citation graph

The edge list is self-contained: an edge is emitted only when both endpoints are
matched, in-scope papers, so graph algorithms never hit a dangling reference.
Direction is explicit — `source_id` cites `target_id`. References pointing
outside the scope are counted (`out_of_scope_references`) rather than dropped
silently, and self-citations are removed and counted (`self_references`). Edges
derive from the enrichment records' references, looked up through a single
`enrichment_id → paper_id` index, so extraction is linear in the number of
references. The content hash folds the edge *set* in independently of file order
and format, so a `parquet` build and a `csv.gz` build of the same corpus share a
content SHA-256.

## Library API

The library is presentation-agnostic: it never prints, reads `argv`, or calls
`sys.exit`. Callers own all input and output.

```python
from datetime import date
from pathlib import Path

from scholar_corpus import BuildConfig, Scope, build_corpus, verify_corpus
from scholar_corpus.adapters import ArxivKaggleAdapter
from scholar_corpus.enrichment import OpenAlexSnapshotAdapter

config = BuildConfig(
    source=ArxivKaggleAdapter("~/data/arxiv-metadata-oai-snapshot.json"),
    scope=Scope(
        source="arxiv",
        categories=("cs.LG", "cs.CL", "cs.AI", "stat.ML"),
        date_from=date(2007, 1, 1),
    ),
    enrichment=OpenAlexSnapshotAdapter("~/data/openalex-works.jsonl"),
    output_dir=Path("~/corpora/arxiv-ml").expanduser(),
    coverage_gate=0.80,
)
result = build_corpus(config)          # raises CoverageBelowGateError below the gate
print(result.content_sha256, result.coverage)
assert verify_corpus(result.corpus_dir).ok
```

## Resumability

Corpus builds are long-running, so a build that dies at hour two must not lose
completed work. The pipeline runs as discrete stages — source-snapshot hash,
scan/filter/dedupe, enrichment join, citation graph — and checkpoints after each,
with additional checkpoints *within* the long scan stage at a configurable
interval (`--checkpoint-interval`). Checkpoints are written atomically
(temp file + rename), so a crash mid-write can never leave a truncated
checkpoint. `build` resumes from the last checkpoint by default and produces
output identical to an uninterrupted run; `--restart` forces a clean rebuild. A
checkpoint from a different scope or a changed snapshot is detected by an input
fingerprint and ignored rather than trusted. All progress is written to a flushed
`build.log`, so a running build is never a silent black box.

The CLI's exit codes are meaningful for scripting: `0` success, `1` error, `2`
usage, `3` coverage below the gate, `4` verification failure.

## Reproducibility

Determinism is treated as a correctness property and tested as one. The same
scope against the same source and enrichment snapshots produces a byte-identical
catalogue and an identical content SHA-256. This works because the hash is
computed over a canonical serialisation of catalogue *content* (rows read back in
`paper_id` order, sorted keys, fixed separators) — never over SQLite's internal
file layout, and never including wall-clock timestamps. `verify` re-derives that
hash from the artifacts on disk and exits non-zero on any mismatch.

## What the coverage figure means

*Join coverage* is the fraction of in-scope source papers matched to an
enrichment record, and the manifest breaks it down by which strategy matched each
one. It is not a quality score and not a claim about the citation graph's
completeness: an unmatched paper is still retained and flagged, never dropped,
and ambiguous matches are reported rather than guessed. The number tells you how
much of your scope carries citation data and by how trustworthy a route —
nothing more. The `build` command exits non-zero when coverage falls below the
configured gate (default 0.80), so a degraded corpus cannot silently become
someone's foundation; the artifacts are still written for inspection.

## Roadmap

1. **Source adapter and catalogue.** ✅ arXiv Kaggle ingest, scope filtering,
   normalisation, SQLite catalogue, manifest, `verify`.
2. **Enrichment and join.** ✅ OpenAlex adapter, the three-strategy join,
   coverage report, coverage gate.
3. **Citation graph.** ✅ In-scope edge extraction (citing → cited),
   self-containment, out-of-scope reporting, configurable parquet/csv.gz.
4. **Resumability and hardening.** ✅ Stage checkpointing, resume, flushed
   logging, exit codes.
5. **Publish.** ⏳ Distributions built and validated; run the
   [release process](RELEASE.md) (TestPyPI dry-run, then PyPI) to ship.

The reference implementation (Datasculptures `arxiv-corpus`) produced 313,012
in-scope papers, 4,720,309 citation edges, and 93.9% join coverage on a pinned
snapshot; reproducing figures in that region is the acceptance benchmark.

## Releasing and benchmarks

- [CHANGELOG.md](CHANGELOG.md) — release notes.
- [RELEASE.md](RELEASE.md) — build, `twine check`, TestPyPI dry-run, and PyPI
  publish steps (uploads use your own tokens).
- [docs/acceptance-benchmark.md](docs/acceptance-benchmark.md) — how to reproduce
  the reference run (~313k papers, ~4.7M edges, ~93.9% coverage) on real Kaggle +
  OpenAlex snapshots, and how to read the figures honestly.

## License

MIT. See [LICENSE](LICENSE).

[kaggle]: https://www.kaggle.com/datasets/Cornell-University/arxiv
[openalex]: https://docs.openalex.org/download-all-data/openalex-snapshot
