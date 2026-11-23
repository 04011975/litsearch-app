from app.services.pubmed_snapshot import pubmed_snapshot_signature


def test_pubmed_snapshot_signature_is_deterministic():
    params = {
        "q": "diabetes",
        "sort": "relevance",
        "page": 1,
        "n": 10,
        "year_min": None,
        "year_max": None,
        "has_abstract": False,
        "mesh": "",
        "mesh_mode": "or",
    }

    first = pubmed_snapshot_signature(**params)
    second = pubmed_snapshot_signature(**params)

    assert first == second


def test_pubmed_snapshot_signature_changes_with_parameters():
    params = {
        "q": "diabetes",
        "sort": "relevance",
        "page": 1,
        "n": 10,
        "year_min": None,
        "year_max": None,
        "has_abstract": False,
        "mesh": "",
        "mesh_mode": "or",
    }

    original = pubmed_snapshot_signature(**params)

    changes = [
        {"q": "asthma"},
        {"sort": "date_desc"},
        {"page": 2},
        {"n": 20},
        {"year_min": 2020},
        {"year_max": 2025},
        {"has_abstract": True},
        {"mesh": "Diabetes Mellitus"},
        {"mesh_mode": "and"},
    ]

    for change in changes:
        modified = {**params, **change}
        assert pubmed_snapshot_signature(**modified) != original


import json

import asyncio

from app.services.pubmed_snapshot import (
    store_pubmed_snapshot,
    load_pubmed_snapshot,
)


def test_pubmed_snapshot_store_and_load():
    async def run_test():
        class FakeRedis:
            def __init__(self):
                self.data = {}

            async def set(self, key, value, ex=None):
                self.data[key] = value
                return True

            async def get(self, key):
                return self.data.get(key)

        redis = FakeRedis()

        papers = [
            {"id": "123", "title": "First article"},
            {"id": "456", "title": "Second article"},
        ]

        snapshot_id = await store_pubmed_snapshot(
            redis,
            request_signature="test-signature",
            papers=papers,
        )

        assert snapshot_id is not None

        restored = await load_pubmed_snapshot(
            redis,
            snapshot_id=snapshot_id,
            request_signature="test-signature",
        )

        assert restored == papers
        assert [paper["id"] for paper in restored] == ["123", "456"]

    asyncio.run(run_test())


def test_pubmed_snapshot_rejects_wrong_signature():
    async def run_test():
        class FakeRedis:
            def __init__(self):
                self.data = {}

            async def set(self, key, value, ex=None):
                self.data[key] = value
                return True

            async def get(self, key):
                return self.data.get(key)

        redis = FakeRedis()

        papers = [
            {"id": "123", "title": "First article"},
        ]

        snapshot_id = await store_pubmed_snapshot(
            redis,
            request_signature="original-signature",
            papers=papers,
        )

        assert snapshot_id is not None

        restored = await load_pubmed_snapshot(
            redis,
            snapshot_id=snapshot_id,
            request_signature="different-signature",
        )

        assert restored is None

    asyncio.run(run_test())


def test_pubmed_snapshot_missing_returns_none():
    async def run_test():
        class FakeRedis:
            async def get(self, key):
                return None

        redis = FakeRedis()

        restored = await load_pubmed_snapshot(
            redis,
            snapshot_id="nonexistent-snapshot",
            request_signature="test-signature",
        )

        assert restored is None

    asyncio.run(run_test())


def test_pubmed_snapshot_rejects_invalid_payload():
    async def run_test():
        class FakeRedis:
            async def get(self, key):
                return json.dumps({
                    "request_signature": "test-signature",
                    "papers": "invalid-papers",
                })

        redis = FakeRedis()

        restored = await load_pubmed_snapshot(
            redis,
            snapshot_id="invalid-snapshot",
            request_signature="test-signature",
        )

        assert restored is None

    asyncio.run(run_test())


def test_pubmed_snapshot_rejects_invalid_paper_items():
    async def run_test():
        class FakeRedis:
            async def get(self, key):
                return json.dumps({
                    "request_signature": "test-signature",
                    "papers": [
                        {"id": "123", "title": "Valid article"},
                        "invalid-article",
                    ],
                })

        redis = FakeRedis()

        restored = await load_pubmed_snapshot(
            redis,
            snapshot_id="invalid-paper-snapshot",
            request_signature="test-signature",
        )

        assert restored is None

    asyncio.run(run_test())


def test_pubmed_snapshot_handles_unavailable_redis():
    async def run_test():
        papers = [
            {"id": "123", "title": "First article"},
        ]

        snapshot_id = await store_pubmed_snapshot(
            None,
            request_signature="test-signature",
            papers=papers,
        )

        assert snapshot_id is None

        restored = await load_pubmed_snapshot(
            None,
            snapshot_id="nonexistent-snapshot",
            request_signature="test-signature",
        )

        assert restored is None

    asyncio.run(run_test())


def test_pubmed_export_rejects_invalid_snapshot(
    client, monkeypatch
):
    from app import main

    async def fake_load_pubmed_snapshot(
        redis, *, snapshot_id, request_signature
    ):
        return None

    async def unexpected_pubmed_search(*args, **kwargs):
        raise AssertionError(
            "PubMed must not be queried for an invalid snapshot"
        )

    monkeypatch.setattr(
        main,
        "load_pubmed_snapshot",
        fake_load_pubmed_snapshot,
    )

    monkeypatch.setattr(
        main,
        "pubmed_search_page",
        unexpected_pubmed_search,
    )

    response = client.get(
        "/export/csv",
        params={
            "q": "diabetes",
            "source": "pubmed",
            "scope": "page",
            "page": 1,
            "n": 10,
            "sort": "relevance",
            "snapshot_id": "invalid-snapshot-id",
        },
    )

    assert response.status_code == 410
    assert response.json()["detail"] == (
        "PubMed snapshot expired or invalid. Run the search again."
    )
