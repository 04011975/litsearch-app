import os
import time
import requests
import pytest


BASE_URL = os.getenv("LITSEARCH_BASE_URL", "http://localhost:8001")


@pytest.mark.integration
def test_export_job_all_sources_with_redis_arq():
    create = requests.post(
        f"{BASE_URL}/export/job",
        params={
            "q": "cancer",
            "source": "all",
            "limit": 20,
            "fmt": "csv",
        },
        timeout=10,
    )

    assert create.status_code in {200, 202}
    data = create.json()
    assert "status_url" in data

    status_url = BASE_URL + data["status_url"]
    last_status = None

    for _ in range(60):
        status = requests.get(status_url, timeout=10)
        assert status.status_code == 200

        last_status = status.json()

        if last_status["status"] in {"done", "failed"}:
            break

        time.sleep(1)

    assert last_status is not None
    assert last_status["status"] == "done"
    assert last_status["source"] == "all"
    assert int(last_status["collected"]) == 20
    assert last_status["download_url"]