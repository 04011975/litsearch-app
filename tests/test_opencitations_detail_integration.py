from app.main import _paper_to_dict
from app.models.paper import Paper


def test_paper_to_dict_includes_opencitations_counts() -> None:
    paper = Paper(
        id="test-paper",
        source="pubmed",
        title="Test paper",
        citation_count=115,
        reference_count=77,
    )

    result = _paper_to_dict(
        paper,
        source=paper.source,
    )

    assert result["citation_count"] == 115
    assert result["reference_count"] == 77


def test_paper_to_dict_preserves_zero_counts() -> None:
    paper = Paper(
        id="test-paper-zero",
        source="europe_pmc",
        title="Test paper with zero counts",
        citation_count=0,
        reference_count=0,
    )

    result = _paper_to_dict(
        paper,
        source=paper.source,
    )

    assert result["citation_count"] == 0
    assert result["reference_count"] == 0


def test_paper_to_dict_allows_missing_counts() -> None:
    paper = Paper(
        id="test-paper-missing",
        source="openalex",
        title="Test paper without counts",
    )

    result = _paper_to_dict(
        paper,
        source=paper.source,
    )

    assert result["citation_count"] is None
    assert result["reference_count"] is None
