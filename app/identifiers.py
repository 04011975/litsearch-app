from __future__ import annotations

import re

_DOI_PATTERN = re.compile(r"^10\.\d{2,9}/\S+$")

_DOI_PREFIXES = (
    "https://doi.org/",
    "http://doi.org/",
    "https://dx.doi.org/",
    "http://dx.doi.org/",
    "doi:",
)


def normalize_doi(value: str | None) -> str | None:
    """Normalize and validate a DOI identifier."""

    doi = str(value or "").strip()

    if not doi:
        return None

    lowered = doi.casefold()

    for prefix in _DOI_PREFIXES:
        if lowered.startswith(prefix):
            doi = doi[len(prefix) :].strip()
            break

    doi = doi.lower()

    if not _DOI_PATTERN.fullmatch(doi):
        return None

    return doi


def doi_matches(requested_doi: str, returned_doi: str | None) -> bool:
    """Check whether a returned DOI exactly matches the requested DOI."""
    requested = normalize_doi(requested_doi)
    returned = normalize_doi(returned_doi)

    return requested is not None and returned is not None and requested == returned

