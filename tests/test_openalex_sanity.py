import pytest

from app.connectors.openalex import openalex_fetch_detail, openalex_search


@pytest.mark.anyio
async def test_openalex_search_returns_results():
    papers, total = openalex_search(
        "machine learning",
        page=1,
        n=5,
        sort="relevance",
        year_min=2021,
        year_max=2023,
    )
    assert total >= 0
    assert isinstance(papers, list)
    assert len(papers) > 0


@pytest.mark.anyio
async def test_openalex_search_date_sort_returns_results():
    papers, total = openalex_search(
        "cancer",
        page=1,
        n=5,
        sort="publication_date:desc",
        year_min=2020,
        year_max=2023,
    )
    assert total >= 0
    assert papers


@pytest.mark.anyio
async def test_openalex_detail_fetch_works():
    papers, total = openalex_search(
        "breast cancer",
        page=1,
        n=3,
        sort="relevance",
    )
    assert total >= 0
    assert papers

    wid = papers[0].id
    detail = openalex_fetch_detail(wid)
    if detail is None:
        pytest.skip("OpenAlex detail fetch timed out or returned no data")

    assert detail.id
    assert detail.title
    assert detail.source == "openalex"


@pytest.mark.anyio
async def test_openalex_abstract_present_for_some_records():
    papers, total = openalex_search(
        "machine learning",
        page=1,
        n=10,
        sort="relevance",
        year_min=2021,
        year_max=2023,
    )
    assert total >= 0
    assert papers

    has_any_abstract = any((p.abstract or "").strip() for p in papers)
    assert has_any_abstract

@pytest.mark.anyio
async def test_openalex_year_range_semantics():
    papers, total = openalex_search(
        "cancer",
        page=1,
        n=10,
        year_min=2020,
        year_max=2021,
    )
    years = [p.year for p in papers if p.year is not None]
    assert years
    assert all(2020 <= y <= 2021 for y in years)