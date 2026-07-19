from app.connectors.opencitations import (
    _parse_count,
    normalize_doi,
)


def test_normalize_doi_accepts_plain_doi() -> None:
    assert normalize_doi("10.1000/Example") == "10.1000/example"


def test_normalize_doi_removes_doi_prefix() -> None:
    assert normalize_doi("doi:10.1000/Example") == "10.1000/example"


def test_normalize_doi_removes_https_url() -> None:
    assert normalize_doi("https://doi.org/10.1000/Example") == "10.1000/example"


def test_normalize_doi_rejects_empty_value() -> None:
    assert normalize_doi(None) is None
    assert normalize_doi("") is None


def test_normalize_doi_rejects_non_doi_identifier() -> None:
    assert normalize_doi("PMID:123456") is None


def test_parse_count_accepts_numeric_string() -> None:
    assert _parse_count([{"count": "34"}]) == 34


def test_parse_count_accepts_zero() -> None:
    assert _parse_count([{"count": "0"}]) == 0


def test_parse_count_rejects_empty_response() -> None:
    assert _parse_count([]) is None


def test_parse_count_rejects_invalid_count() -> None:
    assert _parse_count([{"count": "unknown"}]) is None


def test_parse_count_rejects_negative_count() -> None:
    assert _parse_count([{"count": "-1"}]) is None
