from __future__ import annotations

import logging
from typing import Any

import requests

from app.models.paper import Paper

logger = logging.getLogger("litsearch.doaj")

BASE_URL = "https://doaj.org/api/search/articles"
TIMEOUT = 30
MAX_PAGE_SIZE = 100


class DoajError(Exception):
    """Raised when DOAJ returns an error or malformed response."""


def _extract_authors(bibjson: dict[str, Any]) -> list[str]:
    authors = bibjson.get("author") or []

    out: list[str] = []

    for author in authors:
        if not isinstance(author, dict):
            continue

        name = str(author.get("name") or "").strip()

        if name:
            out.append(name)

    return out


def _extract_doi(bibjson: dict[str, Any]) -> str | None:
    identifiers = bibjson.get("identifier") or []

    for identifier in identifiers:
        if not isinstance(identifier, dict):
            continue

        identifier_type = str(identifier.get("type") or "").strip().lower()

        if identifier_type != "doi":
            continue

        doi = str(identifier.get("id") or "").strip()

        if not doi:
            continue

        if doi.lower().startswith("https://doi.org/"):
            doi = doi.split("https://doi.org/", 1)[1].strip()

        return doi or None

    return None


def _extract_journal(bibjson: dict[str, Any]) -> str:
    journal = bibjson.get("journal") or {}

    if not isinstance(journal, dict):
        return ""

    return str(journal.get("title") or "").strip()


def _extract_year(bibjson: dict[str, Any]) -> int | None:
    raw_year = bibjson.get("year")

    if raw_year is None:
        return None

    try:
        return int(str(raw_year).strip())
    except (TypeError, ValueError):
        return None


def _extract_url(bibjson: dict[str, Any]) -> str | None:
    links = bibjson.get("link") or []

    fallback: str | None = None

    for link in links:
        if not isinstance(link, dict):
            continue

        url = str(link.get("url") or "").strip()

        if not url:
            continue

        link_type = str(link.get("type") or "").strip().lower()

        if link_type == "fulltext":
            return url

        if fallback is None:
            fallback = url

    return fallback


def _has_full_text(bibjson: dict[str, Any]) -> bool:
    links = bibjson.get("link") or []

    for link in links:
        if not isinstance(link, dict):
            continue

        link_type = str(link.get("type") or "").strip().lower()
        url = str(link.get("url") or "").strip()

        if link_type == "fulltext" and url:
            return True

    return False


def _extract_concepts(bibjson: dict[str, Any]) -> list[str]:
    concepts: list[str] = []

    keywords = bibjson.get("keywords") or []

    if isinstance(keywords, list):
        for keyword in keywords:
            value = str(keyword or "").strip()

            if value and value not in concepts:
                concepts.append(value)

    subjects = bibjson.get("subject") or []

    if isinstance(subjects, list):
        for subject in subjects:
            if not isinstance(subject, dict):
                continue

            term = str(subject.get("term") or "").strip()

            if term and term not in concepts:
                concepts.append(term)

    return concepts


def _to_paper(record: dict[str, Any]) -> Paper:
    bibjson = record.get("bibjson") or {}

    if not isinstance(bibjson, dict):
        bibjson = {}

    record_id = str(record.get("id") or "").strip()

    abstract = bibjson.get("abstract")

    if isinstance(abstract, str):
        abstract = abstract.strip() or None
    else:
        abstract = None

    return Paper(
        id=record_id,
        source="doaj",
        title=str(bibjson.get("title") or "").strip(),
        authors=_extract_authors(bibjson),
        journal=_extract_journal(bibjson),
        year=_extract_year(bibjson),
        publication_date=None,
        abstract=abstract,
        doi=_extract_doi(bibjson),
        pmcid=None,
        url=_extract_url(bibjson),
        mesh_terms=[],
        has_full_text=_has_full_text(bibjson),
        concepts=_extract_concepts(bibjson),
    )


def _passes_local_filters(
    paper: Paper,
    year_min: int | None,
    year_max: int | None,
    has_abstract: bool,
) -> bool:
    if has_abstract and not (paper.abstract and paper.abstract.strip()):
        return False

    year = paper.year

    if year_min is not None:
        if year is None or year < year_min:
            return False

    if year_max is not None:
        if year is None or year > year_max:
            return False

    return True


def doaj_search(
    q: str,
    page: int = 1,
    n: int = 20,
    year_min: int | None = None,
    year_max: int | None = None,
    has_abstract: bool = False,
) -> tuple[list[Paper], int]:
    """
    Search DOAJ articles and normalize results to canonical Paper objects.

    year_min/year_max/has_abstract are applied locally in this first version.
    """

    q = (q or "").strip()

    if not q:
        return [], 0

    page = max(1, int(page))
    n = max(1, min(int(n), MAX_PAGE_SIZE))

    url = f"{BASE_URL}/{requests.utils.quote(q, safe='')}"

    params = {
        "page": page,
        "pageSize": n,
    }

    headers = {
        "Accept": "application/json",
        "User-Agent": "LitSearch/1.0",
    }

    try:
        response = requests.get(
            url,
            params=params,
            headers=headers,
            timeout=TIMEOUT,
        )
    except requests.exceptions.Timeout as exc:
        raise DoajError("DOAJ request timed out") from exc
    except requests.exceptions.RequestException as exc:
        raise DoajError(f"DOAJ request failed: {exc}") from exc

    if response.status_code >= 400:
        body = response.text[:500]
        raise DoajError(f"DOAJ API error {response.status_code}: {body}")

    try:
        data = response.json()
    except ValueError as exc:
        raise DoajError("DOAJ returned invalid JSON") from exc

    if not isinstance(data, dict):
        raise DoajError("Unexpected DOAJ response format")

    raw_results = data.get("results") or []

    if not isinstance(raw_results, list):
        raise DoajError("DOAJ search returned malformed results list")

    try:
        total = int(data.get("total", 0) or 0)
    except (TypeError, ValueError):
        total = 0

    papers: list[Paper] = []

    for item in raw_results:
        if not isinstance(item, dict):
            continue

        try:
            paper = _to_paper(item)
        except Exception:
            logger.exception("Failed to map DOAJ record")
            continue

        if _passes_local_filters(
            paper,
            year_min=year_min,
            year_max=year_max,
            has_abstract=has_abstract,
        ):
            papers.append(paper)

    return papers, total
