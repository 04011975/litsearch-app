from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.models.paper import Paper

DOAJ_ID = "000122f776cb4f27b0f575971a4bed38"

SAMPLE_PAPER = Paper(
    id=DOAJ_ID,
    source="doaj",
    title=(
        "A feature selection and scoring scheme for dimensionality "
        "reduction in a machine learning task"
    ),
    authors=["Jane Doe", "John Smith"],
    journal="Example Journal",
    year=2025,
    publication_date=None,
    abstract="Example abstract",
    doi="10.1234/example",
    url="https://example.org/article",
    has_full_text=True,
    concepts=["Machine learning", "Cancer"],
)


def test_doaj_is_allowed_source() -> None:
    assert "doaj" in app.state.allowed_sources


@patch("app.main.doaj_search")
def test_doaj_search_renders_results(mock_doaj_search) -> None:
    mock_doaj_search.return_value = ([SAMPLE_PAPER], 1)

    with TestClient(app) as client:
        response = client.get(
            "/search",
            params={
                "source": "doaj",
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
    assert "DOAJ" in response.text
    assert SAMPLE_PAPER.title in response.text
    assert f"/paper/doaj/{DOAJ_ID}" in response.text
    assert "Open in DOAJ" in response.text


@patch("app.main.doaj_search")
def test_doaj_search_empty_query_does_not_call_connector(mock_doaj_search) -> None:
    with TestClient(app) as client:
        response = client.get(
            "/search",
            params={
                "source": "doaj",
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
    mock_doaj_search.assert_not_called()


@patch("app.main.doaj_search")
def test_doaj_search_passes_filters(mock_doaj_search) -> None:
    mock_doaj_search.return_value = ([SAMPLE_PAPER], 1)

    with TestClient(app) as client:
        response = client.get(
            "/search",
            params={
                "source": "doaj",
                "q": "cancer",
                "page": 2,
                "n": 10,
                "sort": "relevance",
                "year_min": "2020",
                "year_max": "2025",
                "has_abstract": 1,
            },
        )

    assert response.status_code == 200

    mock_doaj_search.assert_called_once_with(
        "cancer",
        page=2,
        n=10,
        year_min=2020,
        year_max=2025,
        has_abstract=True,
    )


@patch("app.main.doaj_fetch_detail")
def test_doaj_detail_page_renders(mock_doaj_fetch_detail) -> None:
    mock_doaj_fetch_detail.return_value = SAMPLE_PAPER

    with TestClient(app) as client:
        response = client.get(f"/paper/doaj/{DOAJ_ID}")

    assert response.status_code == 200
    assert SAMPLE_PAPER.title in response.text
    assert "Open in DOAJ" in response.text
    assert "https://example.org/article" in response.text


@patch("app.main.doaj_fetch_detail")
def test_doaj_missing_detail_returns_404(mock_doaj_fetch_detail) -> None:
    mock_doaj_fetch_detail.return_value = None

    with TestClient(app) as client:
        response = client.get("/paper/doaj/missing-record")

    assert response.status_code == 404
