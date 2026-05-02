from app.models.paper import Paper


def test_search_page_loads(client):
    r = client.get("/search")
    assert r.status_code == 200
    assert "Search Results" in r.text or "LitSearch" in r.text


def test_pubmed_search_page_has_results(client):
    r = client.get(
        "/search",
        params={
            "q": "cancer",
            "source": "pubmed",
            "n": 5,
            "sort": "relevance",
            "year_min": "2020",
            "year_max": "2022",
            "has_abstract": 1,
            "mesh": "",
            "mesh_mode": "or",
        },
    )
    assert r.status_code == 200
    assert "PubMed" in r.text
    assert "records retrieved" in r.text


def test_pubmed_mesh_mode_preserved_in_html(client, monkeypatch):
    async def fake_pubmed_search_page(*args, **kwargs):
        class FakeRes:
            pmids = ["12345"]
            count = 1
            webenv = "fake_webenv"
            query_key = "1"
        return FakeRes()

    async def fake_pubmed_fetch_details(*args, **kwargs):
        return [
            Paper(
                id="12345",
                source="pubmed",
                title="Test paper",
                authors=["Tester A"],
                journal="Test Journal",
                year=2021,
                abstract="Test abstract",
                doi=None,
                pmcid=None,
                url="https://pubmed.ncbi.nlm.nih.gov/12345/",
                mesh_terms=["Humans", "Adolescent"],
                has_full_text=False,
            )
        ]

    monkeypatch.setattr("app.main.pubmed_search_page", fake_pubmed_search_page)
    monkeypatch.setattr("app.main.pubmed_fetch_details", fake_pubmed_fetch_details)

    r = client.get(
        "/search",
        params={
            "q": "cancer",
            "source": "pubmed",
            "n": 5,
            "sort": "relevance",
            "year_min": "2020",
            "year_max": "2022",
            "has_abstract": 1,
            "mesh": "Humans|Adolescent",
            "mesh_mode": "or",
        },
    )

    assert r.status_code == 200
    assert 'name="mesh_mode"' in r.text
    assert "MeSH: OR" in r.text
    assert 'value="Humans|Adolescent"' in r.text


def test_epmc_search_shows_source(client):
    r = client.get(
        "/search",
        params={
            "q": "glioblastoma",
            "source": "europe_pmc",
            "n": 5,
            "sort": "relevance",
            "year_min": "2020",
            "year_max": "2022",
            "has_abstract": 1,
        },
    )
    assert r.status_code == 200
    assert "Europe PMC" in r.text


def test_openalex_search_shows_source(client):
    r = client.get(
        "/search",
        params={
            "q": "machine learning",
            "source": "openalex",
            "n": 5,
            "sort": "relevance",
            "year_min": "2021",
            "year_max": "2023",
        },
    )
    assert r.status_code == 200
    assert "OpenAlex" in r.text


def test_pubmed_export_csv_current_page(client):
    r = client.get(
        "/export/csv",
        params={
            "q": "cancer",
            "source": "pubmed",
            "scope": "page",
            "page": 1,
            "n": 5,
            "sort": "relevance",
            "year_min": "2020",
            "year_max": "2022",
            "has_abstract": 1,
            "mesh": "Humans|Adolescent",
            "mesh_mode": "or",
        },
    )
    assert r.status_code == 200
    assert "text/csv" in r.headers.get("content-type", "")