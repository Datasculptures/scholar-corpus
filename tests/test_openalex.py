"""Tests for the OpenAlex enrichment snapshot adapter."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scholar_corpus.enrichment.base import EnrichmentAdapter
from scholar_corpus.enrichment.openalex import OpenAlexSnapshotAdapter


def test_adapter_conforms_to_protocol(enrichment: OpenAlexSnapshotAdapter) -> None:
    assert isinstance(enrichment, EnrichmentAdapter)
    assert enrichment.source_name == "openalex"
    snap = enrichment.snapshot()
    assert len(snap.sha256) == 64


def test_missing_file_raises() -> None:
    with pytest.raises(FileNotFoundError):
        OpenAlexSnapshotAdapter(Path("nope.json"))


def test_parses_fields_and_skips_bad_lines(enrichment: OpenAlexSnapshotAdapter) -> None:
    records = {r.enrichment_id: r for r in enrichment.iter_records()}
    assert len(records) == 6  # blank + malformed lines skipped

    w1 = records["W1"]
    assert w1.doi == "10.1/abc"          # URL-form DOI normalised
    assert w1.arxiv_id == "2101.00001"   # from ids.arxiv
    assert w1.title_normalized == "deep nets"
    assert w1.publication_year == 2021
    assert w1.author_surnames == ("smith",)
    assert w1.referenced_ids == ("W2", "W99")  # openalex prefix stripped

    assert records["W7"].arxiv_id == "hep-ph/9901001"  # old-style id preserved


def test_missing_id_and_year_string(tmp_path: Path) -> None:
    path = tmp_path / "oa.json"
    path.write_text(
        "\n".join(
            [
                json.dumps({"title": "no id"}),  # skipped: no id
                json.dumps({"id": "https://openalex.org/W9", "title": "Year As String",
                            "publication_year": "2019"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    records = list(OpenAlexSnapshotAdapter(path).iter_records())
    assert len(records) == 1
    assert records[0].enrichment_id == "W9"
    assert records[0].publication_year == 2019
