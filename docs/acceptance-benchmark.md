# Acceptance benchmark: reproducing the reference run

`scholar-corpus` was extracted from the Datasculptures `arxiv-corpus` work, whose
run is both the reference implementation and the acceptance benchmark. This
document explains how to reproduce it on real data and — more importantly — how
to read the result honestly.

The synthetic test suite proves *correctness* (every join strategy, ambiguity
and many-to-one flagging, self-contained edges, determinism, resume). It cannot
prove the *scale figures*, because those depend on real snapshots. This benchmark
is the scale check.

## Target figures

On the reference snapshot, the scope `cs.LG, cs.CL, cs.AI, stat.ML` produced:

| Quantity            | Reference value |
| ------------------- | --------------- |
| In-scope papers     | 313,012         |
| Citation edges      | 4,720,309       |
| Join coverage       | 93.9%           |

The exact numbers depend on the arXiv and OpenAlex snapshot dates. **The
acceptance test is that these figures are recovered to the same order and can be
explained — not that they match to the digit.** A run that lands at, say, 305k
papers and 92% coverage against a newer snapshot passes if the delta is
attributable to snapshot drift.

## Inputs

1. **arXiv metadata** — the Kaggle `arxiv-metadata-oai-snapshot.json`
   (<https://www.kaggle.com/datasets/Cornell-University/arxiv>), a single JSONL
   file of a few GB. Record its filename and note the snapshot date; the manifest
   pins its SHA-256 for you.
2. **OpenAlex works** — an OpenAlex works snapshot as newline-delimited JSON
   (<https://docs.openalex.org/download-all-data/openalex-snapshot>). The full
   works dump is large; a filtered export covering works with an arXiv id or DOI
   in the target categories is sufficient and much smaller. The adapter reads any
   JSONL of OpenAlex work objects.

Keep both snapshots on fast local disk, outside any cloud-sync folder.

## Running it

```bash
scholar-corpus build \
  --source arxiv \
  --snapshot /data/arxiv-metadata-oai-snapshot.json \
  --categories cs.LG cs.CL cs.AI stat.ML \
  --enrichment openalex \
  --enrichment-snapshot /data/openalex-works.jsonl \
  --edge-format parquet \
  --coverage-gate 0.80 \
  --output /data/corpora/arxiv-ml-benchmark \
  --verbose
```

Notes for a run of this size:

- **Parquet edges.** 4.7M edges belong in Parquet; keep the default
  `--edge-format parquet` (install the `parquet` extra). `csv.gz` works but is
  larger and slower to read downstream.
- **Watch progress.** `--verbose` mirrors the flushed `build.log` to the console.
  The scan stage checkpoints every `--checkpoint-interval` records (default
  250,000), so an interrupted run resumes without rescanning.
- **Resume, don't restart.** If the machine dies, rerun the *same* command; it
  resumes from the last checkpoint. Use `--restart` only to force a clean build.
- **No date bound is applied above.** The reference scope is category-only; add
  `--date-from` / `--date-to` if you want a narrower window.

## Reading the result

```bash
scholar-corpus report /data/corpora/arxiv-ml-benchmark
scholar-corpus verify /data/corpora/arxiv-ml-benchmark   # must exit 0
```

Then reconcile against the reference:

- **Papers.** `records` is the in-scope, deduplicated count. Compare to 313,012;
  a newer arXiv snapshot will have *more* papers in these categories, so expect
  this to grow over time.
- **Coverage and its breakdown.** `coverage` is the fraction matched to OpenAlex;
  `strategy` shows how many matched by DOI, external arXiv id, and title. If
  coverage is well below ~93.9%, inspect the breakdown: a collapse in the
  `arxiv_id` route usually means the OpenAlex export is missing arXiv ids for
  many works, not that the join is wrong. `ambiguous` counts records the join
  refused to guess.
- **Edges and self-containment.** `edges` is the in-scope edge count (compare to
  4,720,309); `out-of-scope refs` is how many references pointed outside the
  scope and were counted rather than dropped. A very low edge count with a high
  out-of-scope count means most citations leave the scope — expected if the
  category set is narrow.

Record the manifest's `content_sha256`, both snapshot SHA-256s, and the recovered
figures next to the reference values, with a one-line explanation of any delta.
That reconciliation *is* the passing acceptance test.

## What this benchmark does not cover

Embeddings, full-text, clustering, and scoring are out of scope for this package
by design; they belong to downstream tools that read the catalogue and edge list.
The reference corpus proved that separation is what makes the corpus reusable.
