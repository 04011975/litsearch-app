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