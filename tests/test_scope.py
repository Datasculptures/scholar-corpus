"""Tests for scope definition and the in-scope predicate."""

from __future__ import annotations

from datetime import date

import pytest

from scholar_corpus.models import PaperRecord
from scholar_corpus.scope import Scope


def _record(**overrides: object) -> PaperRecord:
    base: dict[str, object] = {
        "paper_id": "arxiv:1",
        "source": "arxiv",
        "source_id": "1",
        "title": "t",
        "title_normalized": "t",
        "abstract": "a",
        "authors": (),
        "author_surnames": (),
        "categories": ("cs.LG",),
        "primary_category": "cs.LG",
        "date_published": "2021-01-01",
        "date_updated": None,
        "version": "v1",
    }
    base.update(overrides)
    return PaperRecord(**base)  # type: ignore[arg-type]


def test_scope_normalises_categories_to_sorted_unique() -> None:
    scope = Scope(source="arxiv", categories=("cs.LG", "cs.AI", "cs.LG"))
    assert scope.categories == ("cs.AI", "cs.LG")


def test_scope_rejects_inverted_dates() -> None:
    with pytest.raises(ValueError, match="after"):
        Scope(source="arxiv", date_from=date(2022, 1, 1), date_to=date(2021, 1, 1))


def test_empty_categories_match_any() -> None:
    scope = Scope(source="arxiv")
    assert scope.matches(_record(categories=("hep-th",), primary_category="hep-th"))


def test_source_mismatch_is_out_of_scope() -> None:
    scope = Scope(source="biorxiv")
    assert not scope.matches(_record())


def test_category_and_date_bounds() -> None:
    scope = Scope(
        source="arxiv",
        categories=("cs.LG",),
        date_from=date(2020, 1, 1),
        date_to=date(2021, 12, 31),
    )
    assert scope.matches(_record(date_published="2021-06-01"))
    assert not scope.matches(_record(date_published="2019-06-01"))
    assert not scope.matches(_record(date_published="2022-06-01"))
    assert not scope.matches(_record(categories=("stat.ME",), primary_category="stat.ME"))


def test_missing_date_excluded_when_bound_set() -> None:
    scope = Scope(source="arxiv", date_from=date(2020, 1, 1))
    assert not scope.matches(_record(date_published=None))


def test_unparseable_date_excluded() -> None:
    scope = Scope(source="arxiv", date_from=date(2020, 1, 1))
    assert not scope.matches(_record(date_published="not-a-date"))


def test_as_dict_round_trips_bounds() -> None:
    scope = Scope(source="arxiv", categories=("cs.LG",), date_from=date(2020, 1, 1))
    assert scope.as_dict() == {
        "source": "arxiv",
        "categories": ["cs.LG"],
        "date_from": "2020-01-01",
        "date_to": None,
    }
