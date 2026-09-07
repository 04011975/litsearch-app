from __future__ import annotations

import re
from collections import OrderedDict
from typing import Iterable

from app.models.paper import Paper


def normalize_doi(value: str | None) -> str | None:
    if not value:
        return None

    value = value.strip().lower()
    value = value.replace("https://doi.org/", "")
    value = value.replace("http://doi.org/", "")
    value = value.replace("doi:", "")
    value = value.strip(" .;,")

    return value or None


def normalize_text(value: str | None) -> str | None:
    if not value:
        return None

    value = value.lower()
    value = re.sub(r"[^\w\s]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()

    return value or None


def normalize_author(value: str | None) -> str | None:
    if not value:
        return None

    value = value.lower().strip()
    value = re.sub(r"[^\w\s-]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()

    return value or None


def first_author_key(paper: Paper) -> str | None:
    authors = getattr(paper, "authors", None)

    if not authors:
        return None

    if isinstance(authors, list):
        return normalize_author(str(authors[0])) if authors else None

    if isinstance(authors, str):
        first = authors.split(";")[0].split(",")[0]
        return normalize_author(first)

    return None


def paper_year(paper: Paper) -> str | None:
    year = getattr(paper, "year", None)
    if year:
        return str(year)

    date = getattr(paper, "publication_date", None) or getattr(
        paper, "published_date", None
    )
    if date:
        match = re.search(r"\b(19|20)\d{2}\b", str(date))
        if match:
            return match.group(0)

    return None


def metadata_dedup_key(paper: Paper) -> str | None:
    title = normalize_text(getattr(paper, "title", None))
    year = paper_year(paper)
    author = first_author_key(paper)

    if title and year and author:
        return f"title_author_year:{title}|{author}|{year}"

    if title and year:
        return f"title_year:{title}|{year}"

    if title:
        return f"title:{title}"

    return None


def strict_metadata_dedup_key(paper: Paper) -> str | None:
    title = normalize_text(getattr(paper, "title", None))
    year = paper_year(paper)
    author = first_author_key(paper)

    if title and year and author:
        return f"title_author_year:{title}|{author}|{year}"

    return None


def tolerant_metadata_base_key(paper: Paper) -> str | None:
    title = normalize_text(getattr(paper, "title", None))
    author = first_author_key(paper)

    if title and author:
        return f"title_author:{title}|{author}"

    return None


def numeric_paper_year(paper: Paper) -> int | None:
    value = paper_year(paper)

    if value is None:
        return None

    match = re.search(r"\b(19|20)\d{2}\b", str(value))

    if not match:
        return None

    return int(match.group(0))


def identifiers_conflict(a: Paper, b: Paper) -> bool:
    a_doi = normalize_doi(getattr(a, "doi", None))
    b_doi = normalize_doi(getattr(b, "doi", None))

    if a_doi and b_doi and a_doi != b_doi:
        return True

    a_pmid = getattr(a, "pmid", None)
    b_pmid = getattr(b, "pmid", None)

    if a_pmid and b_pmid and str(a_pmid).strip() != str(b_pmid).strip():
        return True

    a_pmcid = getattr(a, "pmcid", None)
    b_pmcid = getattr(b, "pmcid", None)

    if (
        a_pmcid
        and b_pmcid
        and str(a_pmcid).strip().lower() != str(b_pmcid).strip().lower()
    ):
        return True

    return False


def dedup_key(paper: Paper) -> str:
    doi = normalize_doi(getattr(paper, "doi", None))
    if doi:
        return f"doi:{doi}"

    pmid = getattr(paper, "pmid", None)
    if pmid:
        return f"pmid:{str(pmid).strip()}"

    pmcid = getattr(paper, "pmcid", None)
    if pmcid:
        return f"pmcid:{str(pmcid).strip().lower()}"

    metadata_key = metadata_dedup_key(paper)
    if metadata_key:
        return metadata_key

    source = getattr(paper, "source", "unknown")
    paper_id = getattr(paper, "id", None) or getattr(paper, "external_id", None)

    return f"fallback:{source}:{paper_id or id(paper)}"


def merge_values(primary, secondary):
    return primary if primary not in (None, "", [], {}) else secondary


def merge_sources(a_source, b_source) -> str:
    sources: list[str] = []

    for value in (a_source, b_source):
        if not value:
            continue

        if isinstance(value, list):
            candidates = value
        else:
            candidates = str(value).split("|")

        for source in candidates:
            source = str(source).strip()
            if source and source not in sources:
                sources.append(source)

    return "|".join(sources)


def paper_to_dict(paper: Paper) -> dict:
    if hasattr(paper, "model_dump"):
        return paper.model_dump()

    if hasattr(paper, "dict"):
        return paper.dict()

    return dict(getattr(paper, "__dict__", {}))


def merge_papers(primary: Paper, secondary: Paper) -> Paper:
    data = paper_to_dict(primary)
    secondary_data = paper_to_dict(secondary)

    for key, value in data.items():
        data[key] = merge_values(value, secondary_data.get(key))

    if "source" in data:
        data["source"] = merge_sources(
            getattr(primary, "source", None),
            getattr(secondary, "source", None),
        )

    try:
        return Paper(**data)
    except Exception:
        return primary


def deduplicate_papers(papers: Iterable[Paper]) -> tuple[list[Paper], int]:
    unique_by_key: OrderedDict[str, Paper] = OrderedDict()
    key_index: dict[str, str] = {}
    metadata_index: dict[str, str] = {}
    tolerant_metadata_index: dict[str, list[str]] = {}
    duplicates_removed = 0

    for paper in papers:
        key = dedup_key(paper)
        metadata_key = strict_metadata_dedup_key(paper)
        tolerant_key = tolerant_metadata_base_key(paper)

        matched_key = key_index.get(key)

        if matched_key is None and metadata_key:
            candidate_key = metadata_index.get(metadata_key)

            if candidate_key is not None:
                candidate = unique_by_key[candidate_key]

                if not identifiers_conflict(candidate, paper):
                    matched_key = candidate_key

        if matched_key is None and tolerant_key:
            paper_year_value = numeric_paper_year(paper)
            paper_doi = normalize_doi(getattr(paper, "doi", None))

            if paper_year_value is not None:
                for candidate_key in tolerant_metadata_index.get(tolerant_key, []):
                    candidate = unique_by_key[candidate_key]
                    candidate_year_value = numeric_paper_year(candidate)
                    candidate_doi = normalize_doi(getattr(candidate, "doi", None))

                    if candidate_year_value is None:
                        continue

                    if abs(candidate_year_value - paper_year_value) > 1:
                        continue

                    if bool(candidate_doi) == bool(paper_doi):
                        continue

                    if identifiers_conflict(candidate, paper):
                        continue

                    matched_key = candidate_key
                    break

        if matched_key is not None:
            merged = merge_papers(unique_by_key[matched_key], paper)
            unique_by_key[matched_key] = merged
            duplicates_removed += 1

            key_index[key] = matched_key
            key_index[dedup_key(merged)] = matched_key

            merged_metadata_key = strict_metadata_dedup_key(merged)
            if merged_metadata_key:
                metadata_index[merged_metadata_key] = matched_key

            merged_tolerant_key = tolerant_metadata_base_key(merged)
            if merged_tolerant_key:
                tolerant_metadata_index.setdefault(merged_tolerant_key, [])

                if matched_key not in tolerant_metadata_index[merged_tolerant_key]:
                    tolerant_metadata_index[merged_tolerant_key].append(matched_key)
        else:
            unique_by_key[key] = paper
            key_index[key] = key

            if metadata_key:
                metadata_index[metadata_key] = key

            if tolerant_key:
                tolerant_metadata_index.setdefault(tolerant_key, []).append(key)

    return list(unique_by_key.values()), duplicates_removed
