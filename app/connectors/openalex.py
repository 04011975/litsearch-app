from __future__ import annotations

import logging
import os
from typing import Tuple, List, Optional

import requests

from app.models.paper import Paper

logger = logging.getLogger("litsearch.connector.openalex")

BASE_URL = "https://api.openalex.org"
SEARCH_ENDPOINT = "/works"
PER_PAGE_MAX = 200

TOOL_NAME = os.getenv("TOOL_NAME", "LitSearch")
CONTACT_EMAIL = (os.getenv("CONTACT_EMAIL") or "").strip()


def _user_agent() -> str:
    if CONTACT_EMAIL:
        return f"{TOOL_NAME}/0.1 (mailto:{CONTACT_EMAIL})"
    return f"{TOOL_NAME}/0.1"

def _openalex_short_id(raw_id: str) -> str:
    s = (raw_id or "").strip()
    if not s:
        return ""
    # accepteert zowel volledige URL als W-id
    # https://openalex.org/W123 -> W123
    return s.split("/")[-1]

def _map_sort(sort: str) -> Optional[str]:
    """
    OpenAlex sort keys (docs): display_name, cited_by_count, works_count,
    publication_date, relevance_score (only with search). :contentReference[oaicite:2]{index=2}
    """
    s = (sort or "").strip().lower()

    # UI often sends: relevance / year / cited_by_count etc.
    if s in {"", "default", "relevance"}:
        return "relevance_score:desc"
    if s in {"relevance_score"}:
        return "relevance_score:desc"

    # “Year” dropdowns: pick publication_date
    if s in {"year", "newest", "date", "publication_date", "publication_year"}:
        return "publication_date:desc"
    if s in {"oldest"}:
        return "publication_date"

    if s in {"cited_by_count", "citations", "most_cited"}:
        return "cited_by_count:desc"

    # fallback: allow passing a raw OpenAlex sort string
    return sort

def _normalize_doi(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    s = raw.strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if s.startswith(prefix):
            s = s[len(prefix):].strip()
    return s or None

def _extract_authors(work: dict) -> List[str]:
    authorships = work.get("authorships") or []
    out: List[str] = []
    for a in authorships:
        author = (a or {}).get("author") or {}
        name = author.get("display_name")
        if name:
            out.append(name)
    return out

def _landing_url(work: dict) -> Optional[str]:
    primary_location = work.get("primary_location") or {}
    url = primary_location.get("landing_page_url")
    if url:
        return url
    return work.get("id")

def _openalex_abstract_from_inverted_index(inv: dict) -> str:
    if not isinstance(inv, dict):
        return ""
    pos_to_word: dict[int, str] = {}
    for word, positions in inv.items():
        if not isinstance(word, str):
            continue
        if not isinstance(positions, list):
            continue
        for p in positions:
            if isinstance(p, int):
                pos_to_word[p] = word
    if not pos_to_word:
        return ""
    return " ".join(word for _, word in sorted(pos_to_word.items()))

def _journal_name(work: dict) -> str:
    # Primary location source name (preferred)
    j = ((work.get("primary_location") or {}).get("source") or {}).get("display_name") or ""
    if j:
        return j
    # Fallback for older payload variants
    return ((work.get("host_venue") or {}).get("display_name") or "").strip()

def _build_filter(year_min: Optional[int], year_max: Optional[int]) -> Optional[str]:
    """
    Year range uses from_publication_date/to_publication_date inside `filter=...`
    :contentReference[oaicite:3]{index=3}
    """
    parts: list[str] = []
    if year_min is not None:
        parts.append(f"from_publication_date:{int(year_min)}-01-01")
    if year_max is not None:
        parts.append(f"to_publication_date:{int(year_max)}-12-31")
    return ",".join(parts) if parts else None


def openalex_search(
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
    n = min(max(1, int(n)), PER_PAGE_MAX)

    if not q:
        return [], 0

    params = {
        "search": q,
        "page": page,
        "per-page": n,
    }

    sort_param = _map_sort(sort)
    if sort_param:
        params["sort"] = sort_param

    filt = _build_filter(year_min, year_max)
    if filt:
        params["filter"] = filt

    if CONTACT_EMAIL:
        params["mailto"] = CONTACT_EMAIL

    logger.info(
        "openalex_search q=%r page=%s n=%s sort=%r filter=%r",
        q, page, n, params.get("sort"), params.get("filter"),
    )

    try:
        r = requests.get(
            f"{BASE_URL}{SEARCH_ENDPOINT}",
            params=params,
            timeout=(10, 30),
            headers={"User-Agent": _user_agent()},
        )
    except requests.RequestException as e:
        logger.exception("openalex_search request failed: %s", e)
        return [], 0

    if r.status_code == 429:
        logger.warning("openalex_search rate limited (429) url=%s", getattr(r, "url", ""))
        return [], 0

    try:
        r.raise_for_status()
        data = r.json() or {}
    except Exception as e:
        logger.exception("openalex_search invalid response: %s", e)
        return [], 0

    works = data.get("results") or []
    meta = data.get("meta") or {}
    total = int(meta.get("count") or 0)

    papers: List[Paper] = []

    for w in works:
        openalex_id = (w.get("id") or "").split("/")[-1]
        title = (w.get("title") or w.get("display_name") or "").strip()

        year_raw = w.get("publication_year")
        try:
            year = int(year_raw) if year_raw is not None else None
        except Exception:
            year = None

        doi = _normalize_doi(w.get("doi"))
        url = ((w.get("primary_location") or {}).get("landing_page_url")) or w.get("id")
        journal = (((w.get("primary_location") or {}).get("source") or {}).get("display_name") or "").strip()

        concepts = [
            str(c.get("display_name")).strip()
            for c in (w.get("concepts") or [])
            if c.get("display_name")
        ]

        abstract = (w.get("abstract") or "").strip()
        if not abstract:
            abstract = _openalex_abstract_from_inverted_index(
                w.get("abstract_inverted_index") or {}
            )

        papers.append(
            Paper(
                id=openalex_id,
                source="openalex",
                title=title,
                authors=[
                    ((a or {}).get("author") or {}).get("display_name")
                    for a in (w.get("authorships") or [])
                    if ((a or {}).get("author") or {}).get("display_name")
                ],
                journal=journal,
                year=year,
                abstract=abstract or None,
                doi=doi,
                url=url,
                mesh_terms=[],
                concepts=concepts,
                pmcid=None,
                has_full_text=False,
            )
        )

    return papers, total

def openalex_fetch_detail(work_id: str) -> Paper | None:
    wid = (work_id or "").strip()
    if not wid:
        return None

    wid_short = _openalex_short_id(wid)
    if not wid_short:
        return None

    params = {"mailto": CONTACT_EMAIL} if CONTACT_EMAIL else None

    try:
        r = requests.get(
            f"{BASE_URL}{SEARCH_ENDPOINT}/{wid_short}",
            params=params,
            timeout=(10, 30),
            headers={"User-Agent": _user_agent()},
        )
        if r.status_code == 404:
            return None
        if r.status_code == 429:
            logger.warning("openalex_fetch_detail rate limited (429) wid=%s url=%s", wid_short, getattr(r, "url", ""))
            return None
        r.raise_for_status()
        w = r.json() or {}
    except Exception:
        logger.exception("openalex_fetch_detail failed work_id=%r", work_id)
        return None

    openalex_id_full = (w.get("id") or wid)
    openalex_id_short = _openalex_short_id(openalex_id_full)

    journal = _journal_name(w)

    year_raw = w.get("publication_year")
    try:
        year = int(year_raw) if year_raw is not None else None
    except Exception:
        year = None

    abstract = (w.get("abstract") or "").strip()

    if not abstract:
        inv = w.get("abstract_inverted_index")
        if inv:
            abstract = _openalex_abstract_from_inverted_index(inv)

    title = (w.get("title") or w.get("display_name") or "").strip()

    concepts = [
        str(c.get("display_name")).strip()
        for c in (w.get("concepts") or [])
        if c.get("display_name")
    ]

    return Paper(
        id=openalex_id_short,
        source="openalex",
        title=title,
        authors=_extract_authors(w),
        journal=journal,
        year=year,
        abstract=abstract or None,
        doi=_normalize_doi(w.get("doi")),
        url=_landing_url(w),
        mesh_terms=[],
        concepts=concepts,
        pmcid=None,
        has_full_text=False,
    )