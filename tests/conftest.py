import sys
import os
import time

from typing import Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture(scope="session")
def client() -> TestClient:
    return TestClient(app)


def _safe_year(v: Any) -> int | None:
    try:
        if v is None or str(v).strip() == "":
            return None
        return int(v)
    except Exception:
        return None


def _nonempty(s: Any) -> bool:
    return bool(str(s or "").strip())


def _wait_brief() -> None:
    # Kleine pauze om rate limits iets te ontzien tijdens test runs
    time.sleep(float(os.getenv("TEST_SLEEP_SECONDS", "0.15")))