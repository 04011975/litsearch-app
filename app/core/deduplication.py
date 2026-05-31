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

    date = getattr(paper, "publication_date", None) or getattr(paper, "published_date", None)
    if date:
        match = re.search(r"\b(19|20)\d{2}\b", str(date))
        if match:
            return match.group(0)

    return None


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

    title = normalize_text(getattr(paper, "title", None))
    year = paper_year(paper)
    author = first_author_key(paper)

    if title and year and author:
        return f"title_author_year:{title}|{author}|{year}"

    if title and year:
        return f"title_year:{title}|{year}"

    if title:
        return f"title:{title}"

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
    duplicates_removed = 0

    for paper in papers:
        key = dedup_key(paper)

        if key in unique_by_key:
            unique_by_key[key] = merge_papers(unique_by_key[key], paper)
            duplicates_removed += 1
        else:
            unique_by_key[key] = paper

    return list(unique_by_key.values()), duplicates_removed