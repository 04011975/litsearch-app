# app/services/paper_service.py

from __future__ import annotations


def build_paper_detail_dict(
    paper,
    *,
    source: str,
    pid: str,
    paper_to_dict,
    pubmed_external_url,
    europe_pmc_external_url,
) -> dict:
    d = paper_to_dict(paper, source=source)

    if source == "pubmed" and pid.isdigit():
        d["external_url"] = pubmed_external_url(pid)
        d["url"] = d["external_url"]
    elif source == "europe_pmc":
        d["external_url"] = europe_pmc_external_url(paper)
        d["url"] = d["external_url"]
    elif source == "semantic_scholar":
        d["external_url"] = d.get("url") or f"https://www.semanticscholar.org/paper/{pid}"
        d["url"] = d["external_url"]
    else:
        d["external_url"] = d.get("url", "")

    return d