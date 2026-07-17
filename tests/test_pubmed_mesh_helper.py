from unittest.mock import AsyncMock, patch

import pytest

from app.connectors.pubmed import pubmed_fetch_mesh_terms
from app.models.paper import Paper


@pytest.mark.anyio
async def test_pubmed_fetch_mesh_terms_returns_empty_for_empty_pmid() -> None:
    with patch(
        "app.connectors.pubmed.pubmed_fetch_details",
        new_callable=AsyncMock,
    ) as fetch_details:
        result = await pubmed_fetch_mesh_terms("")

    assert result == []
    fetch_details.assert_not_awaited()


@pytest.mark.anyio
async def test_pubmed_fetch_mesh_terms_returns_empty_for_non_numeric_pmid() -> None:
    with patch(
        "app.connectors.pubmed.pubmed_fetch_details",
        new_callable=AsyncMock,
    ) as fetch_details:
        result = await pubmed_fetch_mesh_terms("not-a-pmid")

    assert result == []
    fetch_details.assert_not_awaited()


@pytest.mark.anyio
async def test_pubmed_fetch_mesh_terms_returns_empty_when_record_not_found() -> None:
    with patch(
        "app.connectors.pubmed.pubmed_fetch_details",
        new_callable=AsyncMock,
        return_value=[],
    ) as fetch_details:
        result = await pubmed_fetch_mesh_terms("12345678")

    assert result == []
    fetch_details.assert_awaited_once_with(
        ["12345678"],
        api_key=None,
        tool=None,
        email=None,
    )


@pytest.mark.anyio
async def test_pubmed_fetch_mesh_terms_returns_unique_terms() -> None:
    paper = Paper(
        id="12345678",
        source="pubmed",
        title="Example paper",
        mesh_terms=[
            "Breast Neoplasms",
            "Immunotherapy",
            "breast neoplasms",
            "",
            "  Immunotherapy  ",
        ],
    )

    with patch(
        "app.connectors.pubmed.pubmed_fetch_details",
        new_callable=AsyncMock,
        return_value=[paper],
    ) as fetch_details:
        result = await pubmed_fetch_mesh_terms(
            " 12345678 ",
            api_key="test-key",
            tool="LitSearchTest",
            email="test@example.com",
        )

    assert result == [
        "Breast Neoplasms",
        "Immunotherapy",
    ]

    fetch_details.assert_awaited_once_with(
        ["12345678"],
        api_key="test-key",
        tool="LitSearchTest",
        email="test@example.com",
    )


@pytest.mark.anyio
async def test_pubmed_fetch_mesh_terms_does_not_mutate_paper() -> None:
    original_terms = [
        "Breast Neoplasms",
        "breast neoplasms",
    ]

    paper = Paper(
        id="12345678",
        source="pubmed",
        title="Example paper",
        mesh_terms=list(original_terms),
    )

    with patch(
        "app.connectors.pubmed.pubmed_fetch_details",
        new_callable=AsyncMock,
        return_value=[paper],
    ):
        result = await pubmed_fetch_mesh_terms("12345678")

    assert result == ["Breast Neoplasms"]
    assert paper.mesh_terms == original_terms
