from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Protocol

from app.models.paper import Paper


@dataclass
class EnrichmentResult:
    """Metadata returned by one enrichment provider."""

    values: Dict[str, Any] = field(default_factory=dict)
    sources: Dict[str, List[str]] = field(default_factory=dict)
    matched: bool = False


class EnrichmentProvider(Protocol):
    """Contract implemented by every enrichment provider."""

    name: str

    async def enrich(self, paper: Paper) -> EnrichmentResult: ...
