"""Explicit, documented normalisation.

Title normalisation is a load-bearing part of the (Phase 2) join: the
normalised-title strategy is only as trustworthy as this function. It is kept
small, pure, and heavily specified so its behaviour can be pinned by tests and
reproduced exactly across runs and machines.

Normalisation steps, in order:

1. Unicode NFKC compatibility composition, so visually identical strings that
   differ only in code points collapse together.
2. Case folding (stronger than ``str.lower`` for non-ASCII).
3. Replace any character that is not a Unicode letter or number with a space.
4. Collapse runs of whitespace to a single ASCII space and strip the ends.
"""

from __future__ import annotations

import re
import unicodedata

_WHITESPACE_RUN = re.compile(r"\s+")


def normalize_whitespace(text: str) -> str:
    """Collapse all whitespace runs to single spaces and strip the ends."""
    return _WHITESPACE_RUN.sub(" ", text).strip()


def normalize_title(title: str) -> str:
    """Return the canonical, comparison-ready form of a title.

    The result is deterministic and idempotent: ``normalize_title(x) ==
    normalize_title(normalize_title(x))`` for every ``x``.
    """
    folded = unicodedata.normalize("NFKC", title).casefold()
    kept = [ch if (ch.isalnum() or ch.isspace()) else " " for ch in folded]
    return normalize_whitespace("".join(kept))


def normalize_doi(doi: str | None) -> str | None:
    """Return a lowercased, prefix-stripped DOI, or ``None`` if absent/blank.

    Strips common URL and ``doi:`` prefixes so DOIs from different sources
    compare equal in the (Phase 2) DOI join strategy.
    """
    if doi is None:
        return None
    value = doi.strip().casefold()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if value.startswith(prefix):
            value = value[len(prefix) :]
    value = value.strip()
    return value or None


def surname_of(author_parts: object) -> str | None:
    """Extract a normalised surname from one arXiv ``authors_parsed`` entry.

    The Kaggle arXiv snapshot stores each author as ``[surname, given, suffix]``.
    The surname is the first element. Returns ``None`` for malformed entries.
    """
    if isinstance(author_parts, (list, tuple)) and author_parts:
        first = author_parts[0]
        if isinstance(first, str):
            cleaned = normalize_whitespace(unicodedata.normalize("NFKC", first).casefold())
            return cleaned or None
    return None


_ARXIV_VERSION_SUFFIX = re.compile(r"v\d+$")
_ARXIV_PREFIXES = (
    "arxiv:",
    "https://arxiv.org/abs/",
    "http://arxiv.org/abs/",
)


def normalize_arxiv_id(value: str | None) -> str | None:
    """Return a canonical arXiv id for cross-source matching, or ``None``.

    Lowercases, strips ``arXiv:`` / URL prefixes and a trailing version suffix
    (``v2``), so an id from OpenAlex compares equal to the source's own id in
    the external-identifier join strategy. Old-style ids (``hep-ph/9901001``)
    are preserved intact.
    """
    if value is None:
        return None
    v = value.strip().casefold()
    for prefix in _ARXIV_PREFIXES:
        if v.startswith(prefix):
            v = v[len(prefix) :]
    v = _ARXIV_VERSION_SUFFIX.sub("", v.strip())
    return v or None
