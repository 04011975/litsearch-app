from app.redis_client import REDIS_URL, make_sync_redis


def test_make_sync_redis_uses_configured_redis_url(monkeypatch):
    calls = []

    def fake_from_url(url, *, decode_responses=False):
        calls.append((url, decode_responses))
        return object()

    monkeypatch.setattr(
        "app.redis_client.sync_redis.from_url",
        fake_from_url,
    )

    client = make_sync_redis()

    assert client is not None
    assert calls == [(REDIS_URL, True)]
