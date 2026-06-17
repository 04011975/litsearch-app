from datetime import datetime

import asyncio
import logging
import time
import os

logger = logging.getLogger("litsearch.all_sources")

ALL_SOURCES_CANDIDATE_LIMIT = int(
    os.getenv("ALL_SOURCES_CANDIDATE_LIMIT", "2000")
)

from typing import Any

from app.models.paper import Paper
from app.core.deduplication import deduplicate_papers

from app.connectors.pubmed import (
    build_pubmed_term,
    pubmed_fetch_details,
    pubmed_search_page,
)
from app.connectors.openalex import openalex_search
from app.connectors.europe_pmc import europe_pmc_search
from app.connectors.semantic_scholar import (
    search_semantic_scholar,
    search_semantic_scholar_bulk,
)

def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 2)

def _get_value(p, *names):
    for name in names:
        if isinstance(p, dict):
            value = p.get(name)
        else:
            value = getattr(p, name, None)

        if value not in (None, ""):
            return value

    return None


def all_year_value(p):
    raw = _get_value(p, "year", "publication_year", "pub_year")

    if raw:
        try:
            return int(str(raw)[:4])
        except Exception:
            pass

    date_value = _get_value(p, "publication_date")

    if date_value:
        try:
            return datetime.fromisoformat(str(date_value)[:10]).year
        except Exception:
            return None

    return None


def all_title_value(p):
    return str(_get_value(p, "title") or "").strip().lower()


def all_source_value(p):
    return str(_get_value(p, "source") or "").strip().lower()


def interleave_by_source(items):
    source_order = [
        "pubmed",
        "openalex",
        "europe_pmc",
        "semantic_scholar",
    ]

    buckets = {src: [] for src in source_order}
    others = []

    for p in items:
        src = all_source_value(p)

        if src in buckets:
            buckets[src].append(p)
        else:
            others.append(p)

    result = []

    while any(buckets[src] for src in source_order):
        for src in source_order:
            if buckets[src]:
                result.append(buckets[src].pop(0))

    result.extend(others)
    return result

async def fetch_all_source_candidates(
    *,
    q: str,
    candidate_n: int,
    year_min: int | None = None,
    year_max: int | None = None,
    has_abstract: bool = False,
    mesh: str = "",
    mesh_mode: str = "or",
    ncbi_api_key: str | None = None,
    tool_name: str | None = None,
    contact_email: str | None = None,
) -> dict[str, Any]:
    """
    Fetch raw All Sources candidates from each primary source.

    Returns:
        {
            "combined_raw": list[Paper],
            "source_counts": dict[str, int],
            "failed_sources": list[str],
        }
    """

    pubmed_sort = "relevance"
    openalex_sort = "relevance_score:desc"
    epmc_sort = "relevance"

    async def _fetch_pubmed() -> dict[str, Any]:
        started = time.perf_counter()
        source = "pubmed"

        try:
            term = build_pubmed_term(
                q,
                year_min=year_min,
                year_max=year_max,
                has_abstract=has_abstract,
                mesh=mesh,
            )

            if not term:
                return {"source": source, "papers": [], "count": 0, "failed": False}

            res = await pubmed_search_page(
                term,
                max_results=candidate_n,
                retstart=0,
                sort=pubmed_sort,
                api_key=ncbi_api_key,
                tool=tool_name,
                email=contact_email,
            )

            papers = await pubmed_fetch_details(
                res.pmids,
                api_key=ncbi_api_key,
                tool=tool_name,
                email=contact_email,
            )

            for p in papers or []:
                try:
                    p.source = source
                except Exception:
                    pass

            logger.info(
                "ALL PERF source=%s count=%s elapsed_ms=%s",
                source,
                len(papers or []),
                _elapsed_ms(started),
            )

            return {
                "source": source,
                "papers": papers or [],
                "count": len(papers or []),
                "failed": False,
            }

        except Exception:
            logger.exception("ALL: pubmed failed")
            return {"source": source, "papers": [], "count": 0, "failed": True}

    async def _fetch_openalex() -> dict[str, Any]:
        started = time.perf_counter()
        source = "openalex"

        try:
            papers, _ = await asyncio.to_thread(
                openalex_search,
                q,
                page=1,
                n=candidate_n,
                sort=openalex_sort,
                year_min=year_min,
                year_max=year_max,
            )

            for p in papers or []:
                try:
                    p.source = source
                except Exception:
                    pass

            logger.info(
                "ALL PERF source=%s count=%s elapsed_ms=%s",
                source,
                len(papers or []),
                _elapsed_ms(started),
            )

            return {
                "source": source,
                "papers": papers or [],
                "count": len(papers or []),
                "failed": False,
            }

        except Exception:
            logger.exception("ALL: openalex failed")
            return {"source": source, "papers": [], "count": 0, "failed": True}

    async def _fetch_europe_pmc() -> dict[str, Any]:
        started = time.perf_counter()
        source = "europe_pmc"

        try:
            papers, _total, _ = await asyncio.to_thread(
                europe_pmc_search,
                q,
                n=min(candidate_n, 100),
                cursor="*",
                sort=epmc_sort,
                year_min=year_min,
                year_max=year_max,
                has_abstract=has_abstract,
                mesh=mesh,
            )

            for p in papers or []:
                try:
                    p.source = source
                except Exception:
                    pass

            logger.info(
                "ALL PERF source=%s count=%s elapsed_ms=%s",
                source,
                len(papers or []),
                _elapsed_ms(started),
            )

            return {
                "source": source,
                "papers": papers or [],
                "count": len(papers or []),
                "failed": False,
            }

        except Exception as e:
            logger.warning("ALL: europe_pmc failed/skipped: %s", str(e))
            return {"source": source, "papers": [], "count": 0, "failed": True}

    async def _fetch_semantic_scholar() -> dict[str, Any]:
        started = time.perf_counter()
        source = "semantic_scholar"

        try:
            papers, _ = await asyncio.to_thread(
                search_semantic_scholar,
                q,
                page=1,
                n=candidate_n,
            )

            for p in papers or []:
                try:
                    p.source = source
                except Exception:
                    pass

            logger.info(
                "ALL PERF source=%s count=%s elapsed_ms=%s",
                source,
                len(papers or []),
                _elapsed_ms(started),
            )

            return {
                "source": source,
                "papers": papers or [],
                "count": len(papers or []),
                "failed": False,
            }

        except Exception:
            logger.exception("ALL: semantic scholar failed")
            return {"source": source, "papers": [], "count": 0, "failed": True}

    results = await asyncio.gather(
        _fetch_pubmed(),
        _fetch_openalex(),
        _fetch_europe_pmc(),
        _fetch_semantic_scholar(),
    )

    by_source = {result["source"]: result for result in results}

    source_order = [
        "pubmed",
        "openalex",
        "europe_pmc",
        "semantic_scholar",
    ]

    combined_raw: list[Paper] = []
    source_counts: dict[str, int] = {}
    failed_sources: list[str] = []

    for source in source_order:
        result = by_source[source]
        papers = result["papers"]

        combined_raw.extend(papers)
        source_counts[source] = result["count"]

        if result["failed"]:
            failed_sources.append(source)

    return {
        "combined_raw": combined_raw,
        "source_counts": source_counts,
        "failed_sources": failed_sources,
    }

async def build_all_source_results(
    *,
    q: str,
    sort: str,
    limit: int | None,
    page: int = 1,
    n: int = 10,
    year_min: int | None = None,
    year_max: int | None = None,
    has_abstract: bool = False,
    mesh: str = "",
    mesh_mode: str = "or",
):
    """
    Build deduplicated, centrally sorted All Sources results.
    Used by both UI and export paths.
    """

    total_started = time.perf_counter()
    
    normalized_sort = str(sort or "").strip().lower()

    if normalized_sort in {"oldest", "oldest_first", "date_asc", "asc"}:
        normalized_sort = "date_asc"
    elif normalized_sort in {"recent", "most_recent", "newest", "date_desc", "desc"}:
        normalized_sort = "date_desc"
    elif normalized_sort in {"relevance", "relevant", ""}:
        normalized_sort = "relevance"

    candidate_n = max(int(limit or n), ALL_SOURCES_CANDIDATE_LIMIT)

    logger.info(
        "ALL PERF candidate_limit=%s candidate_n=%s requested_limit=%s page_size=%s",
        ALL_SOURCES_CANDIDATE_LIMIT,
        candidate_n,
        limit,
        n,
    )

    fetch_started = time.perf_counter()

    fetched = await fetch_all_source_candidates(
        q=q,
        candidate_n=candidate_n,
        year_min=year_min,
        year_max=year_max,
        has_abstract=has_abstract,
        mesh=mesh,
        mesh_mode=mesh_mode,
    )

    combined_raw = fetched["combined_raw"]
    source_counts = fetched["source_counts"]
    failed_sources = fetched["failed_sources"]

    fetch_ms = _elapsed_ms(fetch_started)

    dedup_started = time.perf_counter()

    deduped_papers, duplicates_removed = deduplicate_papers(combined_raw)

    dedup_ms = _elapsed_ms(dedup_started)

    sort_started = time.perf_counter()

    if normalized_sort == "date_asc":
        sorted_papers = sorted(
            deduped_papers,
            key=lambda p: (
                all_year_value(p) is None,
                all_year_value(p) or 9999,
                all_title_value(p),
                all_source_value(p),
            ),
        )
    elif normalized_sort == "date_desc":
        sorted_papers = sorted(
            deduped_papers,
            key=lambda p: (
                all_year_value(p) is None,
                -(all_year_value(p) or 0),
                all_title_value(p),
                all_source_value(p),
            ),
        )
    else:
        sorted_papers = interleave_by_source(deduped_papers)

    sort_ms = _elapsed_ms(sort_started)

    total_count = len(sorted_papers)

    pagination_started = time.perf_counter()

    page_i = max(1, int(page or 1))
    n_i = max(1, int(n or 10))
    start = (page_i - 1) * n_i
    end = start + n_i

    page_papers = sorted_papers[start:end]

    pagination_ms = _elapsed_ms(pagination_started)

    total_ms = _elapsed_ms(total_started)

    logger.info(
        "ALL PERF total_ms=%s fetch_ms=%s dedup_ms=%s sort_ms=%s pagination_ms=%s raw=%s deduped=%s duplicates_removed=%s",
        total_ms,
        fetch_ms,
        dedup_ms,
        sort_ms,
        pagination_ms,
        len(combined_raw),
        len(sorted_papers),
        duplicates_removed,
    )

    return {
        "papers": page_papers,
        "all_papers": sorted_papers,
        "total_count": total_count,
        "duplicates_removed": duplicates_removed,
        "source_counts": source_counts,
        "failed_sources": failed_sources,
    }