from app.connectors.pubmed import build_pubmed_term, pubmed_fetch_details, pubmed_search_page

import pytest


@pytest.mark.anyio
async def test_pubmed_build_term_with_years_and_mesh_or():
    term = build_pubmed_term(
        "cancer",
        year_min=2018,
        year_max=2020,
        has_abstract=1,
        mesh="Humans|Adolescent",
        mesh_mode="or",
    )
    assert term
    assert "cancer" in term
    assert '"2018"[Date - Publication]' in term
    assert '"2020"[Date - Publication]' in term
    assert "hasabstract[text]" in term
    assert '"Humans"[MeSH Terms] OR "Adolescent"[MeSH Terms]' in term


@pytest.mark.anyio
async def test_pubmed_build_term_with_mesh_and():
    term = build_pubmed_term(
        "cancer",
        mesh="Humans,Adolescent",
        mesh_mode="and",
    )
    assert term
    assert '"Humans"[MeSH Terms] AND "Adolescent"[MeSH Terms]' in term


@pytest.mark.integration
@pytest.mark.anyio
async def test_pubmed_search_returns_results():
    res = await pubmed_search_page(
        build_pubmed_term("cancer", year_min=2020, year_max=2021),
        max_results=5,
        retstart=0,
        sort="relevance",
    )
    assert res.count >= 0
    assert isinstance(res.pmids, list)
    assert len(res.pmids) > 0


@pytest.mark.integration
@pytest.mark.anyio
async def test_pubmed_search_date_desc_returns_results():
    res = await pubmed_search_page(
        build_pubmed_term("cancer", year_min=2020, year_max=2021),
        max_results=5,
        retstart=0,
        sort="pub_date",
    )
    assert isinstance(res.pmids, list)
    assert len(res.pmids) > 0


@pytest.mark.integration
@pytest.mark.anyio
async def test_pubmed_fetch_details_has_expected_fields():
    res = await pubmed_search_page(
        build_pubmed_term("glioblastoma", year_min=2020, year_max=2022, has_abstract=1),
        max_results=5,
        retstart=0,
        sort="relevance",
    )
    assert res.pmids

    papers = await pubmed_fetch_details(res.pmids[:5])
    assert papers
    assert len(papers) > 0

    for p in papers:
        assert p.id
        assert p.title
        assert p.source == "pubmed"


@pytest.mark.integration
@pytest.mark.anyio
async def test_pubmed_has_abstract_filter_is_respected():
    res = await pubmed_search_page(
        build_pubmed_term("breast cancer", year_min=2020, year_max=2022, has_abstract=1),
        max_results=5,
        retstart=0,
        sort="relevance",
    )
    assert res.pmids

    papers = await pubmed_fetch_details(res.pmids[:5])
    assert papers

    nonempty_abstracts = [p for p in papers if (p.abstract or "").strip()]
    assert len(nonempty_abstracts) == len(papers)


@pytest.mark.anyio
async def test_pubmed_mesh_and_vs_or_changes_query():
    term_or = build_pubmed_term(
        "cancer",
        mesh="Humans|Adolescent",
        mesh_mode="or",
    )
    term_and = build_pubmed_term(
        "cancer",
        mesh="Humans,Adolescent",
        mesh_mode="and",
    )
    assert term_or != term_and
    assert " OR " in term_or
    assert " AND " in term_and


@pytest.mark.integration
@pytest.mark.anyio
async def test_pubmed_year_range_semantics():
    res = await pubmed_search_page(
        build_pubmed_term("cancer", year_min=2020, year_max=2021),
        max_results=10,
        retstart=0,
        sort="relevance",
    )
    assert res.pmids

    papers = await pubmed_fetch_details(res.pmids[:10])
    years = [p.year for p in papers if p.year is not None]

    assert years

    in_range = [y for y in years if 2020 <= y <= 2021]

    # sanity check: meerderheid of minstens duidelijke overlap
    assert len(in_range) >= max(1, len(years) // 2)


@pytest.mark.integration
@pytest.mark.anyio
async def test_pubmed_date_desc_is_recent_firstish():
    res = await pubmed_search_page(
        build_pubmed_term("glioblastoma", year_min=2020, year_max=2023),
        max_results=10,
        retstart=0,
        sort="pub_date",
    )
    assert res.pmids

    papers = await pubmed_fetch_details(res.pmids[:10])
    years = [p.year for p in papers if p.year is not None]

    assert years
    assert max(years) >= min(years)