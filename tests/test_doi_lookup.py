from app.doi_lookup import DoiLookupResult
from app.models.paper import Paper


def test_doi_lookup_result_defaults():
    result = DoiLookupResult(doi="10.1000/example")

    assert result.doi == "10.1000/example"
    assert result.paper is None
    assert result.found_in == []
    assert result.failed_sources == []


def test_doi_lookup_result_with_verified_source():
    paper = Paper(
        id="10.1000/example",
        source="crossref",
        title="Example Article",
        doi="10.1000/example",
    )

    result = DoiLookupResult(
        doi="10.1000/example",
        paper=paper,
        found_in=["crossref"],
    )

    assert result.paper is paper
    assert result.found_in == ["crossref"]
    assert result.failed_sources == []


def test_doi_lookup_result_with_failed_source():
    result = DoiLookupResult(
        doi="10.1000/example",
        failed_sources=["pubmed"],
    )

    assert result.paper is None
    assert result.found_in == []
    assert result.failed_sources == ["pubmed"]


def test_doi_lookup_result_lists_are_independent():
    first = DoiLookupResult(doi="10.1000/first")
    second = DoiLookupResult(doi="10.1000/second")

    first.found_in.append("crossref")
    first.failed_sources.append("pubmed")

    assert second.found_in == []
    assert second.failed_sources == []


import pytest


def test_lookup_crossref_doi_exact_match(monkeypatch):
    import asyncio

    from app.doi_lookup import lookup_crossref_doi
    import app.connectors.crossref as crossref

    paper = Paper(
        id="10.1000/example",
        source="crossref",
        title="Exact DOI Match",
        doi="10.1000/example",
    )

    def fake_crossref_fetch_detail(identifier):
        assert identifier == "10.1000/example"
        return paper

    monkeypatch.setattr(
        crossref,
        "crossref_fetch_detail",
        fake_crossref_fetch_detail,
    )

    result = asyncio.run(
        lookup_crossref_doi("https://doi.org/10.1000/EXAMPLE")
    )

    assert result is paper


def test_lookup_crossref_doi_rejects_mismatch(monkeypatch):
    import asyncio

    from app.doi_lookup import lookup_crossref_doi
    import app.connectors.crossref as crossref

    paper = Paper(
        id="10.1000/different",
        source="crossref",
        title="Incorrect DOI Match",
        doi="10.1000/different",
    )

    def fake_crossref_fetch_detail(identifier):
        assert identifier == "10.1000/example"
        return paper

    monkeypatch.setattr(
        crossref,
        "crossref_fetch_detail",
        fake_crossref_fetch_detail,
    )

    result = asyncio.run(
        lookup_crossref_doi("10.1000/example")
    )

    assert result is None


def test_lookup_crossref_doi_rejects_missing_doi(monkeypatch):
    import asyncio

    from app.doi_lookup import lookup_crossref_doi
    import app.connectors.crossref as crossref

    paper = Paper(
        id="crossref-record-without-doi",
        source="crossref",
        title="Article Without DOI",
        doi=None,
    )

    def fake_crossref_fetch_detail(identifier):
        assert identifier == "10.1000/example"
        return paper

    monkeypatch.setattr(
        crossref,
        "crossref_fetch_detail",
        fake_crossref_fetch_detail,
    )

    result = asyncio.run(
        lookup_crossref_doi("10.1000/example")
    )

    assert result is None


def test_lookup_crossref_doi_propagates_api_error(monkeypatch):
    import asyncio

    from app.doi_lookup import lookup_crossref_doi
    import app.connectors.crossref as crossref

    def fake_crossref_fetch_detail(identifier):
        assert identifier == "10.1000/example"
        raise RuntimeError("Crossref API unavailable")

    monkeypatch.setattr(
        crossref,
        "crossref_fetch_detail",
        fake_crossref_fetch_detail,
    )

    try:
        asyncio.run(
            lookup_crossref_doi("10.1000/example")
        )
    except RuntimeError as exc:
        assert str(exc) == "Crossref API unavailable"
    else:
        raise AssertionError("Expected Crossref API error")


def test_lookup_crossref_doi_rejects_invalid_input(monkeypatch):
    import asyncio

    from app.doi_lookup import lookup_crossref_doi
    import app.connectors.crossref as crossref

    def fake_crossref_fetch_detail(identifier):
        raise AssertionError(
            "Crossref must not be called for an invalid DOI"
        )

    monkeypatch.setattr(
        crossref,
        "crossref_fetch_detail",
        fake_crossref_fetch_detail,
    )

    result = asyncio.run(
        lookup_crossref_doi("not-a-valid-doi")
    )

    assert result is None


def test_lookup_pubmed_doi_exact_match(monkeypatch):
    import asyncio

    from app.doi_lookup import lookup_pubmed_doi
    import app.connectors.pubmed as pubmed

    paper = Paper(
        id="12345678",
        source="pubmed",
        title="Exact DOI Match",
        doi="10.1000/example",
    )

    async def fake_resolve_pmid_by_doi(doi):
        assert doi == "10.1000/example"
        return "12345678"

    async def fake_fetch_details(pmids):
        assert pmids == ["12345678"]
        return [paper]

    monkeypatch.setattr(
        pubmed,
        "pubmed_resolve_pmid_by_doi",
        fake_resolve_pmid_by_doi,
    )
    monkeypatch.setattr(
        pubmed,
        "pubmed_fetch_details",
        fake_fetch_details,
    )

    result = asyncio.run(
        lookup_pubmed_doi("https://doi.org/10.1000/example")
    )

    assert result is paper
    assert result.doi == "10.1000/example"


def test_lookup_pubmed_doi_rejects_mismatch(monkeypatch):
    import asyncio

    from app.doi_lookup import lookup_pubmed_doi
    import app.connectors.pubmed as pubmed

    paper = Paper(
        id="12345678",
        source="pubmed",
        title="Incorrect DOI Match",
        doi="10.1000/different",
    )

    async def fake_resolve_pmid_by_doi(doi):
        assert doi == "10.1000/example"
        return "12345678"

    async def fake_fetch_details(pmids):
        assert pmids == ["12345678"]
        return [paper]

    monkeypatch.setattr(
        pubmed,
        "pubmed_resolve_pmid_by_doi",
        fake_resolve_pmid_by_doi,
    )
    monkeypatch.setattr(
        pubmed,
        "pubmed_fetch_details",
        fake_fetch_details,
    )

    result = asyncio.run(
        lookup_pubmed_doi("10.1000/example")
    )

    assert result is None


def test_lookup_pubmed_doi_not_found(monkeypatch):
    import asyncio

    from app.doi_lookup import lookup_pubmed_doi
    import app.connectors.pubmed as pubmed

    async def fake_resolve_pmid_by_doi(doi):
        assert doi == "10.1000/example"
        return None

    async def fake_fetch_details(pmids):
        raise AssertionError(
            "PubMed details must not be fetched when no PMID is found"
        )

    monkeypatch.setattr(
        pubmed,
        "pubmed_resolve_pmid_by_doi",
        fake_resolve_pmid_by_doi,
    )
    monkeypatch.setattr(
        pubmed,
        "pubmed_fetch_details",
        fake_fetch_details,
    )

    result = asyncio.run(
        lookup_pubmed_doi("10.1000/example")
    )

    assert result is None



def test_lookup_pubmed_doi_rejects_missing_doi(monkeypatch):
    import asyncio

    from app.doi_lookup import lookup_pubmed_doi
    import app.connectors.pubmed as pubmed

    paper = Paper(
        id="12345678",
        source="pubmed",
        title="Article Without DOI",
        doi=None,
    )

    async def fake_resolve_pmid_by_doi(doi):
        assert doi == "10.1000/example"
        return "12345678"

    async def fake_fetch_details(pmids):
        assert pmids == ["12345678"]
        return [paper]

    monkeypatch.setattr(
        pubmed,
        "pubmed_resolve_pmid_by_doi",
        fake_resolve_pmid_by_doi,
    )
    monkeypatch.setattr(
        pubmed,
        "pubmed_fetch_details",
        fake_fetch_details,
    )

    result = asyncio.run(
        lookup_pubmed_doi("10.1000/example")
    )

    assert result is None



def test_lookup_pubmed_doi_rejects_invalid_input(monkeypatch):
    import asyncio

    from app.doi_lookup import lookup_pubmed_doi
    import app.connectors.pubmed as pubmed

    async def fake_resolve_pmid_by_doi(doi):
        raise AssertionError(
            "PubMed must not be called for an invalid DOI"
        )

    async def fake_fetch_details(pmids):
        raise AssertionError(
            "PubMed details must not be fetched for an invalid DOI"
        )

    monkeypatch.setattr(
        pubmed,
        "pubmed_resolve_pmid_by_doi",
        fake_resolve_pmid_by_doi,
    )
    monkeypatch.setattr(
        pubmed,
        "pubmed_fetch_details",
        fake_fetch_details,
    )

    result = asyncio.run(
        lookup_pubmed_doi("not-a-valid-doi")
    )

    assert result is None



def test_lookup_pubmed_doi_propagates_api_error(monkeypatch):
    import asyncio

    from app.doi_lookup import lookup_pubmed_doi
    import app.connectors.pubmed as pubmed

    async def fake_resolve_pmid_by_doi(doi):
        assert doi == "10.1000/example"
        raise RuntimeError("PubMed API unavailable")

    async def fake_fetch_details(pmids):
        raise AssertionError(
            "PubMed details must not be fetched after an API error"
        )

    monkeypatch.setattr(
        pubmed,
        "pubmed_resolve_pmid_by_doi",
        fake_resolve_pmid_by_doi,
    )
    monkeypatch.setattr(
        pubmed,
        "pubmed_fetch_details",
        fake_fetch_details,
    )

    try:
        asyncio.run(
            lookup_pubmed_doi("10.1000/example")
        )
    except RuntimeError as exc:
        assert str(exc) == "PubMed API unavailable"
    else:
        raise AssertionError("Expected PubMed API error")



def test_lookup_pubmed_doi_propagates_fetch_error(monkeypatch):
    import asyncio

    import pytest
    from app.doi_lookup import lookup_pubmed_doi
    import app.connectors.pubmed as pubmed

    async def fake_resolve_pmid_by_doi(doi):
        assert doi == "10.1000/example"
        return "12345678"

    async def fake_fetch_details(pmids):
        assert pmids == ["12345678"]
        raise RuntimeError("PubMed detail API unavailable")

    monkeypatch.setattr(
        pubmed,
        "pubmed_resolve_pmid_by_doi",
        fake_resolve_pmid_by_doi,
    )
    monkeypatch.setattr(
        pubmed,
        "pubmed_fetch_details",
        fake_fetch_details,
    )

    with pytest.raises(
        RuntimeError,
        match="PubMed detail API unavailable",
    ):
        asyncio.run(
            lookup_pubmed_doi("10.1000/example")
        )



def test_lookup_europe_pmc_doi_exact_match(monkeypatch):
    import asyncio

    from app.doi_lookup import lookup_europe_pmc_doi
    import app.connectors.europe_pmc as europe_pmc

    paper = Paper(
        id="12345678",
        source="europe_pmc",
        title="Exact DOI Match",
        doi="10.1000/example",
    )

    def fake_europe_pmc_search(q, *, n, retries):
        assert q == "DOI:10.1000/example"
        assert n == 10
        assert retries == 2
        return [paper], 1, None

    monkeypatch.setattr(
        europe_pmc,
        "europe_pmc_search",
        fake_europe_pmc_search,
    )

    result = asyncio.run(
        lookup_europe_pmc_doi("https://doi.org/10.1000/EXAMPLE")
    )

    assert result is paper
    assert result.doi == "10.1000/example"



def test_lookup_europe_pmc_doi_rejects_mismatch(monkeypatch):
    import asyncio

    from app.doi_lookup import lookup_europe_pmc_doi
    import app.connectors.europe_pmc as europe_pmc

    paper = Paper(
        id="12345678",
        source="europe_pmc",
        title="Incorrect DOI Match",
        doi="10.1000/different",
    )

    def fake_europe_pmc_search(q, *, n, retries):
        assert q == "DOI:10.1000/example"
        assert n == 10
        assert retries == 2
        return [paper], 1, None

    monkeypatch.setattr(
        europe_pmc,
        "europe_pmc_search",
        fake_europe_pmc_search,
    )

    result = asyncio.run(
        lookup_europe_pmc_doi("10.1000/example")
    )

    assert result is None


def test_lookup_europe_pmc_doi_rejects_missing_doi(monkeypatch):
    import asyncio

    from app.doi_lookup import lookup_europe_pmc_doi
    import app.connectors.europe_pmc as europe_pmc

    paper = Paper(
        id="12345678",
        source="europe_pmc",
        title="Article Without DOI",
        doi=None,
    )

    def fake_europe_pmc_search(q, *, n, retries):
        assert q == "DOI:10.1000/example"
        assert n == 10
        assert retries == 2
        return [paper], 1, None

    monkeypatch.setattr(
        europe_pmc,
        "europe_pmc_search",
        fake_europe_pmc_search,
    )

    result = asyncio.run(
        lookup_europe_pmc_doi("10.1000/example")
    )

    assert result is None



def test_lookup_europe_pmc_doi_not_found(monkeypatch):
    import asyncio

    from app.doi_lookup import lookup_europe_pmc_doi
    import app.connectors.europe_pmc as europe_pmc

    def fake_europe_pmc_search(q, *, n, retries):
        assert q == "DOI:10.1000/example"
        assert n == 10
        assert retries == 2
        return [], 0, None

    monkeypatch.setattr(
        europe_pmc,
        "europe_pmc_search",
        fake_europe_pmc_search,
    )

    result = asyncio.run(
        lookup_europe_pmc_doi("10.1000/example")
    )

    assert result is None



def test_lookup_europe_pmc_doi_rejects_invalid_input(monkeypatch):
    import asyncio

    from app.doi_lookup import lookup_europe_pmc_doi
    import app.connectors.europe_pmc as europe_pmc

    def fake_europe_pmc_search(q, *, n, retries):
        raise AssertionError(
            "Europe PMC must not be called for an invalid DOI"
        )

    monkeypatch.setattr(
        europe_pmc,
        "europe_pmc_search",
        fake_europe_pmc_search,
    )

    result = asyncio.run(
        lookup_europe_pmc_doi("not-a-valid-doi")
    )

    assert result is None



def test_lookup_europe_pmc_doi_propagates_api_error(monkeypatch):
    import asyncio

    import pytest
    from app.doi_lookup import lookup_europe_pmc_doi
    import app.connectors.europe_pmc as europe_pmc

    def fake_europe_pmc_search(q, *, n, retries):
        assert q == "DOI:10.1000/example"
        assert n == 10
        assert retries == 2
        raise RuntimeError("Europe PMC API unavailable")

    monkeypatch.setattr(
        europe_pmc,
        "europe_pmc_search",
        fake_europe_pmc_search,
    )

    with pytest.raises(
        RuntimeError,
        match="Europe PMC API unavailable",
    ):
        asyncio.run(
            lookup_europe_pmc_doi("10.1000/example")
        )



def test_lookup_openalex_doi_exact_match(monkeypatch):
    import asyncio

    from app.doi_lookup import lookup_openalex_doi
    import requests

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {
                "id": "https://openalex.org/W123456789",
                "doi": "https://doi.org/10.1000/example",
                "title": "Exact DOI Match",
                "publication_year": 2024,
                "authorships": [],
                "concepts": [],
            }

    def fake_get(url, *, params, timeout, headers):
        assert url == (
            "https://api.openalex.org/works/"
            "https://doi.org/10.1000/example"
        )
        assert timeout == (10, 90)
        assert "User-Agent" in headers
        return FakeResponse()

    monkeypatch.setattr(requests, "get", fake_get)

    result = asyncio.run(
        lookup_openalex_doi("https://doi.org/10.1000/EXAMPLE")
    )

    assert result is not None
    assert result.source == "openalex"
    assert result.id == "W123456789"
    assert result.doi == "10.1000/example"
    assert result.title == "Exact DOI Match"



def test_lookup_openalex_doi_rejects_mismatch(monkeypatch):
    import asyncio

    import requests
    from app.doi_lookup import lookup_openalex_doi

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {
                "id": "https://openalex.org/W123456789",
                "doi": "https://doi.org/10.1000/different",
                "title": "Incorrect DOI Match",
                "publication_year": 2024,
                "authorships": [],
                "concepts": [],
            }

    def fake_get(url, *, params, timeout, headers):
        assert url == (
            "https://api.openalex.org/works/"
            "https://doi.org/10.1000/example"
        )
        return FakeResponse()

    monkeypatch.setattr(requests, "get", fake_get)

    result = asyncio.run(
        lookup_openalex_doi("10.1000/example")
    )

    assert result is None



def test_lookup_openalex_doi_rejects_missing_doi(monkeypatch):
    import asyncio

    import requests
    from app.doi_lookup import lookup_openalex_doi

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {
                "id": "https://openalex.org/W123456789",
                "doi": None,
                "title": "Article Without DOI",
                "publication_year": 2024,
                "authorships": [],
                "concepts": [],
            }

    def fake_get(url, *, params, timeout, headers):
        assert url == (
            "https://api.openalex.org/works/"
            "https://doi.org/10.1000/example"
        )
        return FakeResponse()

    monkeypatch.setattr(requests, "get", fake_get)

    result = asyncio.run(
        lookup_openalex_doi("10.1000/example")
    )

    assert result is None



def test_lookup_openalex_doi_not_found(monkeypatch):
    import asyncio

    import requests
    from app.doi_lookup import lookup_openalex_doi

    class FakeResponse:
        status_code = 404

        def raise_for_status(self):
            raise AssertionError(
                "raise_for_status must not be called for HTTP 404"
            )

    def fake_get(url, *, params, timeout, headers):
        assert url == (
            "https://api.openalex.org/works/"
            "https://doi.org/10.1000/example"
        )
        return FakeResponse()

    monkeypatch.setattr(requests, "get", fake_get)

    result = asyncio.run(
        lookup_openalex_doi("10.1000/example")
    )

    assert result is None



def test_lookup_openalex_doi_rejects_invalid_input(monkeypatch):
    import asyncio

    import requests
    from app.doi_lookup import lookup_openalex_doi

    def fake_get(*args, **kwargs):
        raise AssertionError(
            "OpenAlex must not be called for an invalid DOI"
        )

    monkeypatch.setattr(requests, "get", fake_get)

    result = asyncio.run(
        lookup_openalex_doi("not-a-valid-doi")
    )

    assert result is None



def test_lookup_openalex_doi_propagates_api_error(monkeypatch):
    import asyncio

    import pytest
    import requests

    from app.doi_lookup import lookup_openalex_doi

    def fake_get(url, *, params, timeout, headers):
        assert url == (
            "https://api.openalex.org/works/"
            "https://doi.org/10.1000/example"
        )

        response = requests.Response()
        response.status_code = 429
        response.url = url

        return response

    monkeypatch.setattr(requests, "get", fake_get)

    with pytest.raises(requests.HTTPError) as exc_info:
        asyncio.run(
            lookup_openalex_doi("10.1000/example")
        )

    assert exc_info.value.response.status_code == 429



def test_lookup_doaj_doi_exact_match(monkeypatch):
    import asyncio

    from app.connectors import doaj
    from app.doi_lookup import lookup_doaj_doi
    from app.models.paper import Paper

    expected_paper = Paper(
        id="doaj-123",
        source="doaj",
        title="Example DOAJ Article",
        doi="10.1000/example",
    )

    def fake_doaj_search(q, *, page, n):
        assert q == 'bibjson.identifier.id:"10.1000/example"'
        assert page == 1
        assert n == 10

        return [expected_paper], 1

    monkeypatch.setattr(
        doaj,
        "doaj_search",
        fake_doaj_search,
    )

    result = asyncio.run(
        lookup_doaj_doi("https://doi.org/10.1000/EXAMPLE")
    )

    assert result is expected_paper
    assert result.source == "doaj"
    assert result.doi == "10.1000/example"



def test_lookup_doaj_doi_rejects_mismatch(monkeypatch):
    import asyncio

    from app.connectors import doaj
    from app.doi_lookup import lookup_doaj_doi
    from app.models.paper import Paper

    mismatched_paper = Paper(
        id="doaj-456",
        source="doaj",
        title="Different DOAJ Article",
        doi="10.1000/different",
    )

    def fake_doaj_search(q, *, page, n):
        assert q == 'bibjson.identifier.id:"10.1000/example"'
        assert page == 1
        assert n == 10

        return [mismatched_paper], 1

    monkeypatch.setattr(
        doaj,
        "doaj_search",
        fake_doaj_search,
    )

    result = asyncio.run(
        lookup_doaj_doi("10.1000/example")
    )

    assert result is None



def test_lookup_doaj_doi_rejects_missing_doi(monkeypatch):
    import asyncio

    from app.connectors import doaj
    from app.doi_lookup import lookup_doaj_doi
    from app.models.paper import Paper

    paper_without_doi = Paper(
        id="doaj-789",
        source="doaj",
        title="DOAJ Article Without DOI",
        doi=None,
    )

    def fake_doaj_search(q, *, page, n):
        assert q == 'bibjson.identifier.id:"10.1000/example"'
        assert page == 1
        assert n == 10

        return [paper_without_doi], 1

    monkeypatch.setattr(
        doaj,
        "doaj_search",
        fake_doaj_search,
    )

    result = asyncio.run(
        lookup_doaj_doi("10.1000/example")
    )

    assert result is None



def test_lookup_doaj_doi_not_found(monkeypatch):
    import asyncio

    from app.connectors import doaj
    from app.doi_lookup import lookup_doaj_doi

    def fake_doaj_search(q, *, page, n):
        assert q == 'bibjson.identifier.id:"10.1000/example"'
        assert page == 1
        assert n == 10

        return [], 0

    monkeypatch.setattr(
        doaj,
        "doaj_search",
        fake_doaj_search,
    )

    result = asyncio.run(
        lookup_doaj_doi("10.1000/example")
    )

    assert result is None



def test_lookup_doaj_doi_rejects_invalid_input(monkeypatch):
    import asyncio

    from app.connectors import doaj
    from app.doi_lookup import lookup_doaj_doi

    def fake_doaj_search(*args, **kwargs):
        raise AssertionError(
            "DOAJ must not be called for an invalid DOI"
        )

    monkeypatch.setattr(
        doaj,
        "doaj_search",
        fake_doaj_search,
    )

    result = asyncio.run(
        lookup_doaj_doi("not-a-valid-doi")
    )

    assert result is None



def test_lookup_doaj_doi_propagates_api_error(monkeypatch):
    import asyncio

    import pytest

    from app.connectors import doaj
    from app.doi_lookup import lookup_doaj_doi

    def fake_doaj_search(q, *, page, n):
        assert q == 'bibjson.identifier.id:"10.1000/example"'
        assert page == 1
        assert n == 10

        raise doaj.DoajError("DOAJ API error 429: Too Many Requests")

    monkeypatch.setattr(
        doaj,
        "doaj_search",
        fake_doaj_search,
    )

    with pytest.raises(doaj.DoajError, match="429"):
        asyncio.run(
            lookup_doaj_doi("10.1000/example")
        )



def test_lookup_semantic_scholar_doi_exact_match(monkeypatch):
    import asyncio

    from app.connectors import semantic_scholar as ss
    from app.doi_lookup import lookup_semantic_scholar_doi

    def fake_request(url, params):
        assert url == (
            "https://api.semanticscholar.org/graph/v1/"
            "paper/DOI:10.1000%2Fexample"
        )
        assert params == {"fields": ss.DETAIL_FIELDS}

        return {
            "paperId": "abc123",
            "title": "Example Semantic Scholar Article",
            "externalIds": {"DOI": "10.1000/example"},
            "authors": [],
            "year": 2024,
        }

    monkeypatch.setattr(ss, "_request", fake_request)

    result = asyncio.run(
        lookup_semantic_scholar_doi(
            "https://doi.org/10.1000/EXAMPLE"
        )
    )

    assert result is not None
    assert result.source == "semantic_scholar"
    assert result.doi == "10.1000/example"
    assert result.title == "Example Semantic Scholar Article"



def test_lookup_semantic_scholar_doi_rejects_mismatch(monkeypatch):
    import asyncio

    from app.connectors import semantic_scholar as ss
    from app.doi_lookup import lookup_semantic_scholar_doi

    def fake_request(url, params):
        assert url == (
            "https://api.semanticscholar.org/graph/v1/"
            "paper/DOI:10.1000%2Fexample"
        )
        assert params == {"fields": ss.DETAIL_FIELDS}

        return {
            "paperId": "abc456",
            "title": "Different Semantic Scholar Article",
            "externalIds": {"DOI": "10.1000/different"},
            "authors": [],
            "year": 2024,
        }

    monkeypatch.setattr(ss, "_request", fake_request)

    result = asyncio.run(
        lookup_semantic_scholar_doi("10.1000/example")
    )

    assert result is None



def test_lookup_semantic_scholar_doi_rejects_missing_doi(monkeypatch):
    import asyncio

    from app.connectors import semantic_scholar as ss
    from app.doi_lookup import lookup_semantic_scholar_doi

    def fake_request(url, params):
        assert url == (
            "https://api.semanticscholar.org/graph/v1/"
            "paper/DOI:10.1000%2Fexample"
        )
        assert params == {"fields": ss.DETAIL_FIELDS}

        return {
            "paperId": "abc789",
            "title": "Semantic Scholar Article Without DOI",
            "externalIds": {},
            "authors": [],
            "year": 2024,
        }

    monkeypatch.setattr(ss, "_request", fake_request)

    result = asyncio.run(
        lookup_semantic_scholar_doi("10.1000/example")
    )

    assert result is None



def test_lookup_semantic_scholar_doi_not_found(monkeypatch):
    import asyncio

    from app.connectors import semantic_scholar as ss
    from app.doi_lookup import lookup_semantic_scholar_doi

    def fake_request(url, params):
        assert url == (
            "https://api.semanticscholar.org/graph/v1/"
            "paper/DOI:10.1000%2Fexample"
        )
        assert params == {"fields": ss.DETAIL_FIELDS}

        raise ss.SemanticScholarError(
            "Semantic Scholar API error 404: Paper not found"
        )

    monkeypatch.setattr(ss, "_request", fake_request)

    result = asyncio.run(
        lookup_semantic_scholar_doi("10.1000/example")
    )

    assert result is None



def test_lookup_semantic_scholar_doi_rejects_invalid_input(monkeypatch):
    import asyncio

    from app.connectors import semantic_scholar as ss
    from app.doi_lookup import lookup_semantic_scholar_doi

    def fake_request(*args, **kwargs):
        raise AssertionError(
            "Semantic Scholar must not be called for an invalid DOI"
        )

    monkeypatch.setattr(ss, "_request", fake_request)

    result = asyncio.run(
        lookup_semantic_scholar_doi("not-a-valid-doi")
    )

    assert result is None



def test_lookup_semantic_scholar_doi_propagates_403(monkeypatch):
    import asyncio

    import pytest

    from app.connectors import semantic_scholar as ss
    from app.doi_lookup import lookup_semantic_scholar_doi

    def fake_request(url, params):
        assert url == (
            "https://api.semanticscholar.org/graph/v1/"
            "paper/DOI:10.1000%2Fexample"
        )
        assert params == {"fields": ss.DETAIL_FIELDS}

        raise ss.SemanticScholarError(
            "Semantic Scholar API error 403: Forbidden"
        )

    monkeypatch.setattr(ss, "_request", fake_request)

    with pytest.raises(ss.SemanticScholarError, match="403"):
        asyncio.run(
            lookup_semantic_scholar_doi("10.1000/example")
        )



def test_lookup_semantic_scholar_doi_propagates_429(monkeypatch):
    import asyncio

    import pytest

    from app.connectors import semantic_scholar as ss
    from app.doi_lookup import lookup_semantic_scholar_doi

    def fake_request(url, params):
        assert url == (
            "https://api.semanticscholar.org/graph/v1/"
            "paper/DOI:10.1000%2Fexample"
        )
        assert params == {"fields": ss.DETAIL_FIELDS}

        raise ss.SemanticScholarError(
            "Semantic Scholar rate limit reached (HTTP 429)"
        )

    monkeypatch.setattr(ss, "_request", fake_request)

    with pytest.raises(ss.SemanticScholarError, match="429"):
        asyncio.run(
            lookup_semantic_scholar_doi("10.1000/example")
        )



def test_lookup_doi_collects_verified_sources(monkeypatch):
    import asyncio

    from app import doi_lookup
    from app.models.paper import Paper

    calls = []

    def make_lookup(source, returned_doi):
        async def fake_lookup(doi):
            assert doi == "10.1000/example"
            calls.append(source)

            return Paper(
                id=f"{source}-123",
                source=source,
                title=f"Article from {source}",
                doi=returned_doi,
            )

        return fake_lookup

    sources = [
        "pubmed",
        "crossref",
        "europe_pmc",
        "openalex",
        "doaj",
        "semantic_scholar",
    ]

    for source in sources:
        returned_doi = (
            "10.1000/different"
            if source == "doaj"
            else "10.1000/example"
        )

        monkeypatch.setattr(
            doi_lookup,
            f"lookup_{source}_doi",
            make_lookup(source, returned_doi),
        )

    result = asyncio.run(
        doi_lookup.lookup_doi(
            "https://doi.org/10.1000/EXAMPLE"
        )
    )

    assert result.doi == "10.1000/example"
    assert calls == sources

    assert result.found_in == [
        "pubmed",
        "crossref",
        "europe_pmc",
        "openalex",
        "semantic_scholar",
    ]

    assert result.failed_sources == []
    assert result.paper is not None
    assert result.paper.source == "pubmed"
    assert result.paper.doi == "10.1000/example"



def test_lookup_doi_continues_after_source_error(monkeypatch):
    import asyncio

    from app import doi_lookup
    from app.models.paper import Paper

    calls = []

    sources = [
        "pubmed",
        "crossref",
        "europe_pmc",
        "openalex",
        "doaj",
        "semantic_scholar",
    ]

    def make_lookup(source):
        async def fake_lookup(doi):
            assert doi == "10.1000/example"
            calls.append(source)

            if source == "crossref":
                raise RuntimeError("Crossref API unavailable")

            return Paper(
                id=f"{source}-123",
                source=source,
                title=f"Article from {source}",
                doi="10.1000/example",
            )

        return fake_lookup

    for source in sources:
        monkeypatch.setattr(
            doi_lookup,
            f"lookup_{source}_doi",
            make_lookup(source),
        )

    result = asyncio.run(
        doi_lookup.lookup_doi("10.1000/example")
    )

    assert calls == sources

    assert result.failed_sources == ["crossref"]

    assert result.found_in == [
        "pubmed",
        "europe_pmc",
        "openalex",
        "doaj",
        "semantic_scholar",
    ]

    assert result.paper is not None
    assert result.paper.source == "pubmed"



def test_lookup_doi_not_found_in_any_source(monkeypatch):
    import asyncio

    from app import doi_lookup

    calls = []

    sources = [
        "pubmed",
        "crossref",
        "europe_pmc",
        "openalex",
        "doaj",
        "semantic_scholar",
    ]

    def make_lookup(source):
        async def fake_lookup(doi):
            assert doi == "10.1000/example"
            calls.append(source)
            return None

        return fake_lookup

    for source in sources:
        monkeypatch.setattr(
            doi_lookup,
            f"lookup_{source}_doi",
            make_lookup(source),
        )

    result = asyncio.run(
        doi_lookup.lookup_doi("10.1000/example")
    )

    assert calls == sources
    assert result.doi == "10.1000/example"
    assert result.paper is None
    assert result.found_in == []
    assert result.failed_sources == []



def test_lookup_doi_rejects_invalid_input_without_source_calls(
    monkeypatch,
):
    import asyncio

    from app import doi_lookup

    sources = [
        "pubmed",
        "crossref",
        "europe_pmc",
        "openalex",
        "doaj",
        "semantic_scholar",
    ]

    async def unexpected_lookup(doi):
        raise AssertionError(
            "No source should be called for an invalid DOI"
        )

    for source in sources:
        monkeypatch.setattr(
            doi_lookup,
            f"lookup_{source}_doi",
            unexpected_lookup,
        )

    result = asyncio.run(
        doi_lookup.lookup_doi("not-a-valid-doi")
    )

    assert result.doi == ""
    assert result.paper is None
    assert result.found_in == []
    assert result.failed_sources == []


def test_lookup_pubmed_pmid_exact_match(monkeypatch):
    import asyncio

    from app.doi_lookup import lookup_pubmed_pmid
    import app.connectors.pubmed as pubmed

    paper = Paper(
        id="12345678",
        source="pubmed",
        title="Exact PMID Match",
    )

    async def fake_fetch_details(pmids):
        assert pmids == ["12345678"]
        return [paper]

    monkeypatch.setattr(
        pubmed,
        "pubmed_fetch_details",
        fake_fetch_details,
    )

    result = asyncio.run(
        lookup_pubmed_pmid("12345678")
    )

    assert result is paper
    assert result.id == "12345678"
    assert result.source == "pubmed"


def test_lookup_pubmed_pmid_rejects_mismatch(monkeypatch):
    import asyncio

    from app.doi_lookup import lookup_pubmed_pmid
    import app.connectors.pubmed as pubmed

    paper = Paper(
        id="87654321",
        source="pubmed",
        title="Incorrect PMID Match",
    )

    async def fake_fetch_details(pmids):
        assert pmids == ["12345678"]
        return [paper]

    monkeypatch.setattr(
        pubmed,
        "pubmed_fetch_details",
        fake_fetch_details,
    )

    result = asyncio.run(
        lookup_pubmed_pmid("12345678")
    )

    assert result is None


def test_lookup_pubmed_pmid_not_found(monkeypatch):
    import asyncio

    from app.doi_lookup import lookup_pubmed_pmid
    import app.connectors.pubmed as pubmed

    async def fake_fetch_details(pmids):
        assert pmids == ["12345678"]
        return []

    monkeypatch.setattr(
        pubmed,
        "pubmed_fetch_details",
        fake_fetch_details,
    )

    result = asyncio.run(
        lookup_pubmed_pmid("12345678")
    )

    assert result is None


def test_lookup_pubmed_pmid_rejects_invalid_input(monkeypatch):
    import asyncio

    from app.doi_lookup import lookup_pubmed_pmid
    import app.connectors.pubmed as pubmed

    async def fake_fetch_details(pmids):
        raise AssertionError(
            "PubMed must not be called for an invalid PMID"
        )

    monkeypatch.setattr(
        pubmed,
        "pubmed_fetch_details",
        fake_fetch_details,
    )

    for invalid_pmid in ["", "abc", "123abc", "12 345"]:
        result = asyncio.run(
            lookup_pubmed_pmid(invalid_pmid)
        )

        assert result is None


def test_lookup_pubmed_pmid_propagates_api_error(monkeypatch):
    import asyncio
    import pytest

    from app.doi_lookup import lookup_pubmed_pmid
    import app.connectors.pubmed as pubmed

    async def fake_fetch_details(pmids):
        assert pmids == ["12345678"]
        raise RuntimeError("PubMed API unavailable")

    monkeypatch.setattr(
        pubmed,
        "pubmed_fetch_details",
        fake_fetch_details,
    )

    with pytest.raises(
        RuntimeError,
        match="PubMed API unavailable",
    ):
        asyncio.run(
            lookup_pubmed_pmid("12345678")
        )


def test_pmid_lookup_result_defaults():
    from app.doi_lookup import PmidLookupResult

    result = PmidLookupResult(pmid="12345678")

    assert result.pmid == "12345678"
    assert result.paper is None
    assert result.found_in == []
    assert result.failed_sources == []


def test_lookup_pmid_finds_pubmed_paper(monkeypatch):
    import asyncio

    import app.doi_lookup as doi_lookup

    paper = Paper(
        id="12345678",
        source="pubmed",
        title="Exact PMID Match",
    )

    async def fake_lookup_pubmed_pmid(pmid):
        assert pmid == "12345678"
        return paper

    monkeypatch.setattr(
        doi_lookup,
        "lookup_pubmed_pmid",
        fake_lookup_pubmed_pmid,
    )

    result = asyncio.run(
        doi_lookup.lookup_pmid("12345678")
    )

    assert result.pmid == "12345678"
    assert result.paper is paper
    assert result.found_in == ["pubmed"]
    assert result.failed_sources == []


def test_lookup_pmid_not_found(monkeypatch):
    import asyncio

    import app.doi_lookup as doi_lookup

    async def fake_lookup_pubmed_pmid(pmid):
        assert pmid == "12345678"
        return None

    monkeypatch.setattr(
        doi_lookup,
        "lookup_pubmed_pmid",
        fake_lookup_pubmed_pmid,
    )

    result = asyncio.run(
        doi_lookup.lookup_pmid("12345678")
    )

    assert result.pmid == "12345678"
    assert result.paper is None
    assert result.found_in == []
    assert result.failed_sources == []


def test_lookup_pmid_records_pubmed_api_error(monkeypatch):
    import asyncio

    import app.doi_lookup as doi_lookup

    async def fake_lookup_pubmed_pmid(pmid):
        assert pmid == "12345678"
        raise RuntimeError("PubMed API unavailable")

    monkeypatch.setattr(
        doi_lookup,
        "lookup_pubmed_pmid",
        fake_lookup_pubmed_pmid,
    )

    result = asyncio.run(
        doi_lookup.lookup_pmid("12345678")
    )

    assert result.pmid == "12345678"
    assert result.paper is None
    assert result.found_in == []
    assert result.failed_sources == ["pubmed"]


def test_lookup_pmid_rejects_invalid_input(monkeypatch):
    import asyncio

    import app.doi_lookup as doi_lookup

    async def fake_lookup_pubmed_pmid(pmid):
        raise AssertionError(
            "PubMed must not be called for an invalid PMID"
        )

    monkeypatch.setattr(
        doi_lookup,
        "lookup_pubmed_pmid",
        fake_lookup_pubmed_pmid,
    )

    for invalid_pmid in [
        "",
        "abc",
        "123abc",
        "12 345",
        "１２３４５",
    ]:
        result = asyncio.run(
            doi_lookup.lookup_pmid(invalid_pmid)
        )

        assert result.pmid == ""
        assert result.paper is None
        assert result.found_in == []
        assert result.failed_sources == []


def test_lookup_europe_pmc_pmcid_exact_match(monkeypatch):
    import asyncio

    from app.doi_lookup import lookup_europe_pmc_pmcid
    from app.models.paper import Paper
    import app.connectors.europe_pmc as europe_pmc

    paper = Paper(
        id="12345678",
        source="europe_pmc",
        title="Exact PMCID Match",
        pmcid="PMC1234567",
    )

    def fake_fetch_detail(pid, *, raise_on_error=False):
        assert pid == "PMC1234567"
        assert raise_on_error is True
        return paper

    monkeypatch.setattr(
        europe_pmc,
        "europe_pmc_fetch_detail",
        fake_fetch_detail,
    )

    result = asyncio.run(
        lookup_europe_pmc_pmcid("PMC1234567")
    )

    assert result is paper
    assert result.pmcid == "PMC1234567"


def test_lookup_europe_pmc_pmcid_rejects_mismatch(monkeypatch):
    import asyncio

    from app.doi_lookup import lookup_europe_pmc_pmcid
    from app.models.paper import Paper
    import app.connectors.europe_pmc as europe_pmc

    paper = Paper(
        id="12345678",
        source="europe_pmc",
        title="Incorrect PMCID Match",
        pmcid="PMC9999999",
    )

    def fake_fetch_detail(pid, *, raise_on_error=False):
        assert pid == "PMC1234567"
        assert raise_on_error is True
        return paper

    monkeypatch.setattr(
        europe_pmc,
        "europe_pmc_fetch_detail",
        fake_fetch_detail,
    )

    result = asyncio.run(
        lookup_europe_pmc_pmcid("PMC1234567")
    )

    assert result is None


def test_lookup_europe_pmc_pmcid_rejects_wrong_source(monkeypatch):
    import asyncio

    from app.doi_lookup import lookup_europe_pmc_pmcid
    from app.models.paper import Paper
    import app.connectors.europe_pmc as europe_pmc

    paper = Paper(
        id="12345678",
        source="crossref",
        title="Incorrect Source",
        pmcid="PMC1234567",
    )

    def fake_fetch_detail(pid, *, raise_on_error=False):
        assert pid == "PMC1234567"
        assert raise_on_error is True
        return paper

    monkeypatch.setattr(
        europe_pmc,
        "europe_pmc_fetch_detail",
        fake_fetch_detail,
    )

    result = asyncio.run(
        lookup_europe_pmc_pmcid("PMC1234567")
    )

    assert result is None


def test_lookup_europe_pmc_pmcid_rejects_missing_pmcid(monkeypatch):
    import asyncio

    from app.doi_lookup import lookup_europe_pmc_pmcid
    from app.models.paper import Paper
    import app.connectors.europe_pmc as europe_pmc

    paper = Paper(
        id="12345678",
        source="europe_pmc",
        title="Missing PMCID",
        pmcid=None,
    )

    def fake_fetch_detail(pid, *, raise_on_error=False):
        assert pid == "PMC1234567"
        assert raise_on_error is True
        return paper

    monkeypatch.setattr(
        europe_pmc,
        "europe_pmc_fetch_detail",
        fake_fetch_detail,
    )

    result = asyncio.run(
        lookup_europe_pmc_pmcid("PMC1234567")
    )

    assert result is None


def test_lookup_europe_pmc_pmcid_rejects_invalid_input(monkeypatch):
    import asyncio

    from app.doi_lookup import lookup_europe_pmc_pmcid
    import app.connectors.europe_pmc as europe_pmc

    def fake_fetch_detail(pid):
        raise AssertionError(
            "Europe PMC must not be called for invalid PMCID input"
        )

    monkeypatch.setattr(
        europe_pmc,
        "europe_pmc_fetch_detail",
        fake_fetch_detail,
    )

    invalid_pmcids = [
        "",
        " ",
        "1234567",
        "PMC",
        "PMCABC",
        "PMC123ABC",
        "PMC123 456",
        "PMC-1234567",
        "PMC１２３４５６７",
    ]

    for pmcid in invalid_pmcids:
        result = asyncio.run(
            lookup_europe_pmc_pmcid(pmcid)
        )

        assert result is None


def test_lookup_europe_pmc_pmcid_not_found(monkeypatch):
    import asyncio

    from app.doi_lookup import lookup_europe_pmc_pmcid
    import app.connectors.europe_pmc as europe_pmc

    def fake_fetch_detail(pid, *, raise_on_error=False):
        assert pid == "PMC1234567"
        assert raise_on_error is True
        return None

    monkeypatch.setattr(
        europe_pmc,
        "europe_pmc_fetch_detail",
        fake_fetch_detail,
    )

    result = asyncio.run(
        lookup_europe_pmc_pmcid("PMC1234567")
    )

    assert result is None


def test_lookup_europe_pmc_pmcid_propagates_fetch_error(monkeypatch):
    import asyncio

    import pytest

    from app.doi_lookup import lookup_europe_pmc_pmcid
    import app.connectors.europe_pmc as europe_pmc

    def fake_fetch_detail(pid, *, raise_on_error=False):
        assert pid == "PMC1234567"
        assert raise_on_error is True
        raise RuntimeError("Europe PMC API unavailable")

    monkeypatch.setattr(
        europe_pmc,
        "europe_pmc_fetch_detail",
        fake_fetch_detail,
    )

    with pytest.raises(
        RuntimeError,
        match="Europe PMC API unavailable",
    ):
        asyncio.run(
            lookup_europe_pmc_pmcid("PMC1234567")
        )


def test_europe_pmc_fetch_detail_raises_on_api_error(monkeypatch):
    import pytest
    import requests

    import app.connectors.europe_pmc as europe_pmc

    def fake_get(*args, **kwargs):
        raise requests.exceptions.ConnectionError(
            "Europe PMC API unavailable"
        )

    monkeypatch.setattr(
        europe_pmc.requests,
        "get",
        fake_get,
    )

    with pytest.raises(
        requests.exceptions.ConnectionError,
        match="Europe PMC API unavailable",
    ):
        europe_pmc.europe_pmc_fetch_detail(
            "PMC1234567",
            raise_on_error=True,
        )


def test_europe_pmc_fetch_detail_suppresses_api_error_by_default(monkeypatch):
    import requests

    import app.connectors.europe_pmc as europe_pmc

    def fake_get(*args, **kwargs):
        raise requests.exceptions.ConnectionError(
            "Europe PMC API unavailable"
        )

    monkeypatch.setattr(
        europe_pmc.requests,
        "get",
        fake_get,
    )

    result = europe_pmc.europe_pmc_fetch_detail(
        "PMC1234567"
    )

    assert result is None


def test_pmcid_lookup_result_defaults():
    from app.doi_lookup import PmcidLookupResult

    result = PmcidLookupResult(pmcid="PMC1234567")

    assert result.pmcid == "PMC1234567"
    assert result.paper is None
    assert result.found_in == []
    assert result.failed_sources == []


def test_lookup_pmcid_found_in_europe_pmc(monkeypatch):
    import asyncio

    import app.doi_lookup as doi_lookup
    from app.models.paper import Paper

    paper = Paper(
        id="12345678",
        source="europe_pmc",
        title="Exact PMCID Match",
        pmcid="PMC1234567",
    )

    async def fake_lookup(pmcid):
        assert pmcid == "PMC1234567"
        return paper

    monkeypatch.setattr(
        doi_lookup,
        "lookup_europe_pmc_pmcid",
        fake_lookup,
    )

    result = asyncio.run(
        doi_lookup.lookup_pmcid("PMC1234567")
    )

    assert result.pmcid == "PMC1234567"
    assert result.paper is paper
    assert result.found_in == ["europe_pmc"]
    assert result.failed_sources == []


def test_lookup_pmcid_not_found(monkeypatch):
    import asyncio

    import app.doi_lookup as doi_lookup

    async def fake_lookup(pmcid):
        assert pmcid == "PMC1234567"
        return None

    monkeypatch.setattr(
        doi_lookup,
        "lookup_europe_pmc_pmcid",
        fake_lookup,
    )

    result = asyncio.run(
        doi_lookup.lookup_pmcid("PMC1234567")
    )

    assert result.pmcid == "PMC1234567"
    assert result.paper is None
    assert result.found_in == []
    assert result.failed_sources == []


def test_lookup_pmcid_records_europe_pmc_failure(monkeypatch):
    import asyncio

    import app.doi_lookup as doi_lookup

    async def fake_lookup(pmcid):
        assert pmcid == "PMC1234567"
        raise RuntimeError("Europe PMC API unavailable")

    monkeypatch.setattr(
        doi_lookup,
        "lookup_europe_pmc_pmcid",
        fake_lookup,
    )

    result = asyncio.run(
        doi_lookup.lookup_pmcid("PMC1234567")
    )

    assert result.pmcid == "PMC1234567"
    assert result.paper is None
    assert result.found_in == []
    assert result.failed_sources == ["europe_pmc"]


def test_lookup_pmcid_rejects_invalid_input(monkeypatch):
    import asyncio

    import app.doi_lookup as doi_lookup

    async def fake_lookup(pmcid):
        raise AssertionError(
            "Europe PMC must not be called for invalid PMCID input"
        )

    monkeypatch.setattr(
        doi_lookup,
        "lookup_europe_pmc_pmcid",
        fake_lookup,
    )

    invalid_pmcids = [
        "",
        " ",
        "1234567",
        "PMC",
        "PMCABC",
        "PMC123ABC",
        "PMC123 456",
        "PMC-1234567",
        "PMC１２３４５６７",
    ]

    for pmcid in invalid_pmcids:
        result = asyncio.run(
            doi_lookup.lookup_pmcid(pmcid)
        )

        assert result.pmcid == ""
        assert result.paper is None
        assert result.found_in == []
        assert result.failed_sources == []


def test_lookup_pmcid_normalizes_input(monkeypatch):
    import asyncio

    import app.doi_lookup as doi_lookup
    from app.models.paper import Paper

    paper = Paper(
        id="12345678",
        source="europe_pmc",
        title="Normalized PMCID Match",
        pmcid="PMC1234567",
    )

    async def fake_lookup(pmcid):
        assert pmcid == "PMC1234567"
        return paper

    monkeypatch.setattr(
        doi_lookup,
        "lookup_europe_pmc_pmcid",
        fake_lookup,
    )

    result = asyncio.run(
        doi_lookup.lookup_pmcid("  pmc1234567  ")
    )

    assert result.pmcid == "PMC1234567"
    assert result.paper is paper
    assert result.found_in == ["europe_pmc"]
    assert result.failed_sources == []
