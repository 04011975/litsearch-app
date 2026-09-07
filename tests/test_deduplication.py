from app.core.deduplication import deduplicate_papers
from app.models.paper import Paper


def make_paper(**kwargs):
    data = {
        "id": kwargs.get("id", "1"),
        "source": kwargs.get("source", "pubmed"),
        "title": kwargs.get("title", "Cancer biology"),
        "authors": kwargs.get("authors", ["Smith J"]),
        "journal": kwargs.get("journal", "Test Journal"),
        "year": kwargs.get("year", 2020),
        "doi": kwargs.get("doi", None),
        "pmcid": kwargs.get("pmcid", None),
        "url": kwargs.get("url", None),
    }
    return Paper(**data)


def test_deduplicate_same_doi():
    papers = [
        make_paper(id="1", doi="10.1000/test", source="pubmed"),
        make_paper(id="2", doi="10.1000/test", source="openalex"),
    ]

    result, removed = deduplicate_papers(papers)

    assert len(result) == 1
    assert removed == 1
    assert "pubmed" in result[0].source
    assert "openalex" in result[0].source


def test_deduplicate_doi_record_with_matching_doi_less_record():
    papers = [
        make_paper(
            id="1",
            source="openalex",
            title="Cancer Biology",
            authors=["Smith J"],
            year=2020,
            doi="10.1000/test",
        ),
        make_paper(
            id="2",
            source="semantic_scholar",
            title="Cancer Biology",
            authors=["Smith J"],
            year=2020,
            doi=None,
        ),
    ]

    result, removed = deduplicate_papers(papers)

    assert len(result) == 1
    assert removed == 1


def test_deduplicate_doi_less_record_with_matching_doi_record_reverse_order():
    papers = [
        make_paper(
            id="1",
            source="semantic_scholar",
            title="Cancer Biology",
            authors=["Smith J"],
            year=2020,
            doi=None,
        ),
        make_paper(
            id="2",
            source="openalex",
            title="Cancer Biology",
            authors=["Smith J"],
            year=2020,
            doi="10.1000/test",
        ),
    ]

    result, removed = deduplicate_papers(papers)

    assert len(result) == 1
    assert removed == 1


def test_different_dois_with_same_metadata_remain_separate():
    papers = [
        make_paper(
            id="1",
            source="openalex",
            title="Cancer Biology",
            authors=["Smith J"],
            year=2020,
            doi="10.1000/first",
        ),
        make_paper(
            id="2",
            source="crossref",
            title="Cancer Biology",
            authors=["Smith J"],
            year=2020,
            doi="10.1000/second",
        ),
    ]

    result, removed = deduplicate_papers(papers)

    assert len(result) == 2
    assert removed == 0


def test_doi_less_record_does_not_bridge_conflicting_doi_clusters():
    papers = [
        make_paper(
            id="1",
            source="openalex",
            title="Cancer Biology",
            authors=["Smith J"],
            year=2020,
            doi="10.1000/first",
        ),
        make_paper(
            id="2",
            source="crossref",
            title="Cancer Biology",
            authors=["Smith J"],
            year=2020,
            doi="10.1000/second",
        ),
        make_paper(
            id="3",
            source="semantic_scholar",
            title="Cancer Biology",
            authors=["Smith J"],
            year=2020,
            doi=None,
        ),
    ]

    result, removed = deduplicate_papers(papers)

    assert len(result) == 2
    assert removed == 1


def test_doi_acquired_via_merge_is_reused_for_later_record():
    papers = [
        make_paper(
            id="1",
            source="semantic_scholar",
            title="Cancer Biology",
            authors=["Smith J"],
            year=2020,
            doi=None,
        ),
        make_paper(
            id="2",
            source="openalex",
            title="Cancer Biology",
            authors=["Smith J"],
            year=2020,
            doi="10.1000/test",
        ),
        make_paper(
            id="3",
            source="crossref",
            title="Different metadata from source",
            authors=["Different Author"],
            year=2021,
            doi="10.1000/test",
        ),
    ]

    result, removed = deduplicate_papers(papers)

    assert len(result) == 1
    assert removed == 2


def test_deduplicate_doi_url_prefix():
    papers = [
        make_paper(id="1", doi="https://doi.org/10.1000/test"),
        make_paper(id="2", doi="10.1000/test"),
    ]

    result, removed = deduplicate_papers(papers)

    assert len(result) == 1
    assert removed == 1


def test_deduplicate_same_pmcid():
    papers = [
        make_paper(id="1", pmcid="PMC123"),
        make_paper(id="2", pmcid="pmc123"),
    ]

    result, removed = deduplicate_papers(papers)

    assert len(result) == 1
    assert removed == 1


def test_deduplicate_title_author_year_fallback():
    papers = [
        make_paper(id="1", title="Cancer Biology!", authors=["Smith J"], year=2020),
        make_paper(id="2", title="cancer biology", authors=["Smith J"], year=2020),
    ]

    result, removed = deduplicate_papers(papers)

    assert len(result) == 1
    assert removed == 1


def test_different_papers_remain_separate():
    papers = [
        make_paper(id="1", title="Cancer biology", authors=["Smith J"], year=2020),
        make_paper(id="2", title="Diabetes biology", authors=["Jones A"], year=2020),
    ]

    result, removed = deduplicate_papers(papers)

    assert len(result) == 2
    assert removed == 0


def test_merge_preserves_missing_fields():
    papers = [
        make_paper(id="1", doi="10.1000/test", journal=""),
        make_paper(id="2", doi="10.1000/test", journal="Better Journal"),
    ]

    result, removed = deduplicate_papers(papers)

    assert len(result) == 1
    assert removed == 1
    assert result[0].journal == "Better Journal"


def test_deduplicate_doi_record_with_matching_metadata_one_year_apart():
    papers = [
        make_paper(
            id="1",
            source="openalex",
            title="Applications of Machine Learning in Cancer Prediction and Prognosis",
            authors=["Joseph A. Cruz", "David S. Wishart"],
            year=2006,
            doi="10.1177/117693510600200030",
        ),
        make_paper(
            id="2",
            source="openalex",
            title="Applications of machine learning in cancer prediction and prognosis.",
            authors=["Joseph A. Cruz", "David S. Wishart"],
            year=2007,
            doi=None,
        ),
    ]

    result, removed = deduplicate_papers(papers)

    assert len(result) == 1
    assert removed == 1


def test_same_metadata_two_years_apart_remain_separate():
    papers = [
        make_paper(
            id="1",
            source="openalex",
            title="Cancer Biology",
            authors=["Smith J"],
            year=2020,
            doi="10.1000/first",
        ),
        make_paper(
            id="2",
            source="semantic_scholar",
            title="Cancer Biology",
            authors=["Smith J"],
            year=2022,
            doi=None,
        ),
    ]

    result, removed = deduplicate_papers(papers)

    assert len(result) == 2
    assert removed == 0


def test_doi_less_records_one_year_apart_remain_separate():
    papers = [
        make_paper(
            id="1",
            source="openalex",
            title="Cancer Biology",
            authors=["Smith J"],
            year=2020,
            doi=None,
        ),
        make_paper(
            id="2",
            source="semantic_scholar",
            title="Cancer Biology",
            authors=["Smith J"],
            year=2021,
            doi=None,
        ),
    ]

    result, removed = deduplicate_papers(papers)

    assert len(result) == 2
    assert removed == 0


def test_different_dois_one_year_apart_remain_separate():
    papers = [
        make_paper(
            id="1",
            source="openalex",
            title="Cancer Biology",
            authors=["Smith J"],
            year=2020,
            doi="10.1000/first",
        ),
        make_paper(
            id="2",
            source="crossref",
            title="Cancer Biology",
            authors=["Smith J"],
            year=2021,
            doi="10.1000/second",
        ),
    ]

    result, removed = deduplicate_papers(papers)

    assert len(result) == 2
    assert removed == 0


def test_deduplicate_doi_less_record_with_matching_metadata_one_year_apart_reverse_order():
    papers = [
        make_paper(
            id="1",
            source="openalex",
            title="Applications of machine learning in cancer prediction and prognosis.",
            authors=["Joseph A. Cruz", "David S. Wishart"],
            year=2007,
            doi=None,
        ),
        make_paper(
            id="2",
            source="openalex",
            title="Applications of Machine Learning in Cancer Prediction and Prognosis",
            authors=["Joseph A. Cruz", "David S. Wishart"],
            year=2006,
            doi="10.1177/117693510600200030",
        ),
    ]

    result, removed = deduplicate_papers(papers)

    assert len(result) == 1
    assert removed == 1
    assert result[0].doi == "10.1177/117693510600200030"


def test_year_tolerance_handles_non_numeric_year_without_crashing():
    papers = [
        make_paper(
            id="1",
            source="openalex",
            title="Cancer Biology",
            authors=["Smith J"],
            year=2020,
            doi="10.1000/test",
        ),
        make_paper(
            id="2",
            source="semantic_scholar",
            title="Cancer Biology",
            authors=["Smith J"],
            year="2021 Apr",
            doi=None,
        ),
    ]

    result, removed = deduplicate_papers(papers)

    assert len(result) == 1
    assert removed == 1
