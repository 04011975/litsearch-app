
from app.connectors.openalex import _normalize_doi


def test_openalex_normalize_doi_existing_behavior():
    assert _normalize_doi("10.1000/EXAMPLE") == "10.1000/example"
    assert (
        _normalize_doi("https://doi.org/10.1000/EXAMPLE")
        == "10.1000/example"
    )
    assert _normalize_doi("doi:10.1000/EXAMPLE") == "10.1000/example"
    assert _normalize_doi("") is None

    # Bestaand gedrag: geen strikte DOI-validatie.
    assert _normalize_doi("invalid-doi") == "invalid-doi"



def test_openalex_search_maps_metadata(monkeypatch):
    from app.connectors.openalex import openalex_search
    import app.connectors.openalex as openalex

    work = {
        "id": "https://openalex.org/W123456789",
        "doi": "https://doi.org/10.1000/example",
        "title": "Example Article",
        "publication_year": 2024,
        "authorships": [
            {"author": {"display_name": "Jane Doe"}}
        ],
        "primary_location": {
            "landing_page_url": "https://example.org/article",
            "source": {"display_name": "Example Journal"},
        },
        "abstract_inverted_index": {
            "Example": [0],
            "abstract": [1],
        },
        "concepts": [
            {"display_name": "Machine Learning"}
        ],
    }

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {
                "results": [work],
                "meta": {"count": 1},
            }

    monkeypatch.setattr(
        openalex.requests,
        "get",
        lambda *args, **kwargs: FakeResponse(),
    )

    papers, total = openalex_search("example")

    assert total == 1
    assert len(papers) == 1

    paper = papers[0]

    assert paper.id == "W123456789"
    assert paper.source == "openalex"
    assert paper.title == "Example Article"
    assert paper.authors == ["Jane Doe"]
    assert paper.journal == "Example Journal"
    assert paper.year == 2024
    assert paper.doi == "10.1000/example"
    assert paper.url == "https://example.org/article"
    assert paper.abstract == "Example abstract"
    assert paper.concepts == ["Machine Learning"]



def test_openalex_fetch_detail_maps_metadata(monkeypatch):
    import app.connectors.openalex as openalex

    work = {
        "id": "https://openalex.org/W123456789",
        "doi": "https://doi.org/10.1000/example",
        "title": "Example Article",
        "publication_year": 2024,
        "authorships": [
            {"author": {"display_name": "Jane Doe"}}
        ],
        "primary_location": {
            "landing_page_url": "https://example.org/article",
            "source": {"display_name": "Example Journal"},
        },
        "abstract_inverted_index": {
            "Example": [0],
            "abstract": [1],
        },
        "concepts": [
            {"display_name": "Machine Learning"}
        ],
    }

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return work

    def fake_get(url, *, params, timeout, headers):
        assert url == "https://api.openalex.org/works/W123456789"
        return FakeResponse()

    monkeypatch.setattr(openalex.requests, "get", fake_get)

    paper = openalex.openalex_fetch_detail("W123456789")

    assert paper is not None
    assert paper.id == "W123456789"
    assert paper.source == "openalex"
    assert paper.title == "Example Article"
    assert paper.authors == ["Jane Doe"]
    assert paper.journal == "Example Journal"
    assert paper.year == 2024
    assert paper.doi == "10.1000/example"
    assert paper.url == "https://example.org/article"
    assert paper.abstract == "Example abstract"
    assert paper.concepts == ["Machine Learning"]



def test_openalex_fetch_detail_uses_requested_id_when_response_id_missing(
    monkeypatch,
):
    import app.connectors.openalex as openalex

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {
                "title": "Article Without Response ID",
                "publication_year": 2024,
            }

    def fake_get(url, *, params, timeout, headers):
        assert url == "https://api.openalex.org/works/W123456789"
        return FakeResponse()

    monkeypatch.setattr(openalex.requests, "get", fake_get)

    paper = openalex.openalex_fetch_detail("W123456789")

    assert paper is not None
    assert paper.id == "W123456789"
    assert paper.title == "Article Without Response ID"
    assert paper.source == "openalex"
