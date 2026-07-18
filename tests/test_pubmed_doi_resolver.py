from __future__ import annotations

import pytest

from app.connectors import pubmed


@pytest.mark.anyio
async def test_pubmed_resolve_pmid_by_doi_returns_none_for_empty_doi() -> None:
    result = await pubmed.pubmed_resolve_pmid_by_doi("")

    assert result is None


@pytest.mark.anyio
async def test_pubmed_resolve_pmid_by_doi_normalizes_doi_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_params: dict[str, object] = {}

    async def fake_get_json(
        url: str,
        *,
        params: dict[str, object],
        timeout: float = 30.0,
    ) -> dict:
        captured_params.update(params)
        return {
            "esearchresult": {
                "idlist": ["12345678"],
            }
        }

    monkeypatch.setattr(pubmed, "_get_json", fake_get_json)

    result = await pubmed.pubmed_resolve_pmid_by_doi("https://doi.org/10.1000/Example")

    assert result == "12345678"
    assert captured_params["term"] == '"10.1000/Example"[AID]'


@pytest.mark.anyio
async def test_pubmed_resolve_pmid_by_doi_returns_none_when_no_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_get_json(
        url: str,
        *,
        params: dict[str, object],
        timeout: float = 30.0,
    ) -> dict:
        return {
            "esearchresult": {
                "idlist": [],
            }
        }

    monkeypatch.setattr(pubmed, "_get_json", fake_get_json)

    result = await pubmed.pubmed_resolve_pmid_by_doi("10.1000/not-found")

    assert result is None


@pytest.mark.anyio
async def test_pubmed_resolve_pmid_by_doi_returns_single_numeric_pmid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_get_json(
        url: str,
        *,
        params: dict[str, object],
        timeout: float = 30.0,
    ) -> dict:
        return {
            "esearchresult": {
                "idlist": ["87654321"],
            }
        }

    monkeypatch.setattr(pubmed, "_get_json", fake_get_json)

    result = await pubmed.pubmed_resolve_pmid_by_doi("10.1000/example")

    assert result == "87654321"


@pytest.mark.anyio
async def test_pubmed_resolve_pmid_by_doi_returns_none_for_multiple_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_get_json(
        url: str,
        *,
        params: dict[str, object],
        timeout: float = 30.0,
    ) -> dict:
        return {
            "esearchresult": {
                "idlist": ["11111111", "22222222"],
            }
        }

    monkeypatch.setattr(pubmed, "_get_json", fake_get_json)

    result = await pubmed.pubmed_resolve_pmid_by_doi("10.1000/ambiguous")

    assert result is None


@pytest.mark.anyio
async def test_pubmed_resolve_pmid_by_doi_ignores_non_numeric_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_get_json(
        url: str,
        *,
        params: dict[str, object],
        timeout: float = 30.0,
    ) -> dict:
        return {
            "esearchresult": {
                "idlist": ["not-a-pmid"],
            }
        }

    monkeypatch.setattr(pubmed, "_get_json", fake_get_json)

    result = await pubmed.pubmed_resolve_pmid_by_doi("10.1000/example")

    assert result is None


@pytest.mark.anyio
async def test_pubmed_resolve_pmid_by_doi_passes_ncbi_parameters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_params: dict[str, object] = {}

    async def fake_get_json(
        url: str,
        *,
        params: dict[str, object],
        timeout: float = 30.0,
    ) -> dict:
        captured_params.update(params)
        return {
            "esearchresult": {
                "idlist": ["12345678"],
            }
        }

    monkeypatch.setattr(pubmed, "_get_json", fake_get_json)

    result = await pubmed.pubmed_resolve_pmid_by_doi(
        "10.1000/example",
        api_key="1234567890abcdef",
        tool="TestTool",
        email="test@example.com",
    )

    assert result == "12345678"
    assert captured_params["api_key"] == "1234567890abcdef"
    assert captured_params["tool"] == "TestTool"
    assert captured_params["email"] == "test@example.com"
