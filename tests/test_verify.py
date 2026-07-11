"""Verify re-hashes a corpus and fails on any tamper."""

from __future__ import annotations

import sqlite3
from contextlib import closing

from scholar_corpus.manifest import CATALOGUE_FILENAME, verify_corpus


def test_verify_passes_on_untouched_corpus(built_corpus: object) -> None:
    result = verify_corpus(built_corpus.corpus_dir)  # type: ignore[attr-defined]
    assert result.ok
    assert not result.failed
    assert result.actual_sha256 == built_corpus.content_sha256  # type: ignore[attr-defined]


def test_verify_fails_when_catalogue_tampered(built_corpus: object) -> None:
    catalogue_path = built_corpus.catalogue_path  # type: ignore[attr-defined]
    with closing(sqlite3.connect(catalogue_path)) as conn:
        conn.execute("UPDATE papers SET title = 'tampered' WHERE paper_id = 'arxiv:2101.00001'")
        conn.commit()
    result = verify_corpus(built_corpus.corpus_dir)  # type: ignore[attr-defined]
    assert result.failed
    assert result.expected_sha256 != result.actual_sha256
    assert "does not match" in result.reason


def test_verify_fails_when_catalogue_missing(built_corpus: object) -> None:
    (built_corpus.corpus_dir / CATALOGUE_FILENAME).unlink()  # type: ignore[attr-defined]
    result = verify_corpus(built_corpus.corpus_dir)  # type: ignore[attr-defined]
    assert result.failed
    assert "missing" in result.reason
