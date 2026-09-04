from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.jobs.export_tasks import (
    MULTI_SOURCE_EXPORT_SOURCES,
    SINGLE_EXPORT_SOURCES,
    SUPPORTED_EXPORT_SOURCES,
    _fetch_doaj_export_records,
    run_export_job,
)
from app.models.paper import Paper


def _paper(pid: str) -> Paper:
    return Paper(
        id=pid,
        source="doaj",
        title=f"DOAJ paper {pid}",
        year=2025,
        doi=f"10.1234/{pid}",
    )


def test_doaj_is_registered_as_export_source() -> None:
    assert "doaj" in SINGLE_EXPORT_SOURCES
    assert "doaj" in MULTI_SOURCE_EXPORT_SOURCES
    assert "doaj" in SUPPORTED_EXPORT_SOURCES


@pytest.mark.anyio
@patch("app.jobs.export_tasks.doaj_search")
async def test_fetch_doaj_export_records(mock_doaj_search) -> None:
    mock_doaj_search.return_value = (
        [
            _paper("d1"),
            _paper("d2"),
        ],
        2,
    )

    papers, metadata = await _fetch_doaj_export_records(
        r=None,
        job_id="test-job",
        source="doaj",
        q="machine learning cancer",
        sort="relevance",
        limit=20,
        meta={
            "year_min": "2020",
            "year_max": "2025",
            "has_abstract": "1",
        },
        tenant_id="test-tenant",
        cache_stats={},
        metrics=None,
    )

    assert len(papers) == 2
    assert [paper.source for paper in papers] == ["doaj", "doaj"]

    assert [paper.id for paper in papers] == ["d1", "d2"]

    assert metadata["total_count"] == 2
    assert metadata["page_size"] == 20
    assert metadata["pages_fetched"] == 1

    mock_doaj_search.assert_called_once_with(
        "machine learning cancer",
        page=1,
        n=20,
        year_min=2020,
        year_max=2025,
        has_abstract=True,
    )


@pytest.mark.anyio
@patch("app.jobs.export_tasks.doaj_search")
async def test_fetch_doaj_export_records_paginates(mock_doaj_search) -> None:
    first_page = [_paper(f"d{i}") for i in range(1, 101)]
    second_page = [_paper(f"d{i}") for i in range(101, 121)]

    mock_doaj_search.side_effect = [
        (first_page, 120),
        (second_page, 120),
    ]

    papers, metadata = await _fetch_doaj_export_records(
        r=None,
        job_id="test-job",
        source="doaj",
        q="cancer",
        sort="relevance",
        limit=120,
        meta={},
        tenant_id="test-tenant",
        cache_stats={},
        metrics=None,
    )

    assert len(papers) == 120
    assert metadata["total_count"] == 120
    assert metadata["page_size"] == 100
    assert metadata["pages_fetched"] == 2

    assert mock_doaj_search.call_count == 2

    first_call = mock_doaj_search.call_args_list[0]
    second_call = mock_doaj_search.call_args_list[1]

    assert first_call.kwargs["page"] == 1
    assert first_call.kwargs["n"] == 100

    assert second_call.kwargs["page"] == 2
    assert second_call.kwargs["n"] == 100


@pytest.mark.anyio
@patch("app.jobs.export_tasks.mark_job_done", new_callable=AsyncMock)
@patch("app.jobs.export_tasks.set_job_progress", new_callable=AsyncMock)
@patch("app.jobs.export_tasks.build_all_source_results", new_callable=AsyncMock)
async def test_all_sources_export_writes_doaj_paper(
    mock_build_all_source_results,
    mock_set_job_progress,
    mock_mark_job_done,
    tmp_path,
    monkeypatch,
) -> None:
    job_id = "test-all-doaj"
    download_token = "test-token"

    doaj_paper = Paper(
        id="doaj-1",
        source="doaj",
        title="DOAJ export integration paper",
        authors=["Jane Doe"],
        journal="DOAJ Journal",
        year=2025,
        doi="10.1234/doaj-export",
        url="https://example.org/doaj-paper",
    )

    mock_build_all_source_results.return_value = {
        "all_papers": [doaj_paper],
        "duplicates_removed": 0,
        "source_counts": {
            "pubmed": 0,
            "openalex": 0,
            "crossref": 0,
            "doaj": 1,
            "europe_pmc": 0,
            "semantic_scholar": 0,
        },
        "failed_sources": [],
    }

    class FakeRedis:
        async def hgetall(self, key):
            assert key == f"export:job:{job_id}"
            return {
                b"source": b"all",
                b"q": b"machine learning cancer",
                b"sort": b"relevance",
                b"limit": b"20",
                b"fmt": b"csv",
                b"download_token": download_token.encode(),
                b"tenant_id": b"test",
                b"has_abstract": b"0",
            }

    monkeypatch.setattr(
        "app.jobs.export_tasks.EXPORT_DIR",
        str(tmp_path),
    )

    result = await run_export_job(
        {"redis": FakeRedis()},
        job_id=job_id,
    )

    out_path = tmp_path / f"{job_id}.csv"

    assert out_path.exists()

    content = out_path.read_text(encoding="utf-8")

    assert "DOAJ export integration paper" in content
    assert "doaj" in content
    assert "10.1234/doaj-export" in content

    mock_build_all_source_results.assert_awaited_once()

    kwargs = mock_build_all_source_results.await_args.kwargs
    assert kwargs["q"] == "machine learning cancer"
    assert kwargs["sort"] == "relevance"
    assert kwargs["limit"] == 20
    assert kwargs["page"] == 1
    assert kwargs["n"] == 20

    assert result["ok"] is True
