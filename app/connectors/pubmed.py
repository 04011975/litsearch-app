from __future__ import annotations
import logging
logger = logging.getLogger("litsearch.connector.pubmed")
from dataclasses import dataclass
from typing import Any

import asyncio
import json
import random
import re
import time
import xml.etree.ElementTree as ET

import httpx
# ✅ Canonical Paper model (interface-contract)
# Zorg dat dit bestand bestaat: app/models/paper.py
from app.models.paper import Paper
import os
TOOL_NAME = os.getenv("TOOL_NAME", "LitSearch")
NCBI_API_KEY = os.getenv("NCBI_API_KEY") or None
CONTACT_EMAIL = os.getenv("CONTACT_EMAIL") or None
PUBMED_USER_AGENT = f"{TOOL_NAME}/1.0" + (f" (contact: {CONTACT_EMAIL})" if CONTACT_EMAIL else "")

# =========================================================
# Search result model (PubMed paging)
# =========================================================

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
# Helpers (clean values + parsing)
# =========================================================

def _clean_api_key(api_key: str | None) -> str | None:
    if not api_key:
        return None
    k = str(api_key).strip()
    if not k:
        return None
    if k.lower() in {"xxx", "xxxx", "changeme", "change-me", "your_key_here", "your-api-key"}:
        return None
    if len(k) < 16:
        return None
    return k

def _clean_tool(tool: str | None) -> str | None:
    if not tool:
        return None
    t = str(tool).strip()
    return t or None

def _clean_email(email: str | None) -> str | None:
    if not email:
        return None
    e = str(email).strip()
    if not e:
        return None
    if "@" not in e or "." not in e:
        return None
    if e.lower() in {"info@bibqprompt.com", "bibqprompt@bibqprompt"}:
        return None
    return e

def _extract_year(pubdate: str) -> int | None:
    if not pubdate:
        return None
    for token in pubdate.replace("-", " ").split():
        if len(token) == 4 and token.isdigit():
            try:
                return int(token)
            except Exception:
                return None
    return None

def _safe_text(el: ET.Element | None) -> str:
    if el is None:
        return ""
    return "".join(el.itertext()).strip()

def _first_text(root: ET.Element, xpath: str) -> str:
    el = root.find(xpath)
    return _safe_text(el)

def _join_authors_list(article: ET.Element) -> list[str]:
    out: list[str] = []
    for a in article.findall(".//AuthorList/Author"):
        last = _first_text(a, "LastName")
        initials = _first_text(a, "Initials")
        fore = _first_text(a, "ForeName")
        if last and initials:
            out.append(f"{last} {initials}")
        elif last and fore:
            out.append(f"{last} {fore}")
        elif last:
            out.append(last)
    return out[:25]

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F]")

def _safe_json_loads(text: str) -> dict:
    cleaned = _CONTROL_CHARS.sub("", text or "")
    return json.loads(cleaned, strict=False)

def _normalize_doi(doi: str) -> str:
    d = (doi or "").strip()
    if not d:
        return ""
    return (
        d.replace("https://doi.org/", "")
         .replace("http://doi.org/", "")
         .replace("doi:", "")
         .strip()
    )

def _extract_pmcid(article: ET.Element) -> str | None:
    # PMCID zit meestal in PubmedData/ArticleIdList als IdType="pmc"
    for aid in article.findall(".//ArticleIdList/ArticleId"):
        if (aid.attrib.get("IdType") or "").lower() in {"pmc", "pmcid"}:
            v = (aid.text or "").strip()
            if v:
                return v if v.upper().startswith("PMC") else f"PMC{v}"
    return None

def _best_journal_name(art: ET.Element) -> str:
    # 1) Volledige titel
    title = _first_text(art, ".//Journal/Title").strip()
    if title:
        return title
    # 2) MedlineTA (afkorting)
    medline_ta = _first_text(art, ".//Journal/MedlineTA").strip()
    if medline_ta:
        return medline_ta
    # 3) ISOAbbreviation
    iso = _first_text(art, ".//Journal/ISOAbbreviation").strip()
    return iso

def build_pubmed_term(
    q: str,
    *,
    year_min: int | None = None,
    year_max: int | None = None,
    has_abstract: int = 0,
    mesh: str = "",
    mesh_mode: str | None = None,
) -> str:
    base = (q or "").strip()
    filters: list[str] = []
    if year_min is not None or year_max is not None:
        y1 = str(year_min) if year_min is not None else "1800"
        y2 = str(year_max) if year_max is not None else "3000"
        filters.append(f'("{y1}"[Date - Publication] : "{y2}"[Date - Publication])')
    if has_abstract:
        filters.append("hasabstract[text]")
    terms, mode = _parse_mesh_terms(mesh, mesh_mode=mesh_mode)
    if terms:
        if len(terms) == 1:
            filters.append(f'"{terms[0]}"[MeSH Terms]')
        else:
            op = " AND " if mode == "and" else " OR "
            mesh_expr = op.join([f'"{t}"[MeSH Terms]' for t in terms])
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
        "User-Agent": PUBMED_USER_AGENT,
        "Accept": "application/json,text/plain,*/*",
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.get(url, params=params, headers=headers)
        r.raise_for_status()
        try:
            return _safe_json_loads(r.text or "")
        except Exception as e:
            snippet = (r.text or "")[:600].replace("\n", " ").replace("\r", " ")
            logger.exception(
                "pubmed_json_parse_failed url=%s params=%r err=%s snippet=%r",
                url, params, e, snippet
            )
            raise RuntimeError(
                f"Could not parse NCBI response as JSON: {e}. Response starts: {snippet}"
            )
        
def _extract_pubdate_text(article: ET.Element) -> str:
    def fmt_date(node: ET.Element | None) -> str:
        if node is None:
            return ""
        year = _first_text(node, "Year")
        month = _first_text(node, "Month")
        day = _first_text(node, "Day")
        medline = _first_text(node, "MedlineDate")

        if year and month and day:
            return f"{year} {month} {day}".strip()
        if year and month:
            return f"{year} {month}".strip()
        if year:
            return year
        if medline:
            return medline

        txt = _safe_text(node).strip()
        return txt or ""

    pub = article.find("./MedlineCitation/Article/Journal/JournalIssue/PubDate")
    txt = fmt_date(pub)
    if txt:
        return txt

    for path in [
        ".//BookDocument/ArticleDate",
        ".//BookDocument/DateRevised",
        ".//BookDocument/DateCompleted",
        ".//BookDocument/DateCreated",
        ".//BookDocument/PubDate",
        ".//BookDocument/Book/PubDate",
        ".//BookDocument/Book/BookPubDate",
    ]:
        txt = fmt_date(article.find(path))
        if txt:
            return txt

    return ""

def _fmt_pubdate_node(node: ET.Element | None) -> str:
    if node is None:
        return ""

    year = _first_text(node, "Year")
    month = _first_text(node, "Month")
    day = _first_text(node, "Day")
    medline = _first_text(node, "MedlineDate")

    if year and month and day:
        return f"{year} {month} {day}".strip()
    if year and month:
        return f"{year} {month}".strip()
    if year:
        return year
    if medline:
        return medline

    txt = _safe_text(node).strip()
    return txt or ""

def _extract_preferred_pubdate(art: ET.Element) -> tuple[str, int | None]:
    for node in art.findall("./ArticleDate"):
        pubdate = _fmt_pubdate_node(node)
        year = _extract_year(pubdate)
        if year:
            return pubdate, year

    pub_node = art.find("./Journal/JournalIssue/PubDate")
    pubdate = _fmt_pubdate_node(pub_node)
    year = _extract_year(pubdate)
    if year:
        return pubdate, year

    return "", None

def _parse_mesh_terms(mesh: str, mesh_mode: str | None = None) -> tuple[list[str], str]:
    raw = (mesh or "").strip()
    if not raw:
        return [], "or"
    mode = (mesh_mode or "").strip().lower()
    if mode not in {"and", "or"}:
        mode = "or"
    parts = [p.strip() for p in re.split(r"[|,]+", raw) if p.strip()]
    seen = set()
    terms: list[str] = []
    for p in parts:
        key = p.lower()
        if key not in seen:
            seen.add(key)
            terms.append(p)
    return terms, mode

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
    logger.info(
        "pubmed_esearch_create_history term=%r sort=%s",
        term,
        sort,
    )
    data = await _get_json(url, params=params)
    es = data.get("esearchresult") or {}
    count_str = es.get("count") or "0"
    webenv = es.get("webenv") or ""
    query_key = es.get("querykey") or ""
    if not webenv or not query_key:
        raise RuntimeError(
            f"Missing history metadata (webenv/query_key empty). esearchresult keys: {list(es.keys())}"
        )
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
    logger.info(
        "pubmed_esearch_fetch_page webenv=%s query_key=%s retstart=%s retmax=%s sort=%s",
        webenv,
        query_key,
        retstart,
        retmax,
        sort,
    )
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
    api_key = api_key or NCBI_API_KEY
    tool = tool or TOOL_NAME
    email = email or CONTACT_EMAIL
    if not term:
        return SearchPageResult(pmids=[], count=0, webenv="", query_key="")
    
    logger.info(
    "pubmed_search term=%r retstart=%s n=%s sort=%s",
    term,
    retstart,
    max_results,
    sort,
    )
    cache_key = f"hist::{sort}::{term}"
    cached = HISTORY_CACHE.get(cache_key)
    if cached is None:
        logger.debug("pubmed_search cache MISS term=%r sort=%s", term, sort)
        webenv, query_key, count = await _esearch_create_history(
            term,
            sort=sort,
            api_key=api_key,
            tool=tool,
            email=email,
        )
        HISTORY_CACHE.set(cache_key, (webenv, query_key, count))
    else:
        logger.debug("pubmed_search cache HIT term=%r sort=%s", term, sort)
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
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        logger.exception("pubmed_xml_parse_failed")
        return []
    papers: list[Paper] = []
    records = list(root.findall(".//PubmedArticle")) + list(root.findall(".//PubmedBookArticle"))
    logger.info(
        "PUBMED XML RECORD DEBUG pubmed_articles=%s pubmed_book_articles=%s",
        len(root.findall(".//PubmedArticle")),
        len(root.findall(".//PubmedBookArticle")),
    )
    for article in records:
        try:
            pmid = _first_text(article, "./MedlineCitation/PMID") or _first_text(article, ".//PMID")
            art = article.find("./MedlineCitation/Article")
            book = article.find("./BookDocument")
            is_book_record = book is not None
            title = ""
            abstract = None
            journal = ""
            authors_list: list[str] = []
            year = None
            pubdate = ""
            if art is not None:
                title = _first_text(art, "ArticleTitle") or ""
                abstract_txt = " ".join(_safe_text(x) for x in art.findall(".//Abstract/AbstractText")).strip()
                abstract = abstract_txt or None
                journal = _best_journal_name(art) or ""

                pubdate, year = _extract_preferred_pubdate(art)

                authors_list = _join_authors_list(art)

                authors_list = _join_authors_list(art)
            elif book is not None:
                title = _first_text(book, "ArticleTitle") or _first_text(book, "BookTitle") or ""
                abstract_txt = " ".join(_safe_text(x) for x in book.findall(".//Abstract/AbstractText")).strip()
                abstract = abstract_txt or None
                journal = (
                    _first_text(article, ".//Book/BookTitle")
                    or _first_text(article, ".//CollectionTitle")
                    or "Book / Chapter"
                )
                pubdate = _extract_pubdate_text(article)
                year = _extract_year(pubdate)
                authors_list = _join_authors_list(article)
            else:
                continue
            doi = ""
            for aid in article.findall(".//ArticleIdList/ArticleId"):
                if (aid.attrib.get("IdType") or "").lower() == "doi":
                    doi = (aid.text or "").strip()
                    break
            if not doi:
                for eloc in article.findall(".//ELocationID"):
                    if (eloc.attrib.get("EIdType") or "").lower() == "doi":
                        doi = (eloc.text or "").strip()
                        break
            doi_out = _normalize_doi(doi) or None
            pmcid = _extract_pmcid(article)
            has_full_text = bool(pmcid)
            mesh_terms: list[str] = []
            for mh in article.findall(".//MeshHeadingList/MeshHeading/DescriptorName"):
                t = (mh.text or "").strip()
                if t:
                    mesh_terms.append(t)
            logger.info(
                "PUBMED RECORD DEBUG pmid=%s title=%r pubdate=%r year=%r",
                pmid,
                title[:80],
                pubdate,
                year,
            )
            if is_book_record and journal in {
                "GeneReviews®",
                "LiverTox: Clinical and Research Information on Drug-Induced Liver Injury",
                "Assay Guidance Manual",
                "Medical Genetics Summaries",
                "ASTP Health IT Data Brief",
            }:
                logger.warning(
                    "BOOK-LIKE RECORD DEBUG pmid=%s title=%r journal=%r pubdate=%r year=%r",
                    pmid,
                    title[:80],
                    journal,
                    pubdate,
                    year,
                )
                logger.info(
                    "HIDING MISLEADING BOOK-RECORD DATE pmid=%s journal=%r pubdate=%r year=%r",
                    pmid,
                    journal,
                    pubdate,
                    year,
                )
                year = None
                pubdate = ""

            papers.append(
                Paper(
                    id=pmid,
                    source="pubmed",
                    title=title,
                    authors=authors_list,
                    journal=journal,
                    year=year,
                    publication_date=pubdate or None,
                    abstract=abstract,
                    mesh_terms=mesh_terms,
                    doi=doi_out,
                    url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                    pmcid=pmcid,
                    has_full_text=has_full_text,
                )
            )
        except Exception:
            logger.exception("pubmed_record_parse_failed")
            continue
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
    headers = {"User-Agent": PUBMED_USER_AGENT}
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
    api_key = api_key or NCBI_API_KEY
    tool = tool or TOOL_NAME
    email = email or CONTACT_EMAIL
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
            parsed = _parse_pubmed_article_xml(xml_text)
            logger.warning(
                "PUBMED EFETCH BATCH DEBUG requested=%s parsed=%s batch_pmids=%r",
                len(batch_pmids),
                len(parsed),
                batch_pmids,
            )
            return parsed   
    batches = _chunked(missing, EFETCH_BATCH_SIZE)
    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(*(fetch_batch(client, b) for b in batches))
        fetched_papers = [p for batch in results for p in batch]
        fetched_by_id = {p.id: p for p in fetched_papers}
        requested_set = set(missing)
        fetched_set = set(fetched_by_id.keys())
        if fetched_set != requested_set:
            logger.warning(
                "PUBMED EFETCH SET MISMATCH requested=%s fetched=%s missing_ids=%r extra_ids=%r",
                len(requested_set),
                len(fetched_set),
                sorted(requested_set - fetched_set)[:10],
                sorted(fetched_set - requested_set)[:10],
            )
        all_by_id: dict[str, Paper] = dict(cached_papers)
        # batch-resultaten opslaan
        for pmid in missing:
            p = fetched_by_id.get(pmid)
            if p:
                PAPER_CACHE.set(f"paper::{pmid}", p)
                all_by_id[pmid] = p
        # fallback: ontbrekende PMIDs één voor één ophalen
        still_missing = [pmid for pmid in missing if pmid not in all_by_id]
        if still_missing:
            logger.warning(
                "pubmed_fetch_details batch returned fewer records than requested; retrying individually missing=%r",
                still_missing,
            )
            for pmid in still_missing:
                try:
                    single_results = await fetch_batch(client, [pmid])
                    if single_results:
                        p = single_results[0]
                        PAPER_CACHE.set(f"paper::{pmid}", p)
                        all_by_id[pmid] = p
                except Exception:
                    logger.exception("pubmed_fetch_details single fallback failed pmid=%s", pmid)
    return [all_by_id[p] for p in pmids if p in all_by_id]

__all__ = ["Paper", "SearchPageResult", "build_pubmed_term", "pubmed_search_page", "pubmed_fetch_details"]
