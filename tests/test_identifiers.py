import pytest

from app.identifiers import normalize_doi

from app.identifiers import doi_matches


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("10.1000/xyz123", "10.1000/xyz123"),
        ("10.1000/XYZ123", "10.1000/xyz123"),
        ("10.123/legacy", "10.123/legacy"),
        ("10.1000/abc.def-123", "10.1000/abc.def-123"),
        ("https://doi.org/10.1000/XYZ123", "10.1000/xyz123"),
        ("http://doi.org/10.1000/xyz123", "10.1000/xyz123"),
        ("https://dx.doi.org/10.1000/xyz123", "10.1000/xyz123"),
        ("http://dx.doi.org/10.1000/xyz123", "10.1000/xyz123"),
        ("doi:10.1000/XYZ123", "10.1000/xyz123"),
        (" 10.1000/XYZ123 ", "10.1000/xyz123"),
        ("10.1000/abc(def)", "10.1000/abc(def)"),
        (None, None),
        ("", None),
        ("   ", None),
        ("12345678", None),
        ("PMID:123456", None),
        ("10.abc", None),
        ("10.1000", None),
        ("10.1000/", None),
        ("10.1000/abc def", None),
    ],
)
def test_normalize_doi(raw, expected):
    assert normalize_doi(raw) == expected


@pytest.mark.parametrize(
    ("requested", "returned", "expected"),
    [
        ("10.1000/xyz123", "10.1000/xyz123", True),
        ("10.1000/XYZ123", "10.1000/xyz123", True),
        (
            "https://doi.org/10.1000/xyz123",
            "10.1000/xyz123",
            True,
        ),
        ("10.1000/xyz123", "10.1000/different", False),
        ("10.1000/xyz123", None, False),
        ("10.1000/xyz123", "", False),
        ("invalid-doi", "invalid-doi", False),
        ("", "", False),
    ],
)
def test_doi_matches(requested, returned, expected):
    assert doi_matches(requested, returned) is expected
