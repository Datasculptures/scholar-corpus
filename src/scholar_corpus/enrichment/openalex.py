"""OpenAlex enrichment adapter backed by a works JSONL snapshot.

Reads an OpenAlex works dump (or a filtered export) as newline-delimited JSON,
one work per line. Staying offline keeps builds deterministic and free of API
rate limits, matching the source-side design. A live, ``pyalex``-backed adapter
can be added later behind the same :class:`~scholar_corpus.enrichment.base.EnrichmentAdapter`
protocol without touching the join layer.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from scholar_corpus.adapters.base import SnapshotInfo
from scholar_corpus.enrichment.base import EnrichmentRecord
from scholar_corpus.normalize import (
    normalize_arxiv_id,
    normalize_doi,
    normalize_title,
    normalize_whitespace,
)
from scholar_corpus.paths import DEFAULT_MAX_INPUT_BYTES, check_input_size

_HASH_CHUNK = 1 << 20  # 1 MiB
_OPENALEX_PREFIX = "https://openalex.org/"


class OpenAlexSnapshotAdapter:
    """Adapter over an OpenAlex works JSONL snapshot."""

    source_name = "openalex"

    def __init__(
        self, snapshot_path: Path | str, *, max_bytes: int = DEFAULT_MAX_INPUT_BYTES
    ) -> None:
        path = Path(snapshot_path)
        if not path.is_file():
            raise FileNotFoundError(f"OpenAlex snapshot not found: {path}")
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

    def iter_records(self) -> Iterator[EnrichmentRecord]:
        """Stream every line of the snapshot as a normalised ``EnrichmentRecord``."""
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
                    record = _to_record(raw)
                    if record is not None:
                        yield record


def _strip_id(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        v = value.strip()
        if v.startswith(_OPENALEX_PREFIX):
            v = v[len(_OPENALEX_PREFIX) :]
        return v or None
    return None


def _to_record(raw: dict[str, Any]) -> EnrichmentRecord | None:
    enrichment_id = _strip_id(raw.get("id"))
    if enrichment_id is None:
        return None
    title = raw.get("title") or raw.get("display_name") or ""
    ids = raw.get("ids") if isinstance(raw.get("ids"), dict) else {}
    arxiv_raw = ids.get("arxiv") if isinstance(ids, dict) else None
    if arxiv_raw is None:
        arxiv_raw = raw.get("arxiv_id")
    referenced = tuple(
        rid for rid in (_strip_id(r) for r in _as_list(raw.get("referenced_works"))) if rid
    )
    return EnrichmentRecord(
        enrichment_id=enrichment_id,
        title_normalized=normalize_title(str(title)),
        doi=normalize_doi(raw.get("doi")),
        arxiv_id=normalize_arxiv_id(arxiv_raw if isinstance(arxiv_raw, str) else None),
        publication_year=_as_year(raw.get("publication_year")),
        author_surnames=_surnames(raw.get("authorships")),
        referenced_ids=referenced,
    )


def _as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_year(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _surnames(authorships: object) -> tuple[str, ...]:
    result: list[str] = []
    for entry in _as_list(authorships):
        if not isinstance(entry, dict):
            continue
        author = entry.get("author")
        display = author.get("display_name") if isinstance(author, dict) else None
        surname = _surname_of_display(display)
        if surname is not None:
            result.append(surname)
    return tuple(result)


def _surname_of_display(display: object) -> str | None:
    if isinstance(display, str) and display.strip():
        tokens = normalize_whitespace(display).split(" ")
        if tokens:
            return normalize_whitespace(tokens[-1]).casefold() or None
    return None
