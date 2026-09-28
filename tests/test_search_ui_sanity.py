from app.models.paper import Paper

from app.main import _template_base_context

import asyncio
import html
import re


def test_search_page_loads(client):
    r = client.get("/search")
    assert r.status_code == 200
    assert "Search Results" in r.text or "LitSearch" in r.text


def test_template_context_exposes_semantic_scholar_last_capability(client):
    request = client.get("/search").request

    context = _template_base_context(
        request,
        q="glioblastoma",
        source="semantic_scholar",
        n=5,
        page=2,
        sort="relevance",
        year_min="",
        year_max="",
        has_abstract=0,
        mesh="",
    )

    assert context["supports_last"] is False


def test_template_context_exposes_previous_capability(client):
    request = client.get("/search").request

    context = _template_base_context(
        request,
        q="glioblastoma",
        source="semantic_scholar",
        n=5,
        page=2,
        sort="relevance",
        year_min="",
        year_max="",
        has_abstract=0,
        mesh="",
    )

    assert context["supports_previous"] is True


def test_template_context_exposes_europe_pmc_mesh_capability(client):
    request = client.get("/search").request

    context = _template_base_context(
        request,
        q="glioblastoma",
        source="europe_pmc",
        n=5,
        page=1,
        sort="relevance",
        year_min="",
        year_max="",
        has_abstract=0,
        mesh="Humans|Adolescent",
        mesh_mode="and",
    )

    assert context["supports_mesh_filter"] is True
    assert context["mesh_mode"] == "and"

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


def test_pubmed_sort_options_match_capabilities(client, monkeypatch):
    async def fake_pubmed_search_page(*args, **kwargs):
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
            "sort": "relevance",
        },
    )

    assert r.status_code == 200
    assert '<option value="relevance"' in r.text
    assert '<option value="date_desc"' in r.text
    assert '<option value="date_asc"' not in r.text


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

    monkeypatch.setattr("app.main._redis", object())
    monkeypatch.setattr("app.main.ARQ_REDIS", object())

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
    assert ">Last</a>" in r.text

    assert 'id="goto_page_input"' in r.text
    assert 'id="goto_page_input"\n      type="number"\n      name="page"' in r.text
    assert (
        'name="page"\n'
        '      value="2"\n'
        '      min="1"\n'
        '      max="40"\n'
        '      style="width: 5rem;"\n'
        "      disabled" not in r.text
    )



def test_europe_pmc_previous_navigation_preserves_mesh_mode(client, monkeypatch):
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

    monkeypatch.setattr("app.main._redis", object())
    monkeypatch.setattr("app.main.ARQ_REDIS", object())

    r = client.get(
        "/search",
        params={
            "q": "glioblastoma",
            "source": "europe_pmc",
            "page": 2,
            "n": 5,
            "sort": "relevance",
            "cursor": "*",
            "mesh": "Humans|Adolescent",
            "mesh_mode": "and",
        },
    )

    assert r.status_code == 200

    previous_href = r.text.split(">Previous</a>")[0].rsplit('href="', 1)[-1].split('"', 1)[0]

    assert "mesh_mode=and" in previous_href


def test_europe_pmc_cache_key_distinguishes_mesh_mode():
    from app.main import _epmc_cache_key_filtered

    or_key = _epmc_cache_key_filtered(
        "cancer",
        n=10,
        sort="relevance",
        mesh="Humans|Adolescent",
        mesh_mode="or",
    )

    and_key = _epmc_cache_key_filtered(
        "cancer",
        n=10,
        sort="relevance",
        mesh="Humans|Adolescent",
        mesh_mode="and",
    )

    assert or_key != and_key


def test_europe_pmc_build_key_distinguishes_mesh_mode():
    from app.main import _epmc_build_key_filtered

    or_key = _epmc_build_key_filtered(
        "cancer",
        n=10,
        sort="relevance",
        mesh="Humans|Adolescent",
        mesh_mode="or",
    )
    and_key = _epmc_build_key_filtered(
        "cancer",
        n=10,
        sort="relevance",
        mesh="Humans|Adolescent",
        mesh_mode="and",
    )

    assert or_key != and_key


def test_europe_pmc_next_navigation_preserves_mesh_mode(client, monkeypatch):
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

    monkeypatch.setattr("app.main._redis", object())
    monkeypatch.setattr("app.main.ARQ_REDIS", object())

    r = client.get(
        "/search",
        params={
            "q": "glioblastoma",
            "source": "europe_pmc",
            "page": 1,
            "n": 5,
            "sort": "relevance",
            "cursor": "*",
            "mesh": "Humans|Adolescent",
            "mesh_mode": "and",
        },
    )

    assert r.status_code == 200

    next_href = r.text.split(">Next</a>")[0].rsplit('href="', 1)[-1].split('"', 1)[0]

    assert "mesh_mode=and" in next_href


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


def test_europe_pmc_next_chunk_navigation_preserves_mesh_mode(client, monkeypatch):
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

    monkeypatch.setattr(
        "app.main._europe_pmc_search_compat_async",
        fake_europe_pmc_search,
    )

    r = client.get(
        "/search",
        params={
            "q": "glioblastoma",
            "source": "europe_pmc",
            "page": 100,
            "n": 5,
            "sort": "relevance",
            "cursor": "*",
            "mesh": "Humans|Adolescent",
            "mesh_mode": "and",
        },
    )

    assert r.status_code == 200

    next_href = r.text.split(">Next</a>")[0].rsplit('href="', 1)[-1].split('"', 1)[0]

    assert "page=101" in next_href
    assert "cursor=next-cursor" in next_href
    assert "mesh_mode=and" in next_href


def test_europe_pmc_search_compat_forwards_mesh_mode(monkeypatch):
    from app.main import _europe_pmc_search_compat_async

    captured_kwargs = {}

    async def fake_run_sync(func, *args, **kwargs):
        captured_kwargs.update(kwargs)
        return [], 0, None

    monkeypatch.setattr("app.main._run_sync", fake_run_sync)

    asyncio.run(
        _europe_pmc_search_compat_async(
            "cancer",
            n=10,
            cursor="*",
            sort="relevance",
            mesh="Humans|Adolescent",
            mesh_mode="and",
        )
    )

    assert captured_kwargs["mesh"] == "Humans|Adolescent"
    assert captured_kwargs["mesh_mode"] == "and"


def test_europe_pmc_search_passes_mesh_mode(
    client,
    monkeypatch,
):
    captured_kwargs = {}

    async def fake_europe_pmc_search(*args, **kwargs):
        captured_kwargs.update(kwargs)
        return [], 0, None

    monkeypatch.setattr(
        "app.main._europe_pmc_search_compat_async",
        fake_europe_pmc_search,
    )

    r = client.get(
        "/search",
        params={
            "q": "cancer",
            "source": "europe_pmc",
            "n": 10,
            "sort": "relevance",
            "mesh": "Humans|Adolescent",
            "mesh_mode": "and",
        },
    )

    assert r.status_code == 200
    assert captured_kwargs["mesh"] == "Humans|Adolescent"
    assert captured_kwargs["mesh_mode"] == "and"


def test_europe_pmc_search_passes_mesh_mode_to_template_context(
    client,
    monkeypatch,
):
    captured_context = {}

    async def fake_europe_pmc_search(*args, **kwargs):
        return [], 0, None

    original_template_response = __import__(
        "app.main",
        fromlist=["templates"],
    ).templates.TemplateResponse

    def capture_template_response(request, name, context, *args, **kwargs):
        captured_context.update(context)
        return original_template_response(
            request,
            name,
            context,
            *args,
            **kwargs,
        )

    monkeypatch.setattr(
        "app.main._europe_pmc_search_compat_async",
        fake_europe_pmc_search,
    )
    monkeypatch.setattr(
        "app.main.templates.TemplateResponse",
        capture_template_response,
    )

    r = client.get(
        "/search",
        params={
            "q": "cancer",
            "source": "europe_pmc",
            "n": 10,
            "sort": "relevance",
            "mesh": "Humans|Adolescent",
            "mesh_mode": "and",
        },
    )

    assert r.status_code == 200
    assert captured_context["mesh_mode"] == "and"


def test_europe_pmc_shows_mesh_filter_controls(
    client,
    monkeypatch,
):
    async def fake_europe_pmc_search(*args, **kwargs):
        return [], 0, None

    monkeypatch.setattr(
        "app.main._europe_pmc_search_compat_async",
        fake_europe_pmc_search,
    )

    r = client.get(
        "/search",
        params={
            "q": "cancer",
            "source": "europe_pmc",
            "n": 10,
            "sort": "relevance",
        },
    )

    assert r.status_code == 200
    assert 'id="mesh_input"' in r.text
    assert 'id="mesh_mode"' in r.text


def test_all_sources_does_not_show_partial_mesh_filter_controls(
    client,
    monkeypatch,
):
    async def fake_build_all_source_results(*args, **kwargs):
        return {
            "papers": [],
            "all_papers": [],
            "total_count": 0,
            "duplicates_removed": 0,
            "source_counts": {},
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
            "n": 10,
            "sort": "relevance",
        },
    )

    assert r.status_code == 200
    assert 'id="mesh_input"' not in r.text
    assert 'id="mesh_mode"' not in r.text


def test_europe_pmc_reset_filters_preserves_mesh_parameters(
    client,
    monkeypatch,
):
    async def fake_europe_pmc_search(*args, **kwargs):
        return [], 0, None

    monkeypatch.setattr(
        "app.main._europe_pmc_search_compat_async",
        fake_europe_pmc_search,
    )

    r = client.get(
        "/search",
        params={
            "q": "cancer",
            "source": "europe_pmc",
            "mesh": "Humans|Adolescent",
            "mesh_mode": "and",
        },
    )

    assert r.status_code == 200

    reset_href = (
        r.text.split("Reset filters")[0]
        .rsplit('href="', 1)[-1]
        .split('"', 1)[0]
    )

    assert "mesh=" in reset_href
    assert "mesh_mode=or" in reset_href


def test_europe_pmc_goto_page_preserves_mesh_filters(
    client,
    monkeypatch,
):
    async def fake_europe_pmc_search(*args, **kwargs):
        return [], 100, None

    monkeypatch.setattr(
        "app.main._europe_pmc_search_compat_async",
        fake_europe_pmc_search,
    )

    r = client.get(
        "/search",
        params={
            "q": "cancer",
            "source": "europe_pmc",
            "mesh": "Humans|Adolescent",
            "mesh_mode": "and",
        },
    )

    assert r.status_code == 200

    goto_form = (
        r.text.split('id="goto_form"', 1)[1]
        .split("</form>", 1)[0]
    )

    assert 'name="mesh" value="Humans|Adolescent"' in goto_form
    assert 'name="mesh_mode" value="and"' in goto_form


def test_europe_pmc_page_export_links_preserve_mesh_filters(
    client,
    monkeypatch,
):
    async def fake_europe_pmc_search(*args, **kwargs):
        return [], 100, None

    monkeypatch.setattr(
        "app.main._europe_pmc_search_compat_async",
        fake_europe_pmc_search,
    )

    r = client.get(
        "/search",
        params={
            "q": "cancer",
            "source": "europe_pmc",
            "mesh": "Humans|Adolescent",
            "mesh_mode": "and",
        },
    )

    assert r.status_code == 200

    csv_href = (
        r.text.split(">CSV (current page)</a>")[0]
        .rsplit('href="', 1)[-1]
        .split('"', 1)[0]
    )
    ris_href = (
        r.text.split(">RIS (current page)</a>")[0]
        .rsplit('href="', 1)[-1]
        .split('"', 1)[0]
    )

    for href in (csv_href, ris_href):
        assert "mesh=Humans%7CAdolescent" in href
        assert "mesh_mode=and" in href


def test_europe_pmc_async_export_params_preserve_mesh_filters(
    client,
    monkeypatch,
):
    async def fake_europe_pmc_search(*args, **kwargs):
        return [], 100, None

    monkeypatch.setattr(
        "app.main._europe_pmc_search_compat_async",
        fake_europe_pmc_search,
    )

    r = client.get(
        "/search",
        params={
            "q": "cancer",
            "source": "europe_pmc",
            "mesh": "Humans|Adolescent",
            "mesh_mode": "and",
        },
    )

    assert r.status_code == 200

    build_params = (
        r.text.split("function buildParams()", 1)[1]
        .split("return params;", 1)[0]
    )

    assert 'params.set("mesh", "Humans|Adolescent");' in build_params
    assert 'params.set("mesh_mode", "and");' in build_params


def test_europe_pmc_empty_query_passes_mesh_mode_to_template_context(
    client,
    monkeypatch,
):
    captured = {}

    def fake_template_response(request, name, context):
        captured.update(context)

        from starlette.responses import HTMLResponse

        return HTMLResponse("ok")

    monkeypatch.setattr(
        "app.main.templates.TemplateResponse",
        fake_template_response,
    )

    r = client.get(
        "/search",
        params={
            "q": "",
            "source": "europe_pmc",
            "mesh": "Humans|Adolescent",
            "mesh_mode": "and",
        },
    )

    assert r.status_code == 200
    assert captured["mesh"] == "Humans|Adolescent"
    assert captured["mesh_mode"] == "and"


def test_europe_pmc_deep_paging_unavailable_passes_mesh_mode_to_template_context(
    client,
    monkeypatch,
):
    captured = {}

    def fake_template_response(request, name, context):
        captured.update(context)

        from starlette.responses import HTMLResponse

        return HTMLResponse("ok")

    monkeypatch.setattr(
        "app.main.templates.TemplateResponse",
        fake_template_response,
    )
    monkeypatch.setattr(
        "app.main._redis",
        None,
    )
    monkeypatch.setattr(
        "app.main.ARQ_REDIS",
        None,
    )

    r = client.get(
        "/search",
        params={
            "q": "cancer",
            "source": "europe_pmc",
            "page": 2,
            "n": 10,
            "mesh": "Humans|Adolescent",
            "mesh_mode": "and",
        },
    )

    assert r.status_code == 200
    assert captured["allow_deep_paging"] is False
    assert captured["mesh"] == "Humans|Adolescent"
    assert captured["mesh_mode"] == "and"


def test_europe_pmc_build_status_passes_mesh_mode_to_template_context(
    client,
    monkeypatch,
):
    captured = {}

    def fake_template_response(request, name, context):
        captured.update(context)

        from starlette.responses import HTMLResponse

        return HTMLResponse("ok")

    async def fake_enqueue_build(*args, **kwargs):
        return None

    async def fake_hgetall(*args, **kwargs):
        return {
            b"status": b"queued",
            b"built_up_to_chunk": b"0",
        }

    class FakeRedis:
        async def hgetall(self, *args, **kwargs):
            return await fake_hgetall(*args, **kwargs)

    monkeypatch.setattr(
        "app.main.templates.TemplateResponse",
        fake_template_response,
    )
    monkeypatch.setattr(
        "app.main._redis",
        FakeRedis(),
    )
    monkeypatch.setattr(
        "app.main.ARQ_REDIS",
        FakeRedis(),
    )
    monkeypatch.setattr(
        "app.main._epmc_get_cursor_for_chunk",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "app.main._epmc_enqueue_build",
        fake_enqueue_build,
    )

    r = client.get(
        "/search",
        params={
            "q": "cancer",
            "source": "europe_pmc",
            "page": 2,
            "n": 10,
            "mesh": "Humans|Adolescent",
            "mesh_mode": "and",
        },
    )

    assert r.status_code == 200
    assert captured["epmc_building"] is True
    assert captured["mesh"] == "Humans|Adolescent"
    assert captured["mesh_mode"] == "and"


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


def test_europe_pmc_enqueue_build_accepts_mesh_mode():
    import inspect

    from app.main import _epmc_enqueue_build

    parameter = inspect.signature(_epmc_enqueue_build).parameters["mesh_mode"]

    assert parameter.default == "or"


def test_europe_pmc_enqueue_build_forwards_mesh_mode(monkeypatch):
    import asyncio

    import app.main as main

    class FakeRedis:
        def __init__(self):
            self.enqueued_kwargs = None

        async def hgetall(self, key):
            return {}

        async def hset(self, key, mapping):
            return None

        async def expire(self, key, seconds):
            return None

        async def enqueue_job(self, name, **kwargs):
            self.enqueued_kwargs = kwargs

    fake_redis = FakeRedis()
    monkeypatch.setattr(main, "ARQ_REDIS", fake_redis)

    asyncio.run(
        main._epmc_enqueue_build(
            "cancer",
            n=10,
            sort="relevance",
            target_page=2,
            mesh="Humans|Adolescent",
            mesh_mode="and",
        )
    )

    assert fake_redis.enqueued_kwargs["mesh_mode"] == "and"


def test_europe_pmc_deep_paging_route_forwards_mesh_mode_to_enqueue(
    client,
    monkeypatch,
):
    captured_kwargs = {}

    async def fake_enqueue_build(*args, **kwargs):
        captured_kwargs.update(kwargs)

    class FakeRedis:
        async def hgetall(self, key):
            return {}

    monkeypatch.setattr("app.main._redis", object())
    monkeypatch.setattr("app.main.ARQ_REDIS", FakeRedis())
    monkeypatch.setattr(
        "app.main._epmc_get_cursor_for_chunk",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "app.main._epmc_enqueue_build",
        fake_enqueue_build,
    )

    r = client.get(
        "/search",
        params={
            "q": "glioblastoma",
            "source": "europe_pmc",
            "page": 101,
            "n": 5,
            "sort": "relevance",
            "mesh": "Humans|Adolescent",
            "mesh_mode": "and",
        },
    )

    assert r.status_code == 200
    assert captured_kwargs["mesh"] == "Humans|Adolescent"
    assert captured_kwargs["mesh_mode"] == "and"


def test_europe_pmc_last_navigation_preserves_mesh_mode(client, monkeypatch):
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

    monkeypatch.setattr("app.main._redis", object())
    monkeypatch.setattr("app.main.ARQ_REDIS", object())

    r = client.get(
        "/search",
        params={
            "q": "glioblastoma",
            "source": "europe_pmc",
            "page": 2,
            "n": 5,
            "sort": "relevance",
            "cursor": "*",
            "mesh": "Humans|Adolescent",
            "mesh_mode": "and",
        },
    )

    assert r.status_code == 200

    last_href = r.text.split(">Last</a>")[0].rsplit('href="', 1)[-1].split('"', 1)[0]

    assert "mesh_mode=and" in last_href


def test_europe_pmc_page_export_links_preserve_mesh_mode(client, monkeypatch):
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

    monkeypatch.setattr("app.main._redis", object())
    monkeypatch.setattr("app.main.ARQ_REDIS", object())

    r = client.get(
        "/search",
        params={
            "q": "glioblastoma",
            "source": "europe_pmc",
            "page": 2,
            "n": 5,
            "sort": "relevance",
            "cursor": "*",
            "mesh": "Humans|Adolescent",
            "mesh_mode": "and",
        },
    )

    assert r.status_code == 200

    csv_href = (
        r.text.split(">CSV (current page)</a>")[0]
        .rsplit('href="', 1)[-1]
        .split('"', 1)[0]
    )
    ris_href = (
        r.text.split(">RIS (current page)</a>")[0]
        .rsplit('href="', 1)[-1]
        .split('"', 1)[0]
    )

    assert "mesh_mode=and" in csv_href
    assert "mesh_mode=and" in ris_href


def test_europe_pmc_deep_paging_route_forwards_mesh_mode_to_build_key(
    client,
    monkeypatch,
):
    captured_kwargs = {}

    async def fake_enqueue_build(*args, **kwargs):
        return None

    def fake_build_key(*args, **kwargs):
        captured_kwargs.update(kwargs)
        return "epmc:build:test"

    class FakeRedis:
        async def hgetall(self, key):
            return {}

    monkeypatch.setattr("app.main._redis", object())
    monkeypatch.setattr("app.main.ARQ_REDIS", FakeRedis())
    monkeypatch.setattr(
        "app.main._epmc_get_cursor_for_chunk",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "app.main._epmc_enqueue_build",
        fake_enqueue_build,
    )
    monkeypatch.setattr(
        "app.main._epmc_build_key_filtered",
        fake_build_key,
    )

    r = client.get(
        "/search",
        params={
            "q": "glioblastoma",
            "source": "europe_pmc",
            "page": 101,
            "n": 5,
            "sort": "relevance",
            "mesh": "Humans|Adolescent",
            "mesh_mode": "and",
        },
    )

    assert r.status_code == 200
    assert captured_kwargs["mesh"] == "Humans|Adolescent"
    assert captured_kwargs["mesh_mode"] == "and"


def test_europe_pmc_cached_cursor_redirect_preserves_mesh_mode(
    client,
    monkeypatch,
):
    monkeypatch.setattr("app.main._redis", object())
    monkeypatch.setattr("app.main.ARQ_REDIS", object())
    monkeypatch.setattr(
        "app.main._epmc_get_cursor_for_chunk",
        lambda *args, **kwargs: "cached-cursor",
    )

    r = client.get(
        "/search",
        params={
            "q": "glioblastoma",
            "source": "europe_pmc",
            "page": 101,
            "n": 5,
            "sort": "relevance",
            "mesh": "Humans|Adolescent",
            "mesh_mode": "and",
        },
        follow_redirects=False,
    )

    assert r.status_code in (302, 307)
    location = r.headers["location"]

    assert "cursor=cached-cursor" in location
    assert "mesh_mode=and" in location


def test_europe_pmc_built_cursor_redirect_preserves_mesh_mode(
    client,
    monkeypatch,
):
    cursor_results = iter([None, "built-cursor"])

    async def fake_enqueue_build(*args, **kwargs):
        return None

    monkeypatch.setattr("app.main._redis", object())
    monkeypatch.setattr("app.main.ARQ_REDIS", object())
    monkeypatch.setattr(
        "app.main._epmc_get_cursor_for_chunk",
        lambda *args, **kwargs: next(cursor_results),
    )
    monkeypatch.setattr(
        "app.main._epmc_enqueue_build",
        fake_enqueue_build,
    )

    r = client.get(
        "/search",
        params={
            "q": "glioblastoma",
            "source": "europe_pmc",
            "page": 101,
            "n": 5,
            "sort": "relevance",
            "mesh": "Humans|Adolescent",
            "mesh_mode": "and",
        },
        follow_redirects=False,
    )

    assert r.status_code in (302, 307)
    location = r.headers["location"]

    assert "cursor=built-cursor" in location
    assert "mesh_mode=and" in location


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
    assert 'id="goto_page_input"' in r.text
    assert 'id="goto_page_input"\n      type="number"\n      name="page"' in r.text
    assert (
        'name="page"\n      value="2"\n      min="1"\n      max="10"\n      style="width: 5rem;"\n      disabled'
        in r.text
    )
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


def test_europe_pmc_export_csv_current_page_passes_mesh_mode(
    client,
    monkeypatch,
):
    captured_kwargs = {}

    async def fake_europe_pmc_search(*args, **kwargs):
        captured_kwargs.update(kwargs)
        return [], 0, None

    monkeypatch.setattr(
        "app.main._europe_pmc_search_compat_async",
        fake_europe_pmc_search,
    )

    r = client.get(
        "/export/csv",
        params={
            "q": "cancer",
            "source": "europe_pmc",
            "scope": "page",
            "page": 1,
            "n": 5,
            "sort": "relevance",
            "mesh": "Humans|Adolescent",
            "mesh_mode": "and",
        },
    )

    assert r.status_code == 200
    assert "text/csv" in r.headers.get("content-type", "")
    assert captured_kwargs["mesh"] == "Humans|Adolescent"
    assert captured_kwargs["mesh_mode"] == "and"


def test_europe_pmc_export_csv_page_2_passes_mesh_mode_while_advancing_cursor(
    client,
    monkeypatch,
):
    captured_calls = []

    async def fake_europe_pmc_search(*args, **kwargs):
        captured_calls.append(kwargs)
        return [], 100, "next-cursor"

    monkeypatch.setattr(
        "app.main._europe_pmc_search_compat_async",
        fake_europe_pmc_search,
    )

    r = client.get(
        "/export/csv",
        params={
            "q": "cancer",
            "source": "europe_pmc",
            "scope": "page",
            "page": 2,
            "n": 5,
            "sort": "relevance",
            "cursor": "*",
            "mesh": "Humans|Adolescent",
            "mesh_mode": "and",
        },
    )

    assert r.status_code == 200
    assert len(captured_calls) >= 2
    assert captured_calls[0]["mesh"] == "Humans|Adolescent"
    assert captured_calls[0]["mesh_mode"] == "and"


def test_europe_pmc_export_csv_bulk_passes_mesh_mode(
    client,
    monkeypatch,
):
    captured_kwargs = {}

    async def fake_europe_pmc_search(*args, **kwargs):
        captured_kwargs.update(kwargs)
        return [], 0, None

    monkeypatch.setattr(
        "app.main._europe_pmc_search_compat_async",
        fake_europe_pmc_search,
    )

    r = client.get(
        "/export/csv",
        params={
            "q": "cancer",
            "source": "europe_pmc",
            "scope": "bulk",
            "limit": 5,
            "sort": "relevance",
            "mesh": "Humans|Adolescent",
            "mesh_mode": "and",
        },
    )

    assert r.status_code == 200
    assert "text/csv" in r.headers.get("content-type", "")
    assert captured_kwargs["mesh"] == "Humans|Adolescent"
    assert captured_kwargs["mesh_mode"] == "and"


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
    assert '<select name="has_abstract">' in r.text


def test_doaj_unsupported_sort_falls_back_to_relevance(client, monkeypatch):
    def fake_doaj_search(*args, **kwargs):
        return [], 0

    monkeypatch.setattr("app.main.doaj_search", fake_doaj_search)

    r = client.get(
        "/search",
        params={
            "q": "cancer",
            "source": "doaj",
            "n": 5,
            "sort": "date_desc",
        },
    )

    assert r.status_code == 200
    assert '<option value="relevance" selected>' in r.text


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


def test_all_sources_search_passes_mesh_mode(
    client,
    monkeypatch,
):
    captured_kwargs = {}

    async def fake_build_all_source_results(**kwargs):
        captured_kwargs.update(kwargs)
        return {
            "papers": [],
            "all_papers": [],
            "total_count": 0,
            "duplicates_removed": 0,
            "source_counts": {},
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
            "n": 10,
            "sort": "relevance",
            "mesh": "Humans|Adolescent",
            "mesh_mode": "and",
        },
    )

    assert r.status_code == 200
    assert captured_kwargs["mesh"] == "Humans|Adolescent"
    assert captured_kwargs["mesh_mode"] == "and"


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


def test_all_sources_previous_navigation_preserves_mesh_mode(
    client,
    monkeypatch,
):
    async def fake_build_all_source_results(**kwargs):
        return {
            "papers": [
                Paper(
                    id="p2",
                    source="pubmed",
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
                    source="pubmed",
                    title="Paper 2",
                    year=2025,
                    doi="10.1234/p2",
                ),
            ],
            "total_count": 2,
            "duplicates_removed": 0,
            "source_counts": {
                "pubmed": 2,
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
            "mesh": "Humans|Adolescent",
            "mesh_mode": "and",
            "snapshot_id": "snapshot-test-123",
        },
    )

    assert r.status_code == 200

    previous_link = next(
        line for line in r.text.splitlines() if ">Previous</a>" in line
    )

    assert "mesh=Humans%7CAdolescent" in previous_link
    assert "mesh_mode=and" in previous_link


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


def test_crossref_search_passes_abstract_filter(client, monkeypatch):
    captured = {}

    def fake_crossref_search(*args, **kwargs):
        captured.update(kwargs)
        return [], 0

    monkeypatch.setattr(
        "app.main.crossref_search",
        fake_crossref_search,
    )

    r = client.get(
        "/search",
        params={
            "q": "cancer",
            "source": "crossref",
            "n": 5,
            "sort": "relevance",
            "has_abstract": 1,
        },
    )

    assert r.status_code == 200
    assert captured["has_abstract"] is True


def test_crossref_shows_abstract_filter(client, monkeypatch):
    def fake_crossref_search(*args, **kwargs):
        return [], 0

    monkeypatch.setattr(
        "app.main.crossref_search",
        fake_crossref_search,
    )

    r = client.get(
        "/search",
        params={
            "q": "cancer",
            "source": "crossref",
            "n": 5,
            "sort": "relevance",
        },
    )

    assert r.status_code == 200
    assert '<select name="has_abstract">' in r.text


def test_crossref_abstract_filter_is_preserved_in_next_link(client, monkeypatch):
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

    monkeypatch.setattr(
        "app.main.crossref_search",
        fake_crossref_search,
    )

    r = client.get(
        "/search",
        params={
            "q": "cancer",
            "source": "crossref",
            "page": 1,
            "n": 5,
            "sort": "relevance",
            "has_abstract": 1,
        },
    )

    assert r.status_code == 200

    next_link = next(
        line for line in r.text.splitlines() if ">Next</a>" in line
    )

    assert "page=2" in next_link
    assert "has_abstract=1" in next_link


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


def test_openalex_shows_abstract_filter(client, monkeypatch):
    def fake_openalex_search(*args, **kwargs):
        return [], 0

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
    assert '<select name="has_abstract">' in r.text


def test_openalex_search_passes_abstract_filter(client, monkeypatch):
    calls = []

    def fake_openalex_search(*args, **kwargs):
        calls.append(kwargs)
        return ([], 0)

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
            "has_abstract": 1,
        },
    )

    assert r.status_code == 200
    assert len(calls) == 1
    assert calls[0]["has_abstract"] is True


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


def test_openalex_abstract_filter_changes_cache_keys(client, monkeypatch):
    cache_keys = []

    async def fake_cache_get_json(redis, key):
        cache_keys.append(key)
        return None

    async def fake_cache_set_json(redis, key, value, ttl):
        return None

    def fake_openalex_search(*args, **kwargs):
        return ([], 0)

    monkeypatch.setattr(
        "app.main.cache_get_json",
        fake_cache_get_json,
    )
    monkeypatch.setattr(
        "app.main.cache_set_json",
        fake_cache_set_json,
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
            "has_abstract": 0,
        },
    )

    assert r.status_code == 200
    keys_without_abstract_filter = list(cache_keys)

    cache_keys.clear()

    r = client.get(
        "/search",
        params={
            "q": "cancer",
            "source": "openalex",
            "page": 1,
            "n": 5,
            "sort": "relevance",
            "has_abstract": 1,
        },
    )

    assert r.status_code == 200
    keys_with_abstract_filter = list(cache_keys)

    assert keys_without_abstract_filter != keys_with_abstract_filter


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
