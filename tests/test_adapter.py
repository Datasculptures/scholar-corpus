"""Tests for the arXiv Kaggle source adapter."""

from __future__ import annotations

from pathlib import Path

import pytest

from scholar_corpus.adapters.arxiv_kaggle import ArxivKaggleAdapter
from scholar_corpus.adapters.base import SnapshotInfo, SourceAdapter


def test_adapter_conforms_to_protocol(adapter: ArxivKaggleAdapter) -> None:
    assert isinstance(adapter, SourceAdapter)
    assert adapter.source_name == "arxiv"


def test_missing_file_raises() -> None:
    with pytest.raises(FileNotFoundError):
        ArxivKaggleAdapter(Path("does-not-exist.json"))


def test_snapshot_hashes_file(adapter: ArxivKaggleAdapter) -> None:
    snap = adapter.snapshot()
    assert isinstance(snap, SnapshotInfo)
    assert len(snap.sha256) == 64
    assert snap.byte_size > 0
    assert snap.as_dict()["name"] == adapter.path.name


def test_iter_records_skips_bad_lines_and_parses_fields(
    adapter: ArxivKaggleAdapter,
) -> None:
    records = {r.paper_id: r for r in adapter.iter_records()}
    # Blank line, non-JSON line, and the empty-id record are all skipped.
    assert "arxiv:" not in records
    assert len(records) == 11

    deep = records["arxiv:2101.00001"]
    assert deep.doi == "10.1/abc"
    assert deep.primary_category == "cs.LG"
    assert deep.date_published == "2021-01-01"
    assert deep.published_year == 2021
    assert deep.author_surnames == ("smith",)
    assert deep.version == "v1"

    # DOI from a URL form is normalised.
    assert records["arxiv:2108.00012"].doi == "10.5/xyz"
    # Old-style id is preserved.
    assert "arxiv:hep-ph/9901001" in records
    # Authors string fallback when authors_parsed is absent.
    assert records["arxiv:2107.00010"].authors == ("A. Author",)


def test_iter_records_title_collision_shares_normalised_title(
    adapter: ArxivKaggleAdapter,
) -> None:
    records = {r.paper_id: r for r in adapter.iter_records()}
    a = records["arxiv:2106.00007"]
    b = records["arxiv:2106.00008"]
    assert a.paper_id != b.paper_id
    assert a.title_normalized == b.title_normalized == "collision title"


def test_input_size_cap_enforced(snapshot_path: Path) -> None:
    tiny = ArxivKaggleAdapter(snapshot_path, max_bytes=10)
    with pytest.raises(Exception, match="exceeding the cap"):
        tiny.snapshot()
    with pytest.raises(Exception, match="exceeding the cap"):
        list(tiny.iter_records())
