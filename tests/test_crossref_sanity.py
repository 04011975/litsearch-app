from unittest.mock import Mock, patch

from app.connectors.crossref import crossref_search


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

    assert params["filter"] == (
        "from-pub-date:2020-01-01,"
        "until-pub-date:2025-12-31"
    )
