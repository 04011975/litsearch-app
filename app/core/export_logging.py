import logging
from typing import Any


logger = logging.getLogger("litsearch.export")


def log_export_event(event: str, **fields: Any) -> None:
    payload = {"event": event, **fields}
    logger.info(payload)


def log_export_job_started(
    *,
    job_id: str,
    source: str,
    fmt: str,
    query: str,
    limit: int,
    batch_size: int | None = None,
    sort: str | None = None,
    mode: str | None = None,
) -> None:
    payload = {
        "job_id": job_id,
        "source": source,
        "fmt": fmt,
        "query": query,
        "limit": limit,
        "batch_size": batch_size,
        "sort": sort,
        "mode": mode,
    }
    log_export_event("export_job_started", **payload)


def log_export_batch_completed(
    *,
    job_id: str,
    source: str,
    batch_index: int,
    batch_size_requested: int,
    batch_size_effective: int,
    records_returned: int,
    duration_ms: float,
    cache_hits: int = 0,
    cache_misses: int = 0,
    retry_count: int = 0,
    status: str = "ok",
    extra: dict[str, Any] | None = None,
) -> None:
    payload = {
        "job_id": job_id,
        "source": source,
        "batch_index": batch_index,
        "batch_size_requested": batch_size_requested,
        "batch_size_effective": batch_size_effective,
        "records_returned": records_returned,
        "duration_ms": round(duration_ms, 2),
        "cache_hits": cache_hits,
        "cache_misses": cache_misses,
        "retry_count": retry_count,
        "status": status,
    }
    if extra:
        payload.update(extra)

    log_export_event("export_batch_completed", **payload)


def log_export_batch_failed(
    *,
    job_id: str,
    source: str,
    batch_index: int,
    batch_size_requested: int,
    duration_ms: float,
    retry_count: int = 0,
    error_type: str | None = None,
    error_message: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    payload = {
        "job_id": job_id,
        "source": source,
        "batch_index": batch_index,
        "batch_size_requested": batch_size_requested,
        "duration_ms": round(duration_ms, 2),
        "retry_count": retry_count,
        "status": "error",
        "error_type": error_type,
        "error_message": error_message,
    }
    if extra:
        payload.update(extra)

    log_export_event("export_batch_failed", **payload)


def log_export_job_completed(
    *,
    job_id: str,
    source: str,
    total_records: int,
    total_batches: int,
    total_duration_ms: float,
    cache_hits: int = 0,
    cache_misses: int = 0,
    retry_count: int = 0,
    error_count: int = 0,
    extra: dict[str, Any] | None = None,
) -> None:
    payload = {
        "job_id": job_id,
        "source": source,
        "total_records": total_records,
        "total_batches": total_batches,
        "total_duration_ms": round(total_duration_ms, 2),
        "cache_hits": cache_hits,
        "cache_misses": cache_misses,
        "retry_count": retry_count,
        "error_count": error_count,
    }
    if extra:
        payload.update(extra)

    log_export_event("export_job_completed", **payload)