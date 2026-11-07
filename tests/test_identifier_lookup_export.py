
import pytest
from unittest.mock import AsyncMock

from app.doi_lookup import (
    DoiLookupResult,
    PmidLookupResult,
    PmcidLookupResult,
)
from app.jobs.export_tasks import run_export_job
from app.models.paper import Paper


@pytest.mark.anyio
@pytest.mark.parametrize(
    "lookup_mode,identifier,result_class,source",
    [
        ("doi", "10.1000/example", DoiLookupResult, "pubmed"),
        ("pmid", "12345678", PmidLookupResult, "pubmed"),
        ("pmcid", "PMC1234567", PmcidLookupResult, "europe_pmc"),
    ],
)
async def test_identifier_lookup_export_writes_exact_paper(
    tmp_path,
    monkeypatch,
    lookup_mode,
    identifier,
    result_class,
    source,
):
    job_id = f"test-{lookup_mode}-lookup-export"
    title = f"Exact {lookup_mode.upper()} export test article"

    paper = Paper(
        id=identifier,
        source=source,
        title=title,
        doi=identifier if lookup_mode == "doi" else None,
        pmcid=identifier if lookup_mode == "pmcid" else None,
    )

    lookup_result = result_class(
        **{lookup_mode: identifier},
        paper=paper,
        found_in=[source],
    )

    mock_lookup = AsyncMock(return_value=lookup_result)
    mock_all_sources = AsyncMock()

    monkeypatch.setattr(
        f"app.jobs.export_tasks.lookup_{lookup_mode}",
        mock_lookup,
    )
    monkeypatch.setattr(
        "app.jobs.export_tasks.build_all_source_results",
        mock_all_sources,
    )
    monkeypatch.setattr(
        "app.jobs.export_tasks.set_job_progress",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "app.jobs.export_tasks.mark_job_done",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "app.jobs.export_tasks.EXPORT_DIR",
        str(tmp_path),
    )

    class FakeRedis:
        async def hgetall(self, key):
            assert key == f"export:job:{job_id}"
            return {
                b"source": b"all",
                b"q": identifier.encode(),
                b"lookup": lookup_mode.encode(),
                b"sort": b"relevance",
                b"limit": b"1",
                b"fmt": b"csv",
                b"download_token": b"test-token",
                b"tenant_id": b"test",
                b"has_abstract": b"0",
            }

    result = await run_export_job(
        {"redis": FakeRedis()},
        job_id=job_id,
    )

    out_path = tmp_path / f"{job_id}.csv"

    assert result["ok"] is True
    assert out_path.exists()

    content = out_path.read_text(encoding="utf-8")

    assert title in content
    assert identifier in content
    assert len(content.splitlines()) == 2

    mock_lookup.assert_awaited_once_with(identifier)
    mock_all_sources.assert_not_awaited()
