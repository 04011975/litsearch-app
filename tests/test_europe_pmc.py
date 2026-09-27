from app.connectors.europe_pmc import _map_result_json_to_paper


def test_map_result_normalizes_escaped_subscript_markup_in_abstract():
    item = {
        "pmid": "12345678",
        "title": "Test paper",
        "abstractText": r"Measured T\<sub>1\</sub> values in the study.",
    }

    paper = _map_result_json_to_paper(item)

    assert paper.abstract == "Measured T1 values in the study."


def test_map_result_normalizes_plain_subscript_markup_in_abstract():
    item = {
        "pmid": "12345678",
        "title": "Test paper",
        "abstractText": "Measured T<sub>1</sub> values in the study.",
    }

    paper = _map_result_json_to_paper(item)

    assert paper.abstract == "Measured T1 values in the study."


def test_map_result_normalizes_superscript_markup_in_abstract():
    item = {
        "pmid": "12345678",
        "title": "Test paper",
        "abstractText": r"CO\<sup>2\</sup> concentration increased.",
    }

    paper = _map_result_json_to_paper(item)

    assert paper.abstract == "CO2 concentration increased."


def test_map_result_preserves_plain_abstract_text():
    item = {
        "pmid": "12345678",
        "title": "Test paper",
        "abstractText": "Plain abstract text without markup.",
    }

    paper = _map_result_json_to_paper(item)

    assert paper.abstract == "Plain abstract text without markup."


def test_build_epmc_query_supports_mesh_and_mode():
    from app.connectors.europe_pmc import _build_epmc_query

    query = _build_epmc_query(
        "cancer",
        mesh="Humans|Adolescent",
        mesh_mode="and",
    )

    assert query == '(cancer) AND (MESH:"Humans" AND MESH:"Adolescent")'


def test_europe_pmc_search_accepts_mesh_mode():
    import inspect

    from app.connectors.europe_pmc import europe_pmc_search

    signature = inspect.signature(europe_pmc_search)

    assert "mesh_mode" in signature.parameters
    assert signature.parameters["mesh_mode"].default == "or"


def test_epmc_cursor_job_query_supports_mesh_and_mode():
    from app.jobs.epmc_tasks import _build_epmc_query

    query = _build_epmc_query(
        "cancer",
        mesh="Humans|Adolescent",
        mesh_mode="and",
    )

    assert query == '(cancer) AND (MESH:"Humans" AND MESH:"Adolescent")'


def test_epmc_cursor_call_accepts_mesh_mode():
    import inspect

    from app.jobs.epmc_tasks import _call_epmc

    signature = inspect.signature(_call_epmc)

    assert "mesh_mode" in signature.parameters
    assert signature.parameters["mesh_mode"].default == "or"


def test_build_epmc_cursors_accepts_mesh_mode():
    import inspect

    from app.jobs.epmc_tasks import build_epmc_cursors

    signature = inspect.signature(build_epmc_cursors)

    assert "mesh_mode" in signature.parameters
    assert signature.parameters["mesh_mode"].default == "or"


def test_epmc_lock_key_distinguishes_mesh_mode():
    from app.jobs.epmc_tasks import _epmc_lock_key

    or_key = _epmc_lock_key(
        "cancer",
        n=10,
        sort="relevance",
        mesh="Humans|Adolescent",
        mesh_mode="or",
    )
    and_key = _epmc_lock_key(
        "cancer",
        n=10,
        sort="relevance",
        mesh="Humans|Adolescent",
        mesh_mode="and",
    )

    assert or_key != and_key


def test_build_epmc_cursors_forwards_mesh_mode_to_keys(monkeypatch):
    import asyncio

    import app.jobs.epmc_tasks as epmc_tasks

    captured = {}

    def fake_build_key(q, **kwargs):
        captured["build"] = kwargs
        return "epmc:build:test"

    def fake_cache_key(q, **kwargs):
        captured["cache"] = kwargs
        return "epmc:cursor:test"

    def fake_lock_key(q, **kwargs):
        captured["lock"] = kwargs
        return "epmc:lock:test"

    class FakeRedis:
        async def set(self, *args, **kwargs):
            return False

        async def hset(self, *args, **kwargs):
            return None

        async def expire(self, *args, **kwargs):
            return None

    monkeypatch.setattr(epmc_tasks, "epmc_build_key", fake_build_key)
    monkeypatch.setattr(epmc_tasks, "epmc_cache_key", fake_cache_key)
    monkeypatch.setattr(epmc_tasks, "_epmc_lock_key", fake_lock_key)

    asyncio.run(
        epmc_tasks.build_epmc_cursors(
            {"redis": FakeRedis()},
            q="cancer",
            n=10,
            sort="relevance",
            target_chunk=2,
            mesh="Humans|Adolescent",
            mesh_mode="and",
        )
    )

    assert captured["build"]["mesh_mode"] == "and"
    assert captured["cache"]["mesh_mode"] == "and"
    assert captured["lock"]["mesh_mode"] == "and"


def test_epmc_cursor_call_returns_search_result(monkeypatch):
    import asyncio

    from app.jobs.epmc_tasks import _call_epmc

    expected = (["paper"], 1, "next-cursor")
    captured = {}

    def fake_europe_pmc_search(query, **kwargs):
        captured["query"] = query
        captured.update(kwargs)
        return expected

    monkeypatch.setattr(
        "app.jobs.epmc_tasks.europe_pmc_search",
        fake_europe_pmc_search,
    )

    result = asyncio.run(
        _call_epmc(
            "cancer",
            n=10,
            cursor="*",
            sort="relevance",
            mesh="Humans|Adolescent",
            mesh_mode="and",
        )
    )

    assert result == expected
    assert captured["query"] == (
        '(cancer) AND (MESH:"Humans" AND MESH:"Adolescent")'
    )
    assert captured["n"] == 10
    assert captured["cursor"] == "*"
    assert captured["sort"] == "relevance"
