from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.all_sources import (
    fetch_all_source_candidates,
    interleave_by_source,
)
from app.models.paper import Paper


def _paper(pid: str, source: str) -> Paper:
    return Paper(
        id=pid,
        source=source,
        title=f"Paper {pid}",
        year=2025,
        doi=f"10.1234/{pid}",
    )


def test_interleave_by_source_includes_doaj_in_expected_order() -> None:
    papers = [
        _paper("p1", "pubmed"),
        _paper("o1", "openalex"),
        _paper("c1", "crossref"),
        _paper("d1", "doaj"),
        _paper("e1", "europe_pmc"),
        _paper("s1", "semantic_scholar"),
        _paper("p2", "pubmed"),
        _paper("o2", "openalex"),
        _paper("c2", "crossref"),
        _paper("d2", "doaj"),
        _paper("e2", "europe_pmc"),
        _paper("s2", "semantic_scholar"),
    ]

    result = interleave_by_source(papers)

    assert [paper.source for paper in result] == [
        "pubmed",
        "openalex",
        "crossref",
        "doaj",
        "europe_pmc",
        "semantic_scholar",
        "pubmed",
        "openalex",
        "crossref",
        "doaj",
        "europe_pmc",
        "semantic_scholar",
    ]


@pytest.mark.anyio
@patch("app.all_sources.search_semantic_scholar")
@patch("app.all_sources.europe_pmc_search")
@patch("app.all_sources.doaj_search")
@patch("app.all_sources.crossref_search")
@patch("app.all_sources.openalex_search")
@patch("app.all_sources.pubmed_fetch_details", new_callable=AsyncMock)
@patch("app.all_sources.pubmed_search_page", new_callable=AsyncMock)
async def test_fetch_all_source_candidates_includes_doaj(
    mock_pubmed_search_page,
    mock_pubmed_fetch_details,
    mock_openalex_search,
    mock_crossref_search,
    mock_doaj_search,
    mock_europe_pmc_search,
    mock_semantic_scholar_search,
) -> None:
    pubmed_result = Mock()
    pubmed_result.pmids = ["1"]
    mock_pubmed_search_page.return_value = pubmed_result
    mock_pubmed_fetch_details.return_value = [_paper("p1", "pubmed")]

    mock_openalex_search.return_value = ([_paper("o1", "openalex")], 1)
    mock_crossref_search.return_value = ([_paper("c1", "crossref")], 1)
    mock_doaj_search.return_value = ([_paper("d1", "doaj")], 1)
    mock_europe_pmc_search.return_value = (
        [_paper("e1", "europe_pmc")],
        1,
        None,
    )
    mock_semantic_scholar_search.return_value = (
        [_paper("s1", "semantic_scholar")],
        1,
    )

    result = await fetch_all_source_candidates(
        q="machine learning cancer",
        candidate_n=20,
    )

    assert result["source_counts"] == {
        "pubmed": 1,
        "openalex": 1,
        "crossref": 1,
        "doaj": 1,
        "europe_pmc": 1,
        "semantic_scholar": 1,
    }

    assert result["failed_sources"] == []

    assert [paper.source for paper in result["combined_raw"]] == [
        "pubmed",
        "openalex",
        "crossref",
        "doaj",
        "europe_pmc",
        "semantic_scholar",
    ]

    mock_doaj_search.assert_called_once_with(
        "machine learning cancer",
        page=1,
        n=20,
        year_min=None,
        year_max=None,
        has_abstract=False,
    )


@pytest.mark.anyio
@patch("app.all_sources.search_semantic_scholar")
@patch("app.all_sources.europe_pmc_search")
@patch("app.all_sources.doaj_search")
@patch("app.all_sources.crossref_search")
@patch("app.all_sources.openalex_search")
@patch("app.all_sources.pubmed_fetch_details", new_callable=AsyncMock)
@patch("app.all_sources.pubmed_search_page", new_callable=AsyncMock)
async def test_fetch_all_source_candidates_isolates_doaj_failure(
    mock_pubmed_search_page,
    mock_pubmed_fetch_details,
    mock_openalex_search,
    mock_crossref_search,
    mock_doaj_search,
    mock_europe_pmc_search,
    mock_semantic_scholar_search,
) -> None:
    pubmed_result = Mock()
    pubmed_result.pmids = ["1"]
    mock_pubmed_search_page.return_value = pubmed_result
    mock_pubmed_fetch_details.return_value = [_paper("p1", "pubmed")]

    mock_openalex_search.return_value = ([_paper("o1", "openalex")], 1)
    mock_crossref_search.return_value = ([_paper("c1", "crossref")], 1)
    mock_doaj_search.side_effect = RuntimeError("DOAJ unavailable")
    mock_europe_pmc_search.return_value = (
        [_paper("e1", "europe_pmc")],
        1,
        None,
    )
    mock_semantic_scholar_search.return_value = (
        [_paper("s1", "semantic_scholar")],
        1,
    )

    result = await fetch_all_source_candidates(
        q="machine learning cancer",
        candidate_n=20,
    )

    assert result["source_counts"]["doaj"] == 0
    assert result["failed_sources"] == ["doaj"]

    sources = [paper.source for paper in result["combined_raw"]]

    assert sources == [
        "pubmed",
        "openalex",
        "crossref",
        "europe_pmc",
        "semantic_scholar",
    ]


@pytest.mark.anyio
@patch("app.all_sources.fetch_all_source_candidates")
async def test_build_all_source_results_includes_doaj_after_dedup(
    mock_fetch_all_source_candidates,
) -> None:
    from app.all_sources import build_all_source_results

    papers = [
        _paper("p1", "pubmed"),
        _paper("o1", "openalex"),
        _paper("c1", "crossref"),
        _paper("d1", "doaj"),
        _paper("e1", "europe_pmc"),
        _paper("s1", "semantic_scholar"),
    ]

    mock_fetch_all_source_candidates.return_value = {
        "combined_raw": papers,
        "source_counts": {
            "pubmed": 1,
            "openalex": 1,
            "crossref": 1,
            "doaj": 1,
            "europe_pmc": 1,
            "semantic_scholar": 1,
        },
        "failed_sources": [],
    }

    result = await build_all_source_results(
        q="machine learning cancer",
        sort="relevance",
        limit=None,
        page=1,
        n=20,
    )

    assert result["duplicates_removed"] == 0
    assert result["source_counts"]["doaj"] == 1
    assert result["failed_sources"] == []

    assert [paper.source for paper in result["papers"]] == [
        "pubmed",
        "openalex",
        "crossref",
        "doaj",
        "europe_pmc",
        "semantic_scholar",
    ]

class _FakeRedis:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    async def get(self, key: str):
        return self.data.get(key)

    async def set(self, key: str, value: str, ex: int | None = None):
        self.data[key] = value
        return True


@pytest.mark.anyio
@patch("app.all_sources.fetch_all_source_candidates")
async def test_build_all_source_results_reuses_snapshot_across_pages(
    mock_fetch_all_source_candidates,
) -> None:
    from app.all_sources import build_all_source_results

    first_papers = [
        _paper("p1", "pubmed"),
        _paper("p2", "pubmed"),
        _paper("p3", "pubmed"),
        _paper("p4", "pubmed"),
    ]

    changed_papers = [
        _paper("x1", "pubmed"),
        _paper("x2", "pubmed"),
        _paper("x3", "pubmed"),
        _paper("x4", "pubmed"),
    ]

    mock_fetch_all_source_candidates.side_effect = [
        {
            "combined_raw": first_papers,
            "source_counts": {"pubmed": 4},
            "failed_sources": [],
        },
        {
            "combined_raw": changed_papers,
            "source_counts": {"pubmed": 4},
            "failed_sources": [],
        },
    ]

    redis = _FakeRedis()

    page_1 = await build_all_source_results(
        q="machine learning cancer",
        sort="relevance",
        limit=None,
        page=1,
        n=2,
        redis=redis,
    )

    snapshot_id = page_1["snapshot_id"]

    page_2 = await build_all_source_results(
        q="machine learning cancer",
        sort="relevance",
        limit=None,
        page=2,
        n=2,
        redis=redis,
        snapshot_id=snapshot_id,
    )

    assert snapshot_id
    assert page_2["snapshot_id"] == snapshot_id

    assert [paper.id for paper in page_1["papers"]] == ["p1", "p2"]
    assert [paper.id for paper in page_2["papers"]] == ["p3", "p4"]

    assert page_1["total_count"] == 4
    assert page_2["total_count"] == 4

    assert mock_fetch_all_source_candidates.await_count == 1


@pytest.mark.anyio
@patch("app.all_sources.fetch_all_source_candidates")
async def test_build_all_source_results_rejects_snapshot_for_different_query(
    mock_fetch_all_source_candidates,
) -> None:
    from app.all_sources import build_all_source_results

    alpha_papers = [
        _paper("a1", "pubmed"),
        _paper("a2", "pubmed"),
    ]

    beta_papers = [
        _paper("b1", "pubmed"),
        _paper("b2", "pubmed"),
    ]

    mock_fetch_all_source_candidates.side_effect = [
        {
            "combined_raw": alpha_papers,
            "source_counts": {"pubmed": 2},
            "failed_sources": [],
        },
        {
            "combined_raw": beta_papers,
            "source_counts": {"pubmed": 2},
            "failed_sources": [],
        },
    ]

    redis = _FakeRedis()

    alpha = await build_all_source_results(
        q="alpha",
        sort="relevance",
        limit=None,
        page=1,
        n=2,
        redis=redis,
    )

    alpha_snapshot_id = alpha["snapshot_id"]

    beta = await build_all_source_results(
        q="beta",
        sort="relevance",
        limit=None,
        page=1,
        n=2,
        redis=redis,
        snapshot_id=alpha_snapshot_id,
    )

    assert [paper.id for paper in alpha["papers"]] == ["a1", "a2"]
    assert [paper.id for paper in beta["papers"]] == ["b1", "b2"]

    assert beta["snapshot_id"] != alpha_snapshot_id
    assert mock_fetch_all_source_candidates.await_count == 2


@pytest.mark.anyio
@patch("app.all_sources.fetch_all_source_candidates")
async def test_build_all_source_results_does_not_return_snapshot_id_when_store_fails(
    mock_fetch_all_source_candidates,
) -> None:
    from app.all_sources import build_all_source_results

    mock_fetch_all_source_candidates.return_value = {
        "combined_raw": [
            _paper("p1", "pubmed"),
            _paper("p2", "pubmed"),
        ],
        "source_counts": {"pubmed": 2},
        "failed_sources": [],
    }

    class FailingRedis:
        async def get(self, key: str):
            return None

        async def set(self, key: str, value: str, ex: int | None = None):
            raise RuntimeError("Redis unavailable")

    result = await build_all_source_results(
        q="cancer",
        sort="relevance",
        limit=None,
        page=1,
        n=2,
        redis=FailingRedis(),
    )

    assert [paper.id for paper in result["papers"]] == ["p1", "p2"]
    assert result["snapshot_id"] is None
    assert mock_fetch_all_source_candidates.await_count == 1


@pytest.mark.anyio
@patch("app.all_sources.fetch_all_source_candidates")
async def test_build_all_source_results_rebuilds_expired_snapshot_with_new_id(
    mock_fetch_all_source_candidates,
) -> None:
    from app.all_sources import build_all_source_results

    first_papers = [
        _paper("p1", "pubmed"),
        _paper("p2", "pubmed"),
    ]

    refreshed_papers = [
        _paper("x1", "pubmed"),
        _paper("x2", "pubmed"),
    ]

    mock_fetch_all_source_candidates.side_effect = [
        {
            "combined_raw": first_papers,
            "source_counts": {"pubmed": 2},
            "failed_sources": [],
        },
        {
            "combined_raw": refreshed_papers,
            "source_counts": {"pubmed": 2},
            "failed_sources": [],
        },
    ]

    redis = _FakeRedis()

    first = await build_all_source_results(
        q="cancer",
        sort="relevance",
        limit=None,
        page=1,
        n=2,
        redis=redis,
    )

    old_snapshot_id = first["snapshot_id"]
    assert old_snapshot_id

    # Simulate an expired Redis snapshot.
    redis.data.clear()

    refreshed = await build_all_source_results(
        q="cancer",
        sort="relevance",
        limit=None,
        page=1,
        n=2,
        redis=redis,
        snapshot_id=old_snapshot_id,
    )

    assert [paper.id for paper in refreshed["papers"]] == ["x1", "x2"]
    assert refreshed["snapshot_id"]
    assert refreshed["snapshot_id"] != old_snapshot_id
    assert mock_fetch_all_source_candidates.await_count == 2
