import os
import time
import requests
import pytest

pytestmark = pytest.mark.integration

BASE_URL = os.getenv("LITSEARCH_BASE_URL", "http://localhost:8001")


def _wait_for_done(status_url: str, timeout_s: int = 60) -> dict:
    deadline = time.time() + timeout_s

    while time.time() < deadline:
        r = requests.get(BASE_URL + status_url, timeout=10)
        r.raise_for_status()
        data = r.json()

        if data["status"] in {"done", "failed"}:
            return data

        time.sleep(1)

    raise TimeoutError("Export job did not finish")


def _start_export() -> dict:
    r = requests.post(
        f"{BASE_URL}/export/job",
        params={
            "q": "cancer",
            "source": "europe_pmc",
            "limit": 50,
            "fmt": "csv",
        },
        timeout=10,
    )
    assert r.status_code in {200, 202}
    return r.json()


def test_europe_pmc_export_cache_warm_run():
    first = _start_export()
    first_done = _wait_for_done(first["status_url"])
    assert first_done["status"] == "done"
    assert int(first_done["collected"]) == 50

    second = _start_export()
    second_done = _wait_for_done(second["status_url"])
    assert second_done["status"] == "done"
    assert int(second_done["collected"]) == 50