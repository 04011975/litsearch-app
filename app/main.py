# app/main.py
from __future__ import annotations

import csv
import io

import math
import os
import re
import secrets
import time
import uuid
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Iterable, List, Optional, Tuple
from urllib.parse import urlencode, quote

from openpyxl import Workbook

import anyio
import redis as redis_sync  # sync redis-py client for Europe PMC cursor hash cache
from arq.connections import ArqRedis, RedisSettings, create_pool
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)
from fastapi.templating import Jinja2Templates

from app.connectors.europe_pmc import europe_pmc_fetch_detail, europe_pmc_search, EuropePmcTemporaryError
from app.connectors.openalex import openalex_fetch_detail, openalex_search
from app.connectors.pubmed import build_pubmed_term, pubmed_fetch_details, pubmed_search_page

from app.connectors.semantic_scholar import (
    SemanticScholarError,
    fetch_semantic_scholar_detail,
    search_semantic_scholar,
    search_semantic_scholar_bulk,
)

from app.jobs.epmc_tasks import epmc_build_key, epmc_cache_key
from app.models.paper import Paper
from app.redis_client import make_redis
from app.services.redis_policy import cache_get_json, cache_set_json, make_cache_key, rate_limit_sliding_window
from app.specializations import get_source_info

from app.core.deduplication import deduplicate_papers

from datetime import datetime

from app.all_sources import (
    all_year_value,
    all_title_value,
    interleave_by_source,
    build_all_source_results,
)


# =========================================================
# Small helpers
# =========================================================

def _as_str(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, (bytes, bytearray, memoryview)):
        return bytes(v).decode("utf-8", errors="ignore").strip()
    return str(v).strip()


def _build_url(path: str, params: dict[str, Any] | None = None) -> str:
    if not params:
        return path
    clean: dict[str, Any] = {}
    for k, v in params.items():
        if v is None:
            continue
        if isinstance(v, str) and v == "":
            continue
        clean[str(k)] = v
    qs = urlencode(clean, doseq=True, quote_via=quote)
    return f"{path}?{qs}" if qs else path


def _tenant_id(request: Request) -> str:
    return request.headers.get("X-Tenant-Id") or (request.client.host if request.client else "anon") or "anon"


async def _run_sync(fn: Callable, *args, **kwargs):
    return await anyio.to_thread.run_sync(lambda: fn(*args, **kwargs))

def _extract_concept_suggestions(papers: Iterable[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    for p in papers:
        concepts = p.get("concepts") or []
        if isinstance(concepts, str):
            concepts = [concepts]
        for c in concepts:
            c2 = str(c).strip()
            if c2:
                counter[c2] += 1
    return [{"term": term, "count": count} for term, count in counter.most_common(limit)]


# =========================================================
# Configuration
# =========================================================

load_dotenv()

APP_VERSION = "0.1.0"

DEBUG_ENDPOINTS = os.getenv("DEBUG_ENDPOINTS", "0") == "1"

NCBI_API_KEY = (os.getenv("NCBI_API_KEY") or "").strip() or None
TOOL_NAME = (os.getenv("TOOL_NAME") or "LitSearch").strip()
CONTACT_EMAIL = (os.getenv("CONTACT_EMAIL") or "").strip() or None

REDIS_URL = (os.getenv("REDIS_URL") or "").strip() or None

EUROPE_PMC_MAX_PAGES = int(os.getenv("EUROPE_PMC_MAX_PAGES", "200"))
EUROPE_PMC_CURSOR_TTL_SECONDS = int(os.getenv("EUROPE_PMC_CURSOR_TTL_SECONDS", "86400"))

# Export config
EXPORT_DIR = os.getenv("EXPORT_DIR", "/app/exports")
EXPORT_HARD_CAP = int(os.getenv("EXPORT_HARD_CAP", "2000"))

# Bulk default + UI/endpoint cap
BULK_EXPORT_DEFAULT = int(os.getenv("BULK_EXPORT_DEFAULT", "500"))
BULK_EXPORT_LIMIT = int(os.getenv("BULK_EXPORT_LIMIT", str(BULK_EXPORT_DEFAULT)))
BULK_EXPORT_LIMIT = max(1, min(BULK_EXPORT_LIMIT, EXPORT_HARD_CAP))

PUBMED_MAX_PAGEABLE_RESULTS = 10_000
OPENALEX_BASIC_PAGING_LIMIT = 10_000
OPENALEX_CACHE_TTL_S = 600
OPENALEX_TENANT_RPM = 60
OPENALEX_GLOBAL_RPM = 600
SEMANTIC_SCHOLAR_CACHE_TTL_S = 600

ALLOWED_SOURCES = {"pubmed", "europe_pmc", "openalex", "semantic_scholar", "all"}
SOURCE_PATTERN = "^(" + "|".join(ALLOWED_SOURCES) + ")$"

if not CONTACT_EMAIL:
    print(
        "⚠️ WARNING: CONTACT_EMAIL is not set. "
        "NCBI strongly recommends providing a contact email for PubMed API usage."
    )
    

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


# =========================================================
# Logging + App
# =========================================================

import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    stream=sys.stdout,
    format="%(levelname)s %(name)s %(message)s",
)

logger = logging.getLogger("litsearch.main")

app = FastAPI(title="LitSearch", version=APP_VERSION)


# =========================================================
# Source configuration
# =========================================================
SOURCE_SPECIALIZATIONS = {
    "pubmed": {
        "label": "PubMed",
        "role": "Primary biomedical literature database",
        "specialization": "Curated biomedical and life sciences literature with MeSH indexing.",
        "search_mode": "MeSH-supported search with controlled biomedical indexing.",
        "strengths": [
            "MeSH controlled vocabulary",
            "high-quality biomedical indexing",
            "strong clinical coverage",
        ],
        "limitations": [
            "10,000 result pagination cap",
            "limited full-text metadata",
        ],
    },

    "europe_pmc": {
        "label": "Europe PMC",
        "role": "Full-text biomedical literature repository",
        "specialization": "Biomedical literature with strong integration of full-text and preprints.",
        "search_mode": "Keyword-based search with cursor-based pagination and strong full-text coverage.",
        "strengths": [
            "open-access full text",
            "preprint coverage",
            "grant links",
        ],
        "limitations": [
            "cursor-based pagination",
            "metadata variability",
        ],
    },

    "openalex": {
        "label": "OpenAlex",
        "role": "Global scholarly knowledge graph",
        "specialization": "Cross-disciplinary research graph with citation networks.",
        "search_mode": "Keyword-based search with concept-based refinement across disciplines.",
        "strengths": [
            "citation graph",
            "interdisciplinary coverage",
            "concept extraction",
        ],
        "limitations": [
            "abstract coverage varies",
            "basic pagination limits",
        ],
    },

    "semantic_scholar": {
        "label": "Semantic Scholar",
        "role": "AI-enhanced research discovery engine",
        "specialization": "Large scholarly corpus with ML-derived metadata and citation networks.",
        "search_mode": "Keyword-based search only; MeSH filtering is not available for this source.",
        "strengths": [
            "AI-enhanced metadata",
            "strong computer science coverage",
            "citation graph",
        ],
        "limitations": [
            "no MeSH indexing",
            "metadata heterogeneity",
        ],
    },

        "all": {
        "label": "All sources",
        "role": "Multi-source literature retrieval",
        "specialization": "Combined export across PubMed, Europe PMC, OpenAlex, and Semantic Scholar.",
        "search_mode": "Multi-source export mode. Browser search results are not combined yet.",
        "strengths": [
            "broader coverage across multiple scholarly databases",
            "cross-source deduplication during export",
            "single export workflow",
        ],
        "limitations": [
            "currently available for async export only",
            "browser result listing is not yet combined",
        ],
    },
}


# =========================================================
# Redis (sync cache) + ARQ (async jobs)
# =========================================================

ARQ_REDIS: ArqRedis | None = None
_redis: redis_sync.Redis | None = None  # sync redis for Europe PMC cursor cache


def _redis_client() -> redis_sync.Redis | None:
    if not REDIS_URL:
        return None
    try:
        r = redis_sync.from_url(REDIS_URL, decode_responses=True)
        r.ping()
        return r
    except Exception:
        logger.exception("Sync Redis not available (continuing without cursor cache)")
        return None


@app.on_event("startup")
async def on_startup() -> None:
    global ARQ_REDIS, _redis

    # async redis (rate limiting + json cache)
    app.state.redis = make_redis()

    # sync redis for EPMC cursor hash cache
    _redis = _redis_client()

    # ARQ pool
    if REDIS_URL:
        try:
            ARQ_REDIS = await create_pool(RedisSettings.from_dsn(REDIS_URL))
        except Exception:
            logger.exception("Failed creating ARQ redis pool")
            ARQ_REDIS = None

    try:
        os.makedirs(EXPORT_DIR, exist_ok=True)
    except Exception:
        logger.exception("Failed to create export dir: %s", EXPORT_DIR)


@app.on_event("shutdown")
async def on_shutdown() -> None:
    global ARQ_REDIS, _redis

    # close async redis
    try:
        r = getattr(app.state, "redis", None)
        if r is not None:
            await r.close()
            try:
                await r.connection_pool.disconnect(inuse_connections=True)
            except TypeError:
                await r.connection_pool.disconnect()
    except Exception:
        logger.exception("Failed closing app.state.redis")

    # close ARQ
    try:
        if ARQ_REDIS is not None:
            await ARQ_REDIS.close()
    except Exception:
        logger.exception("Failed closing ARQ_REDIS")
    ARQ_REDIS = None

    # close sync redis
    try:
        if _redis is not None:
            _redis.close()
    except Exception:
        logger.exception("Failed closing sync redis")

@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    start = time.time()
    qp = dict(request.query_params)

    try:
        response = await call_next(request)
        ms = int((time.time() - start) * 1000)
        logger.info(
            "HTTP %s %s status=%s ms=%s source=%s q=%r page=%s n=%s sort=%s cursor=%r",
            request.method,
            request.url.path,
            response.status_code,
            ms,
            qp.get("source", ""),
            qp.get("q", ""),
            qp.get("page", ""),
            qp.get("n", ""),
            qp.get("sort", ""),
            qp.get("cursor", ""),
        )
        return response
    except HTTPException:
        raise
    except Exception:
        ms = int((time.time() - start) * 1000)
        logger.exception("HTTP %s %s FAILED ms=%s qp=%r", request.method, request.url.path, ms, qp)
        return PlainTextResponse("Internal Server Error (see logs)", status_code=500)


# =========================================================
# Helpers (Europe PMC cursor cache) - CHUNK BASED (FILTER-AWARE)
# =========================================================

EPMC_CHUNK_SIZE = int(os.getenv("EUROPE_PMC_BUILD_PAGE_SIZE", "500"))  # must match epmc_tasks.py
EPMC_PAGE_CAP = int(os.getenv("EUROPE_PMC_CONNECTOR_PAGE_CAP", "100"))  # connector cap (keep in sync)


def _epmc_ui_offset(page: int, n: int) -> int:
    return (max(1, int(page)) - 1) * max(1, int(n))


def _epmc_target_chunk(page: int, n: int) -> int:
    off = _epmc_ui_offset(page, n)
    return (off // EPMC_CHUNK_SIZE) + 1


def _epmc_in_chunk_offset(page: int, n: int) -> int:
    off = _epmc_ui_offset(page, n)
    return off % EPMC_CHUNK_SIZE


# =========================================================
# Generic helpers (no imports here!)
# =========================================================

def _safe_int(s: str | None, default: int | None = None) -> int | None:
    try:
        if s is None:
            return default
        s2 = str(s).strip()
        if s2 == "":
            return default
        return int(s2)
    except Exception:
        return default


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


def _mesh_list(mesh: str) -> list[str]:
    m = (mesh or "").strip()
    if not m:
        return []
    return [p.strip() for p in m.split("|") if p.strip()]


def _doi_url(doi: str | None) -> str:
    d = (doi or "").strip()
    if not d:
        return ""
    d = d.replace("https://doi.org/", "").replace("http://doi.org/", "")
    return f"https://doi.org/{d}"


def _pubmed_external_url(pmid: str) -> str:
    return f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"


def _europe_pmc_external_url(p: Any) -> str:
    if isinstance(p, dict):
        pid = (p.get("id") or p.get("pmid") or "").strip()
        pmcid = (p.get("pmcid") or "").strip()
    else:
        pid = (getattr(p, "id", "") or getattr(p, "pmid", "") or "").strip()
        pmcid = (getattr(p, "pmcid", "") or "").strip()

    if pmcid:
        pmcid2 = pmcid.upper()
        pmcid2 = pmcid2[3:] if pmcid2.startswith("PMC") else pmcid2
        return f"https://europepmc.org/article/PMC/{pmcid2}"

    if pid.isdigit():
        return f"https://europepmc.org/article/MED/{pid}"

    if pid:
        return f"https://europepmc.org/search?query={pid}"

    return "https://europepmc.org/"


# -------------------------
# Sorting (UI -> canonical; per-source mapping)
# -------------------------

def _normalize_sort(sort: str | None) -> str:
    s = (sort or "").strip().lower()
    if s in {"relevance", "date_desc", "date_asc"}:
        return s
    if s in {"most recent first", "recent", "newest", "latest"}:
        return "date_desc"
    if s in {"oldest first", "oldest"}:
        return "date_asc"
    if s in {"year_desc", "pub_date_desc", "pub+date"}:
        return "date_desc"
    if s in {"year_asc", "pub_date_asc"}:
        return "date_asc"
    return "relevance"


def _pubmed_sort(ui_sort: str) -> str:
    s = _normalize_sort(ui_sort)

    mapping = {
        "relevance": "relevance",
        "date_desc": "pub_date",
    }

    return mapping.get(s, "relevance")

def _openalex_sort(ui_sort: str) -> str:
    s = _normalize_sort(ui_sort)

    if s == "date_desc":
        return "publication_date:desc"

    if s == "date_asc":
        return "publication_date:asc"

    return "relevance_score:desc"

def _semantic_scholar_sort_mode(ui_sort: str) -> tuple[str, str]:
    s = _normalize_sort(ui_sort)
    if s == "date_desc":
        return "bulk", "publicationDate:desc"
    if s == "date_asc":
        return "bulk", "publicationDate:asc"
    return "relevance", "relevance"


def _paper_year_value(p: dict[str, Any] | Paper) -> int:
    if isinstance(p, dict):
        value = p.get("year") or p.get("publication_date")
    else:
        value = getattr(p, "year", None) or getattr(p, "publication_date", None)

    text = str(value or "")

    match = re.search(r"\b(19|20)\d{2}\b", text)
    if not match:
        return 0

    year = int(match.group(0))
    current_year = datetime.utcnow().year + 1

    if year < 1900 or year > current_year:
        return 0

    return year

def _paper_date_sort_key_ui(p: dict[str, Any]) -> tuple[int, str]:
    year = _paper_year_value(p)
    title = str(p.get("title") or "").lower().strip()
    return (year, title)

def _ui_relevance_score(p: dict[str, Any], q: str) -> tuple[int, int, str]:
    title = str(p.get("title") or "").lower()
    journal = str(p.get("journal") or "").lower()

    score = 0
    for term in q.lower().split():
        if term in title:
            score += 10
        if term in journal:
            score += 2

    year = _paper_year_value(p)
    return (score, year, title)


def _sort_papers_for_ui(
    papers: list[dict[str, Any]],
    sort: str,
    q: str = "",
) -> list[dict[str, Any]]:
    ui_sort = _normalize_sort(sort)

    if ui_sort == "relevance":
        return papers

    if ui_sort == "date_desc":
        return sorted(papers, key=_paper_date_sort_key_ui, reverse=True)

    if ui_sort == "date_asc":
        return sorted(papers, key=_paper_date_sort_key_ui)

    return papers

def _cap_page(page: int, total_pages: int) -> int:
    return max(1, min(int(page), max(1, int(total_pages))))


def _pagination_limits_pubmed(total_count: int, n: int) -> tuple[int, int, bool]:
    n = max(1, int(n))
    total_pages_uncapped = max(1, math.ceil(total_count / n))
    max_pageable_pages = max(1, math.ceil(PUBMED_MAX_PAGEABLE_RESULTS / n))
    total_pages_capped = min(total_pages_uncapped, max_pageable_pages)
    return total_pages_uncapped, total_pages_capped, (total_pages_uncapped != total_pages_capped)


def _pubmed_cap_warning(total_count: int) -> str:
    return (
        f"Your search returned {total_count:,} records. "
        "Due to PubMed ESearch limitations, only the first 10,000 results can be paginated via the API. "
        "Please refine your query (e.g., add terms, restrict years, apply MeSH, or enable “Abstract only”)."
    )


def _paper_to_dict(p: Paper, *, source: str) -> dict[str, Any]:
    pid = (getattr(p, "id", "") or "").strip() or (getattr(p, "pmid", "") or "").strip()

    doi = getattr(p, "doi", None)
    pmcid = (getattr(p, "pmcid", "") or "").strip()
    url = (getattr(p, "url", "") or "").strip()

    authors = getattr(p, "authors", []) or []
    if isinstance(authors, str):
        authors_list = [a.strip() for a in authors.split(",") if a.strip()]
    else:
        authors_list = [str(a).strip() for a in authors if str(a).strip()]
    authors_str = ", ".join(authors_list)

    year_val = getattr(p, "year", None)
    year_str = str(year_val) if year_val is not None else ""

    if source == "pubmed" and pid.isdigit():
        external_url = _pubmed_external_url(pid)
    elif source == "europe_pmc":
        external_url = _europe_pmc_external_url(p)
    else:
        external_url = url

    d: dict[str, Any] = {
        "source": source,
        "id": pid,
        "pmid": pid,
        "title": getattr(p, "title", "") or "",
        "authors": authors_str,
        "journal": getattr(p, "journal", "") or "",
        "year": year_str,
        "publication_date": getattr(p, "publication_date", None) or "",
        "abstract": getattr(p, "abstract", "") or "",
        "doi": doi or "",
        "mesh_terms": getattr(p, "mesh_terms", []) or [],
        "concepts": getattr(p, "concepts", []) or [],
        "pmcid": pmcid,
        "url": url,
        "publisher_url": _doi_url(doi),
        "detail_url": f"/paper/{source}/{pid}",
        "external_url": external_url,
    }

    has_full_text = bool(getattr(p, "has_full_text", False))
    if has_full_text or (pmcid and pmcid.upper().startswith("PMC")):
        d["has_full_text"] = True
        d["full_text_label"] = "Full text (PMCID)"
        d["full_text_url"] = _europe_pmc_external_url(p)

    return d


def _papers_to_csv(papers: List[Paper]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["ID", "Title", "Authors", "Journal", "Year", "DOI", "PMCID", "URL"])
    for p in papers:
        authors = getattr(p, "authors", []) or []
        if isinstance(authors, list):
            authors_str = "; ".join([str(a).strip() for a in authors if str(a).strip()])
        else:
            authors_str = str(authors)
        writer.writerow(
            [
                getattr(p, "id", "") or "",
                getattr(p, "title", "") or "",
                authors_str,
                getattr(p, "journal", "") or "",
                str(getattr(p, "year", "") or ""),
                getattr(p, "doi", "") or "",
                getattr(p, "pmcid", "") or "",
                getattr(p, "url", "") or "",
            ]
        )
    return buf.getvalue()


def _papers_to_ris(papers: List[Paper]) -> str:
    lines: list[str] = []
    for p in papers:
        pid = getattr(p, "id", "") or ""
        lines.append("TY  - JOUR")

        title = getattr(p, "title", "") or ""
        if title:
            lines.append(f"TI  - {title}")

        authors = getattr(p, "authors", []) or []
        if isinstance(authors, str):
            authors_list = [a.strip() for a in authors.split(",") if a.strip()]
        else:
            authors_list = [str(a).strip() for a in authors if str(a).strip()]
        for a in authors_list:
            lines.append(f"AU  - {a}")

        journal = getattr(p, "journal", "") or ""
        if journal:
            lines.append(f"JO  - {journal}")

        year_val = getattr(p, "year", None)
        if year_val is not None:
            lines.append(f"PY  - {year_val}")

        doi = getattr(p, "doi", None)
        if doi:
            lines.append(f"DO  - {doi}")

        abstract = getattr(p, "abstract", None)
        if abstract:
            lines.append(f"AB  - {abstract}")

        pmcid = getattr(p, "pmcid", "") or ""
        if pmcid:
            lines.append(f"AN  - {pmcid}")

        url = getattr(p, "url", "") or ""
        if url:
            lines.append(f"UR  - {url}")

        lines.append(f"ID  - {pid}")
        lines.append("ER  -")
        lines.append("")
    return "\n".join(lines)

def _papers_to_xlsx_bytes(papers: List[Paper]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Results"

    headers = ["ID", "Title", "Authors", "Journal", "Year", "DOI", "PMCID", "URL"]
    ws.append(headers)

    for p in papers:
        authors = getattr(p, "authors", []) or []
        if isinstance(authors, list):
            authors_str = "; ".join(str(a).strip() for a in authors if str(a).strip())
        else:
            authors_str = str(authors)

        ws.append(
            [
                getattr(p, "id", "") or "",
                getattr(p, "title", "") or "",
                authors_str,
                getattr(p, "journal", "") or "",
                getattr(p, "year", "") or "",
                getattr(p, "doi", "") or "",
                getattr(p, "pmcid", "") or "",
                getattr(p, "url", "") or "",
            ]
        )

    # eenvoudige breedtes
    widths = {
        "A": 18,
        "B": 60,
        "C": 40,
        "D": 28,
        "E": 10,
        "F": 24,
        "G": 18,
        "H": 50,
    }
    for col, width in widths.items():
        ws.column_dimensions[col].width = width

    # header vet
    for cell in ws[1]:
        cell.font = cell.font.copy(bold=True)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()

def _extract_mesh_suggestions(papers: Iterable[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    for p in papers:
        terms = p.get("mesh_terms") or []
        if isinstance(terms, str):
            terms = [terms]
        for t in terms:
            t2 = str(t).strip()
            if t2:
                counter[t2] += 1
    return [{"term": term, "count": count} for term, count in counter.most_common(limit)]


async def _europe_pmc_search_compat_async(
    q: str,
    *,
    n: int,
    cursor: Optional[str],
    sort: str,
    year_min: int | None = None,
    year_max: int | None = None,
    has_abstract: int = 0,
    mesh: str = "",
) -> Tuple[List[Paper], int, Optional[str]]:
    return await _run_sync(
        europe_pmc_search,
        q=q,
        n=n,
        cursor=cursor,
        sort=sort,
        year_min=year_min,
        year_max=year_max,
        has_abstract=has_abstract,
        mesh=mesh,
    )


# =========================================================
# Europe PMC FILTER-AWARE cache keys
# =========================================================

def _epmc_key_filters(
    *,
    year_min: int | None = None,
    year_max: int | None = None,
    has_abstract: int = 0,
    mesh: str = "",
) -> dict[str, str]:
    ymn = "" if year_min is None else str(int(year_min))
    ymx = "" if year_max is None else str(int(year_max))
    ha = "1" if int(has_abstract or 0) else "0"
    m = _normalize_mesh(mesh or "")
    return {"year_min": ymn, "year_max": ymx, "has_abstract": ha, "mesh": m}


def _epmc_cache_key_filtered(
    q: str,
    *,
    n: int,
    sort: str,
    year_min: int | None = None,
    year_max: int | None = None,
    has_abstract: int = 0,
    mesh: str = "",
) -> str:
    return epmc_cache_key(
        q,
        n=n,
        sort=sort,
        year_min=year_min,
        year_max=year_max,
        has_abstract=has_abstract,
        mesh=mesh,
    )


def _epmc_build_key_filtered(
    q: str,
    *,
    n: int,
    sort: str,
    year_min: int | None = None,
    year_max: int | None = None,
    has_abstract: int = 0,
    mesh: str = "",
) -> str:
    return epmc_build_key(
        q,
        n=n,
        sort=sort,
        year_min=year_min,
        year_max=year_max,
        has_abstract=has_abstract,
        mesh=mesh,
    )


def _epmc_get_cursor_for_chunk(
    q: str,
    *,
    n: int,
    sort: str,
    chunk: int,
    year_min: int | None = None,
    year_max: int | None = None,
    has_abstract: int = 0,
    mesh: str = "",
) -> Optional[str]:
    if not _redis:
        return None
    try:
        key = _epmc_cache_key_filtered(
            q, n=n, sort=sort,
            year_min=year_min, year_max=year_max,
            has_abstract=has_abstract, mesh=mesh,
        )
        return _redis.hget(key, str(int(chunk)))
    except Exception:
        return None


def _epmc_set_cursor_for_chunk(
    q: str,
    *,
    n: int,
    sort: str,
    chunk: int,
    cursor: str,
    year_min: int | None = None,
    year_max: int | None = None,
    has_abstract: int = 0,
    mesh: str = "",
) -> None:
    if not _redis:
        return
    try:
        key = _epmc_cache_key_filtered(
            q, n=n, sort=sort,
            year_min=year_min, year_max=year_max,
            has_abstract=has_abstract, mesh=mesh,
        )
        pipe = _redis.pipeline()
        pipe.hset(key, str(int(chunk)), cursor)
        pipe.hsetnx(key, "chunk_size", str(int(EPMC_CHUNK_SIZE)))
        pipe.expire(key, EUROPE_PMC_CURSOR_TTL_SECONDS)
        pipe.execute()
    except Exception:
        return


async def _epmc_enqueue_build(
    q: str,
    *,
    n: int,
    sort: str,
    target_page: int,
    year_min: int | None = None,
    year_max: int | None = None,
    has_abstract: int = 0,
    mesh: str = "",
) -> None:
    if not ARQ_REDIS:
        return

    q = (q or "").strip()
    if not q:
        return

    target_page = max(1, min(int(target_page), EUROPE_PMC_MAX_PAGES))
    target_chunk = _epmc_target_chunk(target_page, n)

    bk = _epmc_build_key_filtered(
        q, n=n, sort=sort,
        year_min=year_min, year_max=year_max,
        has_abstract=has_abstract, mesh=mesh,
    )
    now = int(time.time())

    meta_raw = await ARQ_REDIS.hgetall(bk)
    meta = {_as_str(k): _as_str(v) for k, v in (meta_raw or {}).items()}
    built_up_to = int(meta.get("built_up_to_chunk") or "0")
    current_target = int(meta.get("target_chunk") or "0")

    if built_up_to >= target_chunk:
        return

    new_target = max(target_chunk, current_target)

    await ARQ_REDIS.hset(
        bk,
        mapping={
            "status": "queued",
            "target_chunk": str(new_target),
            "requested_page": str(target_page),
            "updated_at": str(now),
        },
    )
    await ARQ_REDIS.expire(bk, EUROPE_PMC_CURSOR_TTL_SECONDS)

    job_hash = _epmc_cache_key_filtered(
        q, n=n, sort=sort,
        year_min=year_min, year_max=year_max,
        has_abstract=has_abstract, mesh=mesh,
    ).split(":")[-1]

    await ARQ_REDIS.enqueue_job(
        "build_epmc_cursors",
        q=q,
        n=int(n),
        sort=sort,
        target_chunk=int(new_target),
        year_min=year_min,
        year_max=year_max,
        has_abstract=int(has_abstract or 0),
        mesh=_normalize_mesh(mesh or ""),
        _job_id=f"epmc-build:{job_hash}:chunk{new_target}",
    )


# =========================================================
# Template base context
# =========================================================

def _template_base_context(
    request: Request,
    *,
    q: str,
    source: str,
    n: int,
    page: int,
    sort: str,
    year_min: str,
    year_max: str,
    has_abstract: int,
    mesh: str,
) -> dict[str, Any]:
    return {
        "request": request,
        "q": q,
        "source": source,
        "n": n,
        "page": page,
        "sort": sort,  # UI sort token (relevance/date_desc/date_asc)
        "year_min": year_min,
        "year_max": year_max,
        "has_abstract": has_abstract,
        "mesh": mesh,
        "mesh_list": _mesh_list(mesh),
        "concept_suggestions": [],
        "bulk_limit": BULK_EXPORT_LIMIT,
        "source_info": get_source_info(source),
        "source_specializations": SOURCE_SPECIALIZATIONS,
        "allow_deep_paging": (source != "europe_pmc") or (_redis is not None),
        "epmc_next_cursor": None,
        "epmc_building": False,
        "epmc_build_status": None,
        "epmc_built_up_to": 0,
        "epmc_target_page": 0,
        "auto_refresh_seconds": None,
    }


# =========================================================
# Detail fetch by source
# =========================================================

async def _fetch_detail_by_source(source: str, pid: str) -> Paper | None:
    source = (source or "").strip()
    pid = (pid or "").strip()

    if source == "pubmed":
        if not pid.isdigit():
            return None
        papers = await pubmed_fetch_details([pid], api_key=NCBI_API_KEY, tool=TOOL_NAME, email=CONTACT_EMAIL)
        return papers[0] if papers else None

    if source == "openalex":
        # voorkom 500 als connector nog een bug heeft -> geef 404
        try:
            return await _run_sync(openalex_fetch_detail, pid)
        except Exception:
            logger.exception("OpenAlex detail failed pid=%s", pid)
            return None

    if source == "europe_pmc":
        candidates = [pid]
        pid_u = pid.upper()
        if pid_u.startswith("PMC"):
            candidates.extend([pid_u[3:], pid_u])
        elif pid.isdigit():
            candidates.append("PMC" + pid)

        for c in candidates:
            try:
                p = await _run_sync(europe_pmc_fetch_detail, c)
            except Exception:
                p = None
            if p:
                return p
        return None

    elif source == "semantic_scholar":
        return await _run_sync(fetch_semantic_scholar_detail, pid)
    return None

    
# =========================================================
# Routes
# =========================================================

if DEBUG_ENDPOINTS:

    @app.get("/debug/epmc", include_in_schema=False)
    async def debug_epmc(q: str, sort: str = "relevance"):
        papers, total, next_cursor = await _run_sync(
            europe_pmc_search,
            q=q,
            n=5,
            cursor=None,
            sort=sort,
        )
        return {
            "query": q,
            "sort": sort,
            "total": total,
            "returned": len(papers),
            "next_cursor": next_cursor,
            "titles": [getattr(p, "title", "") for p in papers[:3]],
        }
    

@app.get("/health", include_in_schema=False)
def health():
    return {"ok": True}


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/search")


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)


@app.get("/search", response_class=HTMLResponse)
async def search(
    request: Request,
    q: str = Query("", description="Query"),
    source: str = Query("pubmed", pattern=SOURCE_PATTERN),
    n: int = Query(10, ge=1, le=50),
    page: int = Query(1, ge=1),
    sort: str = Query("relevance"),
    year_min: str = Query(""),
    year_max: str = Query(""),
    has_abstract: int = Query(0, ge=0, le=1),
    mesh: str = Query(""),
    mesh_mode: str = Query("or"),
):

    logger.info(
        "SEARCH request source=%s q=%r page=%s n=%s sort=%s",
        source,
        q,
        page,
        n,
        sort,
    )

    # --------------------------
    # Normalize inputs
    # --------------------------
    q = (q or "").strip()
    mesh = _normalize_mesh(mesh)
    ui_sort = _normalize_sort(sort)

    warning: str | None = None

    year_min_i = _safe_int(year_min, None)
    year_max_i = _safe_int(year_max, None)

    if source == "europe_pmc" and ui_sort != "relevance":
        warning = "Europe PMC currently supports relevance sorting only."
        ui_sort = "relevance"

    if source == "pubmed" and ui_sort == "date_asc":
        warning = "PubMed API currently supports newest-first publication date sorting, but not oldest-first sorting in this integration."
        ui_sort = "relevance"

    pubmed_sort = _pubmed_sort(ui_sort)
    openalex_sort = _openalex_sort(ui_sort)
    ss_mode, ss_api_sort = _semantic_scholar_sort_mode(ui_sort)
    epmc_sort = ui_sort


    # --------------------------
    # All Sources
    # --------------------------
    if source == "all":
        result = await build_all_source_results(
            q=q,
            sort=ui_sort,
            limit=None,
            page=page,
            n=n,
            year_min=year_min_i,
            year_max=year_max_i,
            has_abstract=has_abstract,
            mesh=mesh,
            mesh_mode="or",
        )

        total_count = result["total_count"]
        duplicates_removed = result["duplicates_removed"]

        combined_papers = [
            _paper_to_dict(
                p,
                source=getattr(p, "source", "") or "unknown",
            )
            for p in result["all_papers"]
        ]

        paged_papers = [
            _paper_to_dict(
                p,
                source=getattr(p, "source", "") or "unknown",
            )
            for p in result["papers"]
        ]

        page_i = max(1, int(page))
        total_pages = max(1, math.ceil(total_count / int(n)))

        if page_i > total_pages:
            page_i = total_pages

        base_params = {
            "q": q,
            "source": "all",
            "n": n,
            "sort": ui_sort,
            "year_min": year_min,
            "year_max": year_max,
            "has_abstract": has_abstract,
            "mesh": mesh,
        }

        next_url = (
            _build_url("/search", {**base_params, "page": page_i + 1})
            if page_i < total_pages
            else None
        )

        last_url = (
            _build_url("/search", {**base_params, "page": total_pages})
            if total_pages > 1
            else None
        )

        ctx = _template_base_context(
            request,
            q=q,
            source="all",
            n=n,
            page=page_i,
            sort=ui_sort,
            year_min=year_min,
            year_max=year_max,
            has_abstract=has_abstract,
            mesh=mesh,
        )

        ctx.update({
            "papers": paged_papers,
            "mesh_suggestions": [],
            "concept_suggestions": [],
            "total_count": total_count,
            "total_pages": total_pages,
            "error": None,
            "warning": f"Multi-source results with DOI/title deduplication ({duplicates_removed} duplicates removed)",
            "next_url": next_url,
            "last_url": last_url,
        })

        return templates.TemplateResponse("results.html", ctx)
        

    # --------------------------
    # EUROPE PMC (cursor paging + deep paging via Redis/ARQ)
    # --------------------------
    if source == "europe_pmc":
        if not q:
            ctx = _template_base_context(
                request, q=q, source=source, n=n, page=1, sort=ui_sort,
                year_min=year_min, year_max=year_max, has_abstract=has_abstract, mesh=mesh
            )

            ctx["source_specializations"] = SOURCE_SPECIALIZATIONS
            ctx["source_info"] = SOURCE_SPECIALIZATIONS.get(source)

            ctx.update({
                "papers": [],
                "mesh_suggestions": [],
                "total_count": 0,
                "total_pages": 1,
                "error": None,
                "warning": None,
                "epmc_next_url": None,
                "epmc_last_url": None,
                "epmc_export_url_csv": None,
                "epmc_export_url_ris": None,
                "epmc_building": False,
            })
            return templates.TemplateResponse("results.html", ctx)

        year_min_i = _safe_int(year_min, None)
        year_max_i = _safe_int(year_max, None)
        has_abs_i = int(has_abstract or 0)

        page_i = max(1, min(int(page), EUROPE_PMC_MAX_PAGES))
        target_chunk = _epmc_target_chunk(page_i, n)
        in_chunk_offset = _epmc_in_chunk_offset(page_i, n)

        logger.info(
            "EUROPE PMC SEARCH request q=%r page=%s n=%s year_min=%r year_max=%r has_abstract=%r",
            q,
            page_i,
            n,
            year_min_i,
            year_max_i,
            has_abs_i,
        )        

        cursor_req = (request.query_params.get("cursor") or "").strip() or None
        cursor_used = cursor_req

        deep_paging_possible = (_redis is not None) and (ARQ_REDIS is not None)

        if not cursor_used and page_i > 1:
            cursor_ready = _epmc_get_cursor_for_chunk(
                q,
                n=n,
                sort=ui_sort,
                chunk=target_chunk,
                year_min=year_min_i,
                year_max=year_max_i,
                has_abstract=has_abs_i,
                mesh=mesh,
            )

            if cursor_ready:
                return RedirectResponse(
                    url=_build_url(
                        "/search",
                        {
                            "q": q,
                            "source": "europe_pmc",
                            "n": n,
                            "sort": ui_sort,
                            "page": page_i,
                            "cursor": cursor_ready,
                            "year_min": year_min,
                            "year_max": year_max,
                            "has_abstract": has_abstract,
                            "mesh": mesh,
                        },
                    )
                )

            if not deep_paging_possible:
                ctx = _template_base_context(
                    request, q=q, source=source, n=n, page=page_i, sort=ui_sort,
                    year_min=year_min, year_max=year_max, has_abstract=has_abstract, mesh=mesh
                )

                ctx["source_specializations"] = SOURCE_SPECIALIZATIONS
                ctx["source_info"] = SOURCE_SPECIALIZATIONS.get(source)

                ctx.update(
                    {
                        "papers": [],
                        "mesh_suggestions": [],
                        "total_count": 0,
                        "total_pages": EUROPE_PMC_MAX_PAGES,
                        "error": "Europe PMC deep paging requires Redis (cursor cache) and an ARQ worker.",
                        "warning": None,
                        "allow_deep_paging": False,
                        "epmc_building": False,
                    }
                )
                return templates.TemplateResponse("results.html", ctx)

            await _epmc_enqueue_build(
                q,
                n=n,
                sort=ui_sort,
                target_page=page_i,
                year_min=year_min_i,
                year_max=year_max_i,
                has_abstract=has_abs_i,
                mesh=mesh,
            )

            cursor_ready = _epmc_get_cursor_for_chunk(
                q,
                n=n,
                sort=ui_sort,
                chunk=target_chunk,
                year_min=year_min_i,
                year_max=year_max_i,
                has_abstract=has_abs_i,
                mesh=mesh,
            )

            if cursor_ready:
                return RedirectResponse(
                    url=_build_url(
                        "/search",
                        {
                            "q": q,
                            "source": "europe_pmc",
                            "n": n,
                            "sort": ui_sort,
                            "page": page_i,
                            "cursor": cursor_ready,
                            "year_min": year_min,
                            "year_max": year_max,
                            "has_abstract": has_abstract,
                            "mesh": mesh,
                        },
                    )
                )

            bk = _epmc_build_key_filtered(
                q,
                n=n,
                sort=ui_sort,
                year_min=year_min_i,
                year_max=year_max_i,
                has_abstract=has_abs_i,
                mesh=mesh,
            )
            meta_raw = await ARQ_REDIS.hgetall(bk)
            meta = {_as_str(k): _as_str(v) for k, v in (meta_raw or {}).items()}
            build_status = meta.get("status") or "queued"
            built_up_to_chunk = int(meta.get("built_up_to_chunk") or "0")

            ctx = _template_base_context(
                request, q=q, source=source, n=n, page=page_i, sort=ui_sort,
                year_min=year_min, year_max=year_max, has_abstract=has_abstract, mesh=mesh
            )

            ctx["source_specializations"] = SOURCE_SPECIALIZATIONS
            ctx["source_info"] = SOURCE_SPECIALIZATIONS.get(source)

            ctx.update(
                {
                    "papers": [],
                    "mesh_suggestions": [],
                    "total_count": 0,
                    "total_pages": EUROPE_PMC_MAX_PAGES,
                    "error": None,
                    "warning": None,
                    "allow_deep_paging": True,
                    "epmc_building": True,
                    "epmc_build_status": build_status,
                    "epmc_built_up_to": built_up_to_chunk,
                    "epmc_target_page": page_i,
                    "auto_refresh_seconds": 2,
                }
            )
            return templates.TemplateResponse("results.html", ctx)

        want_end = in_chunk_offset + int(n)
        to_collect = min(EPMC_CHUNK_SIZE, max(want_end, EPMC_PAGE_CAP))

        collected: list[Paper] = []
        start_cursor = cursor_used or "*"
        cur = start_cursor
        total_count = 0
        next_cursor = None

        epmc_temp_warning = None

        while len(collected) < to_collect and cur:
            step = min(EPMC_PAGE_CAP, to_collect - len(collected))

            try:
                batch, total_count, nxt = await _europe_pmc_search_compat_async(
                    q,
                    n=step,
                    cursor=cur,
                    sort=ui_sort,
                    year_min=year_min_i,
                    year_max=year_max_i,
                    has_abstract=has_abs_i,
                    mesh=mesh,
                )
            except EuropePmcTemporaryError as exc:
                logger.warning(
                    "EUROPE PMC SEARCH temporary failure q=%r page=%s cursor=%r error=%s",
                    q,
                    page_i,
                    cur[:40] if cur else None,
                    str(exc),
                )
                epmc_temp_warning = (
                    "Europe PMC is tijdelijk traag of onbeschikbaar. "
                    "Probeer deze pagina opnieuw."
                )
                break

            if not batch:
                break

            collected.extend(batch)
            next_cursor = nxt
            if not next_cursor:
                break
            cur = next_cursor

        _epmc_set_cursor_for_chunk(
            q,
            n=n,
            sort=ui_sort,
            chunk=target_chunk,
            cursor=start_cursor,
            year_min=year_min_i,
            year_max=year_max_i,
            has_abstract=has_abs_i,
            mesh=mesh,
        )
        if next_cursor:
            _epmc_set_cursor_for_chunk(
                q,
                n=n,
                sort=ui_sort,
                chunk=target_chunk + 1,
                cursor=next_cursor,
                year_min=year_min_i,
                year_max=year_max_i,
                has_abstract=has_abs_i,
                mesh=mesh,
            )

        ep_papers = (collected or [])[in_chunk_offset: in_chunk_offset + int(n)]
        papers = [_paper_to_dict(p, source="europe_pmc") for p in ep_papers]

        logger.info(
            "EUROPE PMC SEARCH success q=%r page=%s results=%s total=%s",
            q,
            page_i,
            len(papers),
            total_count,
        )        

        if epmc_temp_warning:
            warning = epmc_temp_warning
        elif page_i == 1 and int(total_count or 0) == 0:
            warning = "Europe PMC returned 0 results for this query."
        elif page_i > 1 and not ep_papers:
            warning = f"Europe PMC returned an empty page for page {page_i}. Cursor chain may be stale or incomplete."
        else:
            warning = None

        total_pages_raw = max(1, math.ceil(max(0, int(total_count or 0)) / max(1, int(n))))
        total_pages = min(total_pages_raw, EUROPE_PMC_MAX_PAGES)

        epmc_next_url = None
        if page_i < total_pages:
            next_page = page_i + 1
            next_chunk = _epmc_target_chunk(next_page, n)
            if next_chunk == target_chunk:
                epmc_next_url = _build_url(
                    "/search",
                    {
                        "q": q,
                        "source": "europe_pmc",
                        "n": n,
                        "sort": ui_sort,
                        "page": next_page,
                        "cursor": start_cursor,
                        "year_min": year_min,
                        "year_max": year_max,
                        "has_abstract": has_abstract,
                        "mesh": mesh,
                    },
                )
            elif next_cursor:
                epmc_next_url = _build_url(
                    "/search",
                    {
                        "q": q,
                        "source": "europe_pmc",
                        "n": n,
                        "sort": ui_sort,
                        "page": next_page,
                        "cursor": next_cursor,
                        "year_min": year_min,
                        "year_max": year_max,
                        "has_abstract": has_abstract,
                        "mesh": mesh,
                    },
                )

        epmc_last_url = (
            _build_url(
                "/search",
                {
                    "q": q,
                    "source": "europe_pmc",
                    "n": n,
                    "sort": ui_sort,
                    "page": total_pages,
                    "year_min": year_min,
                    "year_max": year_max,
                    "has_abstract": has_abstract,
                    "mesh": mesh,
                },
            )
            if total_pages > 1
            else None
        )

        epmc_export_url_csv = _build_url(
            "/export/csv",
            {
                "q": q,
                "source": "europe_pmc",
                "scope": "page",
                "page": page_i,
                "n": n,
                "sort": ui_sort,
                "cursor": start_cursor,
                "year_min": year_min,
                "year_max": year_max,
                "has_abstract": has_abstract,
                "mesh": mesh,
            },
        )
        epmc_export_url_ris = _build_url(
            "/export/ris",
            {
                "q": q,
                "source": "europe_pmc",
                "scope": "page",
                "page": page_i,
                "n": n,
                "sort": ui_sort,
                "cursor": start_cursor,
                "year_min": year_min,
                "year_max": year_max,
                "has_abstract": has_abstract,
                "mesh": mesh,
            },
        )

        ctx = _template_base_context(
            request, q=q, source=source, n=n, page=page_i, sort=ui_sort,
            year_min=year_min, year_max=year_max, has_abstract=has_abstract, mesh=mesh
        )

        ctx["source_specializations"] = SOURCE_SPECIALIZATIONS
        ctx["source_info"] = SOURCE_SPECIALIZATIONS.get(source)

        ctx.update({
            "papers": papers,
            "mesh_suggestions": [],
            "total_count": int(total_count or 0),
            "total_pages": total_pages,
            "error": None,
            "warning": warning,
            "allow_deep_paging": deep_paging_possible,
            "epmc_building": False,
            "epmc_next_url": epmc_next_url,
            "epmc_last_url": epmc_last_url,
            "epmc_export_url_csv": epmc_export_url_csv,
            "epmc_export_url_ris": epmc_export_url_ris,
        })
        return templates.TemplateResponse("results.html", ctx)


    # --------------------------
    # OPENALEX
    # --------------------------
    if source == "openalex":
        logger.info(
            "OPENALEX SEARCH request q=%r page=%s n=%s sort=%s year_min=%r year_max=%r",
            q,
            page,
            n,
            ui_sort,
            year_min,
            year_max,
        ) 
                              
        if not q:
            ctx = _template_base_context(
                request, q=q, source="openalex", n=n, page=1, sort=ui_sort,
                year_min=year_min, year_max=year_max, has_abstract=has_abstract, mesh=mesh
            )

            ctx["source_specializations"] = SOURCE_SPECIALIZATIONS
            ctx["source_info"] = SOURCE_SPECIALIZATIONS.get(source)

            ctx.update({
                "papers": [],
                "mesh_suggestions": [],
                "total_count": 0,
                "total_pages": 1,
                "error": None,
                "warning": None,
                "next_url": None,
                "last_url": None,
            })
            return templates.TemplateResponse("results.html", ctx)

        redis = getattr(request.app.state, "redis", None)
        tenant_id = _tenant_id(request)
        ok_tenant = True
        ok_global = True

        if redis is not None:
            ok_tenant = await rate_limit_sliding_window(
                redis,
                f"rl:openalex:tenant:{tenant_id}",
                OPENALEX_TENANT_RPM,
                60,
            )
            ok_global = await rate_limit_sliding_window(
                redis,
                "rl:openalex:global",
                OPENALEX_GLOBAL_RPM,
                60,
            )
        
        if not (ok_tenant and ok_global):
            ctx = _template_base_context(
                request, q=q, source="openalex", n=n, page=1, sort=ui_sort,
                year_min=year_min, year_max=year_max, has_abstract=has_abstract, mesh=mesh
            )

            ctx["source_specializations"] = SOURCE_SPECIALIZATIONS
            ctx["source_info"] = SOURCE_SPECIALIZATIONS.get(source)

            ctx.update({"papers": [], "mesh_suggestions": [], "total_count": 0, "total_pages": 1,
                        "error": None, "warning": "OpenAlex rate limit reached. Please retry shortly.",
                        "next_url": None, "last_url": None})
            return templates.TemplateResponse("results.html", ctx)

        per_page = max(1, int(n))
        fetch_n = per_page

        year_min_i = _safe_int(year_min, None)
        year_max_i = _safe_int(year_max, None)

        ck_meta = make_cache_key(
            "cache:openalex:meta",
            {"q": q, "n": per_page, "sort": ui_sort, "year_min": year_min_i, "year_max": year_max_i},
        )
        cached_meta = await cache_get_json(redis, ck_meta)
        if cached_meta and "total_count" in cached_meta:
            total_count = int(cached_meta.get("total_count") or 0)
        else:
            _p1, total_count = await _run_sync(
                openalex_search,
                q,
                page=1,
                n=fetch_n,
                sort=openalex_sort,  # mapped for API
                year_min=year_min_i,
                year_max=year_max_i,
            )
            await cache_set_json(redis, ck_meta, {"total_count": int(total_count)}, OPENALEX_CACHE_TTL_S)

        total_pages_raw = max(1, math.ceil(max(0, total_count) / per_page))
        max_basic_pages = max(1, math.ceil(OPENALEX_BASIC_PAGING_LIMIT / per_page))
        total_pages = min(total_pages_raw, max_basic_pages)

        if total_count > OPENALEX_BASIC_PAGING_LIMIT:
            warning = (
                f"OpenAlex basic paging is limited to the first {OPENALEX_BASIC_PAGING_LIMIT:,} results. "
                "Refine your query/filters or implement cursor paging for deeper results."
            )

        page_i = _cap_page(int(page), total_pages)
        if page_i != int(page):
            return RedirectResponse(
                url=_build_url(
                    "/search",
                    {"q": q, "source": "openalex", "n": n, "page": page_i, "sort": ui_sort,
                     "year_min": year_min, "year_max": year_max, "has_abstract": has_abstract, "mesh": mesh},
                )
            )

        ck_page = make_cache_key(
            "cache:openalex:page",
            {"q": q, "page": page_i, "n": per_page, "sort": ui_sort, "year_min": year_min_i, "year_max": year_max_i},
        )
        cached_page = await cache_get_json(redis, ck_page)
        cached_page = None

        logger.info(
            "OPENALEX cache page_hit=%s meta_hit=%s",
            bool(cached_page),
            bool(cached_meta),
        )       

        if cached_page and isinstance(cached_page.get("papers"), list):
            oa_papers = [Paper.from_dict(d) for d in cached_page["papers"] if isinstance(d, dict)]
        else:
            oa_papers, _ = await _run_sync(
                openalex_search,
                q,
                page=page_i,
                n=fetch_n,
                sort=openalex_sort,  # mapped for API
                year_min=year_min_i,
                year_max=year_max_i,
            )
            await cache_set_json(redis, ck_page, {"papers": [p.to_dict() for p in (oa_papers or [])]}, OPENALEX_CACHE_TTL_S)

        papers = [_paper_to_dict(p, source="openalex") for p in (oa_papers or [])]
        papers = papers[:per_page]

        logger.info(
            "OPENALEX SEARCH success q=%r page=%s results=%s total=%s",
            q,
            page_i,
            len(papers),
            total_count,
        )

        concept_suggestions = _extract_concept_suggestions(papers, limit=10)

        base_params = {"q": q, "source": "openalex", "n": n, "sort": ui_sort,
                    "year_min": year_min, "year_max": year_max, "has_abstract": has_abstract, "mesh": mesh}
        next_url = _build_url("/search", {**base_params, "page": page_i + 1}) if page_i < total_pages else None
        last_url = _build_url("/search", {**base_params, "page": total_pages}) if total_pages > 1 else None

        ctx = _template_base_context(
            request, q=q, source="openalex", n=n, page=page_i, sort=ui_sort,
            year_min=year_min, year_max=year_max, has_abstract=has_abstract, mesh=mesh
        )

        ctx["source_specializations"] = SOURCE_SPECIALIZATIONS
        ctx["source_info"] = SOURCE_SPECIALIZATIONS.get(source)

        ctx.update({
            "papers": papers,
            "mesh_suggestions": [],
            "concept_suggestions": concept_suggestions,
            "total_count": total_count,
            "total_pages": total_pages,
            "error": None,
            "warning": warning,
            "next_url": next_url,
            "last_url": last_url,
        })
        return templates.TemplateResponse("results.html", ctx)


    # --------------------------
    # SEMANTIC SCHOLAR
    # --------------------------
    if source == "semantic_scholar":
        page_i = max(1, int(page))

        has_abstract_flag = str(has_abstract).strip().lower() in {
            "1", "true", "yes", "on"
        }

        ss_year_min_i = _safe_int(year_min, None)
        ss_year_max_i = _safe_int(year_max, None)

        try:
            if ss_mode == "bulk":

                token = (request.query_params.get("token") or "").strip() or None

                ss_papers, total_count, next_token = await _run_sync(
                    search_semantic_scholar_bulk,
                    q,
                    n=n,
                    token=token,
                    sort=ss_api_sort,
                    year_min=ss_year_min_i,
                    year_max=ss_year_max_i,
                    has_abstract=has_abstract_flag,
                )
            else:
                ss_papers, total_count = await _run_sync(
                    search_semantic_scholar,
                    q,
                    page=page_i,
                    n=n,
                    year_min=ss_year_min_i,
                    year_max=ss_year_max_i,
                    has_abstract=has_abstract_flag,
                )

        except Exception as exc:
            logger.exception("Semantic Scholar search failed")

            ctx = _template_base_context(
                request,
                q=q,
                source="semantic_scholar",
                n=n,
                page=page_i,
                sort=ui_sort,
                year_min=year_min,
                year_max=year_max,
                has_abstract=has_abstract,
                mesh=mesh,
            )

            ctx.update({
                "papers": [],
                "mesh_suggestions": [],
                "concept_suggestions": [],
                "total_count": 0,
                "total_pages": 1,
                "error": str(exc),
                "warning": None,
                "next_url": None,
                "last_url": None,
            })

            return templates.TemplateResponse("results.html", ctx)

        papers = [
            _paper_to_dict(p, source="semantic_scholar")
            for p in (ss_papers or [])
        ]

        total_pages = max(1, math.ceil(int(total_count or 0) / int(n)))

        if ss_mode == "bulk":
            next_url = (
                _build_url("/search", {
                    "q": q,
                    "source": "semantic_scholar",
                    "n": n,
                    "page": page_i + 1,
                    "sort": ui_sort,
                    "token": next_token,
                    "year_min": year_min,
                    "year_max": year_max,
                    "has_abstract": has_abstract,
                })
                if next_token
                else None
            )
        else:
            next_url = (
                _build_url("/search", {
                    "q": q,
                    "source": "semantic_scholar",
                    "n": n,
                    "page": page_i + 1,
                    "sort": ui_sort,
                    "year_min": year_min,
                    "year_max": year_max,
                    "has_abstract": has_abstract,
                })
                if page_i < total_pages
                else None
            )

        last_url = (
            _build_url("/search", {
                "q": q,
                "source": "semantic_scholar",
                "n": n,
                "page": total_pages,
                "sort": ui_sort,
                "year_min": year_min,
                "year_max": year_max,
                "has_abstract": has_abstract,
            })
            if total_pages > 1
            else None
        )

        ctx = _template_base_context(
            request,
            q=q,
            source="semantic_scholar",
            n=n,
            page=page_i,
            sort=ui_sort,
            year_min=year_min,
            year_max=year_max,
            has_abstract=has_abstract,
            mesh=mesh,
        )

        ctx.update({
            "papers": papers,
            "mesh_suggestions": [],
            "concept_suggestions": [],
            "total_count": total_count,
            "total_pages": total_pages,
            "error": None,
            "warning": (
                "Semantic Scholar relevance mode is active."
                if ss_mode == "relevance"
                else None
            ),
            "next_url": next_url,
            "last_url": last_url,
        })

        return templates.TemplateResponse("results.html", ctx)


    # --------------------------
    # PUBMED (default)
    # --------------------------
    year_min_i = _safe_int(year_min, None)
    year_max_i = _safe_int(year_max, None)
    mesh_mode = (mesh_mode or "or").strip().lower()
    if mesh_mode not in {"and", "or"}:
        mesh_mode = "or"

    logger.info(
        "PUBMED SEARCH request q=%r page=%s n=%s sort=%s year_min=%r year_max=%r has_abstract=%r mesh=%r mesh_mode=%r",
        q,
        page,
        n,
        ui_sort,
        year_min,
        year_max,
        has_abstract,
        mesh,
        mesh_mode,
    )

    term = build_pubmed_term(
        q,
        year_min=year_min_i,
        year_max=year_max_i,
        has_abstract=has_abstract,
        mesh=mesh,
        mesh_mode=mesh_mode,
    )

    if not term:
        ctx = _template_base_context(
            request,
            q=q,
            source="pubmed",
            n=n,
            page=1,
            sort=ui_sort,
            year_min=year_min,
            year_max=year_max,
            has_abstract=has_abstract,
            mesh=mesh,
        )

        ctx["source_specializations"] = SOURCE_SPECIALIZATIONS
        ctx["source_info"] = SOURCE_SPECIALIZATIONS.get(source)

        ctx["mesh_mode"] = mesh_mode
        ctx.update({
            "papers": [],
            "mesh_suggestions": [],
            "total_count": 0,
            "total_pages": 1,
            "error": None,
            "warning": None,
            "next_url": None,
            "last_url": None,
        })
        return templates.TemplateResponse("results.html", ctx)

    requested_page = max(1, int(page))
    retstart_req = (requested_page - 1) * int(n)    

    logger.info(
        "PUBMED SEARCH DEBUG term=%r ui_sort=%r pubmed_sort=%r mesh=%r mesh_mode=%r page=%s retstart=%s n=%s",
        term,
        ui_sort,
        pubmed_sort,
        mesh,
        mesh_mode,
        requested_page,
        retstart_req,
        n,
    )

    res = await pubmed_search_page(
        term,
        max_results=n,
        retstart=retstart_req,
        sort=pubmed_sort,
        api_key=NCBI_API_KEY,
        tool=TOOL_NAME,
        email=CONTACT_EMAIL,
    )

    total_count = int(res.count or 0)
    _, total_pages_capped, is_capped = _pagination_limits_pubmed(total_count, n)
    capped_page = _cap_page(requested_page, total_pages_capped)

    if capped_page != requested_page:
        return RedirectResponse(
            url=_build_url(
                "/search",
                {
                    "q": q,
                    "source": "pubmed",
                    "n": n,
                    "page": capped_page,
                    "sort": ui_sort,
                    "year_min": year_min,
                    "year_max": year_max,
                    "has_abstract": has_abstract,
                    "mesh": mesh if (mesh or "").strip() else None,
                    "mesh_mode": mesh_mode if (mesh or "").strip() else None,
                },
            )
        )

    if is_capped:
        warning = _pubmed_cap_warning(total_count)

    retstart = (capped_page - 1) * int(n)

    if retstart >= PUBMED_MAX_PAGEABLE_RESULTS:
        papers_dicts: list[dict[str, Any]] = []
        mesh_suggestions: list[dict[str, Any]] = []
    else:
        fetched = await pubmed_fetch_details(
            res.pmids,
            api_key=NCBI_API_KEY,
            tool=TOOL_NAME,
            email=CONTACT_EMAIL,
        )

        papers_dicts = [_paper_to_dict(p, source="pubmed") for p in (fetched or [])]

        mesh_suggestions = _extract_mesh_suggestions(papers_dicts, limit=10)

    logger.info(
        "PUBMED SEARCH success q=%r page=%s results=%s total=%s capped=%s",
        q,
        capped_page,
        len(papers_dicts),
        total_count,
        is_capped,
    )       

    base_params = {
        "q": q,
        "source": "pubmed",
        "n": n,
        "sort": ui_sort,
        "year_min": year_min,
        "year_max": year_max,
        "has_abstract": has_abstract,
        "mesh": mesh if (mesh or "").strip() else None,
        "mesh_mode": mesh_mode if (mesh or "").strip() else None,
    }

    next_url = _build_url("/search", {**base_params, "page": capped_page + 1}) if capped_page < total_pages_capped else None
    last_url = _build_url("/search", {**base_params, "page": total_pages_capped}) if total_pages_capped > 1 else None

    ctx = _template_base_context(
        request,
        q=q,
        source="pubmed",
        n=n,
        page=capped_page,
        sort=ui_sort,
        year_min=year_min,
        year_max=year_max,
        has_abstract=has_abstract,
        mesh=mesh,
    )

    ctx["source_specializations"] = SOURCE_SPECIALIZATIONS
    ctx["source_info"] = SOURCE_SPECIALIZATIONS.get(source)

    ctx["mesh_mode"] = mesh_mode
    ctx.update({
        "papers": papers_dicts,
        "mesh_suggestions": mesh_suggestions,
        "total_count": total_count,
        "total_pages": total_pages_capped,
        "error": None,
        "warning": warning,
        "next_url": next_url,
        "last_url": last_url,
    })

    return templates.TemplateResponse("results.html", ctx)

@app.get("/paper/{source}/{pid}", response_class=HTMLResponse)
async def paper_detail(request: Request, source: str, pid: str):
    if source not in ALLOWED_SOURCES:
        raise HTTPException(status_code=404, detail="Not Found")

    paper = await _fetch_detail_by_source(source, pid)
    if not paper:
        raise HTTPException(status_code=404, detail="Not Found")

    d = _paper_to_dict(paper, source=source)

    if source == "pubmed" and pid.isdigit():
        d["external_url"] = _pubmed_external_url(pid)
        d["url"] = d["external_url"]
    elif source == "europe_pmc":
        d["external_url"] = _europe_pmc_external_url(paper)
        d["url"] = d["external_url"]
    elif source == "semantic_scholar":
        d["external_url"] = d.get("url") or f"https://www.semanticscholar.org/paper/{pid}"
        d["url"] = d["external_url"]
    else:
        d["external_url"] = d.get("url", "")

    return templates.TemplateResponse(
        "paper.html",
        {
            "request": request,
            "pid": pid,
            "paper": d,
            "error": None,
            "source": source,
        },
    )


@app.get("/paper/{pmid}", include_in_schema=False)
async def legacy_pubmed_detail(pmid: str):
    return RedirectResponse(url=f"/paper/pubmed/{pmid}")


@app.get("/paper/europe_pmc/{pid}", include_in_schema=False)
async def legacy_epmc_detail(pid: str):
    return RedirectResponse(url=f"/paper/europe_pmc/{pid}")

@app.get("/paper/semantic_scholar/{pid}", include_in_schema=False)
async def legacy_semantic_scholar_detail(pid: str):
    return RedirectResponse(url=f"/paper/semantic_scholar/{pid}")


# =========================================================
# Async export (ARQ job + download) - unchanged interface
# =========================================================

@app.post("/export/job")
async def create_export_job(
    request: Request,
    q: str = Query(..., min_length=1),
    source: str = Query("pubmed", pattern="^(pubmed|europe_pmc|openalex|semantic_scholar|all)$"),
    n: int = Query(10, ge=1, le=50),
    sort: str = Query("relevance"),
    fmt: str = Query(..., pattern="^(csv|ris|xlsx)$"),
    limit: int = Query(100, ge=1, le=2000),
    year_min: str = Query(""),
    year_max: str = Query(""),
    has_abstract: int = Query(0, ge=0, le=1),
    mesh: str = Query(""),
    mesh_mode: str = Query("or"),
):
    if not ARQ_REDIS:
        raise HTTPException(503, "Redis/ARQ not available")

    mesh_mode = (mesh_mode or "or").strip().lower()
    if mesh_mode not in {"and", "or"}:
        mesh_mode = "or"

    q = (q or "").strip()
    if not q:
        raise HTTPException(400, "Query is empty")
    if source not in ALLOWED_SOURCES:
        raise HTTPException(422, f"Unknown source: {source}")

    limit = min(int(limit), EXPORT_HARD_CAP)
    n = max(1, min(int(n), 50))

    ui_sort = _normalize_sort(sort)
    mesh_norm = _normalize_mesh(mesh or "")
    year_min_i = _safe_int(year_min, None)
    year_max_i = _safe_int(year_max, None)
    has_abs_i = int(has_abstract or 0)
    job_token = (request.query_params.get("token") or "").strip()

    if year_min_i is not None and year_max_i is not None and year_min_i > year_max_i:
        raise HTTPException(422, "year_min must be <= year_max")

    job_id = uuid.uuid4().hex
    token = secrets.token_urlsafe(24)
    key = f"export:job:{job_id}"
    now = int(time.time())

    tenant_id = _tenant_id(request)

    await ARQ_REDIS.hset(
        key,
        mapping={
            "status": "queued",
            "fmt": fmt,
            "source": source,
            "q": q,
            "sort": ui_sort,
            "n": str(int(n)),
            "limit": str(int(limit)),
            "collected": "0",
            "phase": "starting",
            "message": "Queued for export",
            "last_error": "",
            "download_token": token,
            "tenant_id": tenant_id,
            "year_min": "" if year_min_i is None else str(int(year_min_i)),
            "year_max": "" if year_max_i is None else str(int(year_max_i)),
            "has_abstract": str(has_abs_i),
            "mesh": mesh_norm,
            "created_at": str(now),
            "updated_at": str(now),
            "mesh_mode": mesh_mode,
            "token": job_token,
        },
    )
    await ARQ_REDIS.expire(key, 24 * 3600)

    await ARQ_REDIS.enqueue_job("run_export_job", job_id=job_id, _job_id=f"export:{job_id}")

    return {
        "job_id": job_id,
        "status": "queued",
        "status_url": f"/export/job/{job_id}",
        "download_url": f"/export/download/{job_id}?token={token}",
        "download_token": token,
    }


@app.get("/export/job/{job_id}")
async def get_export_job(job_id: str):
    if not ARQ_REDIS:
        raise HTTPException(503, "Redis/ARQ not available")

    key = f"export:job:{job_id}"
    meta_raw = await ARQ_REDIS.hgetall(key)
    if not meta_raw:
        raise HTTPException(404, "Not found")

    meta = {_as_str(k): _as_str(v) for k, v in meta_raw.items()}
    download_token = meta.get("download_token") or ""

    return {
        "job_id": job_id,
        "status": meta.get("status") or "unknown",
        "source": meta.get("source") or "",
        "fmt": meta.get("fmt") or "",
        "collected": int(meta.get("collected") or 0),
        "limit": int(meta.get("limit") or 0),
        "progress_pct": int(meta.get("progress_pct") or 0),
        "phase": meta.get("phase") or "",
        "message": meta.get("message") or "",
        "file_path": meta.get("file_path") or "",
        "download_token": download_token,
        "download_url": f"/export/download/{job_id}?token={download_token}" if download_token else "",
        "last_error": meta.get("last_error") or "",
        "updated_at": meta.get("updated_at") or "",
        "created_at": meta.get("created_at") or "",
    }


@app.get("/export/download/{job_id}")
async def download_export(job_id: str, token: str):
    if not ARQ_REDIS:
        raise HTTPException(503, "Redis/ARQ not available")

    key = f"export:job:{job_id}"
    meta_raw = await ARQ_REDIS.hgetall(key)
    if not meta_raw:
        raise HTTPException(404, "Not found")

    meta = {_as_str(k): _as_str(v) for k, v in meta_raw.items()}

    stored_token = _as_str(meta.get("download_token"))
    if not stored_token or stored_token != _as_str(token):
        raise HTTPException(403, "Forbidden")

    status = _as_str(meta.get("status"))
    if status != "done":
        raise HTTPException(409, f"Job not ready (status={status})")

    path = _as_str(meta.get("file_path"))
    if not path or not os.path.exists(path):
        raise HTTPException(410, "File missing")

    fmt = _as_str(meta.get("fmt") or "csv")
    filename = f"litsearch_export_{job_id}.{fmt}"
    return FileResponse(path, filename=filename)


# =========================================================
# Sync export (page/bulk) - CSV/RIS/XLSX
# =========================================================

@app.get("/export/{fmt}")
async def export(
    fmt: str,
    request: Request,
    scope: str = Query("page", pattern="^(page|bulk)$"),
    bulk_limit: int = Query(BULK_EXPORT_DEFAULT, ge=1, le=EXPORT_HARD_CAP),
):
    params = dict(request.query_params)

    q = (params.get("q") or "").strip()
    source = (params.get("source") or "pubmed").strip()
    n = max(1, min(int(_safe_int(params.get("n"), 10) or 10), 50))
    page = max(1, int(_safe_int(params.get("page"), 1) or 1))
    token = (params.get("token") or "").strip() or None

    ui_sort = _normalize_sort(params.get("sort") or "relevance")
    if source == "europe_pmc" and ui_sort != "relevance":
        ui_sort = "relevance"

    pubmed_sort = _pubmed_sort(ui_sort)
    openalex_sort = _openalex_sort(ui_sort)
    epmc_sort = ui_sort
    ss_mode, ss_api_sort = _semantic_scholar_sort_mode(ui_sort)

    mesh = _normalize_mesh(params.get("mesh", "") or "")
    year_min = (params.get("year_min") or "").strip()
    year_max = (params.get("year_max") or "").strip()
    has_abstract = int(_safe_int(params.get("has_abstract"), 0) or 0)

    mesh_mode = (params.get("mesh_mode") or "or").strip().lower()
    if mesh_mode not in {"and", "or"}:
        mesh_mode = "or"

    year_min_i = _safe_int(year_min, None)
    year_max_i = _safe_int(year_max, None)

    if not q:
        raise HTTPException(400, "Query is empty")
    if source not in ALLOWED_SOURCES:
        raise HTTPException(422, f"Unknown source: {source}")

    bulk_limit = min(max(1, int(bulk_limit)), EXPORT_HARD_CAP)

    redis = getattr(request.app.state, "redis", None)

    papers: list[Paper] = []


    # ALL SOURCES
    if source == "all":
        raise HTTPException(
            status_code=400,
            detail="All-sources export is only available via async export job."
        )

    # OPENALEX
    elif source == "openalex":
        if scope == "bulk":
            cache_key = make_cache_key("export:openalex:bulk", {"q": q, "limit": bulk_limit, "sort": ui_sort,
                                                               "year_min": year_min, "year_max": year_max})
            cached = await cache_get_json(redis, cache_key) if redis else None
            if cached:
                papers = [Paper.from_dict(d) for d in cached if isinstance(d, dict)]
            else:
                # bulk helper not included here; keep existing in your project if you have it
                out: list[Paper] = []
                page_size = 200
                page_i = 1
                while len(out) < bulk_limit:
                    need = min(page_size, bulk_limit - len(out))
                    batch, _total = await _run_sync(
                        openalex_search, q,
                        page=page_i, n=need,
                        sort=openalex_sort,
                        year_min=_safe_int(year_min, None),
                        year_max=_safe_int(year_max, None),
                    )
                    if not batch:
                        break
                    out.extend(batch)
                    page_i += 1
                papers = out[:bulk_limit]
                if redis:
                    await cache_set_json(redis, cache_key, [p.to_dict() for p in papers], 900)
        else:
            cache_key = make_cache_key("export:openalex:page", {"q": q, "page": page, "n": n, "sort": ui_sort,
                                                               "year_min": year_min, "year_max": year_max})
            cached = await cache_get_json(redis, cache_key) if redis else None
            if cached:
                papers = [Paper.from_dict(d) for d in cached if isinstance(d, dict)]
            else:
                papers, _ = await _run_sync(
                    openalex_search, q,
                    page=page, n=n,
                    sort=openalex_sort,
                    year_min=_safe_int(year_min, None),
                    year_max=_safe_int(year_max, None),
                )
                papers = papers or []
                if redis:
                    await cache_set_json(redis, cache_key, [p.to_dict() for p in papers], 600)

    # PUBMED
    elif source == "pubmed":
        if scope == "bulk":
            cache_key = make_cache_key(
                "export:pubmed:bulk",
                {"q": q, "limit": bulk_limit, "sort": ui_sort, "year_min": year_min, "year_max": year_max,
                 "has_abstract": has_abstract, "mesh": mesh, "mesh_mode": mesh_mode},
            )
            cached = await cache_get_json(redis, cache_key) if redis else None
            if cached:
                papers = [Paper.from_dict(d) for d in cached if isinstance(d, dict)]
            else:
                term = build_pubmed_term(
                    q,
                    year_min=_safe_int(year_min, None),
                    year_max=_safe_int(year_max, None),
                    has_abstract=has_abstract,
                    mesh=mesh,
                    mesh_mode=mesh_mode,
                )
                if not term:
                    papers = []
                else:
                    out: list[Paper] = []
                    retstart = 0
                    while len(out) < bulk_limit and retstart < PUBMED_MAX_PAGEABLE_RESULTS:
                        want = min(1000, bulk_limit - len(out), PUBMED_MAX_PAGEABLE_RESULTS - retstart)
                        res = await pubmed_search_page(term, max_results=want, retstart=retstart, sort=pubmed_sort,
                                                      api_key=NCBI_API_KEY, tool=TOOL_NAME, email=CONTACT_EMAIL)
                        if not res.pmids:
                            break
                        fetched = await pubmed_fetch_details(res.pmids, api_key=NCBI_API_KEY, tool=TOOL_NAME, email=CONTACT_EMAIL)
                        out.extend(fetched or [])
                        retstart += want
                    papers = out[:bulk_limit]
                if redis:
                    await cache_set_json(redis, cache_key, [p.to_dict() for p in papers], 900)
        else:
            term = build_pubmed_term(
                q,
                year_min=year_min_i,
                year_max=year_max_i,
                has_abstract=has_abstract,
                mesh=mesh,
                mesh_mode=mesh_mode,
            )
            if not term:
                raise HTTPException(400, "Query invalid")

            retstart = (page - 1) * n
            if retstart >= PUBMED_MAX_PAGEABLE_RESULTS:
                papers = []
            else:
                cache_key = make_cache_key(
                    "export:pubmed:page",
                    {"q": q, "page": page, "n": n, "sort": ui_sort, "year_min": year_min, "year_max": year_max,
                     "has_abstract": has_abstract, "mesh": mesh, "mesh_mode": mesh_mode},
                )
                cached = await cache_get_json(redis, cache_key) if redis else None
                if cached:
                    papers = [Paper.from_dict(d) for d in cached if isinstance(d, dict)]
                else:
                    res = await pubmed_search_page(term, max_results=n, retstart=retstart, sort=pubmed_sort,
                                                  api_key=NCBI_API_KEY, tool=TOOL_NAME, email=CONTACT_EMAIL)
                    papers = await pubmed_fetch_details(res.pmids, api_key=NCBI_API_KEY, tool=TOOL_NAME, email=CONTACT_EMAIL)
                    papers = papers or []
                    if redis:
                        await cache_set_json(redis, cache_key, [p.to_dict() for p in papers], 600)

    # EUROPE PMC
    elif source == "europe_pmc":
        if scope == "bulk":
            cache_key = make_cache_key(
                "export:epmc:bulk",
                {
                    "q": q,
                    "limit": bulk_limit,
                    "sort": ui_sort,
                    "year_min": year_min,
                    "year_max": year_max,
                    "has_abstract": has_abstract,
                },
            )
            cached = await cache_get_json(redis, cache_key) if redis else None
            if cached:
                papers = [Paper.from_dict(d) for d in cached if isinstance(d, dict)]
            else:
                out: list[Paper] = []
                cursor: str | None = "*"
                seen: set[str] = set()
                while len(out) < bulk_limit and cursor:
                    step = min(100, bulk_limit - len(out))
                    batch, _total, nxt = await _europe_pmc_search_compat_async(
                        q,
                        n=step,
                        cursor=cursor,
                        sort=ui_sort,
                        year_min=_safe_int(year_min, None),
                        year_max=_safe_int(year_max, None),
                        has_abstract=has_abstract,
                        mesh=mesh,
                    )
                    if not batch:
                        break
                    for p in batch:
                        pid = (getattr(p, "id", "") or "").strip()
                        if not pid or pid in seen:
                            continue
                        seen.add(pid)
                        out.append(p)
                        if len(out) >= bulk_limit:
                            break
                    cursor = nxt
                papers = out[:bulk_limit]
                if redis:
                    await cache_set_json(redis, cache_key, [p.to_dict() for p in papers], 900)
        else:
            PAGE_CAP = 100
            cursor = (params.get("cursor") or "").strip() or None
            if not cursor:
                cursor = "*" if page == 1 else None
            if not cursor:
                raise HTTPException(400, "Europe PMC page export requires cursor for page>1.")

            offset = (page - 1) * n
            cur = cursor
            remaining = offset
            while remaining > 0 and cur:
                step = min(PAGE_CAP, remaining)
                _batch, _total, nxt = await _europe_pmc_search_compat_async(
                    q,
                    n=step,
                    cursor=cur,
                    sort=ui_sort,
                    year_min=_safe_int(year_min, None),
                    year_max=_safe_int(year_max, None),
                    has_abstract=has_abstract,
                    mesh=mesh,
                )
                if not nxt:
                    cur = None
                    break
                cur = nxt
                remaining -= step

            if not cur:
                raise HTTPException(502, "Europe PMC could not advance cursor to requested page.")

            fetch_n = min(n, PAGE_CAP)
            ep_papers, _total, _next_cursor = await _europe_pmc_search_compat_async(
                q,
                n=fetch_n,
                cursor=cur,
                sort=ui_sort,
                year_min=_safe_int(year_min, None),
                year_max=_safe_int(year_max, None),
                has_abstract=has_abstract,
                mesh=mesh,
            )
            papers = ep_papers or []

    # SEMANTIC SCHOLAR
    elif source == "semantic_scholar":
        has_abstract_flag = str(has_abstract).strip().lower() in {"1", "true", "yes", "on"}

        if ss_mode == "relevance" and bulk_limit > 1000:
            raise HTTPException(
                status_code=422,
                detail="Semantic Scholar relevance export is limited to the first 1000 results. Use Most recent first or Oldest first for larger exports."
            )

        try:
            if ss_mode == "bulk":
                if scope == "bulk":
                    cache_key = make_cache_key(
                        "export:semantic_scholar:bulk",
                        {
                            "q": q,
                            "limit": bulk_limit,
                            "mode": ss_mode,
                            "sort": ss_api_sort,
                            "year_min": year_min_i,
                            "year_max": year_max_i,
                            "has_abstract": has_abstract_flag,
                        },
                    )
                    cached = await cache_get_json(redis, cache_key) if redis else None
                    if cached:
                        papers = [Paper.from_dict(d) for d in cached if isinstance(d, dict)]
                    else:
                        out: list[Paper] = []
                        token: str | None = None

                        while len(out) < bulk_limit:
                            step = min(100, bulk_limit - len(out))
                            batch, _total, next_token = await _run_sync(
                                search_semantic_scholar_bulk,
                                q,
                                n=step,
                                token=token,
                                sort=ss_api_sort,
                                year_min=year_min_i,
                                year_max=year_max_i,
                                has_abstract=has_abstract_flag,
                            )

                            if not batch:
                                break

                            out.extend(batch)

                            if not next_token:
                                break

                            token = next_token

                        papers = out[:bulk_limit]

                        if redis:
                            await cache_set_json(
                                redis,
                                cache_key,
                                [p.to_dict() for p in papers],
                                900,
                            )

                else:
                    token = (params.get("token") or "").strip() or None

                    cache_key = make_cache_key(
                        "export:semantic_scholar:page",
                        {
                            "q": q,
                            "page": page,
                            "token": token or "",
                            "n": n,
                            "mode": ss_mode,
                            "sort": ss_api_sort,
                            "year_min": year_min_i,
                            "year_max": year_max_i,
                            "has_abstract": has_abstract_flag,
                        },
                    )
                    cached = await cache_get_json(redis, cache_key) if redis else None
                    if cached:
                        papers = [Paper.from_dict(d) for d in cached if isinstance(d, dict)]
                    else:
                        papers, _total, _next_token = await _run_sync(
                            search_semantic_scholar_bulk,
                            q,
                            n=n,
                            token=token,
                            sort=ss_api_sort,
                            year_min=year_min_i,
                            year_max=year_max_i,
                            has_abstract=has_abstract_flag,
                        )
                        papers = papers or []

                        if redis:
                            await cache_set_json(
                                redis,
                                cache_key,
                                [p.to_dict() for p in papers],
                                600,
                            )

            else:
                ss_year_min_i = None
                ss_year_max_i = None

                if scope == "bulk":
                    cache_key = make_cache_key(
                        "export:semantic_scholar:bulk",
                        {
                            "q": q,
                            "limit": bulk_limit,
                            "mode": ss_mode,
                            "sort": ss_api_sort,
                            "year_min": ss_year_min_i,
                            "year_max": ss_year_max_i,
                            "has_abstract": has_abstract_flag,
                        },
                    )
                    cached = await cache_get_json(redis, cache_key) if redis else None
                    if cached:
                        papers = [Paper.from_dict(d) for d in cached if isinstance(d, dict)]
                    else:
                        out: list[Paper] = []
                        page_i = 1

                        batch, _total = await _run_sync(
                            search_semantic_scholar,
                            q,
                            page=1,
                            n=bulk_limit,
                            year_min=ss_year_min_i,
                            year_max=ss_year_max_i,
                            has_abstract=has_abstract_flag,
                        )

                        papers = (batch or [])[:bulk_limit]

                        if redis:
                            await cache_set_json(
                                redis,
                                cache_key,
                                [p.to_dict() for p in papers],
                                900,
                            )

                else:
                    cache_key = make_cache_key(
                        "export:semantic_scholar:page",
                        {
                            "q": q,
                            "page": page,
                            "n": n,
                            "mode": ss_mode,
                            "sort": ss_api_sort,
                            "year_min": ss_year_min_i,
                            "year_max": ss_year_max_i,
                            "has_abstract": has_abstract_flag,
                        },
                    )
                    cached = await cache_get_json(redis, cache_key) if redis else None
                    if cached:
                        papers = [Paper.from_dict(d) for d in cached if isinstance(d, dict)]
                    else:
                        papers, _ = await _run_sync(
                            search_semantic_scholar,
                            q,
                            page=page,
                            n=n,
                            year_min=ss_year_min_i,
                            year_max=ss_year_max_i,
                            has_abstract=has_abstract_flag,
                        )
                        papers = papers or []

                        if redis:
                            await cache_set_json(
                                redis,
                                cache_key,
                                [p.to_dict() for p in papers],
                                600,
                            )

        except SemanticScholarError as e:
            raise HTTPException(
                status_code=503,
                detail=str(e),
            ) from e
        
    if fmt == "csv":
        content = _papers_to_csv(papers)
        return Response(
            content=content,
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="litsearch.csv"'},
        )

    elif fmt == "ris":
        content = _papers_to_ris(papers)
        return Response(
            content=content,
            media_type="application/x-research-info-systems",
            headers={"Content-Disposition": 'attachment; filename="litsearch.ris"'},
        )

    elif fmt == "xlsx":
        content = _papers_to_xlsx_bytes(papers)
        return StreamingResponse(
            io.BytesIO(content),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": 'attachment; filename="litsearch.xlsx"'},
        )

    else:
        raise HTTPException(400, "Unsupported format")
