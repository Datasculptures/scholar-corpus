"""arXiv source adapter backed by the Kaggle metadata JSONL snapshot.

The snapshot is a single newline-delimited JSON file (one paper per line),
published on Kaggle as ``arxiv-metadata-oai-snapshot.json``. Reading it directly
keeps the build fully offline with no API rate limits, which is why it is the
first source implementation.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

from scholar_corpus.adapters.base import SnapshotInfo
from scholar_corpus.models import PaperRecord
from scholar_corpus.normalize import (
    normalize_doi,
    normalize_title,
    normalize_whitespace,
    surname_of,
)
from scholar_corpus.paths import DEFAULT_MAX_INPUT_BYTES, check_input_size

_HASH_CHUNK = 1 << 20  # 1 MiB


class ArxivKaggleAdapter:
    """Adapter over the Kaggle arXiv metadata JSONL snapshot."""

    source_name = "arxiv"

    def __init__(
        self, snapshot_path: Path | str, *, max_bytes: int = DEFAULT_MAX_INPUT_BYTES
    ) -> None:
        path = Path(snapshot_path)
        if not path.is_file():
            raise FileNotFoundError(f"arXiv snapshot not found: {path}")
        self._path = path
        self._max_bytes = max_bytes

    @property
    def path(self) -> Path:
        return self._path

    def snapshot(self) -> SnapshotInfo:
        """Return the snapshot identity, hashing the raw file in fixed chunks."""
        size = check_input_size(self._path, max_bytes=self._max_bytes)
        digest = hashlib.sha256()
        with self._path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(_HASH_CHUNK), b""):
                digest.update(chunk)
        return SnapshotInfo(name=self._path.name, sha256=digest.hexdigest(), byte_size=size)

    def iter_records(self) -> Iterator[PaperRecord]:
        """Stream every line of the snapshot as a normalised ``PaperRecord``.

        Blank lines are skipped. Lines that are not valid JSON objects are
        skipped rather than aborting the whole build; malformed input is a data
        problem the coverage/counts surface, not a crash.
        """
        check_input_size(self._path, max_bytes=self._max_bytes)
        with self._path.open("r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    raw: Any = json.loads(stripped)
                except json.JSONDecodeError:
                    continue
                if isinstance(raw, dict):
                    record = self._to_record(raw)
                    if record is not None:
                        yield record

    def _to_record(self, raw: dict[str, Any]) -> PaperRecord | None:
        source_id = raw.get("id")
        if not isinstance(source_id, str) or not source_id:
            return None

        title = normalize_whitespace(str(raw.get("title") or ""))
        abstract = normalize_whitespace(str(raw.get("abstract") or ""))
        categories = _split_categories(raw.get("categories"))
        authors_parsed = raw.get("authors_parsed")
        surnames = _surnames(authors_parsed)
        authors = _author_names(authors_parsed, raw.get("authors"))
        date_published, year = _first_version_date(raw.get("versions"))
        date_updated = _clean_date(raw.get("update_date"))
        version = _latest_version_label(raw.get("versions"))

        return PaperRecord(
            paper_id=f"arxiv:{source_id}",
            source=self.source_name,
            source_id=source_id,
            title=title,
            title_normalized=normalize_title(title),
            abstract=abstract,
            authors=authors,
            author_surnames=surnames,
            categories=categories,
            primary_category=categories[0] if categories else "",
            date_published=date_published,
            date_updated=date_updated,
            published_year=year,
            version=version,
            doi=normalize_doi(raw.get("doi")),
        )


def _split_categories(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return tuple(value.split())
    return ()


def _surnames(authors_parsed: object) -> tuple[str, ...]:
    if not isinstance(authors_parsed, list):
        return ()
    result: list[str] = []
    for entry in authors_parsed:
        surname = surname_of(entry)
        if surname is not None:
            result.append(surname)
    return tuple(result)


def _author_names(authors_parsed: object, authors_field: object) -> tuple[str, ...]:
    if isinstance(authors_parsed, list):
        names: list[str] = []
        for entry in authors_parsed:
            if isinstance(entry, (list, tuple)):
                parts = [str(p) for p in entry if isinstance(p, str) and p.strip()]
                if parts:
                    names.append(normalize_whitespace(" ".join(parts)))
        if names:
            return tuple(names)
    if isinstance(authors_field, str) and authors_field.strip():
        return (normalize_whitespace(authors_field),)
    return ()


def _first_version_date(versions: object) -> tuple[str | None, int | None]:
    if isinstance(versions, list) and versions:
        first = versions[0]
        if isinstance(first, dict):
            parsed = _parse_rfc2822(first.get("created"))
            if parsed is not None:
                return parsed.date().isoformat(), parsed.year
    return None, None


def _latest_version_label(versions: object) -> str | None:
    if isinstance(versions, list) and versions:
        last = versions[-1]
        if isinstance(last, dict):
            label = last.get("version")
            if isinstance(label, str) and label:
                return label
    return None


def _parse_rfc2822(value: object) -> datetime | None:
    if isinstance(value, str) and value.strip():
        try:
            return parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
    return None


def _clean_date(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None
