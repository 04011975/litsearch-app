# app/specializations/__init__.py
from __future__ import annotations

from typing import TypedDict, List, Dict


class SourceInfo(TypedDict):
    label: str
    role: str
    specialization: str
    strengths: List[str]
    limitations: List[str]


SOURCE_SPECIALIZATIONS: Dict[str, SourceInfo] = {
    "pubmed": {
        "label": "PubMed",
        "role": "Layer 1 – Primary literature search",
        "specialization": "Biomedical literature with structured indexing (MeSH)",
        "strengths": [
            "Controlled vocabulary indexing (MeSH)",
            "High curation standards",
            "Established biomedical authority"
        ],
        "limitations": [
            "Deep pagination limit (~10,000 records per query)"
        ],
    },
    "europe_pmc": {
        "label": "Europe PMC",
        "role": "Layer 1 – Primary literature search",
        "specialization": "Biomedical literature with extended coverage (including Open Access and preprints)",
        "strengths": [
            "Broad biomedical coverage",
            "Open Access signal integration",
            "Preprint inclusion"
        ],
        "limitations": [
            "Inconsistent MeSH indexing",
            "Cursor-based pagination model"
        ],
    },
    "openalex": {
        "label": "OpenAlex",
        "role": "Layer 1 – Primary literature search",
        "specialization": "Multidisciplinary database with open metadata and citation network",
        "strengths": [
            "Broad cross-disciplinary coverage",
            "Strong DOI-based metadata",
            "Citation network integration"
        ],
        "limitations": [
            "No controlled vocabulary (e.g., MeSH)",
            "Variable metadata depth across domains"
        ],
    },
    "semantic_scholar": {
        "label": "Semantic Scholar",
        "role": "Layer 1 – Primary literature search",
        "specialization": "Large scholarly database with AI-enhanced metadata and citation network",
        "strengths": [
            "Broad scholarly coverage",
            "Strong computer science and interdisciplinary visibility",
            "Citation graph integration",
            "AI-enhanced metadata"
        ],
        "limitations": [
            "No controlled vocabulary (e.g., MeSH)",
            "Metadata heterogeneity across records",
            "Chronological mode does not support direct page jumps or Last"
        ],
    },
}

def get_source_info(source: str) -> SourceInfo:
    s = (source or "").strip()
    return SOURCE_SPECIALIZATIONS.get(
        s,
        {
            "label": s or "Unknown",
            "role": "Unknown",
            "specialization": "",
            "strengths": [],
            "limitations": [],
        },
    )
