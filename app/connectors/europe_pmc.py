from __future__ import annotations

from typing import Any
import re
import time

import httpx

from .pubmed import Paper

EUROPE_PMC_SEARCH_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
DEFAULT_TIMEOUT_SECONDS = 20.0


def _safe_int(v: Any) -> int:
    try:
        return int(v)
    except Exception:
        return 0


def _clean_year(v: Any) -> str:
    s = str(v or "").strip()
    m = re.search(r"\b(\d{4})\b", s)
    return m.group(1) if m else ""


def _best_identifier(it: dict[str, Any]) -> str:
    pmid = (it.get("pmid") or "").strip()
    if pmid:
        return pmid

    pmcid = (it.get("pmcid") or "").strip()
    if pmcid:
        return pmcid

    epmc_id = (it.get("id") or "").strip()
    return epmc_id


def europe_pmc_search(
    q: str,
    *,
    page: int = 1,
    n: int = 10,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    retries: int = 2,
    polite_delay_seconds: float = 0.0,
) -> tuple[list[Paper], int]:
    """
    Europe PMC search.
    Returns: (papers, total_hits)

    MeSH-termen worden niet consistent geleverd; daarom mesh_terms=[].
    """
    q = (q or "").strip()
    if not q:
        return [], 0

    page = max(1, int(page))
    n = max(1, min(int(n), 100))

    params = {
        "query": q,
        "format": "json",
        "page": page,
        "pageSize": n,
        "resultType": "core",
    }

    last_err: Exception | None = None

    for attempt in range(retries + 1):
        try:
            if polite_delay_seconds > 0:
                time.sleep(polite_delay_seconds)

            with httpx.Client(timeout=timeout_seconds, headers={"User-Agent": "LitSearch/1.0"}) as client:
                r = client.get(EUROPE_PMC_SEARCH_URL, params=params)
                r.raise_for_status()
                data = r.json()

            total = _safe_int(data.get("hitCount"))
            items = data.get("resultList", {}).get("result", []) or []

            papers: list[Paper] = []
            for it in items:
                title = (it.get("title") or "").strip()
                abstract = (it.get("abstractText") or "").strip()
                journal = (it.get("journalTitle") or it.get("journal") or "").strip()
                year = _clean_year(it.get("pubYear"))
                authors = (it.get("authorString") or "").strip()
                doi = (it.get("doi") or "").strip()

                identifier = _best_identifier(it)

                # Europe PMC canonical record URLs:
                pmid = (it.get("pmid") or "").strip()
                pmcid = (it.get("pmcid") or "").strip()

                if pmcid:
                    url = f"https://europepmc.org/articles/{pmcid}"
                elif pmid:
                    url = f"https://europepmc.org/article/MED/{pmid}"
                else:
                    # fallback: search by id
                    url = f"https://europepmc.org/search?query={identifier}" if identifier else "https://europepmc.org/"

                papers.append(
                    Paper(
                        pmid=identifier,  # can be PMID/PMCID/EPMC id
                        title=title,
                        authors=authors,
                        journal=journal,
                        year=year,
                        abstract=abstract,
                        doi=doi,
                        mesh_terms=[],
                        url=url,
                    )
                )

            return papers, total

        except Exception as e:
            last_err = e
            time.sleep(0.5 * (2 ** attempt))

    raise RuntimeError(f"Europe PMC search failed after {retries + 1} attempts: {last_err}")

    return templates.TemplateResponse(
    "paper.html",
    {"request": request, "pmid": pid, "paper": d, "error": None, "source": "europe_pmc"},
)



def europe_pmc_fetch_detail(
    pid: str,
    *,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    retries: int = 2,
) -> Paper | None:
    """
    Fetch 1 Europe PMC record by id (best-effort).
    Works with:
    - PMID (digits)
    - PMCID (starts with PMC)
    - Europe PMC id (fallback)
    """
    pid = (pid or "").strip()
    if not pid:
        return None

    # Europe PMC query fielding:
    if pid.isdigit():
        query = f"EXT_ID:{pid}"
    elif pid.upper().startswith("PMC"):
        query = f"PMCID:{pid}"
    else:
        query = f"ID:{pid}"

    papers, _ = europe_pmc_search(query, page=1, n=1, timeout_seconds=timeout_seconds, retries=retries)
    return papers[0] if papers else None
