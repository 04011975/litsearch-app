from __future__ import annotations

import logging
import os
from typing import List, Optional, Tuple

import requests

from app.models.paper import Paper

logger = logging.getLogger("litsearch.connector.crossref")

BASE_URL = "https://api.crossref.org"
SEARCH_ENDPOINT = "/works"
ROWS_MAX = 100

TOOL_NAME = os.getenv("TOOL_NAME", "LitSearch")
CONTACT_EMAIL = (os.getenv("CONTACT_EMAIL") or "").strip()


def _user_agent() -> str:
    if CONTACT_EMAIL:
        return f"{TOOL_NAME}/0.1 (mailto:{CONTACT_EMAIL})"
    return f"{TOOL_NAME}/0.1"


def _normalize_doi(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    s = raw.strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if s.startswith(prefix):
            s = s[len(prefix):].strip()
    return s or None


def _first_text(value) -> str:
    if isinstance(value, list) and value:
        return str(value[0] or "").strip()
    if isinstance(value, str):
        return value.strip()
    return ""


def _extract_authors(item: dict) -> List[str]:
    authors: List[str] = []
    contributors = item.get("author") or item.get("editor") or []

    for a in contributors:
        given = str(a.get("given") or "").strip()
        family = str(a.get("family") or "").strip()
        name = " ".join(part for part in [given, family] if part)
        if name:
            authors.append(name)

    return authors

def _extract_year(item: dict) -> Optional[int]:
    for key in ("published-print", "published-online", "published", "issued"):
        parts = ((item.get(key) or {}).get("date-parts") or [])
        if parts and isinstance(parts[0], list) and parts[0]:
            try:
                return int(parts[0][0])
            except Exception:
                continue
    return None


def _extract_publication_date(item: dict) -> Optional[str]:
    for key in ("published-print", "published-online", "published", "issued"):
        parts = ((item.get(key) or {}).get("date-parts") or [])
        if parts and isinstance(parts[0], list) and parts[0]:
            nums = parts[0]
            try:
                year = int(nums[0])
                month = int(nums[1]) if len(nums) > 1 else 1
                day = int(nums[2]) if len(nums) > 2 else 1
                return f"{year:04d}-{month:02d}-{day:02d}"
            except Exception:
                continue
    return None


def _build_filter(year_min: Optional[int], year_max: Optional[int]) -> Optional[str]:
    parts: list[str] = []
    if year_min is not None:
        parts.append(f"from-pub-date:{int(year_min)}-01-01")
    if year_max is not None:
        parts.append(f"until-pub-date:{int(year_max)}-12-31")
    return ",".join(parts) if parts else None


def _map_item_to_paper(item: dict) -> Paper:
    doi = _normalize_doi(item.get("DOI"))
    title = _first_text(item.get("title"))
    journal = _first_text(item.get("container-title"))
    year = _extract_year(item)
    publication_date = _extract_publication_date(item)

    return Paper(
        id=doi or str(item.get("URL") or "").strip(),
        source="crossref",
        title=title,
        authors=_extract_authors(item),
        journal=journal,
        year=year,
        publication_date=publication_date,
        abstract=_first_text(item.get("abstract")) or None,
        doi=doi,
        pmcid=None,
        url=item.get("URL"),
        mesh_terms=[],
        concepts=[],
        has_full_text=False,
    )


def crossref_search(
    q: str,
    page: int = 1,
    n: int = 10,
    *,
    sort: str = "relevance",
    year_min: Optional[int] = None,
    year_max: Optional[int] = None,
) -> Tuple[List[Paper], int]:
    q = (q or "").strip()
    page = max(1, int(page))
    n = min(max(1, int(n)), ROWS_MAX)

    if not q:
        return [], 0

    offset = (page - 1) * n

    params = {
        "query": q,
        "rows": n,
        "offset": offset,
    }

    if sort in {"date_desc", "newest", "latest", "recent"}:
        params["sort"] = "published"
        params["order"] = "desc"
    elif sort in {"date_asc", "oldest", "oldest first"}:
        params["sort"] = "published"
        params["order"] = "asc"

    filt = _build_filter(year_min, year_max)
    if filt:
        params["filter"] = filt

    if CONTACT_EMAIL:
        params["mailto"] = CONTACT_EMAIL

    logger.info(
        "crossref_search q=%r page=%s n=%s sort=%r filter=%r",
        q,
        page,
        n,
        sort,
        params.get("filter"),
    )

    try:
        r = requests.get(
            f"{BASE_URL}{SEARCH_ENDPOINT}",
            params=params,
            timeout=(10, 90),
            headers={"User-Agent": _user_agent()},
        )
    except requests.RequestException as e:
        logger.exception("crossref_search request failed: %s", e)
        return [], 0

    if r.status_code == 429:
        logger.warning("crossref_search rate limited url=%s", getattr(r, "url", ""))
        return [], 0

    try:
        r.raise_for_status()
        data = r.json() or {}
    except Exception as e:
        logger.exception("crossref_search invalid response: %s", e)
        return [], 0

    message = data.get("message") or {}
    items = message.get("items") or []
    total = int(message.get("total-results") or 0)

    papers = [_map_item_to_paper(item) for item in items if isinstance(item, dict)]

    return papers, total


def crossref_fetch_detail(identifier: str) -> Paper | None:
    doi = _normalize_doi(identifier)
    if not doi:
        return None

    params = {"mailto": CONTACT_EMAIL} if CONTACT_EMAIL else None

    try:
        r = requests.get(
            f"{BASE_URL}{SEARCH_ENDPOINT}/{doi}",
            params=params,
            timeout=(10, 90),
            headers={"User-Agent": _user_agent()},
        )
        if r.status_code == 404:
            return None
        if r.status_code == 429:
            logger.warning("crossref_fetch_detail rate limited doi=%s", doi)
            return None
        r.raise_for_status()
        data = r.json() or {}
    except Exception:
        logger.exception("crossref_fetch_detail failed identifier=%r", identifier)
        return None

    item = (data.get("message") or {})
    if not item:
        return None

    return _map_item_to_paper(item)