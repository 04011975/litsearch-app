from app.title_search import classify_title_match
from app.models.paper import Paper

import asyncio

def test_exact_title_match():
    result = classify_title_match(
        "Machine Learning in Cancer",
        "Machine Learning in Cancer",
    )

    assert result == "exact"


def test_normalized_title_match():
    result = classify_title_match(
        "Machine-Learning in Cancer!",
        "machine learning in cancer",
    )

    assert result == "normalized"


def test_partial_title_match():
    result = classify_title_match(
        "Machine Learning in Cancer",
        "Applications of Machine Learning in Cancer Research",
    )

    assert result == "partial"


def test_unrelated_titles_do_not_match():
    result = classify_title_match(
        "Machine Learning in Cancer",
        "Climate Change and Marine Biodiversity",
    )

    assert result is None


def test_empty_titles_do_not_match():
    assert classify_title_match("", "Machine Learning in Cancer") is None
    assert classify_title_match("Machine Learning in Cancer", "") is None
    assert classify_title_match("", "") is None
    assert classify_title_match(None, "Machine Learning in Cancer") is None
    assert classify_title_match("Machine Learning in Cancer", None) is None


def test_partial_match_requires_word_boundaries():
    result = classify_title_match(
        "Cancer",
        "Cancerous Cell Development",
    )

    assert result is None


def test_different_word_order_does_not_match():
    result = classify_title_match(
        "Machine Learning in Cancer",
        "Cancer Research Using Machine Learning",
    )

    assert result is None


def test_rank_title_matches():
    from app.title_search import rank_title_matches

    papers = [
        Paper(id="1", title="Applications of Machine Learning in Cancer"),
        Paper(id="2", title="Machine Learning in Cancer"),
        Paper(id="3", title="Climate Change Research"),
        Paper(id="4", title="machine-learning in cancer"),
    ]

    results = rank_title_matches("Machine Learning in Cancer", papers)

    assert [(paper.id, match) for paper, match in results] == [
        ("2", "exact"),
        ("4", "normalized"),
        ("1", "partial"),
    ]


def test_rank_title_matches_empty_papers():
    from app.title_search import rank_title_matches

    results = rank_title_matches(
        "Machine Learning in Cancer",
        [],
    )

    assert results == []


def test_rank_title_matches_preserves_order_within_same_match_type():
    from app.title_search import rank_title_matches

    papers = [
        Paper(id="1", title="Applications of Machine Learning in Cancer"),
        Paper(id="2", title="Recent Advances in Machine Learning in Cancer"),
        Paper(id="3", title="Machine Learning in Cancer"),
    ]

    results = rank_title_matches(
        "Machine Learning in Cancer",
        papers,
    )

    assert [(paper.id, match) for paper, match in results] == [
        ("3", "exact"),
        ("1", "partial"),
        ("2", "partial"),
    ]


def test_search_titles_uses_all_sources(monkeypatch):
    from app import title_search

    async def fake_fetch_all_source_candidates(**kwargs):
        assert kwargs["title_only"] is True

        return {
            "combined_raw": [
                Paper(
                    id="1",
                    source="pubmed",
                    title="Machine Learning in Cancer",
                ),
                Paper(
                    id="2",
                    source="openalex",
                    title="Applications of Machine Learning in Cancer",
                ),
                Paper(
                    id="3",
                    source="crossref",
                    title="Climate Change Research",
                ),
            ],
            "source_counts": {
                "pubmed": 1,
                "openalex": 1,
                "crossref": 1,
            },
            "failed_sources": [],
        }

    monkeypatch.setattr(
        title_search,
        "fetch_all_source_candidates",
        fake_fetch_all_source_candidates,
        raising=False,
    )

    results = asyncio.run(
        title_search.search_titles(
            "Machine Learning in Cancer",
            candidate_n=100,
        )
    )

    assert [(paper.id, match) for paper, match in results.matches] == [
        ("1", "exact"),
        ("2", "partial"),
    ]


def test_search_titles_deduplicates_results(monkeypatch):
    from app import title_search

    async def fake_fetch_all_source_candidates(**kwargs):
        return {
            "combined_raw": [
                Paper(
                    id="pubmed-1",
                    source="pubmed",
                    title="Machine Learning in Cancer",
                    doi="10.1234/example",
                ),
                Paper(
                    id="openalex-1",
                    source="openalex",
                    title="Machine Learning in Cancer",
                    doi="10.1234/example",
                ),
            ],
            "source_counts": {
                "pubmed": 1,
                "openalex": 1,
            },
            "failed_sources": [],
        }

    monkeypatch.setattr(
        title_search,
        "fetch_all_source_candidates",
        fake_fetch_all_source_candidates,
    )

    results = asyncio.run(
        title_search.search_titles(
            "Machine Learning in Cancer",
            candidate_n=100,
        )
    )

    assert len(results.matches) == 1
    assert results.matches[0][1] == "exact"
    assert results.duplicates_removed == 1


def test_title_search_result_defaults():
    from app.title_search import TitleSearchResult

    result = TitleSearchResult(
        query="Machine Learning in Cancer"
    )

    assert result.query == "Machine Learning in Cancer"
    assert result.matches == []
    assert result.source_counts == {}
    assert result.failed_sources == []
    assert result.duplicates_removed == 0


def test_search_titles_returns_source_metadata(monkeypatch):
    from app import title_search

    async def fake_fetch_all_source_candidates(**kwargs):
        return {
            "combined_raw": [
                Paper(
                    id="1",
                    source="pubmed",
                    title="Machine Learning in Cancer",
                ),
            ],
            "source_counts": {
                "pubmed": 1,
                "openalex": 0,
            },
            "failed_sources": ["openalex"],
        }

    monkeypatch.setattr(
        title_search,
        "fetch_all_source_candidates",
        fake_fetch_all_source_candidates,
    )

    result = asyncio.run(
        title_search.search_titles(
            "Machine Learning in Cancer",
            candidate_n=100,
        )
    )

    assert isinstance(result, title_search.TitleSearchResult)
    assert result.query == "Machine Learning in Cancer"
    assert result.source_counts == {
        "pubmed": 1,
        "openalex": 0,
    }
    assert result.failed_sources == ["openalex"]
    assert result.duplicates_removed == 0
    assert [(paper.id, match) for paper, match in result.matches] == [
        ("1", "exact"),
    ]
