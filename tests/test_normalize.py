"""Unit tests for the normalisation functions the join layer depends on."""

from __future__ import annotations

import pytest

from scholar_corpus.normalize import (
    normalize_doi,
    normalize_title,
    normalize_whitespace,
    surname_of,
)


def test_normalize_title_is_idempotent() -> None:
    once = normalize_title("Collision   Title!!!")
    assert once == "collision title"
    assert normalize_title(once) == once


def test_normalize_title_unicode_and_punctuation() -> None:
    assert normalize_title("Über Ünïcode  Café") == "über ünïcode café"
    assert normalize_title("A/B: Testing, 2021!") == "a b testing 2021"


def test_normalize_whitespace() -> None:
    assert normalize_whitespace("  a\t b\n c ") == "a b c"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("10.1/ABC", "10.1/abc"),
        ("https://doi.org/10.5/XYZ", "10.5/xyz"),
        ("http://doi.org/10.5/xyz", "10.5/xyz"),
        ("doi:10.9/q", "10.9/q"),
        ("  ", None),
        (None, None),
    ],
)
def test_normalize_doi(raw: str | None, expected: str | None) -> None:
    assert normalize_doi(raw) == expected


def test_surname_of_handles_good_and_bad_input() -> None:
    assert surname_of(["Smith", "J", ""]) == "smith"
    assert surname_of([]) is None
    assert surname_of("not a list") is None
    assert surname_of([123]) is None
