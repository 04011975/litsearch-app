from unittest.mock import AsyncMock, patch

import pytest

from app.enrichment.providers.pubmed_mesh import PubMedMeshProvider
from app.models.paper import Paper


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def make_paper(
    *,
    paper_id: str = "12345678",
    source: str = "pubmed",
    mesh_terms: list[str] | None = None,
) -> Paper:
    return Paper(
        id=paper_id,
        source=source,
        title="Example paper",
        mesh_terms=list(mesh_terms or []),
    )


@pytest.mark.anyio
async def test_provider_does_not_match_non_pubmed_paper() -> None:
    provider = PubMedMeshProvider()
    paper = make_paper(source="openalex")

    with patch(
        "app.enrichment.providers.pubmed_mesh.pubmed_fetch_mesh_terms",
        new_callable=AsyncMock,
    ) as fetch_mesh:
        result = await provider.enrich(paper)

    assert result.matched is False
    assert result.values == {}
    assert result.sources == {}
    fetch_mesh.assert_not_awaited()


@pytest.mark.anyio
async def test_provider_does_not_match_invalid_pubmed_id() -> None:
    provider = PubMedMeshProvider()
    paper = make_paper(paper_id="not-a-pmid")

    with patch(
        "app.enrichment.providers.pubmed_mesh.pubmed_fetch_mesh_terms",
        new_callable=AsyncMock,
    ) as fetch_mesh:
        result = await provider.enrich(paper)

    assert result.matched is False
    fetch_mesh.assert_not_awaited()


@pytest.mark.anyio
async def test_provider_returns_unmatched_when_no_mesh_terms_found() -> None:
    provider = PubMedMeshProvider()
    paper = make_paper()

    with patch(
        "app.enrichment.providers.pubmed_mesh.pubmed_fetch_mesh_terms",
        new_callable=AsyncMock,
        return_value=[],
    ) as fetch_mesh:
        result = await provider.enrich(paper)

    assert result.matched is False
    assert result.values == {}
    assert result.sources == {}
    fetch_mesh.assert_awaited_once_with("12345678")


@pytest.mark.anyio
async def test_provider_returns_mesh_enrichment_result() -> None:
    provider = PubMedMeshProvider()
    paper = make_paper()

    with patch(
        "app.enrichment.providers.pubmed_mesh.pubmed_fetch_mesh_terms",
        new_callable=AsyncMock,
        return_value=[
            "Breast Neoplasms",
            "Immunotherapy",
        ],
    ) as fetch_mesh:
        result = await provider.enrich(paper)

    assert result.matched is True
    assert result.values == {
        "mesh_terms": [
            "Breast Neoplasms",
            "Immunotherapy",
        ]
    }
    assert result.sources == {
        "mesh_terms": ["pubmed"],
    }
    fetch_mesh.assert_awaited_once_with("12345678")


@pytest.mark.anyio
async def test_provider_does_not_mutate_paper_directly() -> None:
    provider = PubMedMeshProvider()
    paper = make_paper(mesh_terms=["Existing Term"])

    with patch(
        "app.enrichment.providers.pubmed_mesh.pubmed_fetch_mesh_terms",
        new_callable=AsyncMock,
        return_value=["New Term"],
    ):
        result = await provider.enrich(paper)

    assert result.matched is True
    assert paper.mesh_terms == ["Existing Term"]
    assert paper.enrichment_sources == {}


@pytest.mark.anyio
async def test_provider_integrates_with_enrichment_pipeline() -> None:
    from app.enrichment.pipeline import enrich_paper

    provider = PubMedMeshProvider()
    paper = make_paper(
        mesh_terms=[
            "Existing Term",
            "breast neoplasms",
        ]
    )

    with patch(
        "app.enrichment.providers.pubmed_mesh.pubmed_fetch_mesh_terms",
        new_callable=AsyncMock,
        return_value=[
            "Breast Neoplasms",
            "Immunotherapy",
        ],
    ):
        enriched = await enrich_paper(
            paper,
            providers=[provider],
        )

    assert enriched is paper
    assert paper.mesh_terms == [
        "Existing Term",
        "breast neoplasms",
        "Immunotherapy",
    ]
    assert paper.enrichment_sources == {
        "mesh_terms": ["pubmed"],
    }
