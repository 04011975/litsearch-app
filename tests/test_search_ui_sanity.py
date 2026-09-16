from app.models.paper import Paper

import html
import re


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


def test_pubmed_unsupported_date_asc_falls_back_to_relevance(client, monkeypatch):
    received_sorts = []

    async def fake_pubmed_search_page(*args, **kwargs):
        received_sorts.append(kwargs.get("sort"))

        class FakeRes:
            pmids = []
            count = 0
            webenv = "fake_webenv"
            query_key = "1"

        return FakeRes()

    async def fake_pubmed_fetch_details(*args, **kwargs):
        return []

    monkeypatch.setattr(
        "app.main.pubmed_search_page",
        fake_pubmed_search_page,
    )
    monkeypatch.setattr(
        "app.main.pubmed_fetch_details",
        fake_pubmed_fetch_details,
    )

    r = client.get(
        "/search",
        params={
            "q": "glioblastoma",
            "source": "pubmed",
            "n": 5,
            "sort": "date_asc",
        },
    )

    assert r.status_code == 200
    assert received_sorts == ["relevance"]


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


def test_europe_pmc_previous_navigation_goes_to_previous_page(client, monkeypatch):
    async def fake_europe_pmc_search(*args, **kwargs):
        papers = [
            Paper(
                id=f"epmc-{i}",
                source="europe_pmc",
                title=f"Europe PMC paper {i}",
                authors=["Tester A"],
                journal="Test Journal",
                year=2024,
                abstract="Test abstract",
                doi=None,
                pmcid=None,
                url=f"https://europepmc.org/article/MED/{i}",
                mesh_terms=[],
                has_full_text=False,
            )
            for i in range(100)
        ]
        return papers, 200, "next-cursor"

    monkeypatch.setattr(
        "app.main._europe_pmc_search_compat_async",
        fake_europe_pmc_search,
    )

    r = client.get(
        "/search",
        params={
            "q": "glioblastoma",
            "source": "europe_pmc",
            "page": 2,
            "n": 5,
            "sort": "relevance",
            "cursor": "*",
        },
    )

    assert r.status_code == 200
    assert ">Previous</a>" in r.text
    assert "page=1" in r.text


def test_europe_pmc_previous_navigation_uses_previous_chunk_cursor(client, monkeypatch):
    async def fake_europe_pmc_search(*args, **kwargs):
        papers = [
            Paper(
                id=f"epmc-{i}",
                source="europe_pmc",
                title=f"Europe PMC paper {i}",
                authors=["Tester A"],
                journal="Test Journal",
                year=2024,
                abstract="Test abstract",
                doi=None,
                pmcid=None,
                url=f"https://europepmc.org/article/MED/{i}",
                mesh_terms=[],
                has_full_text=False,
            )
            for i in range(100)
        ]
        return papers, 1000, "next-cursor"

    def fake_get_cursor_for_chunk(*args, **kwargs):
        if kwargs.get("chunk") == 1:
            return "previous-chunk-cursor"
        return None

    monkeypatch.setattr(
        "app.main._europe_pmc_search_compat_async",
        fake_europe_pmc_search,
    )
    monkeypatch.setattr(
        "app.main._epmc_get_cursor_for_chunk",
        fake_get_cursor_for_chunk,
    )

    r = client.get(
        "/search",
        params={
            "q": "glioblastoma",
            "source": "europe_pmc",
            "page": 101,
            "n": 5,
            "sort": "relevance",
            "cursor": "current-chunk-cursor",
        },
    )

    assert r.status_code == 200
    assert ">Previous</a>" in r.text
    assert "page=100" in r.text
    assert "cursor=previous-chunk-cursor" in r.text


def test_europe_pmc_unsupported_sort_falls_back_to_relevance(client, monkeypatch):
    received_sorts = []

    async def fake_europe_pmc_search(*args, **kwargs):
        received_sorts.append(kwargs.get("sort"))
        return [], 0, None

    monkeypatch.setattr(
        "app.main._europe_pmc_search_compat_async",
        fake_europe_pmc_search,
    )

    r = client.get(
        "/search",
        params={
            "q": "glioblastoma",
            "source": "europe_pmc",
            "n": 5,
            "sort": "date_desc",
        },
    )

    assert r.status_code == 200
    assert received_sorts == ["relevance"]


def test_semantic_scholar_relevance_previous_navigation(client, monkeypatch):
    def fake_semantic_scholar_search(*args, **kwargs):
        papers = [
            Paper(
                id=f"ss-{i}",
                source="semantic_scholar",
                title=f"Semantic Scholar paper {i}",
                authors=["Tester A"],
                journal="Test Journal",
                year=2024,
                abstract="Test abstract",
                doi=None,
                pmcid=None,
                url=f"https://www.semanticscholar.org/paper/{i}",
                mesh_terms=[],
                has_full_text=False,
            )
            for i in range(5)
        ]
        return papers, 50

    monkeypatch.setattr(
        "app.main.search_semantic_scholar",
        fake_semantic_scholar_search,
    )

    r = client.get(
        "/search",
        params={
            "q": "glioblastoma",
            "source": "semantic_scholar",
            "page": 2,
            "n": 5,
            "sort": "relevance",
        },
    )

    assert r.status_code == 200
    assert ">Previous</a>" in r.text
    assert "page=1" in r.text


def test_semantic_scholar_bulk_previous_navigation_uses_cached_token(
    client, monkeypatch
):
    def fake_semantic_scholar_bulk(*args, **kwargs):
        papers = [
            Paper(
                id=f"ss-bulk-{i}",
                source="semantic_scholar",
                title=f"Semantic Scholar bulk paper {i}",
                authors=["Tester A"],
                journal="Test Journal",
                year=2024,
                abstract="Test abstract",
                doi=None,
                pmcid=None,
                url=f"https://www.semanticscholar.org/paper/bulk-{i}",
                mesh_terms=[],
                has_full_text=False,
            )
            for i in range(5)
        ]
        return papers, 50, "next-page-token"

    monkeypatch.setattr(
        "app.main.search_semantic_scholar_bulk",
        fake_semantic_scholar_bulk,
    )

    monkeypatch.setattr(
        "app.main._ss_get_token_for_page",
        lambda *args, **kwargs: "previous-page-token",
        raising=False,
    )

    r = client.get(
        "/search",
        params={
            "q": "glioblastoma",
            "source": "semantic_scholar",
            "page": 3,
            "n": 5,
            "sort": "date_desc",
            "token": "current-page-token",
        },
    )

    assert r.status_code == 200
    assert ">Previous</a>" in r.text
    assert "page=2" in r.text
    assert "token=previous-page-token" in r.text


def test_semantic_scholar_bulk_page_two_previous_goes_to_first_page_without_token(
    client, monkeypatch
):
    def fake_semantic_scholar_bulk(*args, **kwargs):
        papers = [
            Paper(
                id=f"ss-bulk-{i}",
                source="semantic_scholar",
                title=f"Semantic Scholar bulk paper {i}",
                authors=["Tester A"],
                journal="Test Journal",
                year=2024,
                abstract="Test abstract",
                doi=None,
                pmcid=None,
                url=f"https://www.semanticscholar.org/paper/bulk-{i}",
                mesh_terms=[],
                has_full_text=False,
            )
            for i in range(5)
        ]
        return papers, 50, "next-page-token"

    monkeypatch.setattr(
        "app.main.search_semantic_scholar_bulk",
        fake_semantic_scholar_bulk,
    )

    r = client.get(
        "/search",
        params={
            "q": "glioblastoma",
            "source": "semantic_scholar",
            "page": 2,
            "n": 5,
            "sort": "date_desc",
            "token": "current-page-token",
        },
    )

    assert r.status_code == 200

    match = re.search(r'href="([^"]+)">Previous</a>', r.text)
    assert match is not None

    previous_href = html.unescape(match.group(1))

    assert "page=1" in previous_href
    assert "token=" not in previous_href


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


def test_doaj_only_offers_relevance_sort(client, monkeypatch):
    def fake_doaj_search(*args, **kwargs):
        return (
            [
                Paper(
                    id="doaj-test-id",
                    source="doaj",
                    title="Test DOAJ paper",
                    authors=["Tester A"],
                    journal="Test Journal",
                    year=2024,
                    abstract="Test abstract",
                    doi="10.1234/example",
                    pmcid=None,
                    url="https://doaj.org/article/doaj-test-id",
                    mesh_terms=[],
                    has_full_text=True,
                )
            ],
            1,
        )

    monkeypatch.setattr("app.main.doaj_search", fake_doaj_search)

    r = client.get(
        "/search",
        params={
            "q": "cancer",
            "source": "doaj",
            "n": 5,
            "sort": "relevance",
        },
    )

    assert r.status_code == 200
    assert '<option value="relevance"' in r.text
    assert '<option value="date_desc"' not in r.text
    assert '<option value="date_asc"' not in r.text


def test_doaj_export_limit_stops_at_1000(client, monkeypatch):
    def fake_doaj_search(*args, **kwargs):
        return (
            [
                Paper(
                    id="doaj-test-id",
                    source="doaj",
                    title="Test DOAJ paper",
                    authors=["Tester A"],
                    journal="Test Journal",
                    year=2024,
                    abstract="Test abstract",
                    doi="10.1234/example",
                    pmcid=None,
                    url="https://doaj.org/article/doaj-test-id",
                    mesh_terms=[],
                    has_full_text=True,
                )
            ],
            1,
        )

    monkeypatch.setattr("app.main.doaj_search", fake_doaj_search)

    r = client.get(
        "/search",
        params={
            "q": "cancer",
            "source": "doaj",
            "n": 5,
            "sort": "relevance",
        },
    )

    assert r.status_code == 200
    assert '<option value="1000" selected>First 1000</option>' in r.text
    assert '<option value="2000">First 2000</option>' not in r.text


def test_pubmed_export_limit_still_offers_2000(client):
    r = client.get(
        "/search",
        params={
            "q": "",
            "source": "pubmed",
        },
    )

    assert r.status_code == 200
    assert '<option value="2000">First 2000</option>' in r.text


def test_all_sources_snapshot_id_is_preserved_in_navigation_and_export(
    client,
    monkeypatch,
):
    async def fake_build_all_source_results(**kwargs):
        return {
            "papers": [
                Paper(
                    id="p1",
                    source="pubmed",
                    title="Paper 1",
                    year=2025,
                    doi="10.1234/p1",
                )
            ],
            "all_papers": [
                Paper(
                    id="p1",
                    source="pubmed",
                    title="Paper 1",
                    year=2025,
                    doi="10.1234/p1",
                ),
                Paper(
                    id="p2",
                    source="openalex",
                    title="Paper 2",
                    year=2025,
                    doi="10.1234/p2",
                ),
            ],
            "total_count": 2,
            "duplicates_removed": 0,
            "source_counts": {
                "pubmed": 1,
                "openalex": 1,
            },
            "failed_sources": [],
            "snapshot_id": "snapshot-test-123",
        }

    monkeypatch.setattr(
        "app.main.build_all_source_results",
        fake_build_all_source_results,
    )

    r = client.get(
        "/search",
        params={
            "q": "cancer",
            "source": "all",
            "page": 1,
            "n": 1,
            "sort": "relevance",
        },
    )

    assert r.status_code == 200

    assert "snapshot_id=snapshot-test-123" in r.text

    assert "/export/csv" in r.text and "snapshot_id=snapshot-test-123" in r.text


def test_all_sources_previous_navigation_preserves_snapshot_id(
    client,
    monkeypatch,
):
    async def fake_build_all_source_results(**kwargs):
        return {
            "papers": [
                Paper(
                    id="p2",
                    source="openalex",
                    title="Paper 2",
                    year=2025,
                    doi="10.1234/p2",
                )
            ],
            "all_papers": [
                Paper(
                    id="p1",
                    source="pubmed",
                    title="Paper 1",
                    year=2025,
                    doi="10.1234/p1",
                ),
                Paper(
                    id="p2",
                    source="openalex",
                    title="Paper 2",
                    year=2025,
                    doi="10.1234/p2",
                ),
            ],
            "total_count": 2,
            "duplicates_removed": 0,
            "source_counts": {
                "pubmed": 1,
                "openalex": 1,
            },
            "failed_sources": [],
            "snapshot_id": "snapshot-test-123",
        }

    monkeypatch.setattr(
        "app.main.build_all_source_results",
        fake_build_all_source_results,
    )

    r = client.get(
        "/search",
        params={
            "q": "cancer",
            "source": "all",
            "page": 2,
            "n": 1,
            "sort": "relevance",
            "snapshot_id": "snapshot-test-123",
        },
    )

    assert r.status_code == 200

    previous_link = next(
        line for line in r.text.splitlines() if ">Previous</a>" in line
    )

    assert "page=1" in previous_link
    assert "snapshot_id=snapshot-test-123" in previous_link


def test_all_sources_goto_page_preserves_snapshot_id(
    client,
    monkeypatch,
):
    async def fake_build_all_source_results(**kwargs):
        return {
            "papers": [
                Paper(
                    id="p1",
                    source="pubmed",
                    title="Paper 1",
                    year=2025,
                    doi="10.1234/p1",
                )
            ],
            "all_papers": [
                Paper(
                    id="p1",
                    source="pubmed",
                    title="Paper 1",
                    year=2025,
                    doi="10.1234/p1",
                ),
                Paper(
                    id="p2",
                    source="openalex",
                    title="Paper 2",
                    year=2025,
                    doi="10.1234/p2",
                ),
            ],
            "total_count": 2,
            "duplicates_removed": 0,
            "source_counts": {
                "pubmed": 1,
                "openalex": 1,
            },
            "failed_sources": [],
            "snapshot_id": "snapshot-test-123",
        }

    monkeypatch.setattr(
        "app.main.build_all_source_results",
        fake_build_all_source_results,
    )

    r = client.get(
        "/search",
        params={
            "q": "cancer",
            "source": "all",
            "page": 1,
            "n": 1,
            "sort": "relevance",
        },
    )

    assert r.status_code == 200

    goto_form = r.text.split('<form id="goto_form"', 1)[1].split("</form>", 1)[0]

    assert 'name="snapshot_id"' in goto_form
    assert 'value="snapshot-test-123"' in goto_form


def test_doaj_previous_navigation_goes_to_previous_page(
    client,
    monkeypatch,
):
    def fake_doaj_search(*args, **kwargs):
        return (
            [
                Paper(
                    id="doaj-test-id",
                    source="doaj",
                    title="Test DOAJ paper",
                    authors=["Tester A"],
                    journal="Test Journal",
                    year=2024,
                    abstract="Test abstract",
                    doi="10.1234/example",
                    pmcid=None,
                    url="https://doaj.org/article/doaj-test-id",
                    mesh_terms=[],
                    has_full_text=True,
                )
            ],
            15,
        )

    monkeypatch.setattr("app.main.doaj_search", fake_doaj_search)

    r = client.get(
        "/search",
        params={
            "q": "cancer",
            "source": "doaj",
            "page": 2,
            "n": 5,
            "sort": "relevance",
        },
    )

    assert r.status_code == 200

    previous_link = next(
        line for line in r.text.splitlines() if ">Previous</a>" in line
    )

    assert "page=1" in previous_link


def test_openalex_previous_navigation_goes_to_previous_page(
    client,
    monkeypatch,
):
    def fake_openalex_search(*args, **kwargs):
        return (
            [
                Paper(
                    id="openalex-test-id",
                    source="openalex",
                    title="Test OpenAlex paper",
                    authors=["Tester A"],
                    journal="Test Journal",
                    year=2024,
                    abstract="Test abstract",
                    doi="10.1234/example",
                    pmcid=None,
                    url="https://openalex.org/W123456789",
                    mesh_terms=[],
                    has_full_text=True,
                )
            ],
            15,
        )

    monkeypatch.setattr("app.main.openalex_search", fake_openalex_search)

    r = client.get(
        "/search",
        params={
            "q": "cancer",
            "source": "openalex",
            "page": 2,
            "n": 5,
            "sort": "relevance",
        },
    )

    assert r.status_code == 200

    previous_link = next(
        line for line in r.text.splitlines() if ">Previous</a>" in line
    )

    assert "page=1" in previous_link


def test_crossref_previous_navigation_goes_to_previous_page(
    client,
    monkeypatch,
):
    def fake_crossref_search(*args, **kwargs):
        return (
            [
                Paper(
                    id="crossref-test-id",
                    source="crossref",
                    title="Test Crossref paper",
                    authors=["Tester A"],
                    journal="Test Journal",
                    year=2024,
                    abstract="Test abstract",
                    doi="10.1234/example",
                    pmcid=None,
                    url="https://doi.org/10.1234/example",
                    mesh_terms=[],
                    has_full_text=False,
                )
            ],
            15,
        )

    monkeypatch.setattr("app.main.crossref_search", fake_crossref_search)

    r = client.get(
        "/search",
        params={
            "q": "cancer",
            "source": "crossref",
            "page": 2,
            "n": 5,
            "sort": "relevance",
        },
    )

    assert r.status_code == 200

    previous_link = next(
        line for line in r.text.splitlines() if ">Previous</a>" in line
    )

    assert "page=1" in previous_link


def test_pubmed_previous_navigation_goes_to_previous_page(
    client,
    monkeypatch,
):
    async def fake_pubmed_search_page(*args, **kwargs):
        class FakeRes:
            pmids = ["12345"]
            count = 15
            webenv = "fake_webenv"
            query_key = "1"

        return FakeRes()

    async def fake_pubmed_fetch_details(*args, **kwargs):
        return [
            Paper(
                id="12345",
                source="pubmed",
                title="Test PubMed paper",
                authors=["Tester A"],
                journal="Test Journal",
                year=2024,
                abstract="Test abstract",
                doi="10.1234/example",
                pmcid=None,
                url="https://pubmed.ncbi.nlm.nih.gov/12345/",
                mesh_terms=[],
                has_full_text=False,
            )
        ]

    monkeypatch.setattr(
        "app.main.pubmed_search_page",
        fake_pubmed_search_page,
    )
    monkeypatch.setattr(
        "app.main.pubmed_fetch_details",
        fake_pubmed_fetch_details,
    )

    r = client.get(
        "/search",
        params={
            "q": "cancer",
            "source": "pubmed",
            "page": 2,
            "n": 5,
            "sort": "relevance",
        },
    )

    assert r.status_code == 200

    previous_link = next(
        line for line in r.text.splitlines() if ">Previous</a>" in line
    )

    assert "page=1" in previous_link


def test_openalex_page_one_fetches_upstream_only_once(client, monkeypatch):
    calls = []

    def fake_openalex_search(*args, **kwargs):
        calls.append(
            {
                "page": kwargs.get("page"),
                "n": kwargs.get("n"),
            }
        )
        return (
            [
                Paper(
                    id="openalex-test-id",
                    source="openalex",
                    title="Test OpenAlex paper",
                    authors=["Tester A"],
                    journal="Test Journal",
                    year=2024,
                    abstract="Test abstract",
                    doi="10.1234/example",
                    pmcid=None,
                    url="https://openalex.org/W123456789",
                    mesh_terms=[],
                    has_full_text=True,
                )
            ],
            15,
        )

    monkeypatch.setattr(
        "app.main.openalex_search",
        fake_openalex_search,
    )

    r = client.get(
        "/search",
        params={
            "q": "cancer",
            "source": "openalex",
            "page": 1,
            "n": 5,
            "sort": "relevance",
        },
    )

    assert r.status_code == 200
    assert len(calls) == 1
    assert calls[0]["page"] == 1
    assert calls[0]["n"] == 5


def test_openalex_uses_cached_page_without_upstream_call(client, monkeypatch):
    async def fake_cache_get_json(redis, key):
        if key.startswith("cache:openalex:meta"):
            return {"total_count": 15}

        if key.startswith("cache:openalex:page"):
            return {
                "papers": [
                    Paper(
                        id="cached-openalex-id",
                        source="openalex",
                        title="Cached OpenAlex paper",
                        authors=["Cached Author"],
                        journal="Cached Journal",
                        year=2024,
                        abstract="Cached abstract",
                        doi="10.1234/cached",
                        pmcid=None,
                        url="https://openalex.org/W987654321",
                        mesh_terms=[],
                        has_full_text=True,
                    ).to_dict()
                ]
            }

        return None

    def fail_openalex_search(*args, **kwargs):
        raise AssertionError("openalex_search should not be called on a page cache hit")

    monkeypatch.setattr(
        "app.main.cache_get_json",
        fake_cache_get_json,
    )
    monkeypatch.setattr(
        "app.main.openalex_search",
        fail_openalex_search,
    )

    r = client.get(
        "/search",
        params={
            "q": "cancer",
            "source": "openalex",
            "page": 1,
            "n": 5,
            "sort": "relevance",
        },
    )

    assert r.status_code == 200
    assert "Cached OpenAlex paper" in r.text
