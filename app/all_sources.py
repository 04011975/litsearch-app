from datetime import datetime

import logging
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

logger = logging.getLogger("litsearch.all_sources")

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
    combined_raw: list[Paper] = []
    source_counts: dict[str, int] = {}
    failed_sources: list[str] = []

    pubmed_sort = "relevance"
    openalex_sort = "relevance_score:desc"
    epmc_sort = "relevance"

    # PubMed
    try:
        term = build_pubmed_term(
            q,
            year_min=year_min,
            year_max=year_max,
            has_abstract=has_abstract,
            mesh=mesh,
        )

        if term:
            res = await pubmed_search_page(
                term,
                max_results=candidate_n,
                retstart=0,
                sort=pubmed_sort,
                api_key=ncbi_api_key,
                tool=tool_name,
                email=contact_email,
            )

            fetched = await pubmed_fetch_details(
                res.pmids,
                api_key=ncbi_api_key,
                tool=tool_name,
                email=contact_email,
            )

            source_counts["pubmed"] = len(fetched or [])

            for p in fetched or []:
                try:
                    p.source = "pubmed"
                except Exception:
                    pass

            combined_raw.extend(fetched or [])
        else:
            source_counts["pubmed"] = 0

    except Exception:
        source_counts["pubmed"] = 0
        failed_sources.append("pubmed")
        logger.exception("ALL: pubmed failed")

    # OpenAlex
    try:
        oa_papers, _ = openalex_search(
            q,
            page=1,
            n=candidate_n,
            sort=openalex_sort,
            year_min=year_min,
            year_max=year_max,
        )

        source_counts["openalex"] = len(oa_papers or [])

        for p in oa_papers or []:
            try:
                p.source = "openalex"
            except Exception:
                pass

        combined_raw.extend(oa_papers or [])

    except Exception:
        source_counts["openalex"] = 0
        failed_sources.append("openalex")
        logger.exception("ALL: openalex failed")

    # Europe PMC
    try:
        ep_papers, _total, _ = europe_pmc_search(
            q,
            n=min(candidate_n, 100),
            cursor="*",
            sort=epmc_sort,
            year_min=year_min,
            year_max=year_max,
            has_abstract=has_abstract,
            mesh=mesh,
        )

        source_counts["europe_pmc"] = len(ep_papers or [])

        for p in ep_papers or []:
            try:
                p.source = "europe_pmc"
            except Exception:
                pass

        combined_raw.extend(ep_papers or [])

    except Exception as e:
        source_counts["europe_pmc"] = 0
        failed_sources.append("europe_pmc")
        logger.warning("ALL: europe_pmc failed/skipped: %s", str(e))

    # Semantic Scholar
    try:
        ss_papers, _ = search_semantic_scholar(
            q,
            page=1,
            n=candidate_n,
        )

        source_counts["semantic_scholar"] = len(ss_papers or [])

        for p in ss_papers or []:
            try:
                p.source = "semantic_scholar"
            except Exception:
                pass

        combined_raw.extend(ss_papers or [])

    except Exception:
        source_counts["semantic_scholar"] = 0
        failed_sources.append("semantic_scholar")
        logger.exception("ALL: semantic scholar failed")

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
    
    normalized_sort = str(sort or "").strip().lower()

    if normalized_sort in {"oldest", "oldest_first", "date_asc", "asc"}:
        normalized_sort = "date_asc"
    elif normalized_sort in {"recent", "most_recent", "newest", "date_desc", "desc"}:
        normalized_sort = "date_desc"
    elif normalized_sort in {"relevance", "relevant", ""}:
        normalized_sort = "relevance"

    candidate_n = max(int(limit or n), 2000)

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

    deduped_papers, duplicates_removed = deduplicate_papers(combined_raw)

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

    total_count = len(sorted_papers)

    page_i = max(1, int(page or 1))
    n_i = max(1, int(n or 10))
    start = (page_i - 1) * n_i
    end = start + n_i

    page_papers = sorted_papers[start:end]

    return {
        "papers": page_papers,
        "all_papers": sorted_papers,
        "total_count": total_count,
        "duplicates_removed": duplicates_removed,
        "source_counts": source_counts,
        "failed_sources": failed_sources,
    }