import asyncio

from app.jobs import export_tasks


def test_europe_pmc_async_export_passes_mesh_mode(monkeypatch):
    captured = {}

    async def fake_set_job_progress(*args, **kwargs):
        return None

    async def fake_throttle_or_sleep(*args, **kwargs):
        return None

    async def fake_cache_get_json(*args, **kwargs):
        return None

    async def fake_cache_set_json(*args, **kwargs):
        return None

    def fake_europe_pmc_search(*args, **kwargs):
        captured.update(kwargs)
        return [], 0, None

    monkeypatch.setattr(
        export_tasks,
        "set_job_progress",
        fake_set_job_progress,
    )
    monkeypatch.setattr(
        export_tasks,
        "_throttle_or_sleep",
        fake_throttle_or_sleep,
    )
    monkeypatch.setattr(
        export_tasks,
        "_cache_get_json",
        fake_cache_get_json,
    )
    monkeypatch.setattr(
        export_tasks,
        "_cache_set_json",
        fake_cache_set_json,
    )
    monkeypatch.setattr(
        export_tasks,
        "europe_pmc_search",
        fake_europe_pmc_search,
    )

    asyncio.run(
        export_tasks._fetch_europe_pmc_export_records(
            r=object(),
            job_id="test-job",
            source="europe_pmc",
            q="cancer",
            sort="relevance",
            limit=10,
            meta={
                "year_min": "",
                "year_max": "",
                "has_abstract": "0",
                "mesh": "Humans|Adolescent",
                "mesh_mode": "and",
            },
            tenant_id="test-tenant",
            cache_stats={
                "cache_hit_batches": 0,
                "cache_miss_batches": 0,
                "cache_hit_records": 0,
                "api_fetched_records": 0,
                "epmc_page_cache_hit_batches": 0,
                "epmc_page_cache_miss_batches": 0,
                "epmc_page_cache_hit_records": 0,
                "epmc_api_fetched_records": 0,
                "epmc_pages_fetched": 0,
            },
            metrics=object(),
        )
    )

    assert captured["mesh"] == "Humans|Adolescent"
    assert captured["mesh_mode"] == "and"


def test_europe_pmc_async_export_cache_key_includes_mesh_mode(monkeypatch):
    captured_payloads = []

    def fake_cache_key(prefix, payload):
        if prefix == "cache:epmc:export":
            captured_payloads.append(dict(payload))
        return "cache:epmc:export:test"

    async def fake_set_job_progress(*args, **kwargs):
        return None

    async def fake_throttle_or_sleep(*args, **kwargs):
        return None

    async def fake_cache_get_json(*args, **kwargs):
        return None

    async def fake_cache_set_json(*args, **kwargs):
        return None

    def fake_europe_pmc_search(*args, **kwargs):
        return [], 0, None

    monkeypatch.setattr(export_tasks, "_cache_key", fake_cache_key)
    monkeypatch.setattr(
        export_tasks,
        "set_job_progress",
        fake_set_job_progress,
    )
    monkeypatch.setattr(
        export_tasks,
        "_throttle_or_sleep",
        fake_throttle_or_sleep,
    )
    monkeypatch.setattr(
        export_tasks,
        "_cache_get_json",
        fake_cache_get_json,
    )
    monkeypatch.setattr(
        export_tasks,
        "_cache_set_json",
        fake_cache_set_json,
    )
    monkeypatch.setattr(
        export_tasks,
        "europe_pmc_search",
        fake_europe_pmc_search,
    )

    asyncio.run(
        export_tasks._fetch_europe_pmc_export_records(
            r=object(),
            job_id="test-job",
            source="europe_pmc",
            q="cancer",
            sort="relevance",
            limit=10,
            meta={
                "year_min": "",
                "year_max": "",
                "has_abstract": "0",
                "mesh": "Humans|Adolescent",
                "mesh_mode": "and",
            },
            tenant_id="test-tenant",
            cache_stats={
                "cache_hit_batches": 0,
                "cache_miss_batches": 0,
                "cache_hit_records": 0,
                "api_fetched_records": 0,
                "epmc_page_cache_hit_batches": 0,
                "epmc_page_cache_miss_batches": 0,
                "epmc_page_cache_hit_records": 0,
                "epmc_api_fetched_records": 0,
                "epmc_pages_fetched": 0,
            },
            metrics=object(),
        )
    )

    assert captured_payloads
    assert captured_payloads[0]["mesh"] == "Humans|Adolescent"
    assert captured_payloads[0]["mesh_mode"] == "and"
