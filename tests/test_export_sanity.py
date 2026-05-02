import io
import zipfile

from app.models.paper import Paper


def test_export_pubmed_csv_page(client):
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
            "mesh": "",
            "mesh_mode": "or",
        },
    )
    assert r.status_code == 200
    assert "text/csv" in r.headers.get("content-type", "")
    text = r.text
    assert "ID,Title,Authors,Journal,Year,DOI,PMCID,URL" in text
    assert len(text.splitlines()) >= 2


def test_export_pubmed_ris_page(client):
    r = client.get(
        "/export/ris",
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
            "mesh": "",
            "mesh_mode": "or",
        },
    )
    assert r.status_code == 200
    assert "application/x-research-info-systems" in r.headers.get("content-type", "")
    text = r.text
    assert "TY  - JOUR" in text
    assert "ER  -" in text


def test_export_openalex_csv_page(client):
    r = client.get(
        "/export/csv",
        params={
            "q": "machine learning",
            "source": "openalex",
            "scope": "page",
            "page": 1,
            "n": 5,
            "sort": "relevance",
            "year_min": "2021",
            "year_max": "2023",
        },
    )
    assert r.status_code == 200
    assert "text/csv" in r.headers.get("content-type", "")
    text = r.text
    assert "ID,Title,Authors,Journal,Year,DOI,PMCID,URL" in text
    assert len(text.splitlines()) >= 2


def test_export_epmc_csv_page(client):
    r = client.get(
        "/export/csv",
        params={
            "q": "glioblastoma",
            "source": "europe_pmc",
            "scope": "page",
            "page": 1,
            "n": 5,
            "sort": "relevance",
            "year_min": "2020",
            "year_max": "2022",
            "has_abstract": 1,
            "cursor": "*",
        },
    )
    assert r.status_code == 200
    assert "text/csv" in r.headers.get("content-type", "")
    text = r.text
    assert "ID,Title,Authors,Journal,Year,DOI,PMCID,URL" in text
    assert len(text.splitlines()) >= 2


def test_export_pubmed_xlsx_page(client):
    r = client.get(
        "/export/xlsx",
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
            "mesh": "",
            "mesh_mode": "or",
        },
    )
    assert r.status_code == 200
    assert (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        in r.headers.get("content-type", "")
    )

    # simpele sanity check: xlsx is een zip container
    data = io.BytesIO(r.content)
    assert zipfile.is_zipfile(data)


def test_export_pubmed_mesh_mode_preserved_with_mock(client, monkeypatch):
    async def fake_pubmed_search_page(*args, **kwargs):
        class FakeRes:
            pmids = ["12345"]
            count = 1
            webenv = "fake"
            query_key = "1"
        return FakeRes()

    async def fake_pubmed_fetch_details(*args, **kwargs):
        return [
            Paper(
                id="12345",
                source="pubmed",
                title="Mock PubMed Paper",
                authors=["Tester A"],
                journal="Mock Journal",
                year=2021,
                abstract="Mock abstract",
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
    assert "Mock PubMed Paper" in r.text


def test_export_rejects_empty_query(client):
    r = client.get(
        "/export/csv",
        params={
            "q": "",
            "source": "pubmed",
            "scope": "page",
            "page": 1,
            "n": 5,
            "sort": "relevance",
        },
    )
    assert r.status_code == 400


def test_export_rejects_unknown_source(client):
    r = client.get(
        "/export/csv",
        params={
            "q": "cancer",
            "source": "unknown_source",
            "scope": "page",
            "page": 1,
            "n": 5,
            "sort": "relevance",
        },
    )
    assert r.status_code == 422

