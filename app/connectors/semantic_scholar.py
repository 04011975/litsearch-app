from __future__ import annotations

import logging
import os
import random
import time
from typing import Any

import requests

from app.models.paper import Paper

logger = logging.getLogger("litsearch.semantic_scholar")

BASE_URL = "https://api.semanticscholar.org/graph/v1"
SEARCH_URL = f"{BASE_URL}/paper/search"
TIMEOUT = 20
MAX_PAGE_SIZE = 100

BULK_SEARCH_URL = f"{BASE_URL}/paper/search/bulk"
MAX_BULK_PAGE_SIZE = 1000  # bulk endpoint supports larger batches than regular search

SEARCH_FIELDS = ",".join(
    [
        "paperId",
        "title",
        "authors",
        "year",
        "abstract",
        "venue",
        "url",
        "externalIds",
        "openAccessPdf",
    ]
)

BULK_SEARCH_FIELDS = ",".join(
    [
        "paperId",
        "title",
        "authors",
        "year",
        "abstract",
        "venue",
        "url",
        "externalIds",
        "openAccessPdf",
        "publicationDate",
    ]
)

DETAIL_FIELDS = BULK_SEARCH_FIELDS

_session = requests.Session()
_last_request_time = 0.0
class SemanticScholarError(Exception):
    """Raised when Semantic Scholar returns an error or malformed response."""


def _headers() -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "User-Agent": "LitSearch/1.0",
    }
    api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "").strip()

    logger.debug("Semantic Scholar API key configured=%s", bool(api_key))

    if api_key:
        headers["x-api-key"] = api_key
    return headers


def _request(url: str, params: dict[str, Any]) -> dict[str, Any]:
    global _last_request_time
    last_exc = None

    for attempt in range(3):
        try:
            now = time.time()
            elapsed = now - _last_request_time

            if elapsed < 1.1:
                time.sleep(1.1 - elapsed)

            logger.info("Semantic Scholar API request params=%r", params)

            response = _session.get(
                url,
                params=params,
                headers=_headers(),
                timeout=TIMEOUT,
            )

            _last_request_time = time.time()

            logger.info("Semantic Scholar API response status=%s", response.status_code)

        except requests.exceptions.Timeout as exc:
            last_exc = SemanticScholarError("Semantic Scholar request timed out")
            if attempt < 2:
                time.sleep((2 ** attempt) + random.uniform(0, 0.25))
                continue
            raise last_exc from exc

        except requests.exceptions.RequestException as exc:
            raise SemanticScholarError(f"Semantic Scholar request failed: {exc}") from exc

        if response.status_code == 429:
            logger.warning("Semantic Scholar API rate limit hit params=%r", params)
            if attempt < 2:
                retry_after = response.headers.get("Retry-After")
                try:
                    wait_s = float(retry_after) if retry_after else (2 ** attempt)
                except ValueError:
                    wait_s = 2 ** attempt
                time.sleep(wait_s + random.uniform(0, 0.25))
                continue
            raise SemanticScholarError("Semantic Scholar rate limit reached (HTTP 429)")

        if response.status_code >= 500:
            if attempt < 2:
                time.sleep((2 ** attempt) + random.uniform(0, 0.25))
                continue
            body = response.text[:500]
            raise SemanticScholarError(
                f"Semantic Scholar API error {response.status_code}: {body}"
            )

        if response.status_code >= 400:
            body = response.text[:500]
            raise SemanticScholarError(
                f"Semantic Scholar API error {response.status_code}: {body}"
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise SemanticScholarError("Semantic Scholar returned invalid JSON") from exc

        if not isinstance(data, dict):
            raise SemanticScholarError("Unexpected Semantic Scholar response format")

        return data

    if last_exc:
        raise last_exc
    raise SemanticScholarError("Semantic Scholar request failed")


def _extract_authors(record: dict[str, Any]) -> list[str]:
    authors = record.get("authors") or []
    out: list[str] = []
    for author in authors:
        if not isinstance(author, dict):
            continue
        name = (author.get("name") or "").strip()
        if name:
            out.append(name)
    return out


def _extract_external_ids(record: dict[str, Any]) -> dict[str, Any]:
    external_ids = record.get("externalIds") or {}
    if isinstance(external_ids, dict):
        return external_ids
    return {}


def _extract_doi(record: dict[str, Any]) -> str | None:
    external_ids = _extract_external_ids(record)
    doi = external_ids.get("DOI")
    if not doi:
        return None
    doi = str(doi).strip()
    if doi.lower().startswith("https://doi.org/"):
        doi = doi.split("https://doi.org/", 1)[1].strip()
    return doi or None


def _extract_pmcid(record: dict[str, Any]) -> str | None:
    external_ids = _extract_external_ids(record)
    pmcid = external_ids.get("PMCID") or external_ids.get("PMC")
    if not pmcid:
        return None
    return str(pmcid).strip() or None


def _extract_journal(record: dict[str, Any]) -> str | None:
    venue = record.get("venue")
    if venue and isinstance(venue, str):
        venue = venue.strip()
        if venue:
            return venue
    return None


def _has_full_text(record: dict[str, Any]) -> bool:
    return bool(record.get("openAccessPdf"))


def _to_paper(record: dict[str, Any]) -> Paper:
    paper_id = str(record.get("paperId") or "").strip()

    abstract = record.get("abstract")
    if isinstance(abstract, str):
        abstract = abstract.strip() or None
    else:
        abstract = None

    publication_date = record.get("publicationDate")
    if isinstance(publication_date, str):
        publication_date = publication_date.strip() or None
    else:
        publication_date = None

    return Paper(
        id=paper_id,
        source="semantic_scholar",
        title=(record.get("title") or "").strip(),
        authors=_extract_authors(record),
        journal=_extract_journal(record),
        year=record.get("year"),
        publication_date=publication_date,
        abstract=abstract,
        doi=_extract_doi(record),
        url=record.get("url") or (
            f"https://www.semanticscholar.org/paper/{paper_id}" if paper_id else None
        ),
        pmcid=_extract_pmcid(record),
        mesh_terms=[],
        has_full_text=_has_full_text(record),
    )


def _passes_local_filters(
    paper: Paper,
    year_min: int | None,
    year_max: int | None,
    has_abstract: bool,
) -> bool:
    if has_abstract and not (paper.abstract and str(paper.abstract).strip()):
        return False

    try:
        year = int(paper.year) if paper.year is not None else None
    except (TypeError, ValueError):
        year = None

    if year_min is not None:
        if year is None or year < year_min:
            return False

    if year_max is not None:
        if year is None or year > year_max:
            return False

    return True


def search_semantic_scholar(
    q: str,
    page: int = 1,
    n: int = 20,
    year_min: int | None = None,
    year_max: int | None = None,
    has_abstract: bool = False,
) -> tuple[list[Paper], int]:
    """
    Search Semantic Scholar and normalize results to canonical Paper objects.

    Note:
    - Pagination is offset/limit based.
    - year_min/year_max/has_abstract are applied locally after fetch for v1.
    """
    q = (q or "").strip()
    if not q:
        return [], 0

    page = max(1, int(page))
    n = max(1, min(int(n), MAX_PAGE_SIZE))
    offset = (page - 1) * n

    params = {
        "query": q,
        "offset": offset,
        "limit": n,
        "fields": SEARCH_FIELDS,
    }

    data = _request(SEARCH_URL, params=params)

    raw_items = data.get("data") or []
    if not isinstance(raw_items, list):
        raise SemanticScholarError("Semantic Scholar search returned malformed data list")

    try:
        total = int(data.get("total", 0) or 0)
    except (TypeError, ValueError):
        total = 0

    papers: list[Paper] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        try:
            paper = _to_paper(item)
        except Exception:
            continue

        if _passes_local_filters(
            paper,
            year_min=year_min,
            year_max=year_max,
            has_abstract=has_abstract,
        ):
            papers.append(paper)

    return papers, total

def search_semantic_scholar_bulk(
    q: str,
    *,
    n: int = 20,
    token: str | None = None,
    sort: str = "publicationDate:desc",
    year_min: int | None = None,
    year_max: int | None = None,
    has_abstract: bool = False,
) -> tuple[list[Paper], int | None, str | None]:
    """
    Search Semantic Scholar bulk endpoint.

    Intended for chronological retrieval modes, e.g.:
    - publicationDate:desc
    - publicationDate:asc

    Returns:
        (papers, estimated_total, next_token)
    """
    q = (q or "").strip()
    if not q:
        return [], 0, None

    n = max(1, min(int(n), MAX_BULK_PAGE_SIZE))

    allowed_sorts = {"publicationDate:desc", "publicationDate:asc"}
    if sort not in allowed_sorts:
        raise SemanticScholarError(f"Unsupported Semantic Scholar bulk sort: {sort}")

    params: dict[str, Any] = {
        "query": q,
        "fields": BULK_SEARCH_FIELDS,
        "limit": n,
        "sort": sort,
    }

    if token:
        params["token"] = token

    # Server-side year filtering for bulk mode
    if year_min is not None and year_max is not None:
        params["year"] = f"{year_min}-{year_max}"
    elif year_min is not None:
        params["year"] = f"{year_min}-"
    elif year_max is not None:
        params["year"] = f"-{year_max}"

    data = _request(BULK_SEARCH_URL, params=params)

    raw_items = data.get("data") or []
    if not isinstance(raw_items, list):
        raise SemanticScholarError("Semantic Scholar bulk search returned malformed data list")

    next_token = data.get("token")
    if next_token is not None:
        next_token = str(next_token).strip() or None

    estimated_total_raw = data.get("total")
    try:
        estimated_total = int(estimated_total_raw) if estimated_total_raw is not None else None
    except (TypeError, ValueError):
        estimated_total = None

    papers: list[Paper] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        try:
            paper = _to_paper(item)
        except Exception:
            continue

        # Only keep local abstract filter here.
        # Year filtering is already handled server-side in bulk mode.
        if has_abstract and not (paper.abstract and str(paper.abstract).strip()):
            continue

        papers.append(paper)

    papers = papers[:n]
    return papers, estimated_total, next_token

def fetch_semantic_scholar_detail(paper_id: str) -> Paper | None:
    """
    Fetch one Semantic Scholar paper by paperId and normalize to Paper.
    """
    paper_id = (paper_id or "").strip()
    if not paper_id:
        return None

    url = f"{BASE_URL}/paper/{paper_id}"
    params = {"fields": DETAIL_FIELDS}
    data = _request(url, params=params)

    try:
        return _to_paper(data)
    except Exception:
        return None