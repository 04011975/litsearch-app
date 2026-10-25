from __future__ import annotations

from dataclasses import dataclass, field

from app.core.deduplication import normalize_text, deduplicate_papers

from app.all_sources import fetch_all_source_candidates


@dataclass
class TitleSearchResult:
    query: str
    matches: list[tuple] = field(default_factory=list)
    source_counts: dict[str, int] = field(default_factory=dict)
    failed_sources: list[str] = field(default_factory=list)
    duplicates_removed: int = 0


def classify_title_match(query: str, title: str) -> str | None:
    if not query or not title:
        return None

    if query == title:
        return "exact"

    normalized_query = normalize_text(query)
    normalized_title = normalize_text(title)

    if not normalized_query or not normalized_title:
        return None

    if normalized_query == normalized_title:
        return "normalized"

    query_words = normalized_query.split()
    title_words = normalized_title.split()

    query_length = len(query_words)

    for index in range(len(title_words) - query_length + 1):
        if title_words[index : index + query_length] == query_words:
            return "partial"

    return None


def rank_title_matches(query: str, papers: list) -> list:
    match_priority = {
        "exact": 0,
        "normalized": 1,
        "partial": 2,
    }

    matches = []

    for paper in papers:
        match = classify_title_match(query, paper.title)

        if match is not None:
            matches.append((paper, match))

    matches.sort(
        key=lambda item: match_priority[item[1]]
    )

    return matches


async def search_titles(
    query: str,
    *,
    candidate_n: int = 2000,
) -> TitleSearchResult:
    fetched = await fetch_all_source_candidates(
        q=query,
        candidate_n=candidate_n,
        title_only=True,
    )

    papers = fetched["combined_raw"]

    deduplicated_papers, duplicates_removed = deduplicate_papers(papers)

    matches = rank_title_matches(query, deduplicated_papers)

    return TitleSearchResult(
        query=query,
        matches=matches,
        source_counts=fetched["source_counts"],
        failed_sources=fetched["failed_sources"],
        duplicates_removed=duplicates_removed,
    )
