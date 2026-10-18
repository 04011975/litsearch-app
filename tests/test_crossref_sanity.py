from unittest.mock import Mock, patch

from app.connectors.crossref import crossref_search

from app.connectors.crossref import _map_item_to_paper

import pytest
import requests

@patch("app.connectors.crossref.requests.get")
def test_crossref_search_adds_has_abstract_filter(mock_get):
    response = Mock()
    response.status_code = 200
    response.json.return_value = {
        "message": {
            "total-results": 0,
            "items": [],
        }
    }
    mock_get.return_value = response

    crossref_search(
        "machine learning cancer",
        page=1,
        n=10,
        year_min=2020,
        has_abstract=True,
    )

    params = mock_get.call_args.kwargs["params"]

    assert params["filter"] == "from-pub-date:2020-01-01,has-abstract:true"


@patch("app.connectors.crossref.requests.get")
def test_crossref_search_does_not_add_abstract_filter_when_disabled(mock_get):
    response = Mock()
    response.status_code = 200
    response.json.return_value = {
        "message": {
            "total-results": 0,
            "items": [],
        }
    }
    mock_get.return_value = response

    crossref_search(
        "machine learning cancer",
        page=1,
        n=10,
        year_min=2020,
        year_max=2025,
        has_abstract=False,
    )

    params = mock_get.call_args.kwargs["params"]

    assert params["filter"] == ("from-pub-date:2020-01-01," "until-pub-date:2025-12-31")


@patch("app.connectors.crossref.requests.get")
def test_crossref_fetch_detail_encodes_special_doi_characters(mock_get):
    from app.connectors.crossref import crossref_fetch_detail

    response = Mock()
    response.status_code = 404
    mock_get.return_value = response

    crossref_fetch_detail("10.1000/example?part=1#section")

    mock_get.assert_called_once()

    url = mock_get.call_args.args[0]

    assert url == (
        "https://api.crossref.org/works/" "10.1000%2Fexample%3Fpart%3D1%23section"
    )


@patch("app.connectors.crossref.requests.get")
def test_crossref_fetch_detail_rejects_empty_identifier(mock_get):
    from app.connectors.crossref import crossref_fetch_detail

    assert crossref_fetch_detail("") is None
    assert crossref_fetch_detail(None) is None

    mock_get.assert_not_called()


@patch("app.connectors.crossref.requests.get")
def test_crossref_fetch_detail_raises_on_rate_limit(mock_get):
    import pytest

    from app.connectors.crossref import crossref_fetch_detail

    response = Mock()
    response.status_code = 429
    response.raise_for_status.side_effect = (
        __import__("requests").exceptions.HTTPError(
            "429 Too Many Requests"
        )
    )
    mock_get.return_value = response

    with pytest.raises(
        __import__("requests").exceptions.HTTPError
    ):
        crossref_fetch_detail("10.1000/example")

    mock_get.assert_called_once()


@patch("app.connectors.crossref.requests.get")
def test_crossref_fetch_detail_raises_on_server_error(mock_get):
    from app.connectors.crossref import crossref_fetch_detail

    response = Mock()
    response.status_code = 503
    response.raise_for_status.side_effect = requests.exceptions.HTTPError(
        "503 Service Unavailable"
    )
    mock_get.return_value = response

    with pytest.raises(requests.exceptions.HTTPError):
        crossref_fetch_detail("10.1000/example")

    mock_get.assert_called_once()


@patch("app.connectors.crossref.requests.get")
def test_crossref_fetch_detail_raises_on_timeout(mock_get):
    from app.connectors.crossref import crossref_fetch_detail

    mock_get.side_effect = requests.exceptions.Timeout(
        "Crossref request timed out"
    )

    with pytest.raises(requests.exceptions.Timeout):
        crossref_fetch_detail("10.1000/example")

    mock_get.assert_called_once()


def test_crossref_mapping_normalizes_doi_url():
    paper = _map_item_to_paper(
        {
            "DOI": "https://dx.doi.org/10.1000/Example",
            "title": ["Example publication"],
            "URL": "https://doi.org/10.1000/Example",
        }
    )

    assert paper.doi == "10.1000/example"
    assert paper.id == "10.1000/example"


def test_crossref_mapping_rejects_invalid_doi():
    paper = _map_item_to_paper(
        {
            "DOI": "not-a-valid-doi",
            "title": ["Example publication"],
            "URL": "https://example.org/publication",
        }
    )

    assert paper.doi is None
    assert paper.id == "https://example.org/publication"
