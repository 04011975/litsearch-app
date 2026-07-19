from __future__ import annotations

import asyncio

import pytest

from app.enrichment.providers.opencitations import OpenCitationsProvider
from app.models.paper import Paper


def test_provider_does_not_match_paper_without_doi(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_fetch_counts(
        doi: str,
    ) -> tuple[int | None, int | None]:
        raise AssertionError("Connector must not be called without a DOI")

    monkeypatch.setattr(
        "app.enrichment.providers.opencitations." "opencitations_fetch_counts",
        fake_fetch_counts,
    )

    paper = Paper(
        id="paper-1",
        source="crossref",
        title="Paper without DOI",
    )

    result = asyncio.run(OpenCitationsProvider().enrich(paper))

    assert result.matched is False
    assert result.values == {}
    assert result.sources == {}


def test_provider_returns_both_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_fetch_counts(
        doi: str,
    ) -> tuple[int | None, int | None]:
        assert doi == "10.1000/example"
        return 42, 17

    monkeypatch.setattr(
        "app.enrichment.providers.opencitations." "opencitations_fetch_counts",
        fake_fetch_counts,
    )

    paper = Paper(
        id="paper-2",
        source="openalex",
        title="Paper with counts",
        doi="10.1000/example",
    )

    result = asyncio.run(OpenCitationsProvider().enrich(paper))

    assert result.matched is True
    assert result.values == {
        "citation_count": 42,
        "reference_count": 17,
    }
    assert result.sources == {
        "citation_count": ["opencitations"],
        "reference_count": ["opencitations"],
    }


def test_provider_accepts_zero_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_fetch_counts(
        doi: str,
    ) -> tuple[int | None, int | None]:
        return 0, 0

    monkeypatch.setattr(
        "app.enrichment.providers.opencitations." "opencitations_fetch_counts",
        fake_fetch_counts,
    )

    paper = Paper(
        id="paper-3",
        source="crossref",
        doi="10.1000/uncited",
    )

    result = asyncio.run(OpenCitationsProvider().enrich(paper))

    assert result.matched is True
    assert result.values == {
        "citation_count": 0,
        "reference_count": 0,
    }


def test_provider_returns_partial_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_fetch_counts(
        doi: str,
    ) -> tuple[int | None, int | None]:
        return 12, None

    monkeypatch.setattr(
        "app.enrichment.providers.opencitations." "opencitations_fetch_counts",
        fake_fetch_counts,
    )

    paper = Paper(
        id="paper-4",
        source="europe_pmc",
        doi="10.1000/partial",
    )

    result = asyncio.run(OpenCitationsProvider().enrich(paper))

    assert result.matched is True
    assert result.values == {
        "citation_count": 12,
    }
    assert result.sources == {
        "citation_count": ["opencitations"],
    }


def test_provider_does_not_match_empty_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_fetch_counts(
        doi: str,
    ) -> tuple[int | None, int | None]:
        return None, None

    monkeypatch.setattr(
        "app.enrichment.providers.opencitations." "opencitations_fetch_counts",
        fake_fetch_counts,
    )

    paper = Paper(
        id="paper-5",
        source="semantic_scholar",
        doi="10.1000/not-found",
    )

    result = asyncio.run(OpenCitationsProvider().enrich(paper))

    assert result.matched is False
    assert result.values == {}
    assert result.sources == {}
