import asyncio

from app.enrichment.base import EnrichmentResult
from app.enrichment.pipeline import (
    enrich_paper,
    enrich_papers,
)
from app.models.paper import Paper


class SuccessfulProvider:
    name = "successful_provider"

    async def enrich(self, paper: Paper) -> EnrichmentResult:
        return EnrichmentResult(
            matched=True,
            values={"concepts": ["Cancer research"]},
            sources={"concepts": ["successful_provider"]},
        )


class FailingProvider:
    name = "failing_provider"

    async def enrich(self, paper: Paper) -> EnrichmentResult:
        raise RuntimeError("Provider unavailable")


class CountingProvider:
    name = "counting_provider"

    def __init__(self) -> None:
        self.calls = 0

    async def enrich(self, paper: Paper) -> EnrichmentResult:
        self.calls += 1

        return EnrichmentResult(
            matched=True,
            values={"citation_count": self.calls},
            sources={"citation_count": ["counting_provider"]},
        )


def test_enrich_paper_applies_provider_result():
    paper = Paper(
        id="paper-1",
        source="crossref",
    )

    enriched = asyncio.run(
        enrich_paper(
            paper,
            providers=[SuccessfulProvider()],
        )
    )

    assert enriched is paper
    assert paper.concepts == ["Cancer research"]
    assert paper.enrichment_sources == {"concepts": ["successful_provider"]}


def test_provider_failure_does_not_interrupt_pipeline():
    paper = Paper(
        id="paper-1",
        source="crossref",
    )

    enriched = asyncio.run(
        enrich_paper(
            paper,
            providers=[
                FailingProvider(),
                SuccessfulProvider(),
            ],
        )
    )

    assert enriched is paper
    assert paper.concepts == ["Cancer research"]


def test_enrich_papers_respects_limit():
    papers = [
        Paper(id="paper-1"),
        Paper(id="paper-2"),
        Paper(id="paper-3"),
    ]
    provider = CountingProvider()

    enriched = asyncio.run(
        enrich_papers(
            papers,
            providers=[provider],
            limit=2,
        )
    )

    assert enriched == papers
    assert provider.calls == 2
    assert papers[0].citation_count == 1
    assert papers[1].citation_count == 2
    assert papers[2].citation_count is None


def test_enrich_papers_rejects_negative_limit():
    papers = [Paper(id="paper-1")]

    try:
        asyncio.run(
            enrich_papers(
                papers,
                providers=[],
                limit=-1,
            )
        )
    except ValueError as exc:
        assert str(exc) == ("Enrichment limit must be zero or greater")
    else:
        raise AssertionError("Expected ValueError")
