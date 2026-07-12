from __future__ import annotations

from typing import Optional, Protocol

from app.enrichment.base import EnrichmentResult


class EnrichmentCache(Protocol):
    """Storage contract for enrichment cache implementations."""

    async def get(self, key: str) -> Optional[EnrichmentResult]: ...

    async def set(
        self,
        key: str,
        result: EnrichmentResult,
        ttl_seconds: int,
    ) -> None: ...
