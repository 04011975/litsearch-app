from __future__ import annotations

from unittest.mock import Mock, patch

import pytest
import requests

from app.connectors.doaj import (
    DoajError,
    _extract_authors,
    _extract_concepts,
    _extract_doi,
    _extract_journal,
    _extract_url,
    _extract_year,
    _has_full_text,
    _to_paper,
    doaj_search,
)

SAMPLE_RECORD = {
    "id": "000122f776cb4f27b0f575971a4bed38",
    "created_date": "2025-01-17T18:52:28Z",
    "last_updated": "2025-08-20T01:49:50Z",
    "bibjson": {
        "title": (
            "A feature selection and scoring scheme for dimensionality "
            "reduction in a machine learning task"
        ),
        "abstract": "Example abstract",
        "year": "2025",
        "month": "February",
        "author": [
            {"name": "Jane Doe", "affiliation": "Example University"},
            {"name": "John Smith"},
        ],
        "identifier": [
            {"type": "doi", "id": "10.1234/example"},
            {"type": "pissn", "id": "1234-5678"},
        ],
        "journal": {
            "title": "Example Journal",
            "publisher": "Example Publisher",
        },
        "link": [
            {
                "type": "fulltext",
                "content_type": "HTML",
                "url": "https://example.org/article",
            }
        ],
        "keywords": ["Machine learning", "Cancer"],
        "subject": [
            {
                "scheme": "LCC",
                "code": "Q1-390",
                "term": "Science",
            }
        ],
    },
}


def test_extract_authors() -> None:
    authors = _extract_authors(SAMPLE_RECORD["bibjson"])

    assert authors == ["Jane Doe", "John Smith"]


def test_extract_doi() -> None:
    doi = _extract_doi(SAMPLE_RECORD["bibjson"])

    assert doi == "10.1234/example"


def test_extract_doi_normalizes_doi_url() -> None:
    bibjson = {
        "identifier": [
            {
                "type": "doi",
                "id": "https://doi.org/10.1234/example",
            }
        ]
    }

    assert _extract_doi(bibjson) == "10.1234/example"


def test_extract_year() -> None:
    assert _extract_year(SAMPLE_RECORD["bibjson"]) == 2025


def test_extract_year_invalid_value() -> None:
    assert _extract_year({"year": "not-a-year"}) is None


def test_extract_journal() -> None:
    assert _extract_journal(SAMPLE_RECORD["bibjson"]) == "Example Journal"


def test_extract_url_prefers_fulltext() -> None:
    bibjson = {
        "link": [
            {
                "type": "other",
                "url": "https://example.org/landing",
            },
            {
                "type": "fulltext",
                "url": "https://example.org/fulltext",
            },
        ]
    }

    assert _extract_url(bibjson) == "https://example.org/fulltext"


def test_has_full_text() -> None:
    assert _has_full_text(SAMPLE_RECORD["bibjson"]) is True


def test_extract_concepts_combines_keywords_and_subjects() -> None:
    concepts = _extract_concepts(SAMPLE_RECORD["bibjson"])

    assert concepts == [
        "Machine learning",
        "Cancer",
        "Science",
    ]


def test_to_paper_maps_doaj_record() -> None:
    paper = _to_paper(SAMPLE_RECORD)

    assert paper.id == "000122f776cb4f27b0f575971a4bed38"
    assert paper.source == "doaj"
    assert paper.title.startswith("A feature selection")
    assert paper.authors == ["Jane Doe", "John Smith"]
    assert paper.journal == "Example Journal"
    assert paper.year == 2025
    assert paper.publication_date is None
    assert paper.abstract == "Example abstract"
    assert paper.doi == "10.1234/example"
    assert paper.url == "https://example.org/article"
    assert paper.has_full_text is True
    assert paper.concepts == ["Machine learning", "Cancer", "Science"]


def test_doaj_search_empty_query() -> None:
    papers, total = doaj_search("")

    assert papers == []
    assert total == 0


@patch("app.connectors.doaj.requests.get")
def test_doaj_search_maps_response(mock_get: Mock) -> None:
    response = Mock()
    response.status_code = 200
    response.json.return_value = {
        "total": 1,
        "page": 1,
        "pageSize": 20,
        "results": [SAMPLE_RECORD],
    }

    mock_get.return_value = response

    papers, total = doaj_search(
        "machine learning cancer",
        page=1,
        n=20,
    )

    assert total == 1
    assert len(papers) == 1
    assert papers[0].source == "doaj"
    assert papers[0].doi == "10.1234/example"

    mock_get.assert_called_once()


@patch("app.connectors.doaj.requests.get")
def test_doaj_search_applies_year_filter(mock_get: Mock) -> None:
    response = Mock()
    response.status_code = 200
    response.json.return_value = {
        "total": 1,
        "results": [SAMPLE_RECORD],
    }

    mock_get.return_value = response

    papers, total = doaj_search(
        "machine learning",
        year_min=2026,
    )

    assert total == 1
    assert papers == []


@patch("app.connectors.doaj.requests.get")
def test_doaj_search_applies_abstract_filter(mock_get: Mock) -> None:
    record = {
        **SAMPLE_RECORD,
        "bibjson": {
            **SAMPLE_RECORD["bibjson"],
            "abstract": None,
        },
    }

    response = Mock()
    response.status_code = 200
    response.json.return_value = {
        "total": 1,
        "results": [record],
    }

    mock_get.return_value = response

    papers, total = doaj_search(
        "machine learning",
        has_abstract=True,
    )

    assert total == 1
    assert papers == []


@patch("app.connectors.doaj.requests.get")
def test_doaj_search_raises_on_http_error(mock_get: Mock) -> None:
    response = Mock()
    response.status_code = 500
    response.text = "Internal Server Error"

    mock_get.return_value = response

    with pytest.raises(DoajError, match="DOAJ API error 500"):
        doaj_search("machine learning")


@patch("app.connectors.doaj.requests.get")
def test_doaj_search_raises_on_invalid_json(mock_get: Mock) -> None:
    response = Mock()
    response.status_code = 200
    response.json.side_effect = ValueError("invalid json")

    mock_get.return_value = response

    with pytest.raises(DoajError, match="DOAJ returned invalid JSON"):
        doaj_search("machine learning")


@patch("app.connectors.doaj.requests.get")
def test_doaj_search_raises_on_malformed_results(mock_get: Mock) -> None:
    response = Mock()
    response.status_code = 200
    response.json.return_value = {
        "total": 1,
        "results": "not-a-list",
    }

    mock_get.return_value = response

    with pytest.raises(
        DoajError,
        match="DOAJ search returned malformed results list",
    ):
        doaj_search("machine learning")


@patch("app.connectors.doaj.requests.get")
def test_doaj_search_wraps_timeout(mock_get: Mock) -> None:
    mock_get.side_effect = requests.exceptions.Timeout()
    with pytest.raises(DoajError, match="DOAJ request timed out"):
        doaj_search("machine learning")
