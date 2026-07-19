from __future__ import annotations

import asyncio
import os
from typing import Any
from urllib.parse import quote

import httpx

OPENCITATIONS_API_BASE_URL = os.getenv(
    "OPENCITATIONS_API_BASE_URL",
    "https://api.opencitations.net/index/v2",
).rstrip("/")

OPENCITATIONS_ACCESS_TOKEN = os.getenv(
    "OPENCITATIONS_ACCESS_TOKEN",
    "",
).strip()

OPENCITATIONS_TIMEOUT_SECONDS = float(os.getenv("OPENCITATIONS_TIMEOUT_SECONDS", "20"))


def normalize_doi(value: str | None) -> str | None:
    """Normalize a DOI for use with the OpenCitations API."""

    doi = str(value or "").strip()

    if not doi:
        return None

    lowered = doi.casefold()

    prefixes = (
        "https://doi.org/",
        "http://doi.org/",
        "https://dx.doi.org/",
        "http://dx.doi.org/",
        "doi:",
    )

    for prefix in prefixes:
        if lowered.startswith(prefix):
            doi = doi[len(prefix) :].strip()
            break

    if not doi.casefold().startswith("10."):
        return None

    return doi.lower()


def _headers() -> dict[str, str]:
    headers = {
        "Accept": "application/json",
    }

    if OPENCITATIONS_ACCESS_TOKEN:
        headers["authorization"] = OPENCITATIONS_ACCESS_TOKEN

    return headers


def _parse_count(payload: Any) -> int | None:
    """
    Parse an OpenCitations count response.

    Expected response:
        [{"count": "34"}]
    """

    if not isinstance(payload, list) or not payload:
        return None

    first_result = payload[0]

    if not isinstance(first_result, dict):
        return None

    raw_count = first_result.get("count")

    try:
        count = int(raw_count)
    except (TypeError, ValueError):
        return None

    if count < 0:
        return None

    return count


async def _fetch_count(
    client: httpx.AsyncClient,
    operation: str,
    doi: str,
) -> int | None:
    identifier = quote(f"doi:{doi}", safe=":")
    url = f"{OPENCITATIONS_API_BASE_URL}/{operation}/{identifier}"

    response = await client.get(url)
    response.raise_for_status()

    return _parse_count(response.json())


async def opencitations_fetch_counts(
    doi: str,
) -> tuple[int | None, int | None]:
    """
    Retrieve incoming citation and outgoing reference counts for a DOI.

    Returns:
        (citation_count, reference_count)
    """

    normalized_doi = normalize_doi(doi)

    if normalized_doi is None:
        return None, None

    timeout = httpx.Timeout(OPENCITATIONS_TIMEOUT_SECONDS)

    async with httpx.AsyncClient(
        headers=_headers(),
        timeout=timeout,
        follow_redirects=True,
    ) as client:
        citation_count, reference_count = await asyncio.gather(
            _fetch_count(
                client,
                "citation-count",
                normalized_doi,
            ),
            _fetch_count(
                client,
                "reference-count",
                normalized_doi,
            ),
        )

    return citation_count, reference_count
