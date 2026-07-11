"""Scope definition and in-scope predicate.

A :class:`Scope` is the corpus's boundary: which source, which categories, and
which date range. It is frozen and canonically serialisable so it can be pinned
into the provenance manifest and reproduced exactly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from scholar_corpus.models import PaperRecord


@dataclass(frozen=True, slots=True)
class Scope:
    """The boundary of a corpus build.

    ``categories`` is matched with OR semantics: a paper is in scope if it
    carries at least one of the listed categories. An empty ``categories`` tuple
    means "any category". Date bounds are inclusive and compared against a
    paper's publication date; a record with no publication date is excluded
    whenever any date bound is set, because its membership cannot be verified.
    """

    source: str
    categories: tuple[str, ...] = ()
    date_from: date | None = None
    date_to: date | None = None

    def __post_init__(self) -> None:
        # Normalise categories to a sorted, de-duplicated tuple so equal scopes
        # serialise identically regardless of input order.
        object.__setattr__(self, "categories", tuple(sorted(set(self.categories))))
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError(
                f"date_from {self.date_from} is after date_to {self.date_to}"
            )

    def matches(self, record: PaperRecord) -> bool:
        """Return whether ``record`` falls within this scope."""
        if record.source != self.source:
            return False
        if self.categories and not any(c in self.categories for c in record.categories):
            return False
        if self.date_from is not None or self.date_to is not None:
            published = _parse_iso_date(record.date_published)
            if published is None:
                return False
            if self.date_from is not None and published < self.date_from:
                return False
            if self.date_to is not None and published > self.date_to:
                return False
        return True

    def as_dict(self) -> dict[str, object]:
        """Return a canonical, JSON-serialisable representation."""
        return {
            "source": self.source,
            "categories": list(self.categories),
            "date_from": self.date_from.isoformat() if self.date_from else None,
            "date_to": self.date_to.isoformat() if self.date_to else None,
        }


def _parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None
