
import pytest

from app.connectors.semantic_scholar import (
    SemanticScholarError,
    search_semantic_scholar,
)


@pytest.mark.integration
def test_semantic_scholar_connector():
    try:
        papers, total = search_semantic_scholar("cancer", page=1, n=5)
    except SemanticScholarError as exc:
        if "HTTP 429" in str(exc):
            pytest.skip(
                "Semantic Scholar API rate limit reached (HTTP 429)"
            )
        raise

    assert isinstance(papers, list)
    assert len(papers) <= 5
