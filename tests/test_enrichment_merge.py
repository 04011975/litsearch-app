from app.enrichment.base import EnrichmentResult
from app.enrichment.merge import (
    merge_enrichment_result,
    merge_unique_strings,
)
from app.models.paper import Paper


def test_merge_unique_strings_is_case_insensitive():
    merged = merge_unique_strings(
        ["Breast Neoplasms", "Immunotherapy"],
        ["breast neoplasms", "Biomarkers"],
    )

    assert merged == [
        "Breast Neoplasms",
        "Immunotherapy",
        "Biomarkers",
    ]


def test_merge_enrichment_adds_list_values_and_provenance():
    paper = Paper(
        id="crossref-1",
        source="crossref",
        mesh_terms=["Breast Neoplasms"],
    )

    result = EnrichmentResult(
        matched=True,
        values={
            "mesh_terms": [
                "breast neoplasms",
                "Immunotherapy",
            ]
        },
        sources={"mesh_terms": ["pubmed"]},
    )

    changed_fields = merge_enrichment_result(paper, result)

    assert changed_fields == {"mesh_terms"}
    assert paper.mesh_terms == [
        "Breast Neoplasms",
        "Immunotherapy",
    ]
    assert paper.enrichment_sources == {"mesh_terms": ["pubmed"]}


def test_merge_enrichment_preserves_existing_scalar_value():
    paper = Paper(
        id="paper-1",
        source="crossref",
        abstract="Existing abstract",
    )

    result = EnrichmentResult(
        matched=True,
        values={"abstract": "Incoming abstract"},
        sources={"abstract": ["europe_pmc"]},
    )

    changed_fields = merge_enrichment_result(paper, result)

    assert changed_fields == set()
    assert paper.abstract == "Existing abstract"
    assert paper.enrichment_sources == {}


def test_merge_enrichment_adds_missing_scalar_value():
    paper = Paper(
        id="paper-1",
        source="crossref",
    )

    result = EnrichmentResult(
        matched=True,
        values={"citation_count": 42},
        sources={"citation_count": ["opencitations"]},
    )

    changed_fields = merge_enrichment_result(paper, result)

    assert changed_fields == {"citation_count"}
    assert paper.citation_count == 42
    assert paper.enrichment_sources == {"citation_count": ["opencitations"]}


def test_unmatched_result_does_not_modify_paper():
    paper = Paper(
        id="paper-1",
        source="crossref",
    )

    result = EnrichmentResult(
        matched=False,
        values={"concepts": ["Cancer"]},
        sources={"concepts": ["openalex"]},
    )

    changed_fields = merge_enrichment_result(paper, result)

    assert changed_fields == set()
    assert paper.concepts == []
    assert paper.enrichment_sources == {}


def test_unsupported_fields_are_ignored():
    paper = Paper(
        id="original-id",
        source="crossref",
        title="Original title",
    )

    result = EnrichmentResult(
        matched=True,
        values={
            "id": "changed-id",
            "source": "pubmed",
            "title": "Changed title",
        },
        sources={
            "id": ["provider"],
            "source": ["provider"],
            "title": ["provider"],
        },
    )

    changed_fields = merge_enrichment_result(paper, result)

    assert changed_fields == set()
    assert paper.id == "original-id"
    assert paper.source == "crossref"
    assert paper.title == "Original title"
    assert paper.enrichment_sources == {}
