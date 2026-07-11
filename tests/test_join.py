"""Tests for the three-strategy join and coverage report."""

from __future__ import annotations

from collections.abc import Iterator

from scholar_corpus.adapters.base import SnapshotInfo
from scholar_corpus.enrichment.base import EnrichmentRecord
from scholar_corpus.join import join_records
from scholar_corpus.models import AMBIGUOUS_STRATEGY, PaperRecord
from tests.conftest import (
    EXPECTED_AMBIGUOUS,
    EXPECTED_BY_STRATEGY,
    EXPECTED_MANY_TO_ONE,
    EXPECTED_MATCHED,
)


class _FakeEnrichment:
    """Minimal in-memory EnrichmentAdapter for unit-level join tests."""

    source_name = "fake"

    def __init__(self, records: list[EnrichmentRecord]) -> None:
        self._records = records

    def snapshot(self) -> SnapshotInfo:
        return SnapshotInfo(name="fake", sha256="0" * 64, byte_size=0)

    def iter_records(self) -> Iterator[EnrichmentRecord]:
        yield from self._records


def _paper(pid: str, **kw: object) -> PaperRecord:
    base: dict[str, object] = {
        "paper_id": pid,
        "source": "arxiv",
        "source_id": pid.split(":", 1)[1],
        "title": "t",
        "title_normalized": "t",
        "abstract": "",
        "authors": (),
        "author_surnames": (),
        "categories": ("cs.LG",),
        "primary_category": "cs.LG",
        "date_published": "2021-01-01",
        "date_updated": None,
        "version": "v1",
        "published_year": 2021,
    }
    base.update(kw)
    return PaperRecord(**base)  # type: ignore[arg-type]


def test_join_against_fixture_covers_every_strategy(
    adapter: object, scope: object, enrichment: object
) -> None:
    records = [r for r in adapter.iter_records() if scope.matches(r)]  # type: ignore[attr-defined]
    outcome = join_records(records, enrichment)  # type: ignore[arg-type]
    cov = outcome.coverage
    assert cov.in_scope == 9
    assert cov.matched == EXPECTED_MATCHED
    assert cov.by_strategy == EXPECTED_BY_STRATEGY
    assert cov.ambiguous == EXPECTED_AMBIGUOUS
    assert cov.title_many_to_one == EXPECTED_MANY_TO_ONE
    assert abs(cov.coverage - EXPECTED_MATCHED / 9) < 1e-9

    by_id = {r.paper_id: r for r in outcome.records}
    assert by_id["arxiv:2101.00001"].match_strategy == "doi"
    assert by_id["arxiv:2102.00002"].match_strategy == "arxiv_id"
    assert by_id["arxiv:2103.00003"].match_strategy == "title"
    # Collision pair is flagged, not collapsed onto one enrichment record.
    assert by_id["arxiv:2106.00007"].match_strategy == AMBIGUOUS_STRATEGY
    assert by_id["arxiv:2106.00007"].matched is False
    assert by_id["arxiv:2106.00008"].match_strategy == AMBIGUOUS_STRATEGY
    # Plain unmatched records are retained with a null strategy.
    assert by_id["arxiv:2104.00004"].match_strategy is None


def test_doi_beats_arxiv() -> None:
    paper = _paper("arxiv:1", doi="10.1/x", source_id="1")
    enr = _FakeEnrichment([
        EnrichmentRecord(enrichment_id="D", title_normalized="z", doi="10.1/x"),
        EnrichmentRecord(enrichment_id="A", title_normalized="z", arxiv_id="1"),
    ])
    out = join_records([paper], enr)
    assert out.records[0].match_strategy == "doi"
    assert out.records[0].enrichment_id == "D"


def test_title_requires_a_guard() -> None:
    # Same title, but neither year nor surname agrees -> no match.
    paper = _paper("arxiv:1", title_normalized="deep", author_surnames=("smith",),
                   published_year=2020)
    enr = _FakeEnrichment([
        EnrichmentRecord(enrichment_id="E", title_normalized="deep",
                         author_surnames=("jones",), publication_year=1999),
    ])
    out = join_records([paper], enr)
    assert out.records[0].matched is False
    assert out.records[0].match_strategy is None
    assert out.coverage.matched == 0


def test_title_multiple_candidates_is_ambiguous() -> None:
    paper = _paper("arxiv:1", title_normalized="deep", author_surnames=("smith",),
                   published_year=2021)
    enr = _FakeEnrichment([
        EnrichmentRecord(enrichment_id="E1", title_normalized="deep", publication_year=2021),
        EnrichmentRecord(enrichment_id="E2", title_normalized="deep",
                         author_surnames=("smith",)),
    ])
    out = join_records([paper], enr)
    assert out.records[0].match_strategy == AMBIGUOUS_STRATEGY
    assert out.coverage.ambiguous == 1
    assert out.coverage.matched == 0


def test_title_single_guard_confidence() -> None:
    paper = _paper("arxiv:1", title_normalized="deep", author_surnames=("smith",),
                   published_year=2021)
    enr = _FakeEnrichment([
        EnrichmentRecord(enrichment_id="E", title_normalized="deep", publication_year=2021),
    ])
    out = join_records([paper], enr)
    assert out.records[0].match_strategy == "title"
    assert out.records[0].match_confidence == 0.8  # only year agreed
