# app/core/normalize.py

from __future__ import annotations

import re
from typing import Any

from app.models.paper import Paper


def normalize_doi(value: Any) -> str:
    doi = str(value or "").strip().lower()

    doi = doi.replace("https://doi.org/", "")
    doi = doi.replace("http://doi.org/", "")
    doi = doi.replace("doi:", "")
    doi = doi.strip(" .,/")

    return doi


def normalize_title(value: Any) -> str:
    title = str(value or "").strip()
    title = re.sub(r"\s+", " ", title)
    return title


def normalize_authors(value: Any) -> list[str]:
    if not value:
        return []

    if isinstance(value, list):
        authors = value
    else:
        authors = re.split(r";|,", str(value))

    cleaned = []
    for author in authors:
        a = str(author or "").strip()
        a = re.sub(r"\s+", " ", a)
        if a:
            cleaned.append(a)

    return cleaned


def normalize_year(value: Any) -> int | None:
    if value is None:
        return None

    text = str(value).strip()
    match = re.search(r"\b(18|19|20|21)\d{2}\b", text)

    if not match:
        return None

    try:
        return int(match.group(0))
    except Exception:
        return None


def normalize_paper(p: Paper, *, source: str | None = None) -> Paper:
    p.title = normalize_title(getattr(p, "title", ""))
    p.doi = normalize_doi(getattr(p, "doi", ""))
    p.authors = normalize_authors(getattr(p, "authors", []))
    p.year = normalize_year(getattr(p, "year", None))

    if source:
        p.source = source
    elif not getattr(p, "source", None):
        p.source = "unknown"

    # Dedup-key voorbereiding: DOI heeft hoogste prioriteit
    doi = getattr(p, "doi", "") or ""
    pid = getattr(p, "id", "") or ""

    if doi:
        p.id = doi
    elif pid:
        p.id = str(pid).strip()

    return p


def normalize_papers(papers: list[Paper], *, source: str | None = None) -> list[Paper]:
    return [normalize_paper(p, source=source) for p in papers]