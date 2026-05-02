from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional, List, Any, Dict


def _norm_opt_str(x: Any) -> Optional[str]:
    if x is None:
        return None
    s = str(x).strip()
    if s == "" or s.lower() == "none":
        return None
    return s


@dataclass
class Paper:
    id: str
    source: str = "unknown"

    title: str = ""
    authors: List[str] = field(default_factory=list)
    journal: str = ""
    year: Optional[int] = None
    publication_date: Optional[str] = None

    abstract: Optional[str] = None
    doi: Optional[str] = None
    pmcid: Optional[str] = None
    url: Optional[str] = None

    mesh_terms: List[str] = field(default_factory=list)
    has_full_text: bool = False

    concepts: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Paper":
        if not isinstance(d, dict):
            raise TypeError("Paper.from_dict expects a dict")

        pid = str(d.get("id") or d.get("pmid") or "").strip()
        if not pid:
            raise ValueError("Paper.from_dict: missing id")

        authors = d.get("authors") or []
        if isinstance(authors, str):
            authors = [a.strip() for a in authors.split(",") if a.strip()]
        elif not isinstance(authors, list):
            authors = []

        mesh_terms = d.get("mesh_terms") or []
        if isinstance(mesh_terms, str):
            mesh_terms = [m.strip() for m in mesh_terms.split(",") if m.strip()]
        elif not isinstance(mesh_terms, list):
            mesh_terms = []

        concepts = d.get("concepts") or []
        if isinstance(concepts, str):
            concepts = [c.strip() for c in concepts.split(",") if c.strip()]
        elif not isinstance(concepts, list):
            concepts = []

        year = d.get("year", None)
        try:
            year = int(year) if year is not None and str(year).strip() != "" else None
        except Exception:
            year = None

        return cls(
            id=pid,
            source=str(d.get("source") or "unknown").strip(),
            title=str(d.get("title") or "").strip(),
            authors=[str(a).strip() for a in authors if str(a).strip()],
            journal=str(d.get("journal") or "").strip(),
            year=year,
            publication_date=_norm_opt_str(d.get("publication_date")),
            abstract=_norm_opt_str(d.get("abstract")),
            doi=_norm_opt_str(d.get("doi")),
            pmcid=_norm_opt_str(d.get("pmcid")),
            url=_norm_opt_str(d.get("url")),
            mesh_terms=[str(m).strip() for m in mesh_terms if str(m).strip()],
            concepts=[str(c).strip() for c in concepts if str(c).strip()],
            has_full_text=bool(d.get("has_full_text") or False),
        )