# app/jobs/export_tasks.py

from __future__ import annotations

from app.core.normalize import normalize_papers

from app.core.deduplication import deduplicate_papers

import csv
import io
import json
import hashlib
import logging
import math
import os
import time
import traceback
import uuid
import asyncio
import random
from typing import Any, Callable, List, Optional

import anyio
from arq.connections import ArqRedis
from datetime import datetime, timezone

from app.core.config import get_export_batch_size

from app.core.export_logging import (
    log_export_job_started,
    log_export_batch_completed,
    log_export_batch_failed,
    log_export_job_completed,
)

from app.models.paper import Paper
from app.connectors.europe_pmc import europe_pmc_search
from app.connectors.openalex import openalex_search
from app.connectors.pubmed import build_pubmed_term, pubmed_fetch_details, pubmed_search_page
from app.connectors.semantic_scholar import (
    search_semantic_scholar,
    search_semantic_scholar_bulk,
)

from app.all_sources import build_all_source_results

from dataclasses import dataclass

logger = logging.getLogger("litsearch.export")

EXPORT_DIR = os.getenv("EXPORT_DIR", "/app/exports")
BULK_HARD_CAP = int(os.getenv("EXPORT_HARD_CAP", "2000"))

PUBMED_HARD_CAP = 10_000
OPENALEX_BASIC_PAGING_LIMIT = 10_000
SEMANTIC_SCHOLAR_RELEVANCE_EXPORT_CAP = 1000

SINGLE_EXPORT_SOURCES = {
    "pubmed",
    "openalex",
    "europe_pmc",
    "semantic_scholar",
}

MULTI_SOURCE_EXPORT_SOURCES = [
    "pubmed",
    "openalex",
    "europe_pmc",
    "semantic_scholar",
]

SUPPORTED_EXPORT_SOURCES = SINGLE_EXPORT_SOURCES | {"all"}


# =========================================================
# Redis/meta helpers
# =========================================================

def _as_str(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, (bytes, bytearray, memoryview)):
        return bytes(v).decode("utf-8", errors="replace").strip()
    return str(v).strip()


def _decode_meta(meta: dict) -> dict[str, str]:
    return {_as_str(k): _as_str(v) for k, v in (meta or {}).items()}


def _meta_int(meta: dict[str, str], k: str) -> int | None:
    s = (meta.get(k) or "").strip()
    if not s:
        return None
    try:
        return int(s)
    except Exception:
        return None


async def _job_update(r: ArqRedis, key: str, **fields: Any) -> None:
    safe = {k: ("" if v is None else str(v)) for k, v in fields.items()}
    safe["updated_at"] = datetime.now(timezone.utc).isoformat()
    await r.hset(key, mapping=safe)


def _calc_progress_pct(collected: int, limit: int) -> int:
    try:
        collected_i = max(0, int(collected))
        limit_i = max(0, int(limit))
        if limit_i <= 0:
            return 0
        return max(0, min(100, int((collected_i / limit_i) * 100)))
    except Exception:
        return 0


async def set_job_progress(
    redis: ArqRedis,
    job_id: str,
    *,
    status: str,
    source: str,
    collected: int,
    limit: int,
    phase: str,
    message: str,
    extra: dict | None = None,
) -> None:
    key = f"export:job:{job_id}"

    collected_i = max(0, int(collected))
    limit_i = max(0, int(limit))
    progress_pct = _calc_progress_pct(collected_i, limit_i)

    payload = {
        "status": status,
        "source": source,
        "collected": collected_i,
        "limit": limit_i,
        "progress_pct": progress_pct,
        "phase": phase,
        "message": message,
    }
    if extra:
        payload.update(extra)

    await _job_update(redis, key, **payload)


async def mark_job_done(
    redis: ArqRedis,
    job_id: str,
    *,
    source: str,
    collected: int,
    limit: int,
    file_path: str,
    fmt: str,
    message: str = "Export completed",
    extra: dict | None = None,
) -> None:
    payload = {
        "file_path": file_path,
        "fmt": fmt,
    }
    if extra:
        payload.update(extra)

    await set_job_progress(
        redis,
        job_id,
        status="done",
        source=source,
        collected=collected,
        limit=limit,
        phase="finished",
        message=message,
        extra=payload,
    )


async def mark_job_error(
    redis: ArqRedis,
    job_id: str,
    *,
    source: str,
    collected: int,
    limit: int,
    error: str,
) -> None:
    await set_job_progress(
        redis,
        job_id,
        status="failed",
        source=source,
        collected=collected,
        limit=limit,
        phase="failed",
        message=error,
        extra={"last_error": error},
    )


def _cache_key(prefix: str, payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"{prefix}:{digest}"


def _pubmed_sort(ui_sort: str) -> str:
    s = _normalize_sort(ui_sort)

    if s == "date_desc":
        return "pub_date"

    if s == "date_asc":
        return "pub_date"

    return "relevance"


def _openalex_sort(ui_sort: str) -> str:
    s = _normalize_sort(ui_sort)

    if s == "date_desc":
        return "publication_date:desc"

    if s == "date_asc":
        return "publication_date:asc"

    return "relevance"


def _resolve_export_sources(source: str) -> list[str]:




    if source == "all":
        return list(MULTI_SOURCE_EXPORT_SOURCES)

    if source in SINGLE_EXPORT_SOURCES:
        return [source]

    raise RuntimeError(f"Unsupported source: {source}")


def _normalize_sort(sort: str | None) -> str:
    s = (sort or "").strip().lower()
    if s in {"relevance", "date_desc", "date_asc"}:
        return s
    if s in {"most recent first", "recent", "newest", "latest"}:
        return "date_desc"
    if s in {"oldest first", "oldest"}:
        return "date_asc"
    return "relevance"


def _semantic_scholar_sort_mode(ui_sort: str) -> tuple[str, str]:
    s = (ui_sort or "").strip().lower()
    if s == "date_desc":
        return "bulk", "publicationDate:desc"
    if s == "date_asc":
        return "bulk", "publicationDate:asc"
    return "relevance", "relevance"


async def _cache_get_json(r: ArqRedis, key: str) -> Optional[dict]:
    v = await r.get(key)
    if not v:
        return None
    try:
        return json.loads(v)
    except Exception:
        return None


async def _cache_set_json(r: ArqRedis, key: str, obj: dict, ttl_s: int) -> None:
    await r.set(key, json.dumps(obj), ex=int(ttl_s))


async def _run_sync(fn: Callable, *args, **kwargs):
    return await anyio.to_thread.run_sync(lambda: fn(*args, **kwargs))


def _now_ms() -> int:
    return int(time.time() * 1000)


def _elapsed_ms(start_ms: int) -> int:
    return max(0, _now_ms() - int(start_ms))


def _log_fetch_timing(
    *,
    source: str,
    stage: str,
    started_ms: int,
    returned: int,
    batch_size: int | None = None,
    page: int | None = None,
    token: str | None = None,
    cursor: str | None = None,
    retstart: int | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    fields: list[str] = [
        f"source={source}",
        f"stage={stage}",
        f"took_ms={_elapsed_ms(started_ms)}",
        f"returned={returned}",
    ]

    if batch_size is not None:
        fields.append(f"batch_size={batch_size}")
    if page is not None:
        fields.append(f"page={page}")
    if retstart is not None:
        fields.append(f"retstart={retstart}")
    if token:
        fields.append(f"token={token[:16]}")
    if cursor:
        fields.append(f"cursor={cursor[:24]}")

    if extra:
        for k, v in extra.items():
            if v is None:
                continue
            fields.append(f"{k}={v}")

    logger.info("export_fetch %s", " ".join(fields))


def _new_cache_stats() -> dict[str, int]:
    return {
        "cache_hit_batches": 0,
        "cache_miss_batches": 0,
        "cache_hit_records": 0,
        "api_fetched_records": 0,
    }


def _mark_cache_hit(stats: dict[str, int], returned: int) -> None:
    stats["cache_hit_batches"] += 1
    stats["cache_hit_records"] += max(0, int(returned))


def _mark_cache_miss(stats: dict[str, int], returned: int) -> None:
    stats["cache_miss_batches"] += 1
    stats["api_fetched_records"] += max(0, int(returned))


def _log_cache_summary(
    *,
    source: str,
    stats: dict[str, int],
    collected: int,
    limit: int,
) -> None:
    logger.info(
        "export_cache_summary source=%s collected=%s limit=%s cache_hit_batches=%s cache_miss_batches=%s cache_hit_records=%s api_fetched_records=%s",
        source,
        collected,
        limit,
        stats.get("cache_hit_batches", 0),
        stats.get("cache_miss_batches", 0),
        stats.get("cache_hit_records", 0),
        stats.get("api_fetched_records", 0),
    )

def _log_epmc_summary(
    *,
    stats: dict[str, int],
    collected: int,
    limit: int,
    final_cursor_present: bool,
) -> None:
    logger.info(
        "epmc_export_summary collected=%s limit=%s "
        "page_cache_hit_batches=%s page_cache_miss_batches=%s "
        "page_cache_hit_records=%s api_fetched_records=%s "
        "pages_fetched=%s final_cursor_present=%s final_exported_records=%s",
        collected,
        limit,
        stats.get("epmc_page_cache_hit_batches", 0),
        stats.get("epmc_page_cache_miss_batches", 0),
        stats.get("epmc_page_cache_hit_records", 0),
        stats.get("epmc_api_fetched_records", 0),
        stats.get("epmc_pages_fetched", 0),
        final_cursor_present,
        stats.get("final_exported_records", 0),
    )

def _log_semantic_scholar_summary(
    *,
    mode: str,
    collected: int,
    requested_limit: int,
    effective_limit: int,
    stats: dict[str, int],
    next_token_present: bool | None,
) -> None:
    logger.info(
        "semantic_scholar_export_summary "
        "mode=%s collected=%s requested_limit=%s effective_limit=%s "
        "cache_hit_batches=%s cache_miss_batches=%s "
        "cache_hit_records=%s api_fetched_records=%s "
        "duplicates_skipped=%s missing_id_skipped=%s "
        "next_token_present=%s final_exported_records=%s",
        mode,
        collected,
        requested_limit,
        effective_limit,
        stats.get("cache_hit_batches", 0),
        stats.get("cache_miss_batches", 0),
        stats.get("cache_hit_records", 0),
        stats.get("api_fetched_records", 0),
        stats.get("semantic_scholar_duplicates_skipped", 0),
        stats.get("semantic_scholar_missing_id_skipped", 0),
        next_token_present,
        stats.get("final_exported_records", 0),
    )

def _log_pubmed_summary(
    *,
    stats: dict[str, int],
    collected: int,
    limit: int,
) -> None:
    logger.info(
        "pubmed_export_summary collected=%s limit=%s "
        "esearch_cache_hit_batches=%s esearch_cache_miss_batches=%s esearch_pmids_returned=%s "
        "detail_cache_hit_records=%s detail_cache_miss_records=%s "
        "efetch_api_batches=%s efetch_api_records=%s "
        "final_exported_records=%s",
        collected,
        limit,
        stats.get("esearch_cache_hit_batches", 0),
        stats.get("esearch_cache_miss_batches", 0),
        stats.get("esearch_pmids_returned", 0),
        stats.get("detail_cache_hit_records", 0),
        stats.get("detail_cache_miss_records", 0),
        stats.get("efetch_api_batches", 0),
        stats.get("efetch_api_records", 0),
        stats.get("final_exported_records", 0),
    )

# =========================================================
# Throttling (Redis ZSET sliding window)
# =========================================================

async def _rate_limit_zset(r: ArqRedis, key: str, limit: int, window_s: int) -> bool:
    now_ms = int(time.time() * 1000)
    window_ms = int(window_s) * 1000
    member = f"{now_ms}-{uuid.uuid4().hex}"

    pipe = r.pipeline()
    pipe.zremrangebyscore(key, 0, now_ms - window_ms)
    pipe.zadd(key, {member: now_ms})
    pipe.zcard(key)
    pipe.expire(key, int(window_s) + 2)
    _, _, count, _ = await pipe.execute()
    return int(count) <= int(limit)


async def _throttle_or_sleep(
    r: ArqRedis,
    key: str,
    limit: int,
    window_s: int,
    *,
    sleep_s: float = 0.15,
) -> None:
    limit = max(1, int(limit))
    window_s = max(1, int(window_s))
    while True:
        ok = await _rate_limit_zset(r, key, limit, window_s)
        if ok:
            return
        await asyncio.sleep(sleep_s)


# =========================================================
# Paper serialization helpers
# =========================================================

def _paper_to_dict_safe(p: Paper) -> dict:
    td = getattr(p, "to_dict", None)
    if callable(td):
        return td()

    md = getattr(p, "model_dump", None)
    if callable(md):
        return md()

    d = getattr(p, "dict", None)
    if callable(d):
        return d()

    return dict(getattr(p, "__dict__", {}))


def _paper_from_dict_safe(d: dict) -> Paper:
    fd = getattr(Paper, "from_dict", None)
    if callable(fd):
        return fd(d)
    return Paper(**d)

def _paper_date_sort_key(p: Paper) -> tuple[int, str]:
    try:
        year = int(str(getattr(p, "year", "") or "")[:4])
    except Exception:
        year = 0

    current_year = datetime.utcnow().year + 1

    if year < 1900 or year > current_year:
        year = 0

    title = str(getattr(p, "title", "") or "").lower().strip()

    return (year, title)


def _simple_relevance_score(p: Paper, q: str) -> tuple[int, int, str]:
    title = str(getattr(p, "title", "") or "").lower()
    journal = str(getattr(p, "journal", "") or "").lower()

    score = 0
    for term in q.lower().split():
        if term in title:
            score += 10
        if term in journal:
            score += 2

    year = _paper_date_sort_key(p)[0]
    return (score, year, title)

def _export_relevance_score(p: Paper, q: str) -> tuple[int, int, str]:
    title = str(getattr(p, "title", "") or "").lower()
    journal = str(getattr(p, "journal", "") or "").lower()
    abstract = str(getattr(p, "abstract", "") or "").lower()

    score = 0
    for term in q.lower().split():
        if term in title:
            score += 10
        if term in journal:
            score += 2
        if term in abstract:
            score += 1

    year = _paper_date_sort_key(p)[0]
    title_key = title.strip()

    return (score, year, title_key)


def _export_year_value(p: Paper) -> int:
    try:
        year = int(getattr(p, "year", None) or 0)
    except Exception:
        return 0

    current_year = datetime.utcnow().year + 1
    if year < 1900 or year > current_year:
        return 0

    return year


def _export_relevance_score(p: Paper, q: str) -> tuple[int, int, str]:
    title = str(getattr(p, "title", "") or "").lower()
    journal = str(getattr(p, "journal", "") or "").lower()

    score = 0
    for term in q.lower().split():
        if term in title:
            score += 10
        if term in journal:
            score += 2

    year = _export_year_value(p)
    return (score, year, title)


def _sort_papers_for_export(
    papers: list[Paper],
    sort: str,
    q: str = "",
) -> list[Paper]:
    s = _normalize_sort(sort)

    if s == "date_desc":
        return sorted(papers, key=_paper_date_sort_key, reverse=True)

    if s == "date_asc":
        return sorted(papers, key=_paper_date_sort_key)

    if s == "relevance":
        return papers

    return papers


# =========================================================
# Output writers
# =========================================================

def _papers_to_csv(papers: List[Paper]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["ID", "Source", "Title", "Authors", "Journal", "Year", "DOI", "PMCID", "URL"])
    for p in papers:
        authors = getattr(p, "authors", []) or []
        if isinstance(authors, list):
            authors_str = "; ".join([str(a).strip() for a in authors if str(a).strip()])
        else:
            authors_str = str(authors)

        w.writerow(
            [
                getattr(p, "id", "") or "",
                getattr(p, "source", "") or "",
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

# ExportMetrics tracks processed batch records.
# This can differ from final exported unique records for some sources.
@dataclass
class ExportMetrics:
    total_records: int = 0
    total_batches: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    retry_count: int = 0
    error_count: int = 0

    def record_batch(
        self,
        *,
        records_returned: int,
        cache_hits: int = 0,
        cache_misses: int = 0,
        retry_count: int = 0,
        errored: bool = False,
    ) -> None:
        self.total_batches += 1
        self.total_records += max(0, int(records_returned))
        self.cache_hits += max(0, int(cache_hits))
        self.cache_misses += max(0, int(cache_misses))
        self.retry_count += max(0, int(retry_count))
        if errored:
            self.error_count += 1


async def _fetch_openalex_export_records(
    *,
    r: ArqRedis,
    job_id: str,
    source: str,
    q: str,
    sort: str,
    limit: int,
    meta: dict[str, str],
    tenant_id: str,
    cache_stats: dict[str, int],
    metrics: ExportMetrics,
) -> tuple[list[Paper], dict[str, Any]]:
    papers: list[Paper] = []

    year_min_i = _meta_int(meta, "year_min")
    year_max_i = _meta_int(meta, "year_max")

    per_page = min(get_export_batch_size("openalex"), limit)

    concurrency = max(1, min(int(os.getenv("OPENALEX_EXPORT_CONCURRENCY", "3")), 6))
    ttl_s = int(os.getenv("OPENALEX_EXPORT_CACHE_TTL_S", "600"))

    OPENALEX_TENANT_RPM = int(os.getenv("OPENALEX_TENANT_RPM", "60"))
    OPENALEX_GLOBAL_RPM = int(os.getenv("OPENALEX_GLOBAL_RPM", "600"))
    call_timeout_s = float(os.getenv("EXPORT_CALL_TIMEOUT_S", "45"))

    effective_cap = min(OPENALEX_BASIC_PAGING_LIMIT, limit)
    max_pages = max(1, math.ceil(effective_cap / per_page))

    openalex_sort = _openalex_sort(sort)

    filters_payload = {
        "q": q,
        "sort": openalex_sort,
        "year_min": year_min_i,
        "year_max": year_max_i,
    }

    next_page = 1

    while len(papers) < limit and next_page <= max_pages:
        batch_pages = list(range(next_page, min(max_pages, next_page + concurrency - 1) + 1))
        next_page = batch_pages[-1] + 1

        batch_start = len(papers) + 1
        batch_end = min(len(papers) + (len(batch_pages) * per_page), limit)

        await set_job_progress(
            r,
            job_id,
            status="running",
            source=source,
            collected=len(papers),
            limit=limit,
            phase="fetching",
            message=f"Fetching batch {batch_start}-{batch_end}",
        )

        slot: dict[int, list[Paper]] = {}
        lock = anyio.Lock()

        async def _fetch_one(pno: int) -> None:
            batch_started_ms = _now_ms()
            retries = 0
            cache_hits = 0
            cache_misses = 0

            try:
                remaining_for_page = limit - ((pno - 1) * per_page)
                batch_n = min(per_page, max(0, remaining_for_page))

                if batch_n <= 0:
                    async with lock:
                        slot[pno] = []
                    return

                await set_job_progress(
                    r,
                    job_id,
                    status="running",
                    source=source,
                    collected=len(papers),
                    limit=limit,
                    phase="fetching",
                    message="Waiting for source API",
                )

                await _throttle_or_sleep(
                    r,
                    f"rl:openalex:tenant:{tenant_id}",
                    OPENALEX_TENANT_RPM,
                    60,
                    sleep_s=0.15,
                )
                await _throttle_or_sleep(
                    r,
                    "rl:openalex:global",
                    OPENALEX_GLOBAL_RPM,
                    60,
                    sleep_s=0.15,
                )

                ck = _cache_key(
                    "cache:openalex:export",
                    {**filters_payload, "page": pno, "n": batch_n},
                )
                cached = await _cache_get_json(r, ck)

                if cached and isinstance(cached.get("papers"), list):
                    t0_ms = _now_ms()
                    batch = [_paper_from_dict_safe(d) for d in cached["papers"] if isinstance(d, dict)]
                    batch = normalize_papers(batch, source="openalex")

                    _log_fetch_timing(
                        source="openalex",
                        stage="cache_hit",
                        started_ms=t0_ms,
                        returned=len(batch),
                        batch_size=batch_n,
                        page=pno,
                    )

                    _mark_cache_hit(cache_stats, len(batch))
                    cache_hits = len(batch)

                    metrics.record_batch(
                        records_returned=len(batch),
                        cache_hits=cache_hits,
                        cache_misses=0,
                        retry_count=retries,
                        errored=False,
                    )

                    log_export_batch_completed(
                        job_id=job_id,
                        source="openalex",
                        batch_index=pno,
                        batch_size_requested=per_page,
                        batch_size_effective=batch_n,
                        records_returned=len(batch),
                        duration_ms=_elapsed_ms(batch_started_ms),
                        cache_hits=cache_hits,
                        cache_misses=0,
                        retry_count=retries,
                        extra={
                            "page": pno,
                            "stage": "cache_hit",
                        },
                    )

                else:
                    t0_ms = _now_ms()

                    with anyio.fail_after(call_timeout_s):
                        batch, _total = await _run_sync(
                            openalex_search,
                            q,
                            page=pno,
                            n=batch_n,
                            sort=openalex_sort,
                            year_min=year_min_i,
                            year_max=year_max_i,
                        )

                    batch = batch or []
                    batch = normalize_papers(batch, source="openalex")

                    _log_fetch_timing(
                        source="openalex",
                        stage="api_fetch",
                        started_ms=t0_ms,
                        returned=len(batch),
                        batch_size=batch_n,
                        page=pno,
                    )

                    _mark_cache_miss(cache_stats, len(batch))
                    cache_misses = len(batch)

                    metrics.record_batch(
                        records_returned=len(batch),
                        cache_hits=0,
                        cache_misses=cache_misses,
                        retry_count=retries,
                        errored=False,
                    )

                    log_export_batch_completed(
                        job_id=job_id,
                        source="openalex",
                        batch_index=pno,
                        batch_size_requested=per_page,
                        batch_size_effective=batch_n,
                        records_returned=len(batch),
                        duration_ms=_elapsed_ms(batch_started_ms),
                        cache_hits=0,
                        cache_misses=cache_misses,
                        retry_count=retries,
                        extra={
                            "page": pno,
                            "stage": "api_fetch",
                        },
                    )

                    if batch:
                        await _cache_set_json(
                            r,
                            ck,
                            {"papers": [_paper_to_dict_safe(p) for p in batch]},
                            ttl_s,
                        )

                for p in batch:
                    if not getattr(p, "source", None) or getattr(p, "source") == "unknown":
                        p.source = "openalex"

                async with lock:
                    slot[pno] = batch

            except Exception as exc:
                metrics.record_batch(
                    records_returned=0,
                    cache_hits=0,
                    cache_misses=0,
                    retry_count=retries,
                    errored=True,
                )

                log_export_batch_failed(
                    job_id=job_id,
                    source="openalex",
                    batch_index=pno,
                    batch_size_requested=per_page,
                    duration_ms=_elapsed_ms(batch_started_ms),
                    retry_count=retries,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                    extra={"page": pno},
                )
                raise

        async with anyio.create_task_group() as tg:
            for pno in batch_pages:
                tg.start_soon(_fetch_one, pno)

        made_progress = False

        for pno in sorted(slot.keys()):
            batch = slot[pno] or []

            if batch:
                made_progress = True
                papers.extend(batch)

                if len(papers) > limit:
                    papers = papers[:limit]

                collected = len(papers)

                await set_job_progress(
                    r,
                    job_id,
                    status="running",
                    source=source,
                    collected=collected,
                    limit=limit,
                    phase="fetching",
                    message=f"Fetched {collected} of {limit}",
                )

            if len(papers) >= limit:
                break

        if not made_progress:
            break

        await anyio.sleep(0.05 + random.random() * 0.05)

    return papers, {}


async def _fetch_europe_pmc_export_records(
    *,
    r: ArqRedis,
    job_id: str,
    source: str,
    q: str,
    sort: str,
    limit: int,
    meta: dict[str, str],
    tenant_id: str,
    cache_stats: dict[str, int],
    metrics: ExportMetrics,
) -> tuple[list[Paper], dict[str, Any]]:
    papers: list[Paper] = []

    year_min_i = _meta_int(meta, "year_min")
    year_max_i = _meta_int(meta, "year_max")
    has_abstract_i = int((meta.get("has_abstract") or "0").strip() or "0")

    cursor: Optional[str] = "*"
    seen_ids: set[str] = set()

    EPMC_TENANT_RPM = int(os.getenv("EPMC_TENANT_RPM", "600"))
    EPMC_GLOBAL_RPM = int(os.getenv("EPMC_GLOBAL_RPM", "3000"))
    EPMC_EXPORT_CACHE_TTL_S = int(os.getenv("EPMC_EXPORT_CACHE_TTL_S", "600"))
    batch_cap = max(25, min(int(os.getenv("EPMC_EXPORT_BATCH_SIZE", "100")), 100))
    page_no = 1

    while len(papers) < limit and cursor:
        want = min(batch_cap, limit - len(papers))

        await set_job_progress(
            r,
            job_id,
            status="running",
            source=source,
            collected=len(papers),
            limit=limit,
            phase="fetching",
            message=f"Fetching Europe PMC page {page_no}",
        )

        ck = _cache_key(
            "cache:epmc:export",
            {
                "q": q,
                "sort": sort or "relevance",
                "year_min": year_min_i,
                "year_max": year_max_i,
                "has_abstract": has_abstract_i,
                "cursor": cursor,
                "n": want,
            },
        )
        cached = await _cache_get_json(r, ck)

        if cached and isinstance(cached.get("papers"), list):
            t0_ms = _now_ms()
            batch = [_paper_from_dict_safe(d) for d in cached["papers"] if isinstance(d, dict)]
            batch = normalize_papers(batch, source="europe_pmc")
            next_cursor = (cached.get("next_cursor") or "").strip() or None

            _log_fetch_timing(
                source="europe_pmc",
                stage="cache_hit",
                started_ms=t0_ms,
                returned=len(batch),
                batch_size=want,
                page=page_no,
                cursor=cursor,
                extra={"has_next_cursor": bool(next_cursor)},
            )

            _mark_cache_hit(cache_stats, len(batch))
            cache_stats["epmc_page_cache_hit_batches"] += 1
            cache_stats["epmc_page_cache_hit_records"] += len(batch)

        else:
            await set_job_progress(
                r,
                job_id,
                status="running",
                source=source,
                collected=len(papers),
                limit=limit,
                phase="fetching",
                message="Waiting for Europe PMC API",
            )

            await _throttle_or_sleep(
                r,
                f"rl:epmc:tenant:{tenant_id}:60s",
                EPMC_TENANT_RPM,
                60,
                sleep_s=0.10,
            )
            await _throttle_or_sleep(
                r,
                "rl:epmc:global:60s",
                EPMC_GLOBAL_RPM,
                60,
                sleep_s=0.10,
            )

            t0_ms = _now_ms()
            batch, _total, next_cursor = await _run_sync(
                europe_pmc_search,
                q,
                n=want,
                cursor=cursor,
                sort=sort or "relevance",
                year_min=year_min_i,
                year_max=year_max_i,
                has_abstract=has_abstract_i,
            )
            batch = batch or []
            batch = normalize_papers(batch, source="europe_pmc")

            _log_fetch_timing(
                source="europe_pmc",
                stage="api_fetch",
                started_ms=t0_ms,
                returned=len(batch),
                batch_size=want,
                page=page_no,
                cursor=cursor,
                extra={"has_next_cursor": bool(next_cursor)},
            )

            _mark_cache_miss(cache_stats, len(batch))
            cache_stats["epmc_page_cache_miss_batches"] += 1
            cache_stats["epmc_api_fetched_records"] += len(batch)

            await _cache_set_json(
                r,
                ck,
                {
                    "papers": [_paper_to_dict_safe(p) for p in batch],
                    "next_cursor": next_cursor or "",
                },
                EPMC_EXPORT_CACHE_TTL_S,
            )

        cache_stats["epmc_pages_fetched"] += 1

        if not batch:
            break

        for p in batch:
            pid = (getattr(p, "id", "") or "").strip()
            if not pid or pid in seen_ids:
                continue

            seen_ids.add(pid)

            if not getattr(p, "source", None) or getattr(p, "source") == "unknown":
                p.source = "europe_pmc"

            papers.append(p)

            if len(papers) >= limit:
                break

        cursor = next_cursor
        collected = len(papers)

        await set_job_progress(
            r,
            job_id,
            status="running",
            source=source,
            collected=collected,
            limit=limit,
            phase="fetching",
            message=f"Fetched {collected} of {limit} from Europe PMC",
        )

        page_no += 1

    return papers, {
        "cursor": cursor,
        "final_cursor_present": bool(cursor),
    }


def _pubmed_pmid_key(p: Paper) -> str:
    pmid = str(getattr(p, "pmid", "") or "").strip()
    if pmid:
        return pmid

    pid = str(getattr(p, "id", "") or "").strip()
    if pid.isdigit():
        return pid

    url = str(getattr(p, "url", "") or "")
    if "/pubmed.ncbi.nlm.nih.gov/" in url:
        return url.rstrip("/").split("/")[-1]

    return ""


async def _fetch_pubmed_export_records(
    *,
    r: ArqRedis,
    job_id: str,
    source: str,
    q: str,
    sort: str,
    limit: int,
    meta: dict[str, str],
    tenant_id: str,
    cache_stats: dict[str, int],
    metrics: ExportMetrics,
    NCBI_API_KEY: str | None,
    TOOL_NAME: str | None,
    CONTACT_EMAIL: str | None,
) -> tuple[list[Paper], dict[str, Any]]:
    papers: list[Paper] = []
    
    PUBMED_TENANT_RPS = int(os.getenv("PUBMED_TENANT_RPS", "8"))
    PUBMED_GLOBAL_RPS = int(os.getenv("PUBMED_GLOBAL_RPS", "20"))
    PUBMED_EFETCH_CONCURRENCY = max(1, min(int(os.getenv("PUBMED_EFETCH_CONCURRENCY", "2")), 3))

    mesh_mode = (meta.get("mesh_mode") or "or").strip().lower()
    if mesh_mode not in {"and", "or"}:
        mesh_mode = "or"

    ui_sort = (meta.get("sort") or "relevance").strip().lower()
    pubmed_sort = _pubmed_sort(ui_sort)

    term = build_pubmed_term(
        q,
        year_min=_meta_int(meta, "year_min"),
        year_max=_meta_int(meta, "year_max"),
        has_abstract=int((meta.get("has_abstract") or "0").strip() or "0"),
        mesh=(meta.get("mesh") or ""),
        mesh_mode=mesh_mode,
    )
    if not term:
        raise RuntimeError("Query invalid (empty PubMed term after filters)")

    esearch_chunk = max(200, min(int(os.getenv("PUBMED_EXPORT_ESEARCH_CHUNK", "1000")), 2000))
    efetch_batch = get_export_batch_size("pubmed")

    esearch_ttl = int(os.getenv("PUBMED_ESEARCH_TTL_S", "900"))
    efetch_ttl = int(os.getenv("PUBMED_EFETCH_TTL_S", "21600"))

    seen: set[str] = set()
    retstart = 0
    hard_cap = min(PUBMED_HARD_CAP, limit)

    while len(papers) < limit and retstart < hard_cap:
        want = min(esearch_chunk, hard_cap - retstart, limit - len(papers))
        if want <= 0:
            break

        batch_start = retstart + 1
        batch_end = min(retstart + want, hard_cap)

        await set_job_progress(
            r,
            job_id,
            status="running",
            source=source,
            collected=len(papers),
            limit=limit,
            phase="fetching",
            message=f"Fetching batch {batch_start}-{batch_end}",
        )

        ck = _cache_key(
            "cache:pubmed:esearch",
            {
                "term": term,
                "retstart": retstart,
                "retmax": want,
                "sort": pubmed_sort,
                "mesh_mode": mesh_mode,
            },
        )
        cached = await _cache_get_json(r, ck)

        if cached and isinstance(cached.get("pmids"), list):
            t0_ms = _now_ms()
            pmids = [str(x).strip() for x in cached["pmids"] if str(x).strip()]

            _log_fetch_timing(
                source="pubmed",
                stage="esearch_cache_hit",
                started_ms=t0_ms,
                returned=len(pmids),
                batch_size=want,
                retstart=retstart,
                extra={"sort": pubmed_sort},
            )

            _mark_cache_hit(cache_stats, len(pmids))
            cache_stats["esearch_cache_hit_batches"] += 1
            cache_stats["esearch_pmids_returned"] += len(pmids)

        else:
            await _throttle_or_sleep(
                r,
                f"rl:pubmed:tenant:{tenant_id}:1s",
                PUBMED_TENANT_RPS,
                1,
                sleep_s=0.10,
            )
            await _throttle_or_sleep(
                r,
                "rl:pubmed:global:1s",
                PUBMED_GLOBAL_RPS,
                1,
                sleep_s=0.10,
            )

            t0_ms = _now_ms()
            res = await pubmed_search_page(
                term,
                max_results=want,
                retstart=retstart,
                sort=pubmed_sort,
                api_key=NCBI_API_KEY,
                tool=TOOL_NAME,
                email=CONTACT_EMAIL,
            )
            pmids = [str(x).strip() for x in (res.pmids or []) if str(x).strip()]

            _log_fetch_timing(
                source="pubmed",
                stage="esearch",
                started_ms=t0_ms,
                returned=len(pmids),
                batch_size=want,
                retstart=retstart,
                extra={"sort": pubmed_sort},
            )

            _mark_cache_miss(cache_stats, len(pmids))
            cache_stats["esearch_cache_miss_batches"] += 1
            cache_stats["esearch_pmids_returned"] += len(pmids)

            await _cache_set_json(r, ck, {"pmids": pmids}, esearch_ttl)

        if not pmids:
            break

        new_pmids: list[str] = []
        for pmid in pmids:
            if pmid in seen:
                continue
            seen.add(pmid)
            new_pmids.append(pmid)
            if len(new_pmids) >= (limit - len(papers)):
                break

        details_by_pmid: dict[str, Paper] = {}
        to_fetch: list[str] = []

        for pmid in new_pmids:
            dk = f"cache:pubmed:pmid:{pmid}"
            d = await _cache_get_json(r, dk)

            if isinstance(d, dict) and d:
                try:
                    p = _paper_from_dict_safe(d)
                    details_by_pmid[pmid] = p
                except Exception:
                    to_fetch.append(pmid)
            else:
                to_fetch.append(pmid)

        cache_stats["detail_cache_hit_records"] += len(details_by_pmid)
        cache_stats["detail_cache_miss_records"] += len(to_fetch)

        if details_by_pmid:
            cached_list = normalize_papers(
                list(details_by_pmid.values()),
                source="pubmed",
            )

            details_by_pmid = {
                _pubmed_pmid_key(p): p
                for p in cached_list
                if _pubmed_pmid_key(p)
            }

            for p in details_by_pmid.values():
                if not getattr(p, "source", None) or getattr(p, "source") == "unknown":
                    p.source = "pubmed"

            logger.info(
                "export_cache_detail source=pubmed stage=pmid_detail_cache_hit returned=%s",
                len(details_by_pmid),
            )

        efetch_chunks: list[list[str]] = [
            to_fetch[i : i + efetch_batch]
            for i in range(0, len(to_fetch), efetch_batch)
            if to_fetch[i : i + efetch_batch]
        ]

        for group_start in range(0, len(efetch_chunks), PUBMED_EFETCH_CONCURRENCY):
            chunk_group = efetch_chunks[group_start : group_start + PUBMED_EFETCH_CONCURRENCY]

            async def _fetch_pubmed_chunk(
                chunk_index: int,
                batch_pmids: list[str],
            ) -> tuple[int, list[Paper]]:
                batch_started_ms = _now_ms()
                retries = 0

                absolute_chunk_index = group_start + chunk_index
                fetch_start = (absolute_chunk_index * efetch_batch) + 1
                fetch_end = fetch_start + len(batch_pmids) - 1

                try:
                    await set_job_progress(
                        r,
                        job_id,
                        status="running",
                        source=source,
                        collected=len(papers),
                        limit=limit,
                        phase="fetching",
                        message=f"Fetching page records {fetch_start}-{fetch_end}",
                    )

                    await set_job_progress(
                        r,
                        job_id,
                        status="running",
                        source=source,
                        collected=len(papers),
                        limit=limit,
                        phase="fetching",
                        message="Waiting for source API",
                    )

                    await _throttle_or_sleep(
                        r,
                        f"rl:pubmed:tenant:{tenant_id}:1s",
                        PUBMED_TENANT_RPS,
                        1,
                        sleep_s=0.10,
                    )
                    await _throttle_or_sleep(
                        r,
                        "rl:pubmed:global:1s",
                        PUBMED_GLOBAL_RPS,
                        1,
                        sleep_s=0.10,
                    )

                    t0_ms = _now_ms()

                    with anyio.move_on_after(float(os.getenv("EXPORT_CALL_TIMEOUT_S", "45"))) as scope:
                        fetched_chunk = await pubmed_fetch_details(
                            batch_pmids,
                            api_key=NCBI_API_KEY,
                            tool=TOOL_NAME,
                            email=CONTACT_EMAIL,
                        ) or []

                    pmid_order = {pmid: i for i, pmid in enumerate(batch_pmids)}

                    fetched_chunk = sorted(
                        fetched_chunk,
                        key=lambda p: pmid_order.get(_pubmed_pmid_key(p), 10**9),
                    )

                    if scope.cancel_called:
                        raise RuntimeError(f"PubMed EFetch timeout for chunk {absolute_chunk_index}")

                    fetched_chunk = normalize_papers(fetched_chunk, source="pubmed")

                    _log_fetch_timing(
                        source="pubmed",
                        stage="efetch",
                        started_ms=t0_ms,
                        returned=len(fetched_chunk),
                        batch_size=len(batch_pmids),
                        retstart=retstart,
                        extra={"chunk_index": absolute_chunk_index},
                    )

                    _mark_cache_miss(cache_stats, len(fetched_chunk))
                    cache_stats["efetch_api_batches"] += 1
                    cache_stats["efetch_api_records"] += len(fetched_chunk)

                    metrics.record_batch(
                        records_returned=len(fetched_chunk),
                        cache_hits=0,
                        cache_misses=len(fetched_chunk),
                        retry_count=retries,
                        errored=False,
                    )

                    log_export_batch_completed(
                        job_id=job_id,
                        source="pubmed",
                        batch_index=absolute_chunk_index + 1,
                        batch_size_requested=efetch_batch,
                        batch_size_effective=len(batch_pmids),
                        records_returned=len(fetched_chunk),
                        duration_ms=_elapsed_ms(batch_started_ms),
                        cache_hits=0,
                        cache_misses=len(fetched_chunk),
                        retry_count=retries,
                        extra={
                            "stage": "efetch",
                            "fetch_start": fetch_start,
                            "fetch_end": fetch_end,
                            "retstart": retstart,
                        },
                    )

                    return chunk_index, fetched_chunk

                except Exception as exc:
                    metrics.record_batch(
                        records_returned=0,
                        cache_hits=0,
                        cache_misses=0,
                        retry_count=retries,
                        errored=True,
                    )

                    log_export_batch_failed(
                        job_id=job_id,
                        source="pubmed",
                        batch_index=absolute_chunk_index + 1,
                        batch_size_requested=efetch_batch,
                        duration_ms=_elapsed_ms(batch_started_ms),
                        retry_count=retries,
                        error_type=type(exc).__name__,
                        error_message=str(exc),
                        extra={
                            "stage": "efetch",
                            "fetch_start": fetch_start,
                            "fetch_end": fetch_end,
                            "retstart": retstart,
                        },
                    )
                    raise

            try:
                results = await asyncio.wait_for(
                    asyncio.gather(
                        *[
                            _fetch_pubmed_chunk(chunk_index, batch_pmids)
                            for chunk_index, batch_pmids in enumerate(chunk_group)
                        ]
                    ),
                    timeout=float(os.getenv("EXPORT_GROUP_TIMEOUT_S", "90")),
                )
            except asyncio.TimeoutError:
                logger.error(
                    "pubmed_efetch_group_timeout group_start=%s chunks=%s collected=%s",
                    group_start,
                    len(chunk_group),
                    len(papers),
                )
                raise RuntimeError(f"PubMed EFetch group timeout at group_start={group_start}")

            for _, fetched_chunk in sorted(results, key=lambda x: x[0]):
                for p in fetched_chunk:
                    if not getattr(p, "source", None) or getattr(p, "source") == "unknown":
                        p.source = "pubmed"

                    pmid2 = _pubmed_pmid_key(p)
                    if pmid2:
                        details_by_pmid[pmid2] = p
                        dk = f"cache:pubmed:pmid:{pmid2}"
                        await _cache_set_json(r, dk, _paper_to_dict_safe(p), efetch_ttl)

        ordered_batch = [
            details_by_pmid[pmid]
            for pmid in new_pmids
            if pmid in details_by_pmid
        ]

        if ordered_batch:
            papers.extend(ordered_batch)

            if len(papers) > limit:
                papers = papers[:limit]

            collected = len(papers)
            await set_job_progress(
                r,
                job_id,
                status="running",
                source=source,
                collected=collected,
                limit=limit,
                phase="fetching",
                message=f"Fetched {collected} of {limit}",
            )

        retstart += want

    return papers, {
        "pubmed_sort": pubmed_sort,
        "mesh_mode": mesh_mode,
    }


async def _fetch_semantic_scholar_export_records(
    *,
    r: ArqRedis,
    job_id: str,
    source: str,
    q: str,
    sort: str,
    limit: int,
    meta: dict[str, str],
    tenant_id: str,
    cache_stats: dict[str, int],
    metrics: ExportMetrics,
) -> tuple[list[Paper], dict[str, Any]]:
    papers: list[Paper] = []

    has_abstract_i = int((meta.get("has_abstract") or "0").strip() or "0")

    year_min_i = _meta_int(meta, "year_min")
    year_max_i = _meta_int(meta, "year_max")  

    SS_TENANT_RPM = int(os.getenv("SEMANTIC_SCHOLAR_TENANT_RPM", "60"))
    SS_GLOBAL_RPM = int(os.getenv("SEMANTIC_SCHOLAR_GLOBAL_RPM", "300"))
    ttl_s = int(os.getenv("SEMANTIC_SCHOLAR_EXPORT_CACHE_TTL_S", "600"))
    call_timeout_s = float(os.getenv("EXPORT_CALL_TIMEOUT_S", "45"))

    requested_limit = limit
    ss_mode_for_summary = "relevance"
    ss_effective_limit = limit
    ss_next_token_present: bool | None = None

    ui_sort = _normalize_sort(sort)
    ss_mode, ss_api_sort = _semantic_scholar_sort_mode(ui_sort)

    seen_ids: set[str] = set()

    if ss_mode == "bulk":
        ss_mode_for_summary = "bulk"
        ss_effective_limit = requested_limit

        batch_cap = get_export_batch_size("semantic_scholar_bulk")
        next_token: str | None = (meta.get("token") or "").strip() or None
        batch_index = 0

        while len(papers) < requested_limit:
            want = min(batch_cap, requested_limit - len(papers))
            if want <= 0:
                break

            batch_index += 1
            batch_started_ms = _now_ms()
            retries = 0
            cache_hits = 0
            cache_misses = 0

            try:
                batch_start = len(papers) + 1
                batch_end = min(len(papers) + want, requested_limit)

                await set_job_progress(
                    r,
                    job_id,
                    status="running",
                    source=source,
                    collected=len(papers),
                    limit=requested_limit,
                    phase="fetching",
                    message=f"Fetching batch {batch_start}-{batch_end}",
                    extra={
                        "mode": "bulk",
                        "requested_limit": requested_limit,
                        "effective_limit": ss_effective_limit,
                    },
                )

                await set_job_progress(
                    r,
                    job_id,
                    status="running",
                    source=source,
                    collected=len(papers),
                    limit=requested_limit,
                    phase="fetching",
                    message="Waiting for source API",
                    extra={
                        "mode": "bulk",
                        "requested_limit": requested_limit,
                        "effective_limit": ss_effective_limit,
                    },
                )

                await _throttle_or_sleep(
                    r,
                    f"rl:semantic_scholar:tenant:{tenant_id}:60s",
                    SS_TENANT_RPM,
                    60,
                    sleep_s=0.10,
                )
                await _throttle_or_sleep(
                    r,
                    "rl:semantic_scholar:global:60s",
                    SS_GLOBAL_RPM,
                    60,
                    sleep_s=0.10,
                )

                ck = _cache_key(
                    "cache:semantic_scholar:bulk_export",
                    {
                        "q": q,
                        "token": next_token or "",
                        "n": want,
                        "sort": ss_api_sort,
                        "year_min": year_min_i,
                        "year_max": year_max_i,
                        "has_abstract": bool(has_abstract_i),
                    },
                )
                cached = await _cache_get_json(r, ck)

                if cached and isinstance(cached.get("papers"), list):
                    t0_ms = _now_ms()
                    batch = [_paper_from_dict_safe(d) for d in cached["papers"] if isinstance(d, dict)]
                    batch = normalize_papers(batch, source="semantic_scholar")
                    returned_next_token = (cached.get("next_token") or "").strip() or None
                    ss_next_token_present = bool(returned_next_token)

                    _log_fetch_timing(
                        source="semantic_scholar",
                        stage="bulk_cache_hit",
                        started_ms=t0_ms,
                        returned=len(batch),
                        batch_size=want,
                        token=next_token,
                        extra={"has_next_token": bool(returned_next_token)},
                    )
                    _mark_cache_hit(cache_stats, len(batch))

                    cache_hits = len(batch)

                    metrics.record_batch(
                        records_returned=len(batch),
                        cache_hits=cache_hits,
                        cache_misses=0,
                        retry_count=retries,
                        errored=False,
                    )

                    log_export_batch_completed(
                        job_id=job_id,
                        source="semantic_scholar",
                        batch_index=batch_index,
                        batch_size_requested=batch_cap,
                        batch_size_effective=want,
                        records_returned=len(batch),
                        duration_ms=_elapsed_ms(batch_started_ms),
                        cache_hits=cache_hits,
                        cache_misses=0,
                        retry_count=retries,
                        extra={
                            "mode": "bulk",
                            "stage": "bulk_cache_hit",
                            "token_present": bool(next_token),
                            "next_token_present": bool(returned_next_token),
                        },
                    )

                else:
                    t0_ms = _now_ms()
                    with anyio.fail_after(call_timeout_s):
                        batch, _total, returned_next_token = await _run_sync(
                            search_semantic_scholar_bulk,
                            q,
                            n=want,
                            token=next_token,
                            sort=ss_api_sort,
                            year_min=year_min_i,
                            year_max=year_max_i,
                            has_abstract=bool(has_abstract_i),
                        )
                    batch = batch or []
                    batch = normalize_papers(batch, source="semantic_scholar")
                    ss_next_token_present = bool(returned_next_token)

                    _log_fetch_timing(
                        source="semantic_scholar",
                        stage="bulk_api_fetch",
                        started_ms=t0_ms,
                        returned=len(batch),
                        batch_size=want,
                        token=next_token,
                        extra={"has_next_token": bool(returned_next_token)},
                    )
                    _mark_cache_miss(cache_stats, len(batch))

                    cache_misses = len(batch)

                    metrics.record_batch(
                        records_returned=len(batch),
                        cache_hits=0,
                        cache_misses=cache_misses,
                        retry_count=retries,
                        errored=False,
                    )

                    log_export_batch_completed(
                        job_id=job_id,
                        source="semantic_scholar",
                        batch_index=batch_index,
                        batch_size_requested=batch_cap,
                        batch_size_effective=want,
                        records_returned=len(batch),
                        duration_ms=_elapsed_ms(batch_started_ms),
                        cache_hits=0,
                        cache_misses=cache_misses,
                        retry_count=retries,
                        extra={
                            "mode": "bulk",
                            "stage": "bulk_api_fetch",
                            "token_present": bool(next_token),
                            "next_token_present": bool(returned_next_token),
                        },
                    )

                    await _cache_set_json(
                        r,
                        ck,
                        {
                            "papers": [_paper_to_dict_safe(p) for p in batch],
                            "next_token": returned_next_token or "",
                        },
                        ttl_s,
                    )

                if not batch:
                    break

                made_progress = False
                for p in batch:
                    pid = (getattr(p, "id", "") or "").strip()
                    if pid and pid in seen_ids:
                        continue
                    if pid:
                        seen_ids.add(pid)

                    if not getattr(p, "source", None) or getattr(p, "source") == "unknown":
                        p.source = "semantic_scholar"

                    papers.append(p)
                    made_progress = True

                    if len(papers) >= requested_limit:
                        break

                collected = len(papers)

                await set_job_progress(
                    r,
                    job_id,
                    status="running",
                    source=source,
                    collected=collected,
                    limit=requested_limit,
                    phase="fetching",
                    message=f"Fetched {collected} of {requested_limit}",
                    extra={
                        "mode": "bulk",
                        "requested_limit": requested_limit,
                        "effective_limit": ss_effective_limit,
                    },
                )

                if len(papers) >= requested_limit:
                    break
                if not made_progress:
                    break
                if not returned_next_token:
                    break

                next_token = returned_next_token

            except Exception as exc:
                metrics.record_batch(
                    records_returned=0,
                    cache_hits=0,
                    cache_misses=0,
                    retry_count=retries,
                    errored=True,
                )

                log_export_batch_failed(
                    job_id=job_id,
                    source="semantic_scholar",
                    batch_index=batch_index,
                    batch_size_requested=batch_cap,
                    duration_ms=_elapsed_ms(batch_started_ms),
                    retry_count=retries,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                    extra={
                        "mode": "bulk",
                        "token_present": bool(next_token),
                    },
                )
                raise

    else:
        ss_mode_for_summary = "relevance"

        batch_cap = max(1, min(int(os.getenv("SEMANTIC_SCHOLAR_EXPORT_BATCH_SIZE", "100")), 100))
        effective_limit = min(requested_limit, SEMANTIC_SCHOLAR_RELEVANCE_EXPORT_CAP)
        ss_effective_limit = effective_limit
        page_i = 1

        if requested_limit > effective_limit:
            await set_job_progress(
                r,
                job_id,
                status="running",
                source=source,
                collected=0,
                limit=effective_limit,
                phase="starting",
                message=f"Relevance mode active: export capped at {effective_limit} records",
                extra={
                    "mode": "relevance",
                    "requested_limit": requested_limit,
                    "effective_limit": effective_limit,
                    "cap_reason": "Semantic Scholar relevance mode supports limited export depth",
                },
            )

        want = effective_limit

        await set_job_progress(
            r,
            job_id,
            status="running",
            source=source,
            collected=0,
            limit=effective_limit,
            phase="fetching",
            message="Fetching Semantic Scholar relevance results",
            extra={
                "mode": "relevance",
                "requested_limit": requested_limit,
                "effective_limit": effective_limit,
            },
        )

        await set_job_progress(
            r,
            job_id,
            status="running",
            source=source,
            collected=0,
            limit=effective_limit,
            phase="fetching",
            message="Waiting for source API",
            extra={
                "mode": "relevance",
                "requested_limit": requested_limit,
                "effective_limit": effective_limit,
            },
        )

        await _throttle_or_sleep(
            r,
            f"rl:semantic_scholar:tenant:{tenant_id}:60s",
            SS_TENANT_RPM,
            60,
            sleep_s=0.10,
        )

        await _throttle_or_sleep(
            r,
            "rl:semantic_scholar:global:60s",
            SS_GLOBAL_RPM,
            60,
            sleep_s=0.10,
        )

        ck = _cache_key(
            "cache:semantic_scholar:export",
            {
                "q": q,
                "page": 1,
                "n": want,
                "sort": "relevance",
                "year_min": year_min_i,
                "year_max": year_max_i,
                "has_abstract": bool(has_abstract_i),
            },
        )

        cached = await _cache_get_json(r, ck)

        if cached and isinstance(cached.get("papers"), list):
            t0_ms = _now_ms()

            batch = [
                _paper_from_dict_safe(d)
                for d in cached["papers"]
                if isinstance(d, dict)
            ]

            batch = normalize_papers(batch, source="semantic_scholar")

            _log_fetch_timing(
                source="semantic_scholar",
                stage="relevance_cache_hit",
                started_ms=t0_ms,
                returned=len(batch),
                batch_size=want,
                page=1,
            )

            _mark_cache_hit(cache_stats, len(batch))

        else:
            t0_ms = _now_ms()

            with anyio.fail_after(call_timeout_s):
                batch, _total = await _run_sync(
                    search_semantic_scholar,
                    q,
                    page=1,
                    n=want,
                    year_min=year_min_i,
                    year_max=year_max_i,
                    has_abstract=bool(has_abstract_i),
                )

            batch = batch or []
            batch = normalize_papers(batch, source="semantic_scholar")

            _log_fetch_timing(
                source="semantic_scholar",
                stage="relevance_api_fetch",
                started_ms=t0_ms,
                returned=len(batch),
                batch_size=want,
                page=1,
            )

            _mark_cache_miss(cache_stats, len(batch))

            await _cache_set_json(
                r,
                ck,
                {"papers": [_paper_to_dict_safe(p) for p in batch]},
                ttl_s,
            )

        papers = []

        for p in batch:
            pid = (getattr(p, "id", "") or "").strip()

            if not pid:
                continue

            if pid in seen_ids:
                continue

            seen_ids.add(pid)

            if not getattr(p, "source", None) or getattr(p, "source") == "unknown":
                p.source = "semantic_scholar"

            papers.append(p)

            if len(papers) >= effective_limit:
                break

        await set_job_progress(
            r,
            job_id,
            status="running",
            source=source,
            collected=len(papers),
            limit=effective_limit,
            phase="fetching",
            message=f"Fetched {len(papers)} of {effective_limit}",
            extra={
                "mode": "relevance",
                "requested_limit": requested_limit,
                "effective_limit": effective_limit,
            },
        )

    return papers, {
        "ss_mode_for_summary": ss_mode_for_summary,
        "ss_effective_limit": ss_effective_limit,
        "ss_next_token_present": ss_next_token_present,
        "requested_limit": requested_limit,
    }            

# =========================================================
# Main ARQ task
# =========================================================

async def run_export_job(ctx: dict, *, job_id: str) -> dict:
    """
    ARQ task. MUST return a dict (not None), otherwise arq logs show '●'
    and UI may appear stuck.
    """
    r: ArqRedis = ctx["redis"]
    key = f"export:job:{job_id}"

    NCBI_API_KEY = (os.getenv("NCBI_API_KEY") or "").strip() or None
    TOOL_NAME = (os.getenv("TOOL_NAME") or "LitSearch").strip() or None
    CONTACT_EMAIL = (os.getenv("CONTACT_EMAIL") or "").strip() or None

    raw_meta = await r.hgetall(key)
    meta = _decode_meta(raw_meta)

    if not meta:
        logger.error("export job meta not found key=%s job_id=%s", key, job_id)
        return {"ok": False, "status": "missing", "error": "job meta not found", "job_id": job_id}

    source = _as_str(meta.get("source"))
    q = _as_str(meta.get("q"))
    sort = _as_str(meta.get("sort") or "relevance")   
    limit = min(int(_as_str(meta.get("limit") or "100") or "100"), BULK_HARD_CAP)
    fmt = _as_str(meta.get("fmt") or "csv")
    download_token = _as_str(meta.get("download_token"))
    tenant_id = _as_str(meta.get("tenant_id") or "anon")

    collected = 0
    job_started_ms = _now_ms()
    metrics = ExportMetrics()

    try:
        await set_job_progress(
            r,
            job_id,
            status="running",
            source=source or "unknown",
            collected=0,
            limit=limit,
            phase="starting",
            message="Preparing export job",
            extra={"last_error": ""},
        )

        if not download_token:
            raise RuntimeError("Missing download_token in job meta")
        if not q:
            raise RuntimeError("Query empty")
        if source not in SUPPORTED_EXPORT_SOURCES:
            raise RuntimeError(f"Unsupported source: {source}")
        
        export_sources = _resolve_export_sources(source)

        if fmt not in {"csv", "ris", "xlsx"}:
            raise RuntimeError(f"Unsupported fmt: {fmt}")

        ss_mode = None
        job_batch_size = None

        if source == "openalex":
            job_batch_size = get_export_batch_size("openalex")
        elif source == "pubmed":
            job_batch_size = get_export_batch_size("pubmed")
        elif source == "semantic_scholar":
            ui_sort = _normalize_sort(sort)
            ss_mode, _ss_api_sort = _semantic_scholar_sort_mode(ui_sort)
            if ss_mode == "bulk":
                job_batch_size = get_export_batch_size("semantic_scholar_bulk")

        log_export_job_started(
            job_id=job_id,
            source=source,
            fmt=fmt,
            query=q,
            limit=limit,
            batch_size=job_batch_size,
            sort=sort,
            mode=ss_mode,
        )

        year_min_i = _meta_int(meta, "year_min")
        year_max_i = _meta_int(meta, "year_max")
        has_abstract_i = int((meta.get("has_abstract") or "0").strip() or "0")

        papers: List[Paper] = []
        cache_stats = _new_cache_stats()
        cache_stats.update({
            "esearch_cache_hit_batches": 0,
            "esearch_cache_miss_batches": 0,
            "esearch_pmids_returned": 0,
            "detail_cache_hit_records": 0,
            "detail_cache_miss_records": 0,
            "efetch_api_batches": 0,
            "efetch_api_records": 0,

            "epmc_page_cache_hit_batches": 0,
            "epmc_page_cache_miss_batches": 0,
            "epmc_page_cache_hit_records": 0,
            "epmc_api_fetched_records": 0,
            "epmc_pages_fetched": 0,

        "semantic_scholar_duplicates_skipped": 0,
        "semantic_scholar_missing_id_skipped": 0,

        "cross_source_duplicates_removed": 0,
        "records_before_final_dedup": 0,
        "records_after_final_dedup": 0,

        "final_exported_records": 0,
        })


        # =====================================================
        # ALL SOURCES
        # =====================================================

        if source == "all":
            source_counts: dict[str, int] = {}
            failed_sources: list[str] = []
            target_unique = int(limit)

            export_sort = str(sort or "").strip().lower()

            if export_sort in {"oldest", "oldest_first", "date_asc", "asc"}:
                export_sort = "date_asc"
            elif export_sort in {"recent", "most_recent", "newest", "date_desc", "desc"}:
                export_sort = "date_desc"
            elif export_sort in {"relevance", "relevant", ""}:
                export_sort = "relevance"

            result = await build_all_source_results(
                q=q,
                sort=export_sort,
                limit=target_unique,
                page=1,
                n=target_unique,
                year_min=year_min_i,
                year_max=year_max_i,
                has_abstract=meta.get("has_abstract") in {"1", "true", "True", True},
                mesh=meta.get("mesh") or "",
                mesh_mode=meta.get("mesh_mode") or "or",
            )

            papers = result["all_papers"][:target_unique]
            cross_source_duplicates_removed = result["duplicates_removed"]
            source_counts = result["source_counts"]
            failed_sources = result["failed_sources"]
            

        # =====================================================
        # OPENALEX
        # =====================================================
        elif source == "openalex":
            papers, openalex_meta = await _fetch_openalex_export_records(
                r=r,
                job_id=job_id,
                source=source,
                q=q,
                sort=sort,
                limit=limit,
                meta=meta,
                tenant_id=tenant_id,
                cache_stats=cache_stats,
                metrics=metrics,
            )

        # =====================================================
        # PUBMED
        # =====================================================
        elif source == "pubmed":
            papers, pubmed_meta = await _fetch_pubmed_export_records(
                r=r,
                job_id=job_id,
                source=source,
                q=q,
                sort=sort,
                limit=limit,
                meta=meta,
                tenant_id=tenant_id,
                cache_stats=cache_stats,
                metrics=metrics,
                NCBI_API_KEY=NCBI_API_KEY,
                TOOL_NAME=TOOL_NAME,
                CONTACT_EMAIL=CONTACT_EMAIL,
            )

        # =====================================================
        # EUROPE PMC
        # =====================================================
        elif source == "europe_pmc":
            papers, epmc_meta = await _fetch_europe_pmc_export_records(
                r=r,
                job_id=job_id,
                source=source,
                q=q,
                sort=sort,
                limit=limit,
                meta=meta,
                tenant_id=tenant_id,
                cache_stats=cache_stats,
                metrics=metrics,
            )

            cursor = epmc_meta["cursor"]

        # =====================================================
        # SEMANTIC SCHOLAR
        # =====================================================
        elif source == "semantic_scholar":
            papers, ss_meta = await _fetch_semantic_scholar_export_records(
                r=r,
                job_id=job_id,
                source=source,
                q=q,
                sort=sort,
                limit=limit,
                meta=meta,
                tenant_id=tenant_id,
                cache_stats=cache_stats,
                metrics=metrics,
            )

            ss_mode_for_summary = ss_meta["ss_mode_for_summary"]
            ss_effective_limit = ss_meta["ss_effective_limit"]
            ss_next_token_present = ss_meta["ss_next_token_present"]
            requested_limit = ss_meta["requested_limit"]
        
        
        # =====================================================
        # Final dedup + sort + Write output
        # =====================================================
        final_limit = limit
        if source == "semantic_scholar":
            final_limit = ss_effective_limit

        records_before_final_dedup = len(papers)

        if source in {"pubmed", "openalex"}:
            cross_source_duplicates_removed = 0
        else:
            papers, cross_source_duplicates_removed = deduplicate_papers(papers)

        records_after_final_dedup = len(papers)

        if not (
            source in {"pubmed", "openalex", "all"}
            or (source == "semantic_scholar" and ss_mode_for_summary == "bulk")
        ):
            papers = _sort_papers_for_export(papers, sort, q=q)

        papers = papers[:final_limit]

        collected = len(papers)

        cache_stats["records_before_final_dedup"] = records_before_final_dedup
        cache_stats["records_after_final_dedup"] = records_after_final_dedup
        cache_stats["cross_source_duplicates_removed"] = cross_source_duplicates_removed
        cache_stats["final_exported_records"] = len(papers)

        logger.info(
            "final_dedup_summary source=%s before=%s after=%s duplicates_removed=%s",
            source,
            records_before_final_dedup,
            records_after_final_dedup,
            cross_source_duplicates_removed,
        )

        done_message = "Export completed"
        done_limit = limit

        done_extra: dict[str, Any] = {
            "exported_records": len(papers),
            "records_before_final_dedup": records_before_final_dedup,
            "records_after_final_dedup": records_after_final_dedup,
            "duplicates_removed": cross_source_duplicates_removed,
        }
    
        if source == "all":
            done_extra.update({
                "sources": "|".join(MULTI_SOURCE_EXPORT_SOURCES),
                "source_counts": json.dumps(source_counts, sort_keys=True),
            })

        if source == "semantic_scholar":
            done_extra.update({
                "mode": ss_mode_for_summary,
                "requested_limit": requested_limit,
                "effective_limit": ss_effective_limit,
            })

            if ss_mode_for_summary == "relevance":
                if requested_limit > ss_effective_limit:
                    done_message = (
                        f"Relevance mode export completed "
                        f"(requested {requested_limit}, effective cap {ss_effective_limit}, exported {len(papers)})"
                    )
                else:
                    done_message = f"Relevance mode export completed ({len(papers)} records)"

                # Zorg dat de eindstatus 100% wordt in de UI
                done_limit = len(papers) if len(papers) > 0 else ss_effective_limit

            elif ss_mode_for_summary == "bulk":
                done_message = f"Chronological export completed ({len(papers)} records)"

        progress_limit = limit
        if source == "semantic_scholar":
            progress_limit = ss_effective_limit

        await set_job_progress(
            r,
            job_id,
            status="running",
            source=source,
            collected=collected,
            limit=progress_limit,
            phase="building",
            message="Building export file",
        )

        os.makedirs(EXPORT_DIR, exist_ok=True)
        out_path = os.path.join(EXPORT_DIR, f"{job_id}.{fmt}")

        await set_job_progress(
            r,
            job_id,
            status="running",
            source=source,
            collected=collected,
            limit=progress_limit,
            phase="writing",
            message="Writing export file",
        )

        write_t0_ms = _now_ms()

        if fmt == "csv":
            content = _papers_to_csv(papers)
            with open(out_path, "w", encoding="utf-8", newline="") as f:
                f.write(content)

        elif fmt == "ris":
            content = _papers_to_ris(papers)
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(content)

        elif fmt == "xlsx":
            from openpyxl import Workbook

            wb = Workbook(write_only=True)
            ws = wb.create_sheet("Export")
            ws.append(["ID", "Source", "Title", "Authors", "Journal", "Year", "DOI", "PMCID", "URL"])

            for p in papers:
                authors = getattr(p, "authors", []) or []
                authors_str = (
                    "; ".join(str(a).strip() for a in authors if str(a).strip())
                    if isinstance(authors, list)
                    else str(authors)
                )

                ws.append(
                    [
                        getattr(p, "id", "") or "",
                        getattr(p, "source", "") or "",
                        getattr(p, "title", "") or "",
                        authors_str,
                        getattr(p, "journal", "") or "",
                        str(getattr(p, "year", "") or ""),
                        getattr(p, "doi", "") or "",
                        getattr(p, "pmcid", "") or "",
                        getattr(p, "url", "") or "",
                    ]
                )

            wb.save(out_path)

        else:
            raise ValueError(f"Unsupported export format: {fmt}")

        logger.info(
            "export_write source=%s fmt=%s records=%s took_ms=%s path=%s",
            source,
            fmt,
            len(papers),
            _elapsed_ms(write_t0_ms),
            out_path,
        )

        _log_cache_summary(
            source=source,
            stats=cache_stats,
            collected=len(papers),
            limit=final_limit,
        )

        if source == "pubmed":
            _log_pubmed_summary(
                stats=cache_stats,
                collected=len(papers),
                limit=final_limit,
            )

        if source == "europe_pmc":
            _log_epmc_summary(
                stats=cache_stats,
                collected=len(papers),
                limit=final_limit,
                final_cursor_present=bool(cursor),
            )

        if source == "semantic_scholar":
            _log_semantic_scholar_summary(
                mode=ss_mode_for_summary,
                collected=len(papers),
                requested_limit=requested_limit,
                effective_limit=ss_effective_limit,
                stats=cache_stats,
                next_token_present=ss_next_token_present,
            )

        if not (
            source == "openalex"
            or source == "pubmed"
            or (source == "semantic_scholar" and ss_mode_for_summary == "bulk")
        ):
            metrics.total_records = len(papers)
            metrics.total_batches = (
                cache_stats.get("cache_hit_batches", 0)
                + cache_stats.get("cache_miss_batches", 0)
            )
            metrics.cache_hits = cache_stats.get("cache_hit_records", 0)
            metrics.cache_misses = cache_stats.get("api_fetched_records", 0)

        log_export_job_completed(
            job_id=job_id,
            source=source,
            total_records=metrics.total_records,
            total_batches=metrics.total_batches,
            total_duration_ms=_elapsed_ms(job_started_ms),
            cache_hits=metrics.cache_hits,
            cache_misses=metrics.cache_misses,
            retry_count=metrics.retry_count,
            error_count=metrics.error_count,
            extra={
                "fmt": fmt,
                "final_limit": final_limit,
                "exported_records": len(papers),
                "records_before_final_dedup": records_before_final_dedup,
                "duplicates_removed": cross_source_duplicates_removed,
            },
        )

        await mark_job_done(
            r,
            job_id,
            source=source,
            collected=len(papers),
            limit=done_limit,
            file_path=out_path,
            fmt=fmt,
            message=done_message,
            extra=done_extra,
        )

        logger.info("export done job_id=%s source=%s fmt=%s collected=%s", job_id, source, fmt, len(papers))

        return {
            "ok": True,
            "status": "done",
            "job_id": job_id,
            "collected": len(papers),
            "records_before_final_dedup": records_before_final_dedup,
            "duplicates_removed": cross_source_duplicates_removed,
        }

    except Exception as e:
        tb = traceback.format_exc(limit=10)
        await mark_job_error(
            r,
            job_id,
            source=source or "unknown",
            collected=collected,
            limit=limit if "limit" in locals() else 0,
            error=repr(e),
        )
        metrics.error_count = 1
        logger.error("export failed job_id=%s error=%r\n%s", job_id, e, tb)
        return {"ok": False, "status": "failed", "job_id": job_id, "error": repr(e)}
