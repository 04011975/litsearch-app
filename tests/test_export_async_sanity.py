import time
import pytest

from app.main import ARQ_REDIS


pytestmark = pytest.mark.skipif(
    ARQ_REDIS is None,
    reason="Async export backend not available (Redis/ARQ not configured).",
)


def _wait_until_done(client, job_id: str, timeout_s: float = 30.0, sleep_s: float = 1.0):
    deadline = time.time() + timeout_s
    last_status = None

    while time.time() < deadline:
        r = client.get(f"/export/job/{job_id}")
        assert r.status_code == 200

        meta = r.json()
        last_status = meta.get("status")

        if last_status == "done":
            return meta
        if last_status == "failed":
            raise AssertionError(f"Export job failed: {meta.get('last_error')}")

        time.sleep(sleep_s)

    raise AssertionError(f"Export job did not finish in time; last_status={last_status}")


def test_async_export_job_pubmed_csv(client):
    create = client.post(
        "/export/job",
        params={
            "q": "cancer",
            "source": "pubmed",
            "n": 5,
            "sort": "relevance",
            "fmt": "csv",
            "limit": 20,
            "year_min": "2020",
            "year_max": "2022",
            "has_abstract": 1,
            "mesh": "",
            "mesh_mode": "or",
        },
    )
    assert create.status_code == 200

    data = create.json()
    assert "job_id" in data
    assert "status_url" in data
    assert "download_url" in data

    job_id = data["job_id"]

    meta = _wait_until_done(client, job_id, timeout_s=45.0, sleep_s=1.0)
    assert meta["status"] == "done"
    assert meta["fmt"] == "csv"
    assert meta["source"] == "pubmed"

    download = client.get(data["download_url"])
    assert download.status_code == 200
    assert "text/csv" in download.headers.get("content-type", "")
    assert "attachment" in download.headers.get("content-disposition", "")
    assert "ID,Source,Title,Authors,Journal,Year,DOI,PMCID,URL" in download.text


def test_async_export_job_openalex_csv(client):
    create = client.post(
        "/export/job",
        params={
            "q": "machine learning",
            "source": "openalex",
            "n": 5,
            "sort": "relevance",
            "fmt": "csv",
            "limit": 20,
            "year_min": "2021",
            "year_max": "2023",
        },
    )
    assert create.status_code == 200

    data = create.json()
    job_id = data["job_id"]

    meta = _wait_until_done(client, job_id, timeout_s=45.0, sleep_s=1.0)
    assert meta["status"] == "done"
    assert meta["source"] == "openalex"

    download = client.get(data["download_url"])
    assert download.status_code == 200
    assert "text/csv" in download.headers.get("content-type", "")
    assert "ID,Source,Title,Authors,Journal,Year,DOI,PMCID,URL" in download.text


def test_async_export_job_epmc_csv(client):
    create = client.post(
        "/export/job",
        params={
            "q": "glioblastoma",
            "source": "europe_pmc",
            "n": 5,
            "sort": "relevance",
            "fmt": "csv",
            "limit": 20,
            "year_min": "2020",
            "year_max": "2022",
            "has_abstract": 1,
        },
    )
    assert create.status_code == 200

    data = create.json()
    job_id = data["job_id"]

    meta = _wait_until_done(client, job_id, timeout_s=45.0, sleep_s=1.0)
    assert meta["status"] == "done"
    assert meta["source"] == "europe_pmc"

    download = client.get(data["download_url"])
    assert download.status_code == 200
    assert "text/csv" in download.headers.get("content-type", "")
    assert "ID,Source,Title,Authors,Journal,Year,DOI,PMCID,URL" in download.text


def test_async_export_job_rejects_empty_query(client):
    r = client.post(
        "/export/job",
        params={
            "q": "",
            "source": "pubmed",
            "fmt": "csv",
            "limit": 10,
        },
    )
    assert r.status_code in (400, 422)


def test_async_export_job_rejects_unknown_source(client):
    r = client.post(
        "/export/job",
        params={
            "q": "cancer",
            "source": "unknown_source",
            "fmt": "csv",
            "limit": 10,
        },
    )
    assert r.status_code == 422


def test_async_export_job_status_404_for_unknown_job(client):
    r = client.get("/export/job/does-not-exist")
    assert r.status_code == 404


def test_async_export_download_forbidden_with_wrong_token(client):
    create = client.post(
        "/export/job",
        params={
            "q": "cancer",
            "source": "pubmed",
            "n": 5,
            "sort": "relevance",
            "fmt": "csv",
            "limit": 10,
            "year_min": "2020",
            "year_max": "2022",
            "has_abstract": 1,
            "mesh": "",
            "mesh_mode": "or",
        },
    )
    assert create.status_code == 200

    job_id = create.json()["job_id"]

    wrong = client.get(f"/export/download/{job_id}?token=definitely-wrong-token")
    assert wrong.status_code in (403, 409)