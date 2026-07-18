from __future__ import annotations

from app.connectors.pubmed import (
    pubmed_fetch_mesh_terms,
    pubmed_resolve_pmid_by_doi,
)

from app.enrichment.base import EnrichmentResult
from app.models.paper import Paper


class PubMedMeshProvider:
    """Enrich papers with MeSH descriptor terms from PubMed."""

    name = "pubmed_mesh"

    async def enrich(self, paper: Paper) -> EnrichmentResult:
        pmid = await self._get_pmid(paper)

        if pmid is None:
            return EnrichmentResult(matched=False)

        mesh_terms = await pubmed_fetch_mesh_terms(pmid)

        if not mesh_terms:
            return EnrichmentResult(matched=False)

        return EnrichmentResult(
            values={
                "mesh_terms": mesh_terms,
            },
            sources={
                "mesh_terms": ["pubmed"],
            },
            matched=True,
        )

    @staticmethod
    async def _get_pmid(paper: Paper) -> str | None:
        paper_id = str(paper.id or "").strip()

        if paper.source == "pubmed":
            if not paper_id.isdigit():
                return None

            return paper_id

        doi = str(paper.doi or "").strip()

        if not doi:
            return None

        return await pubmed_resolve_pmid_by_doi(doi)
