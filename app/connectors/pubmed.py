from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import asyncio
import json
import random
import re
import time
import xml.etree.ElementTree as ET

import httpx

# =========================================================
# Data model
# =========================================================

@dataclass(frozen=True)
class Paper:
    pmid: str
    title: str
    authors: str
    journal: str
    year: str
    abstract: str
    doi: str
    mesh_terms: list[str]
    url: str = ""   # optional (can be used by templates)


@dataclass(frozen=True)
class SearchPageResult:
    pmids: list[str]
    count: int
    webenv: str
    query_key: str


# =========================================================
# PubMed ESearch paging limit
# =========================================================

ESEARCH_MAX_PMIDS_PER_QUERY = 10_000


# =========================================================
# Simple TTL cache
# =========================================================

class TTLCache:
    def __init__(self, ttl_seconds: int = 300) -> None:
        self.ttl = ttl_seconds
        self._store: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        item = self._store.get(key)
        if not item:
            return None
        expires_at, value = item
        if time.time() > expires_at:
            self._store.pop(key, None)
            return None
        return value

    def set(self, key: str, value: Any) -> None:
        self._store[key] = (time.time() + self.ttl, value)


HISTORY_CACHE = TTLCache(ttl_seconds=900)   # 15 min
PAPER_CACHE = TTLCache(ttl_seconds=3600)   # 60 min


# =========================================================
# Helpers
# =========================================================

def _clean_api_key(api_key: str | None) -> str | None:
    """
    Prevents sending placeholders like 'xxx' which cause NCBI 400.
    NCBI API keys are typically long (often 30+ chars).
    """
    if not api_key:
        return None
    k = str(api_key).strip()
    if not k:
        return None
    if k.lower() in {"xxx", "xxxx", "changeme", "change-me", "your_key_here", "your-api-key"}:
        return None
    # Heuristic: too short = likely not a real key
    if len(k) < 16:
        return None
    return k


def _clean_tool(tool: str | None) -> str | None:
    if not tool:
        return None
    t = str(tool).strip()
    if not t:
        return None
    return t


def _clean_email(email: str | None) -> str | None:
    if not email:
        return None
    e = str(email).strip()
    if not e:
        return None
    # Accept only if it looks like an email; otherwise don't send it
    if "@" not in e or "." not in e:
        return None
    if e.lower() in {"you@example.com", "example@example.com"}:
        # also treat placeholders as "don’t send"
        return None
    return e


def _extract_year(pubdate: str) -> str:
    if not pubdate:
        return ""
    for token in pubdate.replace("-", " ").split():
        if len(token) == 4 and token.isdigit():
            return token
    return ""


def _safe_text(el: ET.Element | None) -> str:
    if el is None:
        return ""
    return "".join(el.itertext()).strip()


def _first_text(root: ET.Element, xpath: str) -> str:
    el = root.find(xpath)
    return _safe_text(el)


def _join_authors(article: ET.Element) -> str:
    authors: list[str] = []
    for a in article.findall(".//AuthorList/Author"):
        last = _first_text(a, "LastName")
        initials = _first_text(a, "Initials")
        fore = _first_text(a, "ForeName")
        if last and initials:
            authors.append(f"{last} {initials}")
        elif last and fore:
            authors.append(f"{last} {fore}")
        elif last:
            authors.append(last)
    return ", ".join(authors[:25])


_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F]")


def _safe_json_loads(text: str) -> dict:
    cleaned = _CONTROL_CHARS.sub("", text or "")
    return json.loads(cleaned, strict=False)


def build_pubmed_term(
    q: str,
    *,
    year_min: int | None = None,
    year_max: int | None = None,
    has_abstract: int = 0,
    mesh: str = "",
) -> str:
    """
    Builds a PubMed term that preserves Boolean syntax in 'q' and adds filters around it.

    mesh supports:
    - single term: "Neoplasms"
    - multi: "Neoplasms|Humans" or "Neoplasms,Humans"
    Multi-MeSH is combined as AND (narrowing refinement).
    """
    base = (q or "").strip()
    filters: list[str] = []

    if year_min is not None or year_max is not None:
        y1 = str(year_min) if year_min is not None else "1800"
        y2 = str(year_max) if year_max is not None else "3000"
        filters.append(f'("{y1}"[Date - Publication] : "{y2}"[Date - Publication])')

    if has_abstract:
        filters.append("hasabstract[text]")

    m = (mesh or "").strip()
    if m:
        parts = [p.strip() for p in re.split(r"[|,]+", m) if p.strip()]
        if len(parts) == 1:
            filters.append(f'"{parts[0]}"[MeSH Terms]')
        else:
            mesh_expr = " AND ".join([f'"{t}"[MeSH Terms]' for t in parts])
            filters.append(f"({mesh_expr})")

    if not base and not filters:
        return ""

    if base and filters:
        return f"({base}) AND " + " AND ".join(filters)
    if base:
        return base
    return " AND ".join(filters)


async def _get_json(url: str, params: dict[str, Any], timeout: float = 30.0) -> dict:
    headers = {
        "User-Agent": "LitSearch/1.0",
        "Accept": "application/json,text/plain,*/*",
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.get(url, params=params, headers=headers)
        r.raise_for_status()
        try:
            return _safe_json_loads(r.text or "")
        except Exception as e:
            snippet = (r.text or "")[:600].replace("\n", " ").replace("\r", " ")
            raise RuntimeError(f"Could not parse NCBI response as JSON: {e}. Response starts: {snippet}")


# =========================================================
# PubMed: ESearch with History Server
# =========================================================

async def _esearch_create_history(
    term: str,
    *,
    sort: str = "relevance",
    api_key: str | None = None,
    tool: str | None = None,
    email: str | None = None,
) -> tuple[str, str, int]:
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"

    api_key = _clean_api_key(api_key)
    tool = _clean_tool(tool)
    email = _clean_email(email)

    params: dict[str, Any] = {
        "db": "pubmed",
        "term": term,
        "retmode": "json",
        "retmax": 0,
        "usehistory": "y",
        "sort": sort,
    }
    if api_key:
        params["api_key"] = api_key
    if tool:
        params["tool"] = tool
    if email:
        params["email"] = email

    data = await _get_json(url, params=params)
    es = data.get("esearchresult") or {}

    count_str = es.get("count") or "0"
    webenv = es.get("webenv") or ""
    query_key = es.get("querykey") or ""

    if not webenv or not query_key:
        # show a tiny bit more context
        raise RuntimeError(f"Missing history metadata (webenv/query_key empty). esearchresult keys: {list(es.keys())}")

    try:
        count = int(count_str)
    except Exception:
        count = 0

    return webenv, query_key, count


async def _esearch_fetch_page_from_history(
    webenv: str,
    query_key: str,
    *,
    retstart: int,
    retmax: int,
    sort: str = "relevance",
    api_key: str | None = None,
    tool: str | None = None,
    email: str | None = None,
) -> list[str]:
    if retstart >= ESEARCH_MAX_PMIDS_PER_QUERY:
        return []

    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"

    api_key = _clean_api_key(api_key)
    tool = _clean_tool(tool)
    email = _clean_email(email)

    params: dict[str, Any] = {
        "db": "pubmed",
        "retmode": "json",
        "retstart": retstart,
        "retmax": retmax,
        "webenv": webenv,
        "query_key": query_key,
        "sort": sort,
    }
    if api_key:
        params["api_key"] = api_key
    if tool:
        params["tool"] = tool
    if email:
        params["email"] = email

    data = await _get_json(url, params=params)
    es = data.get("esearchresult") or {}
    idlist = es.get("idlist") or []
    return [str(x) for x in idlist]


async def pubmed_search_page(
    term: str,
    *,
    max_results: int = 10,
    retstart: int = 0,
    sort: str = "relevance",
    api_key: str | None = None,
    tool: str | None = None,
    email: str | None = None,
) -> SearchPageResult:
    term = (term or "").strip()
    if not term:
        return SearchPageResult(pmids=[], count=0, webenv="", query_key="")

    cache_key = f"hist::{sort}::{term}"
    cached = HISTORY_CACHE.get(cache_key)

    if cached is None:
        webenv, query_key, count = await _esearch_create_history(
            term,
            sort=sort,
            api_key=api_key,
            tool=tool,
            email=email,
        )
        HISTORY_CACHE.set(cache_key, (webenv, query_key, count))
    else:
        webenv, query_key, count = cached

    pmids = await _esearch_fetch_page_from_history(
        webenv,
        query_key,
        retstart=retstart,
        retmax=max_results,
        sort=sort,
        api_key=api_key,
        tool=tool,
        email=email,
    )

    return SearchPageResult(pmids=pmids, count=count, webenv=webenv, query_key=query_key)


# =========================================================
# PubMed: EFetch details (XML)
# =========================================================

def _parse_pubmed_article_xml(xml_text: str) -> list[Paper]:
    root = ET.fromstring(xml_text)
    papers: list[Paper] = []

    for article in root.findall(".//PubmedArticle"):
        pmid = _first_text(article, ".//MedlineCitation/PMID")

        art = article.find(".//MedlineCitation/Article")
        if art is None:
            continue

        title = _first_text(art, "ArticleTitle")
        abstract = " ".join([_safe_text(x) for x in art.findall(".//Abstract/AbstractText")]).strip()

        journal = _first_text(art, ".//Journal/Title")
        pubdate = _first_text(art, ".//JournalIssue/PubDate/Year")
        if not pubdate:
            pubdate = _first_text(art, ".//JournalIssue/PubDate/MedlineDate")
        year = _extract_year(pubdate)

        authors = _join_authors(art)

        # --- DOI (robust) ---
        doi = ""

        # 1) Most common: ArticleIdList anywhere under PubmedArticle (incl. PubmedData)
        for aid in article.findall(".//ArticleIdList/ArticleId"):
            if (aid.attrib.get("IdType") or "").lower() == "doi":
                doi = (aid.text or "").strip()
                break

        # 2) Fallback: ELocationID in Article
        if not doi:
            for eloc in art.findall(".//ELocationID"):
                if (eloc.attrib.get("EIdType") or "").lower() == "doi":
                    doi = (eloc.text or "").strip()
                    break

        doi = (
            doi.replace("https://doi.org/", "")
               .replace("http://doi.org/", "")
               .replace("doi:", "")
               .strip()
        )

        mesh_terms: list[str] = []
        for mh in article.findall(".//MeshHeadingList/MeshHeading/DescriptorName"):
            t = (mh.text or "").strip()
            if t:
                mesh_terms.append(t)

        papers.append(
            Paper(
                pmid=pmid,
                title=title,
                authors=authors,
                journal=journal,
                year=year,
                abstract=abstract,
                doi=doi,
                mesh_terms=mesh_terms,
                url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "",
            )
        )

    return papers


# =========================
# Performance tuning knobs
# =========================

EFETCH_BATCH_SIZE = 20
EFETCH_MAX_CONCURRENCY = 3
EFETCH_DELAY_SECONDS = 0.34
EFETCH_MAX_RETRIES = 4


def _chunked(items: list[str], size: int) -> list[list[str]]:
    return [items[i:i + size] for i in range(0, len(items), size)]


async def _get_text_with_retry(
    client: httpx.AsyncClient,
    url: str,
    params: dict[str, Any],
    *,
    timeout: float = 45.0,
    max_retries: int = EFETCH_MAX_RETRIES,
) -> str:
    last_err: Exception | None = None

    headers = {"User-Agent": "LitSearch/1.0"}

    for attempt in range(max_retries):
        try:
            r = await client.get(url, params=params, headers=headers, timeout=timeout)

            if r.status_code in (429, 500, 502, 503, 504):
                raise httpx.HTTPStatusError(
                    f"Temporary HTTP {r.status_code}",
                    request=r.request,
                    response=r,
                )

            r.raise_for_status()
            return r.text

        except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPStatusError) as e:
            last_err = e
            base = 0.5 * (2 ** attempt)
            jitter = random.uniform(0.0, 0.25)
            await asyncio.sleep(base + jitter)

    raise RuntimeError(f"EFetch failed after {max_retries} retries: {last_err}")


async def pubmed_fetch_details(
    pmids: list[str],
    *,
    api_key: str | None = None,
    tool: str | None = None,
    email: str | None = None,
) -> list[Paper]:
    pmids = [str(p).strip() for p in (pmids or []) if str(p).strip()]
    if not pmids:
        return []

    api_key = _clean_api_key(api_key)
    tool = _clean_tool(tool)
    email = _clean_email(email)

    cached_papers: dict[str, Paper] = {}
    missing: list[str] = []

    for pmid in pmids:
        cached = PAPER_CACHE.get(f"paper::{pmid}")
        if cached is not None:
            cached_papers[pmid] = cached
        else:
            missing.append(pmid)

    if not missing:
        return [cached_papers[p] for p in pmids if p in cached_papers]

    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    sem = asyncio.Semaphore(EFETCH_MAX_CONCURRENCY)

    async def fetch_batch(client: httpx.AsyncClient, batch_pmids: list[str]) -> list[Paper]:
        async with sem:
            if EFETCH_DELAY_SECONDS > 0:
                await asyncio.sleep(EFETCH_DELAY_SECONDS)

            params: dict[str, Any] = {
                "db": "pubmed",
                "id": ",".join(batch_pmids),
                "retmode": "xml",
            }
            if api_key:
                params["api_key"] = api_key
            if tool:
                params["tool"] = tool
            if email:
                params["email"] = email

            xml_text = await _get_text_with_retry(client, url, params)
            return _parse_pubmed_article_xml(xml_text)

    batches = _chunked(missing, EFETCH_BATCH_SIZE)

    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(*(fetch_batch(client, b) for b in batches))

    fetched_papers = [p for batch in results for p in batch]
    fetched_by_id = {p.pmid: p for p in fetched_papers}

    all_by_id: dict[str, Paper] = dict(cached_papers)

    for pmid in missing:
        p = fetched_by_id.get(pmid)
        if p:
            PAPER_CACHE.set(f"paper::{pmid}", p)
            all_by_id[pmid] = p

    return [all_by_id[p] for p in pmids if p in all_by_id]
