# app/connectors/europe_pmc.py
from __future__ import annotations

import logging
import os
import re
import time
from typing import Any, Optional

import requests

from app.models.paper import Paper

logger = logging.getLogger("litsearch.connector.europe_pmc")

EUROPE_PMC_SEARCH_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
DEFAULT_TIMEOUT_SECONDS = 20.0

TOOL_NAME = os.getenv("TOOL_NAME", "LitSearch")
CONTACT_EMAIL = (os.getenv("CONTACT_EMAIL") or "").strip()
USER_AGENT = f"{TOOL_NAME}/0.1" + (f" (mailto:{CONTACT_EMAIL})" if CONTACT_EMAIL else "")

DEFAULT_RESULT_TYPE = "core"
MAX_PAGE_SIZE = 1000


class EuropePmcTemporaryError(Exception):
    """Tijdelijke fout vanuit Europe PMC, zoals timeout of 5xx."""
    pass


def _clean_year(v: Any) -> int | None:
    s = str(v or "").strip()
    m = re.search(r"\b(\d{4})\b", s)
    return int(m.group(1)) if m else None


def _parse_authors(author_string: str) -> list[str]:
    s = (author_string or "").strip()
    if not s:
        return []
    return [p.strip() for p in s.split(",") if p.strip()]


def _normalize_mesh(mesh: str) -> str:
    raw = (mesh or "").strip()
    if not raw:
        return ""
    parts = [p.strip() for p in re.split(r"[|,]+", raw) if p.strip()]
    seen: set[str] = set()
    out: list[str] = []
    for p in parts:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return "|".join(out)


def _canonical_epmc_url(pmid: str, pmcid: str, identifier: str) -> str:
    if pmcid:
        pmcid2 = pmcid.upper()
        pmcid2 = pmcid2[3:] if pmcid2.startswith("PMC") else pmcid2
        return f"https://europepmc.org/article/PMC/{pmcid2}"
    if pmid and pmid.isdigit():
        return f"https://europepmc.org/article/MED/{pmid}"
    if identifier:
        return f"https://europepmc.org/search?query={identifier}"
    return "https://europepmc.org/"


def _first_fulltext_url_json(item: dict) -> str:
    ftl = item.get("fullTextUrlList")
    if isinstance(ftl, dict):
        ftl = ftl.get("fullTextUrl") or ftl.get("fullTextUrlList")
    if not ftl:
        return ""
    if isinstance(ftl, list) and ftl:
        u = (ftl[0].get("url") or "").strip()
        return u
    return ""


def _map_epmc_sort(sort: str) -> str | None:
    return None


def _build_epmc_query(
    q: str,
    *,
    year_min: int | None = None,
    year_max: int | None = None,
    has_abstract: int = 0,
    mesh: str = "",
) -> str:
    q = (q or "").strip()
    if not q:
        return ""

    parts: list[str] = [f"({q})"]

    try:
        y_min = int(year_min) if year_min not in (None, "") else None
    except Exception:
        y_min = None

    try:
        y_max = int(year_max) if year_max not in (None, "") else None
    except Exception:
        y_max = None

    if y_min is not None or y_max is not None:
        if y_min is None:
            y_min = 1000
        if y_max is None:
            y_max = 3000
        if y_min > y_max:
            y_min, y_max = y_max, y_min
        parts.append(f"PUB_YEAR:[{y_min} TO {y_max}]")

    if int(has_abstract or 0) == 1:
        parts.append("HAS_ABSTRACT:Y")

    mesh_norm = _normalize_mesh(mesh)
    if mesh_norm:
        mesh_terms = [t for t in mesh_norm.split("|") if t.strip()]
        if mesh_terms:
            mesh_q = " OR ".join([f'MESH:"{term}"' for term in mesh_terms])
            parts.append(f"({mesh_q})")

    return " AND ".join(parts)


def _map_result_json_to_paper(item: dict) -> Paper:
    pmid = str(item.get("pmid") or "").strip()
    pmcid = str(item.get("pmcid") or "").strip()
    epmc_id = str(item.get("id") or "").strip()

    identifier = pmid or pmcid or epmc_id or ""
    landing_url = _canonical_epmc_url(pmid, pmcid, identifier)

    title = str(item.get("title") or "").strip()
    author_string = str(item.get("authorString") or "").strip()
    journal = str(item.get("journalTitle") or "").strip()
    pub_year = item.get("pubYear")
    doi = str(item.get("doi") or "").strip()
    abstract = str(item.get("abstractText") or "").strip()

    is_open_access = str(item.get("isOpenAccess") or "").strip()
    ft_url = _first_fulltext_url_json(item)
    has_full_text = (is_open_access == "Y") or bool(pmcid)

    return Paper(
        id=identifier,
        source="europe_pmc",
        title=title,
        authors=_parse_authors(author_string),
        journal=journal,
        year=_clean_year(pub_year),
        doi=doi or None,
        pmcid=pmcid or None,
        abstract=abstract or None,
        url=(ft_url or landing_url),
        mesh_terms=[],
        has_full_text=has_full_text,
    )


def europe_pmc_search(
    q: str,
    *,
    page: int = 1,
    n: int = 10,
    cursor: Optional[str] = None,
    sort: str = "relevance",
    year_min: int | None = None,
    year_max: int | None = None,
    has_abstract: int = 0,
    mesh: str = "",
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    retries: int = 2,
) -> tuple[list[Paper], int, Optional[str]]:
    q = (q or "").strip()
    if not q:
        return [], 0, None

    epmc_query = _build_epmc_query(
        q,
        year_min=year_min,
        year_max=year_max,
        has_abstract=has_abstract,
        mesh=mesh,
    )
    if not epmc_query:
        return [], 0, None

    page_size = max(1, min(int(n), 100))
    cursor_mark = (cursor or "").strip() or None

    params: dict[str, Any] = {
        "query": epmc_query,
        "format": "json",
        "resultType": DEFAULT_RESULT_TYPE,
        "pageSize": str(page_size),
    }

    if cursor_mark:
        params["cursorMark"] = cursor_mark

    mapped_sort = _map_epmc_sort(sort)
    if mapped_sort:
        params["sort"] = mapped_sort

    headers = {
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    }

    last_exc: Exception | None = None

    for attempt in range(retries + 1):
        try:
            logger.info(
                "epmc_request q=%r query=%r sort_in=%r sort_mapped=%r cursor=%r params=%r attempt=%s/%s",
                q,
                epmc_query,
                sort,
                mapped_sort,
                cursor_mark[:40] if cursor_mark else None,
                params,
                attempt + 1,
                retries + 1,
            )

            r = requests.get(
                EUROPE_PMC_SEARCH_URL,
                params=params,
                headers=headers,
                timeout=timeout_seconds,
            )
            r.raise_for_status()

            data = r.json() if r.content else {}

            if "hitCount" not in data and "resultList" not in data:
                logger.warning(
                    "epmc_unexpected_payload q=%r query=%r sort_in=%r sort_mapped=%r url=%s first=%r",
                    q,
                    epmc_query,
                    sort,
                    mapped_sort,
                    r.url,
                    r.text[:500],
                )
                return [], 0, None

            total = int(data.get("hitCount") or 0)
            next_cursor = data.get("nextCursorMark") or None

            results = data.get("resultList", {}).get("result", [])
            if not isinstance(results, list):
                results = []

            papers = [_map_result_json_to_paper(item) for item in results if isinstance(item, dict)]

            logger.info(
                "epmc_search_ok q=%r sort_in=%r sort_mapped=%r page=%s cursor_in=%r total=%s returned=%s next_cursor=%r",
                q,
                sort,
                mapped_sort,
                page,
                cursor_mark[:40] if cursor_mark else None,
                total,
                len(papers),
                next_cursor[:40] if next_cursor else None,
            )

            return papers, total, next_cursor

        except requests.exceptions.ReadTimeout as e:
            last_exc = e
            if attempt < retries:
                sleep_s = 0.5 * (attempt + 1)
                logger.warning(
                    "epmc_timeout_retry q=%r cursor=%r attempt=%s/%s sleep_s=%.2f",
                    q,
                    cursor_mark[:40] if cursor_mark else None,
                    attempt + 1,
                    retries + 1,
                    sleep_s,
                )
                time.sleep(sleep_s)
                continue

            logger.warning(
                "epmc_timeout_final q=%r cursor=%r params=%r",
                q,
                cursor_mark[:40] if cursor_mark else None,
                params,
            )
            raise EuropePmcTemporaryError("Europe PMC timed out") from e

        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if e.response is not None else None

            if status_code in {429, 500, 502, 503, 504}:
                last_exc = e
                if attempt < retries:
                    sleep_s = 0.75 * (attempt + 1)
                    logger.warning(
                        "epmc_http_retry status=%r q=%r cursor=%r attempt=%s/%s sleep_s=%.2f",
                        status_code,
                        q,
                        cursor_mark[:40] if cursor_mark else None,
                        attempt + 1,
                        retries + 1,
                        sleep_s,
                    )
                    time.sleep(sleep_s)
                    continue

                logger.warning(
                    "epmc_http_temporary_failure status=%r q=%r cursor=%r params=%r",
                    status_code,
                    q,
                    cursor_mark[:40] if cursor_mark else None,
                    params,
                )
                raise EuropePmcTemporaryError(
                    f"Europe PMC temporary failure (HTTP {status_code})"
                ) from e

            logger.exception(
                "Europe PMC non-retryable HTTP error q=%r cursor=%r params=%r status=%r",
                epmc_query,
                cursor_mark,
                params,
                status_code,
            )
            raise

        except requests.exceptions.RequestException as e:
            last_exc = e
            if attempt < retries:
                sleep_s = 0.5 * (attempt + 1)
                logger.warning(
                    "epmc_request_retry q=%r cursor=%r attempt=%s/%s sleep_s=%.2f error=%s",
                    q,
                    cursor_mark[:40] if cursor_mark else None,
                    attempt + 1,
                    retries + 1,
                    sleep_s,
                    type(e).__name__,
                )
                time.sleep(sleep_s)
                continue

            logger.warning(
                "epmc_request_final_failure q=%r cursor=%r params=%r error=%s",
                q,
                cursor_mark[:40] if cursor_mark else None,
                params,
                type(e).__name__,
            )
            raise EuropePmcTemporaryError("Europe PMC request failed") from e

        except Exception as e:
            logger.exception(
                "Europe PMC unexpected failure q=%r cursor=%r params=%r",
                epmc_query,
                cursor_mark,
                params,
            )
            raise

    raise last_exc or RuntimeError("Europe PMC search failed unexpectedly")


def europe_pmc_fetch_detail(
    pid: str,
    *,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> Paper | None:
    pid = (pid or "").strip()
    if not pid:
        return None

    pid_u = pid.upper()
    if pid.isdigit():
        query = f"EXT_ID:{pid} SRC:MED"
    elif pid_u.startswith("PMC"):
        query = f"PMCID:{pid_u}"
    else:
        query = f"ID:{pid}"

    params: dict[str, Any] = {
        "query": query,
        "resultType": DEFAULT_RESULT_TYPE,
        "format": "json",
        "pageSize": "1",
        "cursorMark": "*",
    }

    headers = {
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    }

    try:
        r = requests.get(
            EUROPE_PMC_SEARCH_URL,
            params=params,
            headers=headers,
            timeout=timeout_seconds,
        )
        r.raise_for_status()
        data = r.json() if r.content else {}
        results = data.get("resultList", {}).get("result", [])
        if isinstance(results, list) and results:
            first = results[0]
            if isinstance(first, dict):
                return _map_result_json_to_paper(first)
        return None
    except Exception:
        logger.exception("Europe PMC detail fetch failed pid=%r", pid)
        return None