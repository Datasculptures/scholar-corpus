"""Shared fixtures: a small synthetic arXiv snapshot and a built corpus.

The snapshot deliberately exercises every Phase 1 code path and seeds the join
paths for Phase 2:

* in-scope papers across cs.LG / cs.CL / cs.AI / stat.ML,
* an out-of-scope category (hep-th),
* an out-of-date-range paper,
* a deliberate normalised-title collision (two distinct ids, same title),
* a unicode-heavy title,
* an old-style arXiv id,
* a record with a missing id, a blank line, and a non-JSON line (all skipped).
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from scholar_corpus.adapters.arxiv_kaggle import ArxivKaggleAdapter
from scholar_corpus.build import BuildConfig, BuildResult, build_corpus
from scholar_corpus.enrichment.openalex import OpenAlexSnapshotAdapter
from scholar_corpus.scope import Scope


def _v(year: int) -> list[dict[str, str]]:
    return [{"version": "v1", "created": f"Fri, 1 Jan {year} 00:00:00 GMT"}]


SNAPSHOT_RECORDS: list[dict[str, Any]] = [
    {"id": "2101.00001", "title": "Deep Nets", "abstract": "a", "categories": "cs.LG",
     "doi": "10.1/ABC", "authors_parsed": [["Smith", "J", ""]], "versions": _v(2021),
     "update_date": "2021-02-01"},
    {"id": "2102.00002", "title": "Language Models", "abstract": "b", "categories": "cs.CL cs.LG",
     "doi": None, "authors_parsed": [["Doe", "A", ""]], "versions": _v(2021),
     "update_date": "2021-03-01"},
    {"id": "2103.00003", "title": "Bandits", "abstract": "c", "categories": "cs.AI stat.ML",
     "authors_parsed": [["Ng", "B", ""]], "versions": _v(2021), "update_date": "2021-04-01"},
    {"id": "2104.00004", "title": "Gaussian Processes", "abstract": "d", "categories": "stat.ML",
     "authors_parsed": [["Rasmussen", "C", ""]], "versions": _v(2022), "update_date": "2022-01-01"},
    {"id": "1901.00005", "title": "Old Paper", "abstract": "e", "categories": "cs.LG",
     "versions": _v(2019), "update_date": "2019-06-01"},
    {"id": "2005.00006", "title": "String Theory", "abstract": "f", "categories": "hep-th",
     "versions": _v(2020), "update_date": "2020-06-01"},
    {"id": "2106.00007", "title": "Collision Title", "abstract": "g", "categories": "cs.LG",
     "authors_parsed": [["Alpha", "X", ""]], "versions": _v(2021), "update_date": "2021-07-01"},
    {"id": "2106.00008", "title": "Collision   Title!!!", "abstract": "h", "categories": "cs.LG",
     "authors_parsed": [["Beta", "Y", ""]], "versions": _v(2021), "update_date": "2021-07-02"},
    {"id": "", "title": "No Id", "abstract": "x", "categories": "cs.LG", "versions": _v(2021)},
    {"id": "2107.00010", "title": "Über Ünïcode  Café", "abstract": "i", "categories": "cs.CL",
     "authors": "A. Author", "versions": _v(2021), "update_date": "2021-08-01"},
    {"id": "hep-ph/9901001", "title": "Old ID Scheme", "abstract": "j", "categories": "cs.LG",
     "versions": _v(2021), "update_date": "2021-09-01"},
    {"id": "2108.00012", "title": "Reasoning", "abstract": "k", "categories": "cs.AI",
     "doi": "https://doi.org/10.5/XYZ", "authors_parsed": [["Gamma", "Z", ""]],
     "versions": _v(2021), "update_date": "2021-10-01"},
]

# Derived expectations, kept next to the data so tests read as assertions of fact.
EXPECTED_IN_SCOPE = 9
EXPECTED_SCANNED = 11
EXPECTED_DUPLICATES = 0


@pytest.fixture
def snapshot_path(tmp_path: Path) -> Path:
    """Write the synthetic snapshot as JSONL, with a blank and a non-JSON line."""
    path = tmp_path / "arxiv-snapshot.json"
    lines = [json.dumps(rec) for rec in SNAPSHOT_RECORDS]
    lines.insert(4, "")  # blank line, must be skipped
    lines.insert(7, "this is not json")  # malformed line, must be skipped
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


@pytest.fixture
def scope() -> Scope:
    return Scope(
        source="arxiv",
        categories=("cs.LG", "cs.CL", "cs.AI", "stat.ML"),
        date_from=date(2020, 1, 1),
    )


@pytest.fixture
def adapter(snapshot_path: Path) -> ArxivKaggleAdapter:
    return ArxivKaggleAdapter(snapshot_path)


@pytest.fixture
def built_corpus(
    adapter: ArxivKaggleAdapter, scope: Scope, tmp_path: Path
) -> BuildResult:
    config = BuildConfig(source=adapter, scope=scope, output_dir=tmp_path / "corpus")
    return build_corpus(config)


# --- Phase 2: OpenAlex enrichment fixture, joined against the arXiv fixture ---

def _work(**kw: Any) -> dict[str, Any]:
    return kw


OPENALEX_RECORDS: list[dict[str, Any]] = [
    _work(id="https://openalex.org/W1", doi="https://doi.org/10.1/ABC", title="Deep Nets",
          publication_year=2021, ids={"arxiv": "2101.00001"},
          authorships=[{"author": {"display_name": "J. Smith"}}],
          referenced_works=["https://openalex.org/W2", "https://openalex.org/W99"]),
    _work(id="https://openalex.org/W2", title="Language Models", publication_year=2021,
          ids={"arxiv": "2102.00002"},
          authorships=[{"author": {"display_name": "A. Doe"}}], referenced_works=[]),
    _work(id="https://openalex.org/W3", title="Bandits", publication_year=2021,
          authorships=[{"author": {"display_name": "B. Ng"}}],
          referenced_works=["https://openalex.org/W1", "https://openalex.org/W4"]),
    _work(id="https://openalex.org/W4", doi="10.5/XYZ", title="Reasoning",
          publication_year=2021, authorships=[{"author": {"display_name": "Z. Gamma"}}],
          referenced_works=["https://openalex.org/W3"]),
    _work(id="https://openalex.org/W5", title="Collision Title", publication_year=2021,
          authorships=[{"author": {"display_name": "X. Alpha"}}]),
    _work(id="https://openalex.org/W7", title="Old ID Scheme", publication_year=2021,
          ids={"arxiv": "hep-ph/9901001"},
          authorships=[{"author": {"display_name": "Q. Legacy"}}],
          referenced_works=["https://openalex.org/W7", "https://openalex.org/W2"]),
]

# Expected join outcome against the in-scope arXiv fixture (9 papers).
EXPECTED_MATCHED = 5
EXPECTED_BY_STRATEGY = {"doi": 2, "arxiv_id": 2, "title": 1}
EXPECTED_AMBIGUOUS = 2
EXPECTED_MANY_TO_ONE = 1

# Expected citation graph over the matched papers.
EXPECTED_EDGES = 5
EXPECTED_OUT_OF_SCOPE_REFS = 1
EXPECTED_SELF_REFS = 1


@pytest.fixture
def openalex_snapshot_path(tmp_path: Path) -> Path:
    path = tmp_path / "openalex.json"
    lines = [json.dumps(rec) for rec in OPENALEX_RECORDS]
    lines.insert(2, "")  # blank line, skipped
    lines.insert(4, "{not json}")  # malformed, skipped
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


@pytest.fixture
def enrichment(openalex_snapshot_path: Path) -> OpenAlexSnapshotAdapter:
    return OpenAlexSnapshotAdapter(openalex_snapshot_path)
