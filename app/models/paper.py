from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


def _norm_opt_str(x: Any) -> Optional[str]:
    if x is None:
        return None

    s = str(x).strip()
    if s == "" or s.lower() == "none":
        return None

    return s


def _norm_opt_int(x: Any) -> Optional[int]:
    if x is None:
        return None

    try:
        value = str(x).strip()
        if not value or value.lower() == "none":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


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

    citation_count: Optional[int] = None
    reference_count: Optional[int] = None

    enrichment_sources: Dict[str, List[str]] = field(default_factory=dict)

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
            mesh_terms = [
                mesh_term.strip()
                for mesh_term in mesh_terms.split(",")
                if mesh_term.strip()
            ]
        elif not isinstance(mesh_terms, list):
            mesh_terms = []

        concepts = d.get("concepts") or []
        if isinstance(concepts, str):
            concepts = [
                concept.strip() for concept in concepts.split(",") if concept.strip()
            ]
        elif not isinstance(concepts, list):
            concepts = []

        enrichment_sources_raw = d.get("enrichment_sources") or {}
        enrichment_sources: Dict[str, List[str]] = {}

        if isinstance(enrichment_sources_raw, dict):
            for metadata_field, sources in enrichment_sources_raw.items():
                field_name = str(metadata_field or "").strip()
                if not field_name:
                    continue

                if isinstance(sources, str):
                    normalized_sources = [
                        source.strip()
                        for source in sources.split(",")
                        if source.strip()
                    ]
                elif isinstance(sources, list):
                    normalized_sources = [
                        str(source).strip() for source in sources if str(source).strip()
                    ]
                else:
                    normalized_sources = []

                if normalized_sources:
                    enrichment_sources[field_name] = normalized_sources

        year = d.get("year")
        try:
            year = int(year) if year is not None and str(year).strip() != "" else None
        except (TypeError, ValueError):
            year = None

        return cls(
            id=pid,
            source=str(d.get("source") or "unknown").strip(),
            title=str(d.get("title") or "").strip(),
            authors=[str(author).strip() for author in authors if str(author).strip()],
            journal=str(d.get("journal") or "").strip(),
            year=year,
            publication_date=_norm_opt_str(d.get("publication_date")),
            abstract=_norm_opt_str(d.get("abstract")),
            doi=_norm_opt_str(d.get("doi")),
            pmcid=_norm_opt_str(d.get("pmcid")),
            url=_norm_opt_str(d.get("url")),
            mesh_terms=[
                str(mesh_term).strip()
                for mesh_term in mesh_terms
                if str(mesh_term).strip()
            ],
            concepts=[
                str(concept).strip() for concept in concepts if str(concept).strip()
            ],
            citation_count=_norm_opt_int(d.get("citation_count")),
            reference_count=_norm_opt_int(d.get("reference_count")),
            enrichment_sources=enrichment_sources,
            has_full_text=bool(d.get("has_full_text") or False),
        )
