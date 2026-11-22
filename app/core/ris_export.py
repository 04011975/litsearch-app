
import html
import re
from typing import List

from app.models.paper import Paper


def papers_to_ris(papers: List[Paper]) -> str:
    lines: list[str] = []

    for p in papers:
        pid = getattr(p, "id", "") or ""
        lines.append("TY  - JOUR")

        title = getattr(p, "title", "") or ""
        if title:
            lines.append(f"TI  - {title}")

        authors = getattr(p, "authors", []) or []
        if isinstance(authors, str):
            authors_list = [a.strip() for a in authors.split(",") if a.strip()]
        else:
            authors_list = [str(a).strip() for a in authors if str(a).strip()]

        for a in authors_list:
            lines.append(f"AU  - {a}")

        journal = getattr(p, "journal", "") or ""
        if journal:
            lines.append(f"JO  - {journal}")

        year_val = getattr(p, "year", None)
        if year_val is not None:
            lines.append(f"PY  - {year_val}")

        doi = getattr(p, "doi", None)
        if doi:
            lines.append(f"DO  - {doi}")

        abstract = getattr(p, "abstract", None)
        if abstract:
            abstract = html.unescape(str(abstract))
            abstract = re.sub(r"<[^>]+>", " ", abstract)
            abstract = " ".join(abstract.split())

            if abstract:
                lines.append(f"AB  - {abstract}")

        pmcid = getattr(p, "pmcid", "") or ""
        if pmcid:
            lines.append(f"AN  - {pmcid}")

        url = getattr(p, "url", "") or ""
        if url:
            lines.append(f"UR  - {url}")

        lines.append(f"ID  - {pid}")
        lines.append("ER  -")
        lines.append("")

    return "\n".join(lines)
