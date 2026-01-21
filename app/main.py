from __future__ import annotations

import csv
import io
import math
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, List

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from .connectors.pubmed import Paper, build_pubmed_term, pubmed_fetch_details, pubmed_search_page
from .connectors.europe_pmc import europe_pmc_search, europe_pmc_fetch_detail

# =========================================================
# Configuration
# =========================================================

load_dotenv()

APP_VERSION = "0.1.0"

NCBI_API_KEY = os.getenv("NCBI_API_KEY") or None
TOOL_NAME = os.getenv("TOOL_NAME") or "LitSearch"
CONTACT_EMAIL = os.getenv("CONTACT_EMAIL") or None

if not CONTACT_EMAIL:
    print(
        "⚠️ WARNING: CONTACT_EMAIL is not set. "
        "NCBI strongly recommends providing a contact email for PubMed API usage."
    )

BULK_EXPORT_LIMIT = 500
PUBMED_MAX_PAGEABLE_RESULTS = 10_000

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(
    title="LitSearch",
    version=APP_VERSION,
)

# =========================================================
# Helpers
# =========================================================

def _safe_int(s: str | None, default: int | None = 0) -> int | None:
    try:
        if s is None:
            return default
        s2 = str(s).strip()
        if s2 == "":
            return default
        return int(s2)
    except Exception:
        return default


def _normalize_mesh(mesh: str) -> str:
    """
    Accepts: "A, B | C"
    Stores:  "A|B|C" (order preserved, duplicates removed)
    """
    raw = (mesh or "").strip()
    if not raw:
        return ""
    parts = [p.strip() for p in re.split(r"[|,]+", raw) if p.strip()]
    seen: set[str] = set()
    out: list[str] = []
    for p in parts:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return "|".join(out)


def _mesh_list(mesh: str) -> list[str]:
    m = (mesh or "").strip()
    if not m:
        return []
    return [p.strip() for p in m.split("|") if p.strip()]


def _doi_url(doi: str) -> str:
    d = (doi or "").strip()
    if not d:
        return ""
    d = d.replace("https://doi.org/", "").replace("http://doi.org/", "")
    return f"https://doi.org/{d}"


def _europe_pmc_external_url(p: Any) -> str:
    """
    Accepts Paper or dict.
    Priority:
    1) PMCID -> https://europepmc.org/article/PMC/<id_without_PMC_prefix>
    2) PMID  -> https://europepmc.org/article/MED/<pmid>
    3) fallback: search by id
    """
    if isinstance(p, dict):
        pid = (p.get("pmid") or p.get("id") or "").strip()
        pmcid = (p.get("pmcid") or "").strip()
    else:
        pid = (getattr(p, "pmid", "") or "").strip()
        pmcid = (getattr(p, "pmcid", "") or "").strip()

    if pmcid:
        pmcid2 = pmcid.upper()
        pmcid2 = pmcid2[3:] if pmcid2.startswith("PMC") else pmcid2
        return f"https://europepmc.org/article/PMC/{pmcid2}"

    if pid.isdigit():
        return f"https://europepmc.org/article/MED/{pid}"

    if pid:
        return f"https://europepmc.org/search?query={pid}"

    return "https://europepmc.org/"


def _paper_to_dict(p: Paper) -> dict[str, Any]:
    """
    Template-friendly dict for both PubMed & Europe PMC paper objects.
    (We keep extra fields optional via getattr.)
    """
    doi = getattr(p, "doi", "") or ""
    pmcid = getattr(p, "pmcid", "") or ""
    url = getattr(p, "url", "") or ""

    d: dict[str, Any] = {
        "pmid": getattr(p, "pmid", "") or "",
        "title": getattr(p, "title", "") or "",
        "authors": getattr(p, "authors", "") or "",
        "journal": getattr(p, "journal", "") or "",
        "year": getattr(p, "year", "") or "",
        "abstract": getattr(p, "abstract", "") or "",
        "doi": doi,
        "mesh_terms": getattr(p, "mesh_terms", []) or [],
        # Common extra fields used by templates:
        "url": url,
        "pmcid": pmcid,
        "publisher_url": _doi_url(doi),  # used by your templates as "Publisher (DOI)"
    }

    # Optional full text badge (Europe PMC)
    has_full_text = bool(getattr(p, "has_full_text", False))
    if has_full_text or (pmcid and pmcid.upper().startswith("PMC")):
        d["has_full_text"] = True
        d["full_text_label"] = "Full text (PMCID)"
        # Best-effort: open the Europe PMC record for full text
        d["full_text_url"] = _europe_pmc_external_url(p)

    return d


def _map_sort(sort: str) -> str:
    # UI sort -> PubMed ESearch sort
    if sort == "year_desc":
        return "pub+date"
    return "relevance"


def _papers_to_csv(papers: List[Paper]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["ID", "Title", "Authors", "Journal", "Year", "DOI", "PMCID", "Full text", "MeSH terms", "URL"])
    for p in papers:
        writer.writerow(
            [
                getattr(p, "pmid", ""),
                getattr(p, "title", ""),
                getattr(p, "authors", ""),
                getattr(p, "journal", ""),
                getattr(p, "year", ""),
                getattr(p, "doi", ""),
                getattr(p, "pmcid", ""),
                "yes" if getattr(p, "has_full_text", False) else "",
                "; ".join(getattr(p, "mesh_terms", []) or []),
                getattr(p, "url", ""),
            ]
        )
    return buf.getvalue()


def _papers_to_ris(papers: List[Paper]) -> str:
    lines: list[str] = []
    for p in papers:
        authors = [a.strip() for a in (getattr(p, "authors", "") or "").split(",") if a.strip()]
        lines.append("TY  - JOUR")
        title = getattr(p, "title", "") or ""
        if title:
            lines.append(f"TI  - {title}")
        for a in authors:
            lines.append(f"AU  - {a}")
        journal = getattr(p, "journal", "") or ""
        if journal:
            lines.append(f"JO  - {journal}")
        year = getattr(p, "year", "") or ""
        if year:
            lines.append(f"PY  - {year}")
        doi = getattr(p, "doi", "") or ""
        if doi:
            lines.append(f"DO  - {doi}")
        abstract = getattr(p, "abstract", "") or ""
        if abstract:
            lines.append(f"AB  - {abstract}")
        lines.append(f"ID  - {getattr(p, 'pmid', '')}")
        pmcid = getattr(p, "pmcid", "") or ""
        if pmcid:
            lines.append(f"AN  - {pmcid}")
        lines.append("ER  -")
        lines.append("")
    return "\n".join(lines)


def _extract_mesh_suggestions(papers: Iterable[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    for p in papers:
        terms = p.get("mesh_terms") or []
        if isinstance(terms, str):
            terms = [terms]
        for t in terms:
            t2 = str(t).strip()
            if t2:
                counter[t2] += 1
    return [{"term": term, "count": count} for term, count in counter.most_common(limit)]


def _pagination_limits_pubmed(total_count: int, n: int) -> tuple[int, int, bool]:
    n = max(1, n)
    total_pages_uncapped = max(1, math.ceil(total_count / n))
    max_pageable_pages = max(1, math.ceil(PUBMED_MAX_PAGEABLE_RESULTS / n))
    total_pages_capped = min(total_pages_uncapped, max_pageable_pages)
    return total_pages_uncapped, total_pages_capped, (total_pages_uncapped != total_pages_capped)


def _cap_page(page: int, total_pages: int) -> int:
    return max(1, min(page, max(1, total_pages)))


def _pubmed_cap_warning(total_count: int) -> str:
    return (
        f"Your search returned {total_count:,} records. "
        "Due to PubMed ESearch limitations, only the first 10,000 results can be paginated via the API. "
        "Please refine your query (e.g., add additional terms, restrict publication years, apply MeSH terms, "
        "or enable “Abstract only”)."
    )


def _fetch_europe_pmc_bulk(q: str, limit: int = BULK_EXPORT_LIMIT) -> List[Paper]:
    """
    Fetch up to 'limit' records from Europe PMC by paging.
    """
    limit = max(1, min(int(limit), BULK_EXPORT_LIMIT))
    page_size = 100
    page = 1
    out: list[Paper] = []

    while len(out) < limit:
        n = min(page_size, limit - len(out))
        papers, _total = europe_pmc_search(q, page=page, n=n)
        if not papers:
            break
        out.extend(papers)
        page += 1

    return out


# =========================================================
# Routes
# =========================================================

@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/search")

from fastapi.responses import Response

@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)

@app.get("/search", response_class=HTMLResponse)
async def search(
    request: Request,
    q: str = Query("", description="Query"),
    source: str = Query("pubmed", pattern="^(pubmed|europe_pmc)$"),
    n: int = Query(10, ge=1, le=50),
    page: int = Query(1, ge=1),
    sort: str = Query("relevance"),
    year_min: str = Query(""),
    year_max: str = Query(""),
    has_abstract: int = Query(0, ge=0, le=1),
    mesh: str = Query(""),
):
    mesh = _normalize_mesh(mesh)

    papers: list[dict[str, Any]] = []
    mesh_suggestions: list[dict[str, Any]] = []
    warning: str | None = None
    error: str | None = None

    try:
        # --------------------------
        # Europe PMC
        # --------------------------
        if source == "europe_pmc":
            if not (q or "").strip():
                return templates.TemplateResponse(
                    "results.html",
                    {
                        "request": request,
                        "q": q,
                        "source": source,
                        "n": n,
                        "page": 1,
                        "sort": sort,
                        "year_min": year_min,
                        "year_max": year_max,
                        "has_abstract": has_abstract,
                        "mesh": mesh,  # UI keeps it; not applied to Europe PMC query
                        "mesh_list": _mesh_list(mesh),
                        "papers": [],
                        "mesh_suggestions": [],
                        "total_count": 0,
                        "total_pages": 1,
                        "bulk_limit": BULK_EXPORT_LIMIT,
                        "error": None,
                        "warning": None,
                    },
                )

            ep_papers, total_count = europe_pmc_search(q, page=page, n=n)
            total_pages = max(1, math.ceil(max(0, total_count) / max(1, n)))
            page = _cap_page(page, total_pages)

            papers = [_paper_to_dict(p) for p in ep_papers]
            for d in papers:
                d["external_url"] = _europe_pmc_external_url(d)
                # keep url consistent for template "Open in Europe PMC"
                d["url"] = d.get("external_url", "") or d.get("url", "")

            return templates.TemplateResponse(
                "results.html",
                {
                    "request": request,
                    "q": q,
                    "source": source,
                    "n": n,
                    "page": page,
                    "sort": sort,
                    "year_min": year_min,
                    "year_max": year_max,
                    "has_abstract": has_abstract,
                    "mesh": mesh,
                    "mesh_list": _mesh_list(mesh),
                    "papers": papers,
                    "mesh_suggestions": [],
                    "total_count": total_count,
                    "total_pages": total_pages,
                    "bulk_limit": BULK_EXPORT_LIMIT,
                    "error": None,
                    "warning": None,
                },
            )

        # --------------------------
        # PubMed (default)
        # --------------------------
        year_min_i = _safe_int(year_min, None)
        year_max_i = _safe_int(year_max, None)

        term = build_pubmed_term(
            q,
            year_min=year_min_i,
            year_max=year_max_i,
            has_abstract=has_abstract,
            mesh=mesh,
        )

        if not term:
            return templates.TemplateResponse(
                "results.html",
                {
                    "request": request,
                    "q": q,
                    "source": source,
                    "n": n,
                    "page": 1,
                    "sort": sort,
                    "year_min": year_min,
                    "year_max": year_max,
                    "has_abstract": has_abstract,
                    "mesh": mesh,
                    "mesh_list": _mesh_list(mesh),
                    "papers": [],
                    "mesh_suggestions": [],
                    "total_count": 0,
                    "total_pages": 1,
                    "bulk_limit": BULK_EXPORT_LIMIT,
                    "error": None,
                    "warning": None,
                },
            )

        pubmed_sort = _map_sort(sort)
        retstart = (page - 1) * n

        res = await pubmed_search_page(
            term,
            max_results=n,
            retstart=retstart,
            sort=pubmed_sort,
            api_key=NCBI_API_KEY,
            tool=TOOL_NAME,
            email=CONTACT_EMAIL,
        )

        total_count = int(res.count or 0)
        _, total_pages_capped, is_capped = _pagination_limits_pubmed(total_count, n)
        capped_page = _cap_page(page, total_pages_capped)

        if capped_page != page:
            url = (
                f"/search?q={q}"
                f"&source={source}"
                f"&n={n}"
                f"&page={capped_page}"
                f"&sort={sort}"
                f"&year_min={year_min}"
                f"&year_max={year_max}"
                f"&has_abstract={has_abstract}"
                f"&mesh={mesh}"
            )
            return RedirectResponse(url=url)

        if is_capped:
            warning = _pubmed_cap_warning(total_count)

        if retstart >= PUBMED_MAX_PAGEABLE_RESULTS:
            papers = []
            mesh_suggestions = []
        else:
            fetched = await pubmed_fetch_details(
                res.pmids,
                api_key=NCBI_API_KEY,
                tool=TOOL_NAME,
                email=CONTACT_EMAIL,
            )
            papers = [_paper_to_dict(p) for p in fetched]
            mesh_suggestions = _extract_mesh_suggestions(papers, limit=10)

        return templates.TemplateResponse(
            "results.html",
            {
                "request": request,
                "q": q,
                "source": source,
                "n": n,
                "page": capped_page,
                "sort": sort,
                "year_min": year_min,
                "year_max": year_max,
                "has_abstract": has_abstract,
                "mesh": mesh,
                "mesh_list": _mesh_list(mesh),
                "papers": papers,
                "mesh_suggestions": mesh_suggestions,
                "total_count": total_count,
                "total_pages": total_pages_capped,
                "bulk_limit": BULK_EXPORT_LIMIT,
                "error": error,
                "warning": warning,
            },
        )

    except Exception as e:
        error = str(e)
        return templates.TemplateResponse(
            "results.html",
            {
                "request": request,
                "q": q,
                "source": source,
                "n": n,
                "page": page,
                "sort": sort,
                "year_min": year_min,
                "year_max": year_max,
                "has_abstract": has_abstract,
                "mesh": mesh,
                "mesh_list": _mesh_list(mesh),
                "papers": [],
                "mesh_suggestions": [],
                "total_count": 0,
                "total_pages": 1,
                "bulk_limit": BULK_EXPORT_LIMIT,
                "error": error,
                "warning": None,
            },
        )


@app.get("/paper/{pmid}", response_class=HTMLResponse)
async def paper_detail_pubmed(request: Request, pmid: str):
    pmid = (pmid or "").strip()
    if not pmid.isdigit():
        raise HTTPException(status_code=400, detail="PMID must be numeric")

    papers = await pubmed_fetch_details(
        [pmid],
        api_key=NCBI_API_KEY,
        tool=TOOL_NAME,
        email=CONTACT_EMAIL,
    )
    paper = papers[0] if papers else None

    d = _paper_to_dict(paper) if paper else None
    if d:
        d["url"] = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"

    return templates.TemplateResponse(
        "paper.html",
        {
            "request": request,
            "pmid": pmid,
            "paper": d,
            "error": None if paper else "Article not found.",
            "source": "pubmed",  # IMPORTANT for correct "Open in PubMed" label
        },
    )


@app.get("/paper/europe_pmc/{pid}", response_class=HTMLResponse)
async def paper_detail_europe_pmc(request: Request, pid: str):
    pid = (pid or "").strip()
    if not pid:
        raise HTTPException(status_code=400, detail="ID is required")

    paper = europe_pmc_fetch_detail(pid)
    if not paper:
        raise HTTPException(status_code=404, detail="Not Found")

    d = _paper_to_dict(paper)
    d["url"] = _europe_pmc_external_url(paper)

    return templates.TemplateResponse(
        "paper.html",
        {
            "request": request,
            "pmid": pid,
            "paper": d,
            "error": None,
            "source": "europe_pmc",  # IMPORTANT for correct label
        },
    )


@app.get("/export/{fmt}")
async def export(
    fmt: str,
    request: Request,
    scope: str = Query("page", pattern="^(page|bulk)$"),
    bulk_limit: int = Query(BULK_EXPORT_LIMIT, ge=1, le=BULK_EXPORT_LIMIT),
):
    params = dict(request.query_params)

    q = params.get("q", "")
    source = params.get("source", "pubmed")
    n = int(_safe_int(params.get("n"), 10) or 10)
    page = int(_safe_int(params.get("page"), 1) or 1)
    sort = params.get("sort", "relevance")
    mesh = _normalize_mesh(params.get("mesh", "") or "")

    # --------------------------
    # Europe PMC export
    # --------------------------
    if source == "europe_pmc":
        if scope == "bulk":
            papers = _fetch_europe_pmc_bulk(q, limit=int(bulk_limit))
        else:
            ep_papers, _ = europe_pmc_search(q, page=page, n=n)
            papers = ep_papers

    # --------------------------
    # PubMed export
    # --------------------------
    else:
        term = build_pubmed_term(
            q,
            year_min=_safe_int(params.get("year_min"), None),
            year_max=_safe_int(params.get("year_max"), None),
            has_abstract=int(_safe_int(params.get("has_abstract"), 0) or 0),
            mesh=mesh,
        )

        if not term:
            raise HTTPException(status_code=400, detail="Query is empty")

        pubmed_sort = _map_sort(sort)

        if scope == "bulk":
            retstart = 0
            retmax = min(int(bulk_limit), PUBMED_MAX_PAGEABLE_RESULTS)
        else:
            retstart = (max(1, page) - 1) * n
            retmax = n

        if retstart >= PUBMED_MAX_PAGEABLE_RESULTS:
            papers = []
        else:
            res = await pubmed_search_page(
                term,
                max_results=retmax,
                retstart=retstart,
                sort=pubmed_sort,
                api_key=NCBI_API_KEY,
                tool=TOOL_NAME,
                email=CONTACT_EMAIL,
            )
            papers = await pubmed_fetch_details(
                res.pmids,
                api_key=NCBI_API_KEY,
                tool=TOOL_NAME,
                email=CONTACT_EMAIL,
            )

    if fmt == "csv":
        content = _papers_to_csv(papers)
        media = "text/csv"
        filename = "litsearch.csv"
    elif fmt == "ris":
        content = _papers_to_ris(papers)
        media = "application/x-research-info-systems"
        filename = "litsearch.ris"
    else:
        raise HTTPException(status_code=400, detail="Unsupported format")

    return StreamingResponse(
        io.StringIO(content),
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )