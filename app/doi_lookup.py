from __future__ import annotations

from dataclasses import dataclass, field

from app.identifiers import doi_matches, normalize_doi
from app.models.paper import Paper


@dataclass
class DoiLookupResult:
    """Result of an exact DOI lookup across literature sources."""

    doi: str
    paper: Paper | None = None
    found_in: list[str] = field(default_factory=list)
    failed_sources: list[str] = field(default_factory=list)


@dataclass
class PmidLookupResult:
    """Result of an exact PMID lookup across literature sources."""

    pmid: str
    paper: Paper | None = None
    found_in: list[str] = field(default_factory=list)
    failed_sources: list[str] = field(default_factory=list)


async def lookup_crossref_doi(doi: str) -> Paper | None:
    """Retrieve a Crossref paper only when its DOI matches exactly."""
    from app.connectors.crossref import crossref_fetch_detail
    from starlette.concurrency import run_in_threadpool

    normalized_doi = normalize_doi(doi)
    if normalized_doi is None:
        return None

    paper = await run_in_threadpool(
        crossref_fetch_detail,
        normalized_doi,
    )

    if paper is None or not doi_matches(normalized_doi, paper.doi):
        return None

    return paper


async def lookup_pubmed_doi(doi: str) -> Paper | None:
    """Retrieve a PubMed paper only when its DOI matches exactly."""
    from app.connectors.pubmed import (
        pubmed_fetch_details,
        pubmed_resolve_pmid_by_doi,
    )

    normalized_doi = normalize_doi(doi)
    if normalized_doi is None:
        return None

    pmid = await pubmed_resolve_pmid_by_doi(normalized_doi)
    if pmid is None:
        return None

    papers = await pubmed_fetch_details([pmid])

    for paper in papers:
        if doi_matches(normalized_doi, paper.doi):
            return paper

    return None


async def lookup_pubmed_pmid(pmid: str) -> Paper | None:
    """Retrieve a PubMed paper only when its PMID matches exactly."""
    from app.connectors.pubmed import pubmed_fetch_details

    normalized_pmid = str(pmid or "").strip()

    if not normalized_pmid or not normalized_pmid.isdigit():
        return None

    papers = await pubmed_fetch_details([normalized_pmid])

    for paper in papers:
        if paper.source == "pubmed" and str(paper.id) == normalized_pmid:
            return paper

    return None


async def lookup_europe_pmc_doi(doi: str) -> Paper | None:
    """Retrieve a Europe PMC paper only when its DOI matches exactly."""
    from starlette.concurrency import run_in_threadpool

    from app.connectors.europe_pmc import europe_pmc_search

    normalized_doi = normalize_doi(doi)
    if normalized_doi is None:
        return None

    papers, _, _ = await run_in_threadpool(
        europe_pmc_search,
        f"DOI:{normalized_doi}",
        n=10,
        retries=2,
    )

    for paper in papers:
        if doi_matches(normalized_doi, paper.doi):
            return paper

    return None



async def lookup_openalex_doi(doi: str) -> Paper | None:
    """Retrieve an OpenAlex work only when its DOI matches exactly."""
    import requests
    from starlette.concurrency import run_in_threadpool

    from app.connectors import openalex

    normalized_doi = normalize_doi(doi)
    if normalized_doi is None:
        return None

    def fetch():
        url = (
            f"{openalex.BASE_URL}{openalex.SEARCH_ENDPOINT}/"
            f"https://doi.org/{normalized_doi}"
        )

        params = (
            {"mailto": openalex.CONTACT_EMAIL}
            if openalex.CONTACT_EMAIL
            else None
        )

        response = requests.get(
            url,
            params=params,
            timeout=(10, 90),
            headers={"User-Agent": openalex._user_agent()},
        )

        if response.status_code == 404:
            return None

        response.raise_for_status()
        return response.json()

    work = await run_in_threadpool(fetch)

    if work is None:
        return None

    returned_doi = work.get("doi")
    if not doi_matches(normalized_doi, returned_doi):
        return None

    openalex_id = openalex._openalex_short_id(
        work.get("id") or ""
    )

    title = (
        work.get("title") or work.get("display_name") or ""
    ).strip()

    year_raw = work.get("publication_year")
    try:
        year = int(year_raw) if year_raw is not None else None
    except (TypeError, ValueError):
        year = None

    abstract = (work.get("abstract") or "").strip()
    if not abstract:
        inverted_index = work.get("abstract_inverted_index")
        if inverted_index:
            abstract = openalex._openalex_abstract_from_inverted_index(
                inverted_index
            )

    concepts = [
        str(concept.get("display_name")).strip()
        for concept in (work.get("concepts") or [])
        if concept.get("display_name")
    ]

    return Paper(
        id=openalex_id,
        source="openalex",
        title=title,
        authors=openalex._extract_authors(work),
        journal=openalex._journal_name(work),
        year=year,
        abstract=abstract or None,
        doi=normalized_doi,
        url=openalex._landing_url(work),
        mesh_terms=[],
        concepts=concepts,
        pmcid=None,
        has_full_text=False,
    )



async def lookup_doaj_doi(doi: str) -> Paper | None:
    """Retrieve a DOAJ article only when its DOI matches exactly."""
    from starlette.concurrency import run_in_threadpool

    from app.connectors.doaj import doaj_search

    normalized_doi = normalize_doi(doi)

    if normalized_doi is None:
        return None

    query = f'bibjson.identifier.id:"{normalized_doi}"'

    papers, _ = await run_in_threadpool(
        doaj_search,
        query,
        page=1,
        n=10,
    )

    for paper in papers:
        if doi_matches(normalized_doi, paper.doi):
            return paper

    return None



async def lookup_semantic_scholar_doi(doi: str) -> Paper | None:
    """Retrieve a Semantic Scholar paper by exact DOI."""
    from urllib.parse import quote

    from starlette.concurrency import run_in_threadpool

    from app.connectors import semantic_scholar as ss

    normalized_doi = normalize_doi(doi)

    if normalized_doi is None:
        return None

    def fetch() -> Paper | None:
        identifier = quote(
            f"DOI:{normalized_doi}",
            safe=":",
        )
        url = f"{ss.BASE_URL}/paper/{identifier}"

        try:
            data = ss._request(
                url,
                params={"fields": ss.DETAIL_FIELDS},
            )
        except ss.SemanticScholarError as exc:
            message = str(exc)

            if message.startswith("Semantic Scholar API error 404:"):
                return None

            raise

        paper = ss._to_paper(data)

        if not doi_matches(normalized_doi, paper.doi):
            return None

        return paper

    return await run_in_threadpool(fetch)



async def lookup_doi(doi: str) -> DoiLookupResult:
    """Look up an exact DOI across all supported literature sources."""
    normalized_doi = normalize_doi(doi)

    if normalized_doi is None:
        return DoiLookupResult(doi="")

    result = DoiLookupResult(doi=normalized_doi)

    sources = [
        ("pubmed", lookup_pubmed_doi),
        ("crossref", lookup_crossref_doi),
        ("europe_pmc", lookup_europe_pmc_doi),
        ("openalex", lookup_openalex_doi),
        ("doaj", lookup_doaj_doi),
        ("semantic_scholar", lookup_semantic_scholar_doi),
    ]

    for source_name, lookup_function in sources:
        try:
            paper = await lookup_function(normalized_doi)
        except Exception:
            result.failed_sources.append(source_name)
            continue

        if paper is None:
            continue

        if not doi_matches(normalized_doi, paper.doi):
            continue

        result.found_in.append(source_name)

        if result.paper is None:
            result.paper = paper

    return result


async def lookup_pmid(pmid: str) -> PmidLookupResult:
    """Look up an exact PMID across supported literature sources."""
    normalized_pmid = str(pmid or "").strip()

    if not normalized_pmid or not normalized_pmid.isascii() or not normalized_pmid.isdigit():
        return PmidLookupResult(pmid="")

    result = PmidLookupResult(pmid=normalized_pmid)

    try:
        paper = await lookup_pubmed_pmid(normalized_pmid)
    except Exception:
        result.failed_sources.append("pubmed")
        return result

    if paper is not None:
        if paper.source == "pubmed" and str(paper.id) == normalized_pmid:
            result.paper = paper
            result.found_in.append("pubmed")

    return result