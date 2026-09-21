from __future__ import annotations

from unittest.mock import patch

import pytest

from app.jobs.export_tasks import (
    ExportMetrics,
    _fetch_openalex_export_records,
    _new_cache_stats,
)


@pytest.mark.anyio
@patch("app.jobs.export_tasks.openalex_search")
async def test_fetch_openalex_export_records_passes_abstract_filter(
    mock_openalex_search,
    monkeypatch,
) -> None:
    async def fake_throttle(*args, **kwargs):
        return None

    async def fake_cache_get(*args, **kwargs):
        return None

    async def fake_cache_set(*args, **kwargs):
        return None

    async def fake_set_job_progress(*args, **kwargs):
        return None

    monkeypatch.setattr(
        "app.jobs.export_tasks._throttle_or_sleep",
        fake_throttle,
    )
    monkeypatch.setattr(
        "app.jobs.export_tasks._cache_get_json",
        fake_cache_get,
    )
    monkeypatch.setattr(
        "app.jobs.export_tasks._cache_set_json",
        fake_cache_set,
    )
    monkeypatch.setattr(
        "app.jobs.export_tasks.set_job_progress",
        fake_set_job_progress,
    )

    mock_openalex_search.return_value = ([], 0)

    await _fetch_openalex_export_records(
        r=None,
        job_id="test-job",
        source="openalex",
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

    assert mock_openalex_search.call_count == 1

    call = mock_openalex_search.call_args

    assert call.kwargs["year_min"] == 2020
    assert call.kwargs["year_max"] == 2025
    assert call.kwargs["has_abstract"] is True


@pytest.mark.anyio
@patch("app.jobs.export_tasks.openalex_search")
async def test_fetch_openalex_export_records_abstract_filter_changes_cache_key(
    mock_openalex_search,
    monkeypatch,
) -> None:
    cache_keys = []

    async def fake_throttle(*args, **kwargs):
        return None

    async def fake_cache_get(redis, key):
        cache_keys.append(key)
        return None

    async def fake_cache_set(*args, **kwargs):
        return None

    async def fake_set_job_progress(*args, **kwargs):
        return None

    monkeypatch.setattr(
        "app.jobs.export_tasks._throttle_or_sleep",
        fake_throttle,
    )
    monkeypatch.setattr(
        "app.jobs.export_tasks._cache_get_json",
        fake_cache_get,
    )
    monkeypatch.setattr(
        "app.jobs.export_tasks._cache_set_json",
        fake_cache_set,
    )
    monkeypatch.setattr(
        "app.jobs.export_tasks.set_job_progress",
        fake_set_job_progress,
    )

    mock_openalex_search.return_value = ([], 0)

    common_kwargs = {
        "r": None,
        "job_id": "test-job",
        "source": "openalex",
        "q": "cancer",
        "sort": "relevance",
        "limit": 20,
        "tenant_id": "test-tenant",
        "metrics": ExportMetrics(),
    }

    await _fetch_openalex_export_records(
        **common_kwargs,
        meta={
            "year_min": "2020",
            "year_max": "2025",
            "has_abstract": "0",
        },
        cache_stats=_new_cache_stats(),
    )

    keys_without_abstract_filter = list(cache_keys)
    cache_keys.clear()

    await _fetch_openalex_export_records(
        **common_kwargs,
        meta={
            "year_min": "2020",
            "year_max": "2025",
            "has_abstract": "1",
        },
        cache_stats=_new_cache_stats(),
    )

    keys_with_abstract_filter = list(cache_keys)

    assert keys_without_abstract_filter
    assert keys_with_abstract_filter
    assert keys_without_abstract_filter != keys_with_abstract_filter