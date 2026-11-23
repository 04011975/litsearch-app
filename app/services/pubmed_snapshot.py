from __future__ import annotations

import uuid


PUBMED_SNAPSHOT_TTL_SECONDS = 900


def create_pubmed_snapshot_id() -> str:
    """Generate a unique identifier for a PubMed result snapshot."""
    return uuid.uuid4().hex


def pubmed_snapshot_key(snapshot_id: str) -> str:
    """Return the Redis key for a PubMed result snapshot."""
    return f"pubmed:snapshot:{snapshot_id}"


from app.services.redis_policy import cache_set_json


async def store_pubmed_snapshot(
    redis,
    *,
    request_signature: str,
    papers: list[dict],
) -> str | None:
    """Store an ordered PubMed result page and return its snapshot ID."""
    if redis is None:
        return None

    snapshot_id = create_pubmed_snapshot_id()

    payload = {
        "request_signature": request_signature,
        "papers": papers,
    }

    stored = await cache_set_json(
        redis,
        pubmed_snapshot_key(snapshot_id),
        payload,
        PUBMED_SNAPSHOT_TTL_SECONDS,
    )

    return snapshot_id if stored else None


from app.services.redis_policy import cache_get_json


async def load_pubmed_snapshot(
    redis,
    *,
    snapshot_id: str,
    request_signature: str,
) -> list[dict] | None:
    """Load an ordered PubMed snapshot if its signature matches."""
    if redis is None or not snapshot_id:
        return None

    payload = await cache_get_json(
        redis,
        pubmed_snapshot_key(snapshot_id),
    )

    if not isinstance(payload, dict):
        return None

    if payload.get("request_signature") != request_signature:
        return None

    papers = payload.get("papers")

    if not isinstance(papers, list):
        return None

    if not all(isinstance(paper, dict) for paper in papers):
        return None

    return papers


def pubmed_snapshot_signature(
    *,
    q: str,
    sort: str,
    page: int,
    n: int,
    year_min: int | None,
    year_max: int | None,
    has_abstract: bool,
    mesh: str,
    mesh_mode: str,
) -> str:
    """Build a deterministic signature for a PubMed result page."""
    return "|".join(
        [
            "v1",
            (q or "").strip(),
            (sort or "").strip(),
            str(page),
            str(n),
            str(year_min) if year_min is not None else "",
            str(year_max) if year_max is not None else "",
            "1" if has_abstract else "0",
            (mesh or "").strip(),
            (mesh_mode or "or").strip().lower(),
        ]
    )
