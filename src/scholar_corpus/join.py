"""The join layer: match source records to enrichment records.

Strategies run in order of decreasing reliability, and every matched pair
records which strategy matched it and a confidence indicator, so coverage can be
audited rather than asserted:

1. **DOI** — exact, when the source record carries a DOI. Confidence 1.0.
2. **External arXiv id** — the enrichment source's own arXiv id field.
   Confidence 0.99.
3. **Normalised title** — guarded against false positives by requiring
   agreement on author surname or publication year. Confidence 0.9 when both
   agree, 0.8 when one does.

Safeguards required by the spec:

* Unmatched source records are retained and flagged, never dropped.
* A title match with more than one guarded candidate is *ambiguous*: reported,
  not guessed.
* Title matching never produces a many-to-one collapse silently: if two source
  papers resolve to the same enrichment record by title, both are un-assigned
  and flagged, and the collapse is counted.

The join is deterministic: records are processed in ``paper_id`` order and the
first enrichment record seen for a given key wins, so the same inputs always
produce the same annotations and the same coverage figures.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from scholar_corpus.enrichment.base import EnrichmentAdapter, EnrichmentRecord
from scholar_corpus.models import PaperRecord
from scholar_corpus.normalize import normalize_arxiv_id

STRATEGY_DOI = "doi"
STRATEGY_ARXIV = "arxiv_id"
STRATEGY_TITLE = "title"

CONFIDENCE_DOI = 1.0
CONFIDENCE_ARXIV = 0.99
CONFIDENCE_TITLE_BOTH = 0.9
CONFIDENCE_TITLE_ONE = 0.8


@dataclass(frozen=True, slots=True)
class CoverageReport:
    """Auditable coverage figures for a join."""

    in_scope: int
    matched: int
    unmatched: int
    ambiguous: int
    title_many_to_one: int
    by_strategy: dict[str, int]

    @property
    def coverage(self) -> float:
        return self.matched / self.in_scope if self.in_scope else 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "in_scope": self.in_scope,
            "matched": self.matched,
            "unmatched": self.unmatched,
            "ambiguous": self.ambiguous,
            "title_many_to_one": self.title_many_to_one,
            "by_strategy": dict(self.by_strategy),
            "coverage": self.coverage,
        }


@dataclass(frozen=True, slots=True)
class JoinOutcome:
    """The annotated records, coverage report, and matched enrichment records.

    ``matched_enrichment`` maps each confidently matched enrichment id to its
    record, so the citation-graph stage can read ``referenced_ids`` without
    re-scanning the enrichment source.
    """

    records: list[PaperRecord]
    coverage: CoverageReport
    matched_enrichment: dict[str, EnrichmentRecord]


@dataclass(frozen=True, slots=True)
class _Indexes:
    by_doi: dict[str, EnrichmentRecord]
    by_arxiv: dict[str, EnrichmentRecord]
    by_title: dict[str, list[EnrichmentRecord]]


def _build_indexes(records: Iterable[EnrichmentRecord]) -> _Indexes:
    by_doi: dict[str, EnrichmentRecord] = {}
    by_arxiv: dict[str, EnrichmentRecord] = {}
    by_title: dict[str, list[EnrichmentRecord]] = defaultdict(list)
    for e in records:
        if e.doi and e.doi not in by_doi:
            by_doi[e.doi] = e
        if e.arxiv_id and e.arxiv_id not in by_arxiv:
            by_arxiv[e.arxiv_id] = e
        if e.title_normalized:
            by_title[e.title_normalized].append(e)
    return _Indexes(by_doi=by_doi, by_arxiv=by_arxiv, by_title=dict(by_title))


def _match_identifier(
    record: PaperRecord, indexes: _Indexes
) -> tuple[EnrichmentRecord, str, float] | None:
    if record.doi and record.doi in indexes.by_doi:
        return indexes.by_doi[record.doi], STRATEGY_DOI, CONFIDENCE_DOI
    arxiv_id = normalize_arxiv_id(record.source_id)
    if arxiv_id and arxiv_id in indexes.by_arxiv:
        return indexes.by_arxiv[arxiv_id], STRATEGY_ARXIV, CONFIDENCE_ARXIV
    return None


def _guarded_title_candidates(
    record: PaperRecord, candidates: list[EnrichmentRecord], claimed: set[str]
) -> list[tuple[EnrichmentRecord, float]]:
    """Return candidates that pass the surname/year guard, with a confidence."""
    guarded: list[tuple[EnrichmentRecord, float]] = []
    for e in candidates:
        if e.enrichment_id in claimed:
            continue
        year_ok = (
            record.published_year is not None
            and e.publication_year is not None
            and record.published_year == e.publication_year
        )
        surname_ok = bool(set(record.author_surnames) & set(e.author_surnames))
        if year_ok and surname_ok:
            guarded.append((e, CONFIDENCE_TITLE_BOTH))
        elif year_ok or surname_ok:
            guarded.append((e, CONFIDENCE_TITLE_ONE))
    return guarded


def join_records(
    source_records: Iterable[PaperRecord], enrichment: EnrichmentAdapter
) -> JoinOutcome:
    """Join source records against an enrichment source and report coverage."""
    records = sorted(source_records, key=lambda r: r.paper_id)
    indexes = _build_indexes(enrichment.iter_records())

    claimed: set[str] = set()
    by_strategy = {STRATEGY_DOI: 0, STRATEGY_ARXIV: 0, STRATEGY_TITLE: 0}
    ambiguous_ids: set[str] = set()
    annotated: dict[str, PaperRecord] = {}
    matched_enrichment: dict[str, EnrichmentRecord] = {}
    title_pending: list[PaperRecord] = []

    # Pass 1: identifier strategies (DOI then external arXiv id).
    for record in records:
        hit = _match_identifier(record, indexes)
        if hit is not None:
            enrichment_record, strategy, confidence = hit
            annotated[record.paper_id] = record.with_match(
                strategy=strategy,
                confidence=confidence,
                enrichment_id=enrichment_record.enrichment_id,
            )
            claimed.add(enrichment_record.enrichment_id)
            matched_enrichment[enrichment_record.enrichment_id] = enrichment_record
            by_strategy[strategy] += 1
        else:
            title_pending.append(record)

    # Pass 2: normalised-title strategy, guarded and de-collided.
    provisional: dict[str, tuple[PaperRecord, EnrichmentRecord, float]] = {}
    per_enrichment: dict[str, list[str]] = defaultdict(list)
    for record in title_pending:
        candidates = indexes.by_title.get(record.title_normalized, [])
        guarded = _guarded_title_candidates(record, candidates, claimed)
        if len(guarded) == 1:
            enrichment_record, confidence = guarded[0]
            provisional[record.paper_id] = (record, enrichment_record, confidence)
            per_enrichment[enrichment_record.enrichment_id].append(record.paper_id)
        else:
            if len(guarded) > 1:
                ambiguous_ids.add(record.paper_id)
            annotated[record.paper_id] = (
                record.flag_ambiguous() if len(guarded) > 1 else record
            )

    # Resolve many-to-one collapses: an enrichment record claimed by >1 source.
    title_many_to_one = 0
    for paper_ids in per_enrichment.values():
        if len(paper_ids) > 1:
            title_many_to_one += 1
            for paper_id in paper_ids:
                record = provisional[paper_id][0]
                annotated[paper_id] = record.flag_ambiguous()
                ambiguous_ids.add(paper_id)
        else:
            record, enrichment_record, confidence = provisional[paper_ids[0]]
            annotated[paper_ids[0]] = record.with_match(
                strategy=STRATEGY_TITLE,
                confidence=confidence,
                enrichment_id=enrichment_record.enrichment_id,
            )
            matched_enrichment[enrichment_record.enrichment_id] = enrichment_record
            by_strategy[STRATEGY_TITLE] += 1

    ordered = [annotated[record.paper_id] for record in records]
    matched = sum(by_strategy.values())
    in_scope = len(records)
    report = CoverageReport(
        in_scope=in_scope,
        matched=matched,
        unmatched=in_scope - matched,
        ambiguous=len(ambiguous_ids),
        title_many_to_one=title_many_to_one,
        by_strategy=by_strategy,
    )
    return JoinOutcome(records=ordered, coverage=report, matched_enrichment=matched_enrichment)
