"""Read-only summaries of an existing corpus (library API).

Presentation-agnostic: returns plain dicts. The CLI renders them.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scholar_corpus.catalogue import count_rows
from scholar_corpus.manifest import CATALOGUE_FILENAME, read_manifest


def corpus_report(corpus_dir: Path) -> dict[str, Any]:
    """Return a structured summary of the corpus at ``corpus_dir``.

    The shape is stable across phases: ``coverage`` and ``graph`` are ``None``
    for a catalogue-only build, populated once enrichment and the citation graph
    have run, so the same renderer works throughout.
    """
    corpus_dir = Path(corpus_dir)
    manifest = read_manifest(corpus_dir)
    total, unmatched = count_rows(corpus_dir / CATALOGUE_FILENAME)
    matched = total - unmatched
    return {
        "corpus_dir": str(corpus_dir),
        "tool_version": manifest.tool_version,
        "scope": manifest.scope,
        "source": manifest.source,
        "records": total,
        "matched": matched,
        "unmatched": unmatched,
        "edges": manifest.counts.get("edges", 0),
        "coverage": manifest.coverage,
        "graph": manifest.graph,
        "content_sha256": manifest.content_sha256,
    }
