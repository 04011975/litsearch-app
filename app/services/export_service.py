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