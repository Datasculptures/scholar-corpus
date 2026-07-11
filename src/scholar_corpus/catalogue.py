"""SQLite catalogue: the deduplicated, normalised paper table.

The catalogue is Datasette-compatible: a single ``papers`` table keyed by the
stable ``paper_id``. The join columns (``matched``, ``match_strategy``,
``match_confidence``, ``enrichment_id``) exist from Phase 1 so the Phase 2 join
needs no migration; in Phase 1 they carry their inert defaults.

Determinism is a correctness property. Rows are always written in ``paper_id``
order, and the content hash (see :mod:`scholar_corpus.manifest`) is computed by
reading the table back through :func:`iter_rows`, so it depends only on content,
never on SQLite's internal file layout.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Iterator
from contextlib import closing
from pathlib import Path
from typing import Any

from scholar_corpus.models import CATALOGUE_COLUMNS, PaperRecord

_INTEGER_COLUMNS = frozenset({"matched", "published_year"})
_REAL_COLUMNS = frozenset({"match_confidence"})

TABLE_NAME = "papers"


def _column_ddl() -> str:
    parts: list[str] = []
    for col in CATALOGUE_COLUMNS:
        if col == "paper_id":
            parts.append(f"{col} TEXT PRIMARY KEY")
        elif col in _INTEGER_COLUMNS:
            parts.append(f"{col} INTEGER")
        elif col in _REAL_COLUMNS:
            parts.append(f"{col} REAL")
        else:
            parts.append(f"{col} TEXT")
    return ", ".join(parts)


def write_catalogue(path: Path, records: Iterable[PaperRecord]) -> int:
    """Write ``records`` to a fresh SQLite catalogue at ``path``.

    Returns the number of rows written. Any existing file at ``path`` is
    replaced. Rows are sorted by ``paper_id`` before insertion so output is
    deterministic regardless of input order.
    """
    path = Path(path)
    if path.exists():
        path.unlink()
    ordered = sorted(records, key=lambda r: r.paper_id)
    placeholders = ", ".join([f":{col}" for col in CATALOGUE_COLUMNS])
    column_list = ", ".join(CATALOGUE_COLUMNS)
    insert_sql = f"INSERT INTO {TABLE_NAME} ({column_list}) VALUES ({placeholders})"
    with closing(sqlite3.connect(path)) as conn:
        conn.execute(f"CREATE TABLE {TABLE_NAME} ({_column_ddl()})")
        conn.executemany(insert_sql, (r.as_row() for r in ordered))
        conn.execute(f"CREATE INDEX idx_{TABLE_NAME}_matched ON {TABLE_NAME} (matched)")
        conn.commit()
    return len(ordered)


def iter_rows(path: Path) -> Iterator[dict[str, Any]]:
    """Yield catalogue rows as dicts, ordered by ``paper_id``.

    This is the single read path used for both content hashing and reporting,
    so the hash and the report always describe the same bytes.
    """
    columns = ", ".join(CATALOGUE_COLUMNS)
    with closing(sqlite3.connect(f"file:{Path(path)}?mode=ro", uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(f"SELECT {columns} FROM {TABLE_NAME} ORDER BY paper_id")
        for row in cursor:
            yield {col: row[col] for col in CATALOGUE_COLUMNS}


def count_rows(path: Path) -> tuple[int, int]:
    """Return ``(total_rows, unmatched_rows)`` for the catalogue at ``path``."""
    with closing(sqlite3.connect(f"file:{Path(path)}?mode=ro", uri=True)) as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()[0]
        unmatched = conn.execute(
            f"SELECT COUNT(*) FROM {TABLE_NAME} WHERE matched = 0"
        ).fetchone()[0]
    return int(total), int(unmatched)
