# app/jobs/epmc_tasks.py
from __future__ import annotations

import asyncio
import hashlib
import os
import time
from typing import Any, Optional

from arq.connections import ArqRedis

from app.connectors.europe_pmc import europe_pmc_search

EUROPE_PMC_MAX_PAGES = int(os.environ.get("EUROPE_PMC_MAX_PAGES", "200"))
EUROPE_PMC_CURSOR_TTL_SECONDS = int(os.environ.get("EUROPE_PMC_CURSOR_TTL_SECONDS", "86400"))

# Chunk size = aantal records per chunk (moet matchen met main.py helper)
EPMC_CHUNK_SIZE = int(os.environ.get("EUROPE_PMC_BUILD_PAGE_SIZE", "500"))

# Hoeveel records per API call tijdens bouwen (connector kan dit cap'en, bv. naar 100)
EPMC_BUILD_BATCH_SIZE = int(os.environ.get("EPMC_BUILD_BATCH_SIZE", "100"))

# throttle tussen calls (Europe PMC kan gevoelig zijn)
EPMC_THROTTLE_SECONDS = float(os.environ.get("EUROPE_PMC_THROTTLE_SECONDS", "0.0"))

# lock settings
LOCK_TTL_MS = int(os.environ.get("EUROPE_PMC_LOCK_TTL_MS", "120000"))  # 2 min


def _as_str(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, (bytes, bytearray, memoryview)):
        return bytes(v).decode("utf-8", errors="ignore").strip()
    return str(v).strip()


def _safe_int(v: Any, default: Optional[int] = None) -> Optional[int]:
    try:
        if v is None:
            return default
        s = str(v).strip()
        if not s:
            return default
        return int(s)
    except Exception:
        return default


def _normalize_mesh(mesh: str) -> str:
    raw = (mesh or "").strip()
    if not raw:
        return ""
    # accept "a|b,c" style
    parts = []
    for chunk in raw.replace(",", "|").split("|"):
        c = chunk.strip()
        if c:
            parts.append(c)
    # dedup preserve order
    seen = set()
    out = []
    for p in parts:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return "|".join(out)


def _epmc_filters_key(
    *,
    year_min: Optional[int] = None,
    year_max: Optional[int] = None,
    has_abstract: int = 0,
    mesh: str = "",
) -> str:
    ymn = "" if year_min is None else str(int(year_min))
    ymx = "" if year_max is None else str(int(year_max))
    ha = "1" if int(has_abstract or 0) else "0"
    m = _normalize_mesh(mesh or "")
    return f"ymin={ymn}:ymax={ymx}:abs={ha}:mesh={m}"


def epmc_cache_key(
    q: str,
    *,
    n: int,
    sort: str,
    year_min: Optional[int] = None,
    year_max: Optional[int] = None,
    has_abstract: int = 0,
    mesh: str = "",
) -> str:
    """
    FILTER-AWARE cache key. Prevents cursor collisions between different year/abstract/mesh filters.
    """
    fkey = _epmc_filters_key(year_min=year_min, year_max=year_max, has_abstract=has_abstract, mesh=mesh)
    h = hashlib.sha1(f"{q}::{n}::{sort}::{fkey}".encode("utf-8")).hexdigest()[:16]
    return f"epmc:cursor:{h}"


def epmc_build_key(
    q: str,
    *,
    n: int,
    sort: str,
    year_min: Optional[int] = None,
    year_max: Optional[int] = None,
    has_abstract: int = 0,
    mesh: str = "",
) -> str:
    fkey = _epmc_filters_key(year_min=year_min, year_max=year_max, has_abstract=has_abstract, mesh=mesh)
    h = hashlib.sha1(f"{q}::{n}::{sort}::{fkey}".encode("utf-8")).hexdigest()[:16]
    return f"epmc:build:{h}"


def _epmc_lock_key(
    q: str,
    *,
    n: int,
    sort: str,
    year_min: Optional[int] = None,
    year_max: Optional[int] = None,
    has_abstract: int = 0,
    mesh: str = "",
) -> str:
    fkey = _epmc_filters_key(year_min=year_min, year_max=year_max, has_abstract=has_abstract, mesh=mesh)
    h = hashlib.sha1(f"{q}::{n}::{sort}::{fkey}".encode("utf-8")).hexdigest()[:16]
    return f"epmc:lock:{h}"


def _page_to_chunk(*, page: int, ui_n: int) -> int:
    page = max(1, int(page))
    ui_n = max(1, int(ui_n))
    offset = (page - 1) * ui_n
    return (offset // max(1, EPMC_CHUNK_SIZE)) + 1


def _build_epmc_query(
    q: str,
    *,
    year_min: Optional[int] = None,
    year_max: Optional[int] = None,
    has_abstract: int = 0,
    mesh: str = "",
) -> str:
    """
    Compose a Europe PMC query string including filters.

    Year filter:
      FIRST_PDATE:[YYYY-01-01 TO YYYY-12-31] (inclusive-ish)
      If only year_min: [YYYY-01-01 TO 3000-12-31]
      If only year_max: [1000-01-01 TO YYYY-12-31]

    Abstract filter:
      HAS_ABSTRACT:Y

    MeSH filter:
      MESH:"term" OR MESH:"term2"  (joined with OR)
    """
    q = (q or "").strip()
    if not q:
        return ""

    parts = [f"({q})"]

    ymn = _safe_int(year_min, None)
    ymx = _safe_int(year_max, None)
    if ymn is not None or ymx is not None:
        start_year = ymn if ymn is not None else 1000
        end_year = ymx if ymx is not None else 3000
        # normalize if reversed
        if ymn is not None and ymx is not None and ymn > ymx:
            start_year, end_year = end_year, start_year
        parts.append(f'FIRST_PDATE:[{start_year}-01-01 TO {end_year}-12-31]')

    if int(has_abstract or 0):
        parts.append("HAS_ABSTRACT:Y")

    mesh_norm = _normalize_mesh(mesh or "")
    if mesh_norm:
        terms = [t for t in mesh_norm.split("|") if t.strip()]
        if terms:
            # quote terms; Europe PMC query accepts MESH:"...".
            mesh_q = " OR ".join([f'MESH:"{t}"' for t in terms])
            parts.append(f"({mesh_q})")

    return " AND ".join(parts)


async def _call_epmc(
    q: str,
    *,
    n: int,
    cursor: str,
    sort: str,
    year_min: Optional[int] = None,
    year_max: Optional[int] = None,
    has_abstract: int = 0,
    mesh: str = "",
) -> tuple:
    """
    europe_pmc_search is blocking (requests) → thread
    """
    qq = _build_epmc_query(q, year_min=year_min, year_max=year_max, has_abstract=has_abstract, mesh=mesh)
    return await asyncio.to_thread(europe_pmc_search, qq, n=n, cursor=cursor, sort=sort)


async def build_epmc_cursors(
    ctx: dict,
    *,
    q: str,
    n: int,
    sort: str,
    # NEW canonical:
    target_chunk: Optional[int] = None,
    # BACKCOMPAT:
    target_page: Optional[int] = None,
    # NEW filters (optional)
    year_min: Optional[int] = None,
    year_max: Optional[int] = None,
    has_abstract: int = 0,
    mesh: str = "",
) -> dict:
    """
    Chunk-based cursor chain builder (FILTER-AWARE).

    Cache hash (ck):
      field "1" = "*" (cursorMark for chunk 1 start)
      field "2" = cursorMark that starts chunk 2
      ...
      field "chunk_size" = EPMC_CHUNK_SIZE (debug/compat)
    """
    r: ArqRedis = ctx["redis"]

    q = (q or "").strip()
    if not q:
        return {"ok": False, "status": "failed", "error": "empty_query"}

    sort = (sort or "relevance").strip() or "relevance"
    ui_n = max(1, int(n))

    year_min_i = _safe_int(year_min, None)
    year_max_i = _safe_int(year_max, None)
    has_abstract_i = int(has_abstract or 0)
    mesh_norm = _normalize_mesh(mesh or "")

    # -------------------------
    # Backward compatibility
    # -------------------------
    if target_chunk is None:
        if target_page is None:
            return {"ok": False, "status": "failed", "error": "missing_target"}
        try:
            target_chunk = _page_to_chunk(page=int(target_page), ui_n=ui_n)
        except Exception:
            return {"ok": False, "status": "failed", "error": "bad_target_page"}

    target_chunk = max(1, int(target_chunk))

    # Safety cap
    max_chunks = max(1, ((EUROPE_PMC_MAX_PAGES * ui_n) // max(1, EPMC_CHUNK_SIZE)) + 1)
    target_chunk = min(target_chunk, max_chunks)

    # build batch size (connector kan dit alsnog cap’en)
    build_n = max(1, min(int(EPMC_BUILD_BATCH_SIZE), 500))

    bk = epmc_build_key(
        q,
        n=ui_n,
        sort=sort,
        year_min=year_min_i,
        year_max=year_max_i,
        has_abstract=has_abstract_i,
        mesh=mesh_norm,
    )
    ck = epmc_cache_key(
        q,
        n=ui_n,
        sort=sort,
        year_min=year_min_i,
        year_max=year_max_i,
        has_abstract=has_abstract_i,
        mesh=mesh_norm,
    )
    lk = _epmc_lock_key(
        q,
        n=ui_n,
        sort=sort,
        year_min=year_min_i,
        year_max=year_max_i,
        has_abstract=has_abstract_i,
        mesh=mesh_norm,
    )

    now = int(time.time())

    # -------------------------
    # Acquire lock (best-effort)
    # -------------------------
    lock_token = f"{now}:{os.getpid()}"
    got_lock = await r.set(lk, lock_token, nx=True, px=LOCK_TTL_MS)
    if not got_lock:
        await r.hset(
            bk,
            mapping={
                "status": "running",
                "target_chunk": str(target_chunk),
                "updated_at": str(now),
                "note": "lock_busy",
            },
        )
        await r.expire(bk, EUROPE_PMC_CURSOR_TTL_SECONDS)
        return {"ok": True, "status": "lock_busy"}

    async def _refresh_lock() -> None:
        cur = _as_str(await r.get(lk))
        if cur == lock_token:
            await r.pexpire(lk, LOCK_TTL_MS)

    async def _release_lock() -> None:
        cur = _as_str(await r.get(lk))
        if cur == lock_token:
            await r.delete(lk)

    try:
        # Seed chunk 1 start cursor
        await r.hset(ck, mapping={"1": "*"})
        await r.hsetnx(ck, "chunk_size", str(int(EPMC_CHUNK_SIZE)))
        await r.expire(ck, EUROPE_PMC_CURSOR_TTL_SECONDS)

        # Determine highest built chunk
        fields = await r.hkeys(ck)
        built_up_to = 1
        for f in fields or []:
            s = _as_str(f)
            if s.isdigit():
                built_up_to = max(built_up_to, int(s))

        if built_up_to >= target_chunk:
            await r.hset(
                bk,
                mapping={
                    "status": "done",
                    "target_chunk": str(target_chunk),
                    "built_up_to_chunk": str(built_up_to),
                    "updated_at": str(int(time.time())),
                },
            )
            await r.expire(bk, EUROPE_PMC_CURSOR_TTL_SECONDS)
            return {"ok": True, "status": "already_built", "built_up_to_chunk": built_up_to}

        await r.hset(
            bk,
            mapping={
                "status": "running",
                "target_chunk": str(target_chunk),
                "built_up_to_chunk": str(built_up_to),
                "started_at": str(now),
                "updated_at": str(now),
                "chunk_size": str(int(EPMC_CHUNK_SIZE)),
                "build_n": str(int(build_n)),
                "year_min": "" if year_min_i is None else str(year_min_i),
                "year_max": "" if year_max_i is None else str(year_max_i),
                "has_abstract": str(has_abstract_i),
                "mesh": mesh_norm,
            },
        )
        await r.expire(bk, EUROPE_PMC_CURSOR_TTL_SECONDS)

        # Start cursor at built_up_to chunk start
        cursor = _as_str(await r.hget(ck, str(built_up_to))) or "*"
        chunk_now = built_up_to

        # Advance exactly EPMC_CHUNK_SIZE records per chunk
        full_steps = EPMC_CHUNK_SIZE // build_n
        remainder = EPMC_CHUNK_SIZE % build_n

        while chunk_now < target_chunk:
            await _refresh_lock()

            for step_i in range(full_steps):
                _papers, _total, next_cursor = await _call_epmc(
                    q,
                    n=build_n,
                    cursor=cursor,
                    sort=sort,
                    year_min=year_min_i,
                    year_max=year_max_i,
                    has_abstract=has_abstract_i,
                    mesh=mesh_norm,
                )
                if not next_cursor:
                    await r.hset(
                        bk,
                        mapping={
                            "status": "failed",
                            "last_error": (
                                f"No nextCursorMark while advancing chunk={chunk_now} "
                                f"step={step_i+1}/{full_steps + (1 if remainder else 0)}"
                            ),
                            "built_up_to_chunk": str(chunk_now),
                            "updated_at": str(int(time.time())),
                        },
                    )
                    await r.expire(bk, EUROPE_PMC_CURSOR_TTL_SECONDS)
                    return {"ok": False, "status": "failed_no_next_cursor", "chunk": chunk_now, "step": step_i + 1}

                cursor = next_cursor
                if EPMC_THROTTLE_SECONDS > 0:
                    await asyncio.sleep(EPMC_THROTTLE_SECONDS)

            if remainder:
                _papers, _total, next_cursor = await _call_epmc(
                    q,
                    n=remainder,
                    cursor=cursor,
                    sort=sort,
                    year_min=year_min_i,
                    year_max=year_max_i,
                    has_abstract=has_abstract_i,
                    mesh=mesh_norm,
                )
                if not next_cursor:
                    await r.hset(
                        bk,
                        mapping={
                            "status": "failed",
                            "last_error": f"No nextCursorMark while advancing chunk={chunk_now} remainder={remainder}",
                            "built_up_to_chunk": str(chunk_now),
                            "updated_at": str(int(time.time())),
                        },
                    )
                    await r.expire(bk, EUROPE_PMC_CURSOR_TTL_SECONDS)
                    return {"ok": False, "status": "failed_no_next_cursor", "chunk": chunk_now, "remainder": remainder}

                cursor = next_cursor
                if EPMC_THROTTLE_SECONDS > 0:
                    await asyncio.sleep(EPMC_THROTTLE_SECONDS)

            chunk_now += 1
            await r.hset(ck, mapping={str(chunk_now): cursor})
            await r.expire(ck, EUROPE_PMC_CURSOR_TTL_SECONDS)

            await r.hset(
                bk,
                mapping={
                    "status": "running",
                    "built_up_to_chunk": str(chunk_now),
                    "updated_at": str(int(time.time())),
                },
            )
            await r.expire(bk, EUROPE_PMC_CURSOR_TTL_SECONDS)

        await r.hset(
            bk,
            mapping={
                "status": "done",
                "built_up_to_chunk": str(chunk_now),
                "updated_at": str(int(time.time())),
            },
        )
        await r.expire(bk, EUROPE_PMC_CURSOR_TTL_SECONDS)
        return {"ok": True, "status": "done", "built_up_to_chunk": chunk_now}

    finally:
        await _release_lock()