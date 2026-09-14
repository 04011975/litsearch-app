import pytest

from app.connectors.openalex import openalex_fetch_detail, openalex_search


@pytest.mark.integration
@pytest.mark.anyio
async def test_openalex_search_returns_results():
    papers, total = openalex_search(
        "machine learning",
        page=1,
        n=5,
        sort="relevance",
        year_min=2021,
        year_max=2023,
    )
    assert total >= 0
    assert isinstance(papers, list)
    assert len(papers) > 0


@pytest.mark.integration
@pytest.mark.anyio
async def test_openalex_search_date_sort_returns_results():
    papers, total = openalex_search(
        "cancer",
        page=1,
        n=5,
        sort="publication_date:desc",
        year_min=2020,
        year_max=2023,
    )
    assert total >= 0
    assert papers


@pytest.mark.integration
@pytest.mark.anyio
async def test_openalex_detail_fetch_works():
    papers, total = openalex_search(
        "breast cancer",
        page=1,
        n=3,
        sort="relevance",
    )
    assert total >= 0
    assert papers

    wid = papers[0].id
    detail = openalex_fetch_detail(wid)
    if detail is None:
        pytest.skip("OpenAlex detail fetch timed out or returned no data")

    assert detail.id
    assert detail.title
    assert detail.source == "openalex"


@pytest.mark.integration
@pytest.mark.anyio
async def test_openalex_abstract_present_for_some_records():
    papers, total = openalex_search(
        "machine learning",
        page=1,
        n=10,
        sort="relevance",
        year_min=2021,
        year_max=2023,
    )
    assert total >= 0
    assert papers

    has_any_abstract = any((p.abstract or "").strip() for p in papers)
    assert has_any_abstract


@pytest.mark.integration
@pytest.mark.anyio
async def test_openalex_year_range_semantics():
    papers, total = openalex_search(
        "cancer",
        page=1,
        n=10,
        year_min=2020,
        year_max=2021,
    )
    years = [p.year for p in papers if p.year is not None]
    assert years
    assert all(2020 <= y <= 2021 for y in years)


def test_openalex_search_retries_after_429(monkeypatch):
    calls = []

    class FakeResponse:
        def __init__(self, status_code, data=None):
            self.status_code = status_code
            self._data = data or {}
            self.url = "https://api.openalex.org/works"

        def raise_for_status(self):
            return None

        def json(self):
            return self._data

    responses = [
        FakeResponse(429),
        FakeResponse(
            200,
            {
                "meta": {"count": 1},
                "results": [
                    {
                        "id": "https://openalex.org/W123",
                        "title": "Test paper",
                        "publication_year": 2024,
                        "doi": "https://doi.org/10.1234/test",
                        "primary_location": {
                            "landing_page_url": "https://example.test/paper",
                            "source": {"display_name": "Test Journal"},
                        },
                        "authorships": [
                            {
                                "author": {
                                    "display_name": "Test Author",
                                }
                            }
                        ],
                        "concepts": [],
                        "abstract": "Test abstract",
                    }
                ],
            },
        ),
    ]

    def fake_get(*args, **kwargs):
        calls.append(1)
        return responses.pop(0)

    monkeypatch.setattr(
        "app.connectors.openalex.requests.get",
        fake_get,
    )
    monkeypatch.setattr(
        "app.connectors.openalex.time.sleep",
        lambda seconds: None,
    )

    papers, total = openalex_search(
        "cancer",
        page=1,
        n=10,
        sort="relevance",
    )

    assert len(calls) == 2
    assert total == 1
    assert len(papers) == 1
    assert papers[0].id == "W123"


def test_openalex_search_stops_after_repeated_429(monkeypatch):
    calls = []

    class FakeResponse:
        status_code = 429
        headers = {}
        url = "https://api.openalex.org/works"

    def fake_get(*args, **kwargs):
        calls.append(1)
        return FakeResponse()

    monkeypatch.setattr(
        "app.connectors.openalex.requests.get",
        fake_get,
    )
    monkeypatch.setattr(
        "app.connectors.openalex.time.sleep",
        lambda seconds: None,
    )

    papers, total = openalex_search(
        "cancer",
        page=1,
        n=10,
        sort="relevance",
    )

    assert len(calls) == 3
    assert papers == []
    assert total == 0
