import app.main as main


def test_title_search_empty_form_does_not_call_backend(
    client, monkeypatch
):
    async def unexpected_search(query):
        raise AssertionError(
            "Title Search backend must not be called for an empty query."
        )

    monkeypatch.setattr(
        main,
        "search_titles",
        unexpected_search,
    )

    response = client.get("/title-search")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "<h2>Title Search</h2>" in response.text
    assert 'action="/title-search"' in response.text
    assert "No matching publications found." not in response.text


def test_title_search_displays_exact_match(client, monkeypatch):
    from app.models.paper import Paper
    from app.title_search import TitleSearchResult

    paper = Paper(
        id="test-pubmed-001",
        title="Machine Learning in Cancer",
        source="pubmed",
    )

    async def fake_search_titles(query):
        assert query == "Machine Learning in Cancer"

        return TitleSearchResult(
            query=query,
            matches=[(paper, "exact")],
            source_counts={"pubmed": 1},
            failed_sources=[],
            duplicates_removed=0,
        )

    monkeypatch.setattr(
        main,
        "search_titles",
        fake_search_titles,
    )

    response = client.get(
        "/title-search",
        params={"q": "Machine Learning in Cancer"},
    )

    assert response.status_code == 200
    assert "Search Results (1)" in response.text
    assert "<h3>Machine Learning in Cancer</h3>" in response.text
    assert "Exact match" in response.text
    assert "Source: pubmed" in response.text


def test_title_search_displays_no_matches(client, monkeypatch):
    from app.title_search import TitleSearchResult

    async def fake_search_titles(query):
        assert query == "Nonexistent Scientific Publication"

        return TitleSearchResult(
            query=query,
            matches=[],
            source_counts={"pubmed": 0, "openalex": 0},
            failed_sources=[],
            duplicates_removed=0,
        )

    monkeypatch.setattr(
        main,
        "search_titles",
        fake_search_titles,
    )

    response = client.get(
        "/title-search",
        params={"q": "Nonexistent Scientific Publication"},
    )

    assert response.status_code == 200
    assert "No matching publications found." in response.text
    assert "Search Results (1)" not in response.text
    assert "Incomplete search results" not in response.text


def test_title_search_displays_failed_sources_warning(
    client, monkeypatch
):
    from app.title_search import TitleSearchResult

    async def fake_search_titles(query):
        assert query == "Machine Learning in Cancer"

        return TitleSearchResult(
            query=query,
            matches=[],
            source_counts={"pubmed": 0},
            failed_sources=["semantic_scholar"],
            duplicates_removed=0,
        )

    monkeypatch.setattr(
        main,
        "search_titles",
        fake_search_titles,
    )

    response = client.get(
        "/title-search",
        params={"q": "Machine Learning in Cancer"},
    )

    assert response.status_code == 200
    assert "Incomplete search results" in response.text
    assert "semantic_scholar" in response.text
    assert "Results may be incomplete." in response.text

def test_title_search_displays_duplicates_removed(
    client, monkeypatch
):
    from app.models.paper import Paper
    from app.title_search import TitleSearchResult

    paper = Paper(
        id="test-pubmed-001",
        title="Machine Learning in Cancer",
        source="pubmed",
    )

    async def fake_search_titles(query):
        assert query == "Machine Learning in Cancer"

        return TitleSearchResult(
            query=query,
            matches=[(paper, "exact")],
            source_counts={"pubmed": 2, "openalex": 2},
            failed_sources=[],
            duplicates_removed=3,
        )

    monkeypatch.setattr(
        main,
        "search_titles",
        fake_search_titles,
    )

    response = client.get(
        "/title-search",
        params={"q": "Machine Learning in Cancer"},
    )

    assert response.status_code == 200
    assert "Duplicate records removed:" in response.text
    assert "3" in response.text
    assert "Search Results (1)" in response.text


def test_title_search_displays_source_statistics(
    client, monkeypatch
):
    from app.title_search import TitleSearchResult

    async def fake_search_titles(query):
        assert query == "Machine Learning in Cancer"

        return TitleSearchResult(
            query=query,
            matches=[],
            source_counts={
                "pubmed": 12,
                "openalex": 8,
                "crossref": 5,
            },
            failed_sources=[],
            duplicates_removed=0,
        )

    monkeypatch.setattr(
        main,
        "search_titles",
        fake_search_titles,
    )

    response = client.get(
        "/title-search",
        params={"q": "Machine Learning in Cancer"},
    )

    assert response.status_code == 200
    assert "Source Retrieval Statistics" in response.text
    assert "pubmed" in response.text
    assert "openalex" in response.text
    assert "crossref" in response.text
    assert "Candidate records retrieved" in response.text


def test_title_search_navigation(client):
    literature_response = client.get("/search")

    assert literature_response.status_code == 200
    assert 'href="/title-search"' in literature_response.text

    title_response = client.get("/title-search")

    assert title_response.status_code == 200
    assert 'href="/search"' in title_response.text
    assert 'action="/title-search"' in title_response.text


def test_title_search_available_as_search_mode(client):
    response = client.get("/search")

    assert response.status_code == 200
    assert 'id="search_mode"' in response.text
    assert '<option value="literature"' in response.text
    assert '<option value="identifier"' in response.text
    assert '<option value="title"' in response.text


def test_title_search_detail_link_uses_primary_source(
    client, monkeypatch
):
    from app.models.paper import Paper
    from app.title_search import TitleSearchResult

    paper = Paper(
        id="10.1234/example",
        title="Machine Learning in Cancer",
        source="crossref|semantic_scholar",
        doi="10.1234/example",
    )

    async def fake_search_titles(query):
        return TitleSearchResult(
            query=query,
            matches=[(paper, "exact")],
            source_counts={
                "crossref": 1,
                "semantic_scholar": 1,
            },
            failed_sources=[],
            duplicates_removed=1,
        )

    monkeypatch.setattr(
        main,
        "search_titles",
        fake_search_titles,
    )

    response = client.get(
        "/title-search",
        params={"q": "Machine Learning in Cancer"},
    )

    assert response.status_code == 200
    assert 'href="/paper/crossref/10.1234/example"' in response.text
    assert "View details" in response.text
    assert "/paper/crossref|semantic_scholar/" not in response.text
