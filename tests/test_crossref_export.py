from __future__ import annotations

from unittest.mock import patch

import pytest

from app.jobs.export_tasks import (
    ExportMetrics,
    _fetch_crossref_export_records,
    _new_cache_stats,
)


@pytest.mark.anyio
@patch("app.jobs.export_tasks.crossref_search")
async def test_fetch_crossref_export_records_passes_abstract_filter(
    mock_crossref_search,
) -> None:
    mock_crossref_search.return_value = ([], 0)

    await _fetch_crossref_export_records(
        r=None,
        job_id="test-job",
        source="crossref",
        q="cancer",
        sort="relevance",
        limit=20,
        meta={
            "year_min": "2020",
            "year_max": "2025",
            "has_abstract": "1",
        },
        tenant_id="test-tenant",
        cache_stats=_new_cache_stats(),
        metrics=ExportMetrics(),
    )

    assert mock_crossref_search.call_count == 1

    call = mock_crossref_search.call_args

    assert call.kwargs["year_min"] == 2020
    assert call.kwargs["year_max"] == 2025
    assert call.kwargs["has_abstract"] is True


@pytest.mark.anyio
@patch("app.jobs.export_tasks.crossref_search")
async def test_fetch_crossref_export_records_disables_abstract_filter(
    mock_crossref_search,
) -> None:
    mock_crossref_search.return_value = ([], 0)

    await _fetch_crossref_export_records(
        r=None,
        job_id="test-job",
        source="crossref",
        q="cancer",
        sort="relevance",
        limit=20,
        meta={
            "year_min": "2020",
            "year_max": "2025",
            "has_abstract": "0",
        },
        tenant_id="test-tenant",
        cache_stats=_new_cache_stats(),
        metrics=ExportMetrics(),
    )

    assert mock_crossref_search.call_count == 1
    assert mock_crossref_search.call_args.kwargs["has_abstract"] is False
