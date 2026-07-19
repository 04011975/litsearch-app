from __future__ import annotations

from app.connectors.opencitations import opencitations_fetch_counts
from app.enrichment.base import EnrichmentResult
from app.models.paper import Paper


class OpenCitationsProvider:
    """Enrich DOI-identified papers with OpenCitations counts."""

    name = "opencitations"

    async def enrich(self, paper: Paper) -> EnrichmentResult:
        doi = str(paper.doi or "").strip()

        if not doi:
            return EnrichmentResult(matched=False)

        citation_count, reference_count = await opencitations_fetch_counts(doi)

        values: dict[str, int] = {}
        sources: dict[str, list[str]] = {}

        if citation_count is not None:
            values["citation_count"] = citation_count
            sources["citation_count"] = ["opencitations"]

        if reference_count is not None:
            values["reference_count"] = reference_count
            sources["reference_count"] = ["opencitations"]

        if not values:
            return EnrichmentResult(matched=False)

        return EnrichmentResult(
            values=values,
            sources=sources,
            matched=True,
        )
