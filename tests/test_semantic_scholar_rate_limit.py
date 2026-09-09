from app.connectors.semantic_scholar import _acquire_distributed_rate_limit


def test_distributed_rate_limit_allows_first_request():
    class FakeRedis:
        def set(self, key, value, *, nx=False, px=None):
            assert key == "rate_limit:semantic_scholar:global"
            assert value == "1"
            assert nx is True
            assert px == 1100
            return True

    _acquire_distributed_rate_limit(FakeRedis())


def test_distributed_rate_limit_waits_until_slot_is_available(monkeypatch):
    attempts = 0
    sleeps = []

    class FakeRedis:
        def set(self, key, value, *, nx=False, px=None):
            nonlocal attempts
            attempts += 1

            if attempts == 1:
                return False

            return True

    def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(
        "app.connectors.semantic_scholar.time.sleep",
        fake_sleep,
    )

    _acquire_distributed_rate_limit(FakeRedis())

    assert attempts == 2
    assert sleeps == [1.1]


def test_distributed_rate_limit_fails_open_when_redis_errors():
    class FailingRedis:
        def set(self, key, value, *, nx=False, px=None):
            raise ConnectionError("Redis unavailable")

    _acquire_distributed_rate_limit(FailingRedis())


def test_request_acquires_distributed_rate_limit_before_http_request(monkeypatch):
    events = []

    class FakeResponse:
        status_code = 200
        headers = {}

        def json(self):
            return {}

    def fake_acquire(redis_client):
        events.append("acquire")

    def fake_get(*args, **kwargs):
        events.append("get")
        return FakeResponse()

    monkeypatch.setattr(
        "app.connectors.semantic_scholar._acquire_distributed_rate_limit",
        fake_acquire,
    )
    monkeypatch.setattr(
        "app.connectors.semantic_scholar._session.get",
        fake_get,
    )
    monkeypatch.setattr(
        "app.connectors.semantic_scholar.time.sleep",
        lambda seconds: None,
    )
    monkeypatch.setattr(
        "app.connectors.semantic_scholar._last_request_time",
        0.0,
    )

    from app.connectors.semantic_scholar import _request

    _request("https://example.test", {"query": "test"})

    assert events == ["acquire", "get"]


def test_request_reacquires_distributed_rate_limit_on_429_retry(monkeypatch):
    acquire_calls = []
    request_calls = []

    class FakeResponse:
        def __init__(self, status_code):
            self.status_code = status_code
            self.headers = {}
            self.text = ""

        def json(self):
            return {}

    responses = [
        FakeResponse(429),
        FakeResponse(200),
    ]

    def fake_acquire(redis_client):
        acquire_calls.append(redis_client)

    def fake_get(*args, **kwargs):
        request_calls.append(1)
        return responses.pop(0)

    monkeypatch.setattr(
        "app.connectors.semantic_scholar._acquire_distributed_rate_limit",
        fake_acquire,
    )
    monkeypatch.setattr(
        "app.connectors.semantic_scholar._session.get",
        fake_get,
    )
    monkeypatch.setattr(
        "app.connectors.semantic_scholar.time.sleep",
        lambda seconds: None,
    )
    monkeypatch.setattr(
        "app.connectors.semantic_scholar.random.uniform",
        lambda a, b: 0,
    )
    monkeypatch.setattr(
        "app.connectors.semantic_scholar._last_request_time",
        0.0,
    )

    from app.connectors.semantic_scholar import _request

    result = _request("https://example.test", {"query": "test"})

    assert result == {}
    assert len(request_calls) == 2
    assert len(acquire_calls) == 2
