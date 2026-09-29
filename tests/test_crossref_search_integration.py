from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.models.paper import Paper

CROSSREF_ID = "10.1234/example"

SAMPLE_PAPER = Paper(
    id=CROSSREF_ID,
    source="crossref",
    title="Example Crossref article",
    authors=["Jane Doe", "John Smith"],
    journal="Example Journal",
    year=2025,
    publication_date=None,
    abstract="Example abstract",
    doi=CROSSREF_ID,
    url="https://example.org/article",
    has_full_text=False,
    concepts=[],
)


def test_crossref_is_allowed_source() -> None:
    assert "crossref" in app.state.allowed_sources


@patch("app.main.crossref_search")
def test_crossref_search_renders_results(mock_crossref_search) -> None:
    mock_crossref_search.return_value = ([SAMPLE_PAPER], 1)

    with TestClient(app) as client:
        response = client.get(
            "/search",
            params={
                "source": "crossref",
                "q": "machine learning cancer",
                "page": 1,
                "n": 20,
                "sort": "relevance",
                "year_min": "",
                "year_max": "",
                "has_abstract": 0,
            },
        )

    assert response.status_code == 200
    assert "Crossref" in response.text
    assert SAMPLE_PAPER.title in response.text
    assert f"/paper/crossref/{CROSSREF_ID}" in response.text
    assert "Open in Crossref" in response.text


@patch("app.main.crossref_search")
def test_crossref_search_empty_query_does_not_call_connector(
    mock_crossref_search,
) -> None:
    with TestClient(app) as client:
        response = client.get(
            "/search",
            params={
                "source": "crossref",
                "q": "",
                "page": 1,
                "n": 20,
                "sort": "relevance",
                "year_min": "",
                "year_max": "",
                "has_abstract": 0,
            },
        )

    assert response.status_code == 200
    mock_crossref_search.assert_not_called()


@patch("app.main.crossref_search")
def test_crossref_search_passes_filters(mock_crossref_search) -> None:
    mock_crossref_search.return_value = ([SAMPLE_PAPER], 1)

    with TestClient(app) as client:
        response = client.get(
            "/search",
            params={
                "source": "crossref",
                "q": "cancer",
                "page": 2,
                "n": 10,
                "sort": "date_desc",
                "year_min": "2020",
                "year_max": "2025",
                "has_abstract": 1,
            },
        )

    assert response.status_code == 200

    mock_crossref_search.assert_called_once_with(
        "cancer",
        page=2,
        n=10,
        sort="date_desc",
        year_min=2020,
        year_max=2025,
        has_abstract=True,
    )


@patch("app.main.crossref_fetch_detail")
def test_crossref_detail_page_renders(mock_crossref_fetch_detail) -> None:
    mock_crossref_fetch_detail.return_value = SAMPLE_PAPER

    with TestClient(app) as client:
        response = client.get(f"/paper/crossref/{CROSSREF_ID}")

    assert response.status_code == 200
    assert SAMPLE_PAPER.title in response.text
    assert "Open in Crossref" in response.text
    assert "https://example.org/article" in response.text


@patch("app.main.crossref_fetch_detail")
def test_crossref_missing_detail_returns_404(mock_crossref_fetch_detail) -> None:
    mock_crossref_fetch_detail.return_value = None

    with TestClient(app) as client:
        response = client.get("/paper/crossref/10.1234/missing-record")

    assert response.status_code == 404


@patch("app.main.crossref_search")
def test_crossref_search_renders_page_navigation(mock_crossref_search) -> None:
    mock_crossref_search.return_value = ([SAMPLE_PAPER], 50)

    with TestClient(app) as client:
        response = client.get(
            "/search",
            params={
                "source": "crossref",
                "q": "cancer",
                "page": 2,
                "n": 10,
                "sort": "relevance",
                "year_min": "",
                "year_max": "",
                "has_abstract": 0,
            },
        )

    assert response.status_code == 200
    assert ">Previous</a>" in response.text
    assert "page=1" in response.text
    assert ">Next</a>" in response.text
    assert "page=3" in response.text
    assert ">Last</a>" in response.text
    assert "page=5" in response.text
