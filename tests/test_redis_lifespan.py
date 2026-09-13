from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI

import app.main as main_module


@pytest.mark.anyio
async def test_lifespan_closes_async_redis_with_aclose(monkeypatch):
    redis_client = SimpleNamespace(
        aclose=AsyncMock(),
        connection_pool=SimpleNamespace(disconnect=AsyncMock()),
    )

    monkeypatch.setattr(main_module, "make_redis", lambda: redis_client)
    monkeypatch.setattr(main_module, "_redis_client", lambda: None)
    monkeypatch.setattr(main_module, "REDIS_URL", "")

    test_app = FastAPI()

    async with main_module.lifespan(test_app):
        pass

    redis_client.aclose.assert_awaited_once_with()
