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
    doi: str | None = None,
    mesh_terms: list[str] | None = None,
) -> Paper:
    return Paper(
        id=paper_id,
        source=source,
        title="Example paper",
        doi=doi,
        mesh_terms=list(mesh_terms or []),
    )


@pytest.mark.anyio
async def test_provider_does_not_match_non_pubmed_paper_without_doi() -> None:
    provider = PubMedMeshProvider()
    paper = make_paper(source="openalex")

    with (
        patch(
            "app.enrichment.providers.pubmed_mesh.pubmed_resolve_pmid_by_doi",
            new_callable=AsyncMock,
        ) as resolve_pmid,
        patch(
            "app.enrichment.providers.pubmed_mesh.pubmed_fetch_mesh_terms",
            new_callable=AsyncMock,
        ) as fetch_mesh,
    ):
        result = await provider.enrich(paper)

    assert result.matched is False
    assert result.values == {}
    assert result.sources == {}
    resolve_pmid.assert_not_awaited()
    fetch_mesh.assert_not_awaited()


@pytest.mark.anyio
@pytest.mark.parametrize(
    "source",
    [
        "crossref",
        "openalex",
        "europe_pmc",
    ],
)
async def test_provider_resolves_non_pubmed_paper_by_doi(source: str) -> None:
    provider = PubMedMeshProvider()
    paper = make_paper(
        paper_id=f"{source}-record",
        source=source,
        doi="10.1000/example",
    )

    with (
        patch(
            "app.enrichment.providers.pubmed_mesh.pubmed_resolve_pmid_by_doi",
            new_callable=AsyncMock,
            return_value="87654321",
        ) as resolve_pmid,
        patch(
            "app.enrichment.providers.pubmed_mesh.pubmed_fetch_mesh_terms",
            new_callable=AsyncMock,
            return_value=[
                "Breast Neoplasms",
                "Immunotherapy",
            ],
        ) as fetch_mesh,
    ):
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
    resolve_pmid.assert_awaited_once_with("10.1000/example")
    fetch_mesh.assert_awaited_once_with("87654321")


@pytest.mark.anyio
async def test_provider_returns_unmatched_when_doi_has_no_pubmed_match() -> None:
    provider = PubMedMeshProvider()
    paper = make_paper(
        paper_id="crossref-record",
        source="crossref",
        doi="10.1000/not-found",
    )

    with (
        patch(
            "app.enrichment.providers.pubmed_mesh.pubmed_resolve_pmid_by_doi",
            new_callable=AsyncMock,
            return_value=None,
        ) as resolve_pmid,
        patch(
            "app.enrichment.providers.pubmed_mesh.pubmed_fetch_mesh_terms",
            new_callable=AsyncMock,
        ) as fetch_mesh,
    ):
        result = await provider.enrich(paper)

    assert result.matched is False
    assert result.values == {}
    assert result.sources == {}
    resolve_pmid.assert_awaited_once_with("10.1000/not-found")
    fetch_mesh.assert_not_awaited()


@pytest.mark.anyio
async def test_provider_does_not_resolve_doi_for_pubmed_paper() -> None:
    provider = PubMedMeshProvider()
    paper = make_paper(
        paper_id="12345678",
        source="pubmed",
        doi="10.1000/example",
    )

    with (
        patch(
            "app.enrichment.providers.pubmed_mesh.pubmed_resolve_pmid_by_doi",
            new_callable=AsyncMock,
        ) as resolve_pmid,
        patch(
            "app.enrichment.providers.pubmed_mesh.pubmed_fetch_mesh_terms",
            new_callable=AsyncMock,
            return_value=["Example Term"],
        ) as fetch_mesh,
    ):
        result = await provider.enrich(paper)

    assert result.matched is True
    resolve_pmid.assert_not_awaited()
    fetch_mesh.assert_awaited_once_with("12345678")


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
