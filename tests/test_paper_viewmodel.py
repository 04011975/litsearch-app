from app.main import _paper_to_dict
from app.models.paper import Paper


def test_doaj_full_text_without_pmcid_does_not_create_pmcid_link() -> None:
    paper = Paper(
        id="000122f776cb4f27b0f575971a4bed38",
        source="doaj",
        title="DOAJ paper with full text",
        has_full_text=True,
        pmcid=None,
    )

    result = _paper_to_dict(
        paper,
        source=paper.source,
    )

    assert "has_full_text" not in result
    assert "full_text_label" not in result
    assert "full_text_url" not in result


def test_valid_pmcid_creates_europe_pmc_full_text_link() -> None:
    paper = Paper(
        id="12345678",
        source="pubmed",
        title="PubMed paper with PMCID",
        has_full_text=True,
        pmcid="PMC1234567",
    )

    result = _paper_to_dict(
        paper,
        source=paper.source,
    )

    assert result["has_full_text"] is True
    assert result["full_text_label"] == "Full text (PMCID)"
    assert result["full_text_url"] == "https://europepmc.org/article/PMC/1234567"
