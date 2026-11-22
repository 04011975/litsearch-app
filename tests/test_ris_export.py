
from app.core.ris_export import papers_to_ris
from app.models.paper import Paper


def test_ris_export_normalizes_abstract():
    paper = Paper(
        id="test-ris-1",
        source="openalex",
        title="Test RIS Export",
        authors=["Tester A"],
        journal="Test Journal",
        year=2024,
        abstract="Background\n<h4>Methods</h4>Study results",
        doi="10.1234/test-ris",
        pmcid=None,
        url="https://example.org/test-ris",
        mesh_terms=[],
        has_full_text=False,
    )

    result = papers_to_ris([paper])

    assert "TY  - JOUR" in result
    assert "TI  - Test RIS Export" in result
    assert "AU  - Tester A" in result
    assert "JO  - Test Journal" in result
    assert "PY  - 2024" in result
    assert "DO  - 10.1234/test-ris" in result
    assert "AB  - Background Methods Study results" in result
    assert "UR  - https://example.org/test-ris" in result
    assert "ID  - test-ris-1" in result
    assert "ER  -" in result

    assert "<h4>" not in result
    assert "Background\n<h4>" not in result
