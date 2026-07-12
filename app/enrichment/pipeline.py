from __future__ import annotations

import logging
from typing import Iterable, List, Optional, Sequence

from app.enrichment.base import (
    EnrichmentProvider,
    EnrichmentResult,
)
from app.enrichment.merge import merge_enrichment_result
from app.models.paper import Paper

logger = logging.getLogger(__name__)


async def enrich_paper(
    paper: Paper,
    providers: Sequence[EnrichmentProvider],
) -> Paper:
    """
    Enrich one Paper using the configured providers.

    Provider failures are logged and never interrupt retrieval.
    """

    for provider in providers:
        try:
            result = await provider.enrich(paper)
        except Exception:
            logger.exception(
                "ENRICHMENT provider=%s paper_id=%s status=failed",
                provider.name,
                paper.id,
            )
            continue

        if not isinstance(result, EnrichmentResult):
            logger.warning(
                "ENRICHMENT provider=%s paper_id=%s " "status=invalid_result",
                provider.name,
                paper.id,
            )
            continue

        changed_fields = merge_enrichment_result(paper, result)

        logger.debug(
            "ENRICHMENT provider=%s paper_id=%s matched=%s " "changed_fields=%s",
            provider.name,
            paper.id,
            result.matched,
            sorted(changed_fields),
        )

    return paper


async def enrich_papers(
    papers: Iterable[Paper],
    providers: Sequence[EnrichmentProvider],
    limit: Optional[int] = None,
) -> List[Paper]:
    """
    Enrich a collection of papers.

    When limit is set, only the first `limit` papers are enriched.
    All papers are still returned.
    """

    enriched_papers = list(papers)

    if limit is not None and limit < 0:
        raise ValueError("Enrichment limit must be zero or greater")

    papers_to_enrich = enriched_papers if limit is None else enriched_papers[:limit]

    for paper in papers_to_enrich:
        await enrich_paper(paper, providers)

    return enriched_papers
