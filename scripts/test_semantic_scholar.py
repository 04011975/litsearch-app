def test_semantic_scholar_connector():
    from app.connectors.semantic_scholar import search_semantic_scholar

    papers, total = search_semantic_scholar("cancer", page=1, n=5)

    assert isinstance(papers, list)
    assert len(papers) <= 5