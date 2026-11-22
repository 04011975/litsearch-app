
from app.core.normalize import normalize_paper
from app.models.paper import Paper


def test_normalize_paper_preserves_original_abstract():
    paper = Paper(
        id="test-1",
        source="openalex",
        title="Diabetes and Cancer",
        authors=["Test Author"],
        year=2010,
        abstract="Diabetes treatments.This consensus statement",
        doi="10.2337/dc10-0666",
    )

    result = normalize_paper(paper)

    assert result.abstract == "Diabetes treatments.This consensus statement"
