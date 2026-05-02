import pytest

from app.connectors.europe_pmc import europe_pmc_fetch_detail, europe_pmc_search


@pytest.mark.anyio
async def test_epmc_search_returns_results():
    papers, total, next_cursor = europe_pmc_search(
        "glioblastoma",
        n=5,
        sort="relevance",
        year_min=2020,
        year_max=2022,
    )
    assert total >= 0
    assert isinstance(papers, list)
    assert len(papers) > 0
    assert next_cursor is None or isinstance(next_cursor, str)


@pytest.mark.anyio
async def test_epmc_has_abstract_filter():
    papers, total, _ = europe_pmc_search(
        "breast cancer",
        n=5,
        sort="relevance",
        year_min=2020,
        year_max=2022,
        has_abstract=1,
    )
    assert total >= 0
    assert papers
    assert all((p.abstract or "").strip() for p in papers)


@pytest.mark.anyio
async def test_epmc_detail_fetch_works():
    papers, total, _ = europe_pmc_search(
        "melanoma",
        n=3,
        sort="relevance",
    )
    assert total >= 0
    assert papers

    pid = papers[0].id
    detail = europe_pmc_fetch_detail(pid)
    assert detail is not None
    assert detail.id
    assert detail.title
    assert detail.source == "europe_pmc"


@pytest.mark.anyio
async def test_epmc_cursor_paging_works():
    page1, total1, cursor1 = europe_pmc_search(
        "cancer",
        n=5,
        cursor="*",
        sort="relevance",
    )
    assert total1 >= 0
    assert page1
    assert cursor1 is None or isinstance(cursor1, str)

    if cursor1:
        page2, total2, cursor2 = europe_pmc_search(
            "cancer",
            n=5,
            cursor=cursor1,
            sort="relevance",
        )
        assert total2 >= 0
        assert isinstance(page2, list)

@pytest.mark.anyio
async def test_epmc_year_range_semantics():
    papers, total, _ = europe_pmc_search(
        "cancer",
        n=10,
        year_min=2020,
        year_max=2021,
    )
    years = [p.year for p in papers if p.year is not None]
    assert years
    assert all(2020 <= y <= 2021 for y in years)
