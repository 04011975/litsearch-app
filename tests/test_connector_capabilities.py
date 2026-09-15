import pytest

from app.connector_capabilities import (
    CONNECTOR_CAPABILITIES,
    get_search_source_capabilities,
    get_search_mode_capabilities,
)


def test_all_expected_sources_are_registered():
    assert set(CONNECTOR_CAPABILITIES) == {
        "all",
        "pubmed",
        "europe_pmc",
        "openalex",
        "crossref",
        "doaj",
        "semantic_scholar",
    }


@pytest.mark.parametrize(
    ("source", "pagination_type"),
    [
        ("all", "snapshot"),
        ("pubmed", "page"),
        ("europe_pmc", "cursor"),
        ("openalex", "page"),
        ("crossref", "page"),
        ("doaj", "page"),
    ],
)
def test_default_pagination_types(source, pagination_type):
    capabilities = get_search_mode_capabilities(source)

    assert capabilities.pagination_type == pagination_type


def test_semantic_scholar_relevance_capabilities():
    capabilities = get_search_mode_capabilities(
        "semantic_scholar",
        "relevance",
    )

    assert capabilities.pagination_type == "page"
    assert capabilities.supported_sorts == ("relevance",)
    assert capabilities.supports_previous is True
    assert capabilities.supports_last is False
    assert capabilities.supports_page_jump is False
    assert capabilities.max_result_window == 1000


def test_semantic_scholar_bulk_capabilities():
    capabilities = get_search_mode_capabilities(
        "semantic_scholar",
        "bulk",
    )

    assert capabilities.pagination_type == "token"
    assert capabilities.supported_sorts == ("date_desc", "date_asc")
    assert capabilities.supports_previous is True
    assert capabilities.supports_last is False
    assert capabilities.supports_page_jump is False
    assert capabilities.supports_year_filter is True


def test_pubmed_oldest_first_is_not_declared_supported():
    capabilities = get_search_mode_capabilities("pubmed")

    assert "date_desc" in capabilities.supported_sorts
    assert "date_asc" not in capabilities.supported_sorts


def test_doaj_result_window_is_declared():
    capabilities = get_search_mode_capabilities("doaj")

    assert capabilities.max_result_window == 1000


def test_doaj_supports_relevance_sort_only():
    capabilities = get_search_mode_capabilities("doaj")

    assert capabilities.supported_sorts == ("relevance",)


def test_search_source_default_mode_is_used():
    connector = get_search_source_capabilities("semantic_scholar")
    capabilities = get_search_mode_capabilities("semantic_scholar")

    assert connector.default_mode == "relevance"
    assert capabilities is connector.modes["relevance"]


def test_europe_pmc_filter_capabilities():
    capabilities = get_search_mode_capabilities("europe_pmc")

    assert capabilities.supports_year_filter is True
    assert capabilities.supports_abstract_filter is True
    assert capabilities.supports_mesh_filter is True


def test_semantic_scholar_relevance_supports_local_filters():
    capabilities = get_search_mode_capabilities(
        "semantic_scholar",
        "relevance",
    )

    assert capabilities.supports_year_filter is True
    assert capabilities.supports_abstract_filter is True


def test_crossref_filter_capabilities():
    capabilities = get_search_mode_capabilities("crossref")

    assert capabilities.supports_year_filter is True
    assert capabilities.supports_abstract_filter is False
    assert capabilities.supports_mesh_filter is False
