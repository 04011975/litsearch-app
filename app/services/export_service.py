# app/services/export_service.py

from __future__ import annotations

from dataclasses import dataclass 

@dataclass(frozen=True)
class ExportRequestParams:
    q: str
    source: str
    fmt: str
    scope: str
    sort: str
    n: int
    page: int
    bulk_limit: int
    year_min: str = ""
    year_max: str = ""
    has_abstract: int = 0
    mesh: str = ""
    mesh_mode: str = "or"
    token: str | None = None

def build_export_request_params(
    *,
    query_params: dict[str, str],
    fmt: str,
    scope: str,
    bulk_limit: int,
    normalize_sort,
    normalize_mesh,
    safe_int,
    max_page_size: int = 50,
) -> ExportRequestParams:
    q = (query_params.get("q") or "").strip()
    source = (query_params.get("source") or "pubmed").strip()
    n = max(1, min(int(safe_int(query_params.get("n"), 10) or 10), max_page_size))
    page = max(1, int(safe_int(query_params.get("page"), 1) or 1))
    token = (query_params.get("token") or "").strip() or None

    sort = normalize_sort(query_params.get("sort") or "relevance")
    mesh = normalize_mesh(query_params.get("mesh", "") or "")
    year_min = (query_params.get("year_min") or "").strip()
    year_max = (query_params.get("year_max") or "").strip()
    has_abstract = int(safe_int(query_params.get("has_abstract"), 0) or 0)

    mesh_mode = (query_params.get("mesh_mode") or "or").strip().lower()
    if mesh_mode not in {"and", "or"}:
        mesh_mode = "or"

    return ExportRequestParams(
        q=q,
        source=source,
        fmt=fmt,
        scope=scope,
        sort=sort,
        n=n,
        page=page,
        bulk_limit=bulk_limit,
        year_min=year_min,
        year_max=year_max,
        has_abstract=has_abstract,
        mesh=mesh,
        mesh_mode=mesh_mode,
        token=token,
    )

def validate_export_request_params(
    params: ExportRequestParams,
    *,
    allowed_sources: set[str],
    export_hard_cap: int,
    safe_int,
) -> int:
    if not params.q:
        raise ValueError("Query is empty")

    if params.source not in allowed_sources:
        raise ValueError(f"Unknown source: {params.source}")

    year_min_i = safe_int(params.year_min, None)
    year_max_i = safe_int(params.year_max, None)

    if year_min_i is not None and year_max_i is not None and year_min_i > year_max_i:
        raise ValueError("year_min must be <= year_max")

    return min(max(1, int(params.bulk_limit)), int(export_hard_cap))