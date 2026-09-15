from dataclasses import dataclass
from typing import Literal

PaginationType = Literal["page", "cursor", "token", "snapshot"]


@dataclass(frozen=True)
class SearchModeCapabilities:
    pagination_type: PaginationType
    supported_sorts: tuple[str, ...]
    supports_previous: bool
    supports_last: bool
    supports_page_jump: bool
    supports_year_filter: bool
    supports_abstract_filter: bool
    supports_mesh_filter: bool
    max_result_window: int | None = None


@dataclass(frozen=True)
class SearchSourceCapabilities:
    source: str
    default_mode: str
    modes: dict[str, SearchModeCapabilities]


CONNECTOR_CAPABILITIES: dict[str, SearchSourceCapabilities] = {
    "all": SearchSourceCapabilities(
        source="all",
        default_mode="default",
        modes={
            "default": SearchModeCapabilities(
                pagination_type="snapshot",
                supported_sorts=("relevance", "date_desc", "date_asc"),
                supports_previous=True,
                supports_last=True,
                supports_page_jump=True,
                supports_year_filter=True,
                supports_abstract_filter=True,
                supports_mesh_filter=True,
            )
        },
    ),
    "pubmed": SearchSourceCapabilities(
        source="pubmed",
        default_mode="default",
        modes={
            "default": SearchModeCapabilities(
                pagination_type="page",
                supported_sorts=("relevance", "date_desc"),
                supports_previous=True,
                supports_last=True,
                supports_page_jump=True,
                supports_year_filter=True,
                supports_abstract_filter=True,
                supports_mesh_filter=True,
            )
        },
    ),
    "europe_pmc": SearchSourceCapabilities(
        source="europe_pmc",
        default_mode="default",
        modes={
            "default": SearchModeCapabilities(
                pagination_type="cursor",
                supported_sorts=("relevance",),
                supports_previous=True,
                supports_last=True,
                supports_page_jump=True,
                supports_year_filter=True,
                supports_abstract_filter=True,
                supports_mesh_filter=True,
            )
        },
    ),
    "openalex": SearchSourceCapabilities(
        source="openalex",
        default_mode="default",
        modes={
            "default": SearchModeCapabilities(
                pagination_type="page",
                supported_sorts=("relevance", "date_desc", "date_asc"),
                supports_previous=True,
                supports_last=True,
                supports_page_jump=True,
                supports_year_filter=True,
                supports_abstract_filter=False,
                supports_mesh_filter=False,
            )
        },
    ),
    "crossref": SearchSourceCapabilities(
        source="crossref",
        default_mode="default",
        modes={
            "default": SearchModeCapabilities(
                pagination_type="page",
                supported_sorts=("relevance", "date_desc", "date_asc"),
                supports_previous=True,
                supports_last=True,
                supports_page_jump=True,
                supports_year_filter=True,
                supports_abstract_filter=False,
                supports_mesh_filter=False,
            )
        },
    ),
    "doaj": SearchSourceCapabilities(
        source="doaj",
        default_mode="default",
        modes={
            "default": SearchModeCapabilities(
                pagination_type="page",
                supported_sorts=("relevance",),
                supports_previous=True,
                supports_last=True,
                supports_page_jump=True,
                supports_year_filter=True,
                supports_abstract_filter=True,
                supports_mesh_filter=False,
                max_result_window=1000,
            )
        },
    ),
    "semantic_scholar": SearchSourceCapabilities(
        source="semantic_scholar",
        default_mode="relevance",
        modes={
            "relevance": SearchModeCapabilities(
                pagination_type="page",
                supported_sorts=("relevance",),
                supports_previous=True,
                supports_last=False,
                supports_page_jump=False,
                supports_year_filter=True,
                supports_abstract_filter=True,
                supports_mesh_filter=False,
                max_result_window=1000,
            ),
            "bulk": SearchModeCapabilities(
                pagination_type="token",
                supported_sorts=("date_desc", "date_asc"),
                supports_previous=True,
                supports_last=False,
                supports_page_jump=False,
                supports_year_filter=True,
                supports_abstract_filter=True,
                supports_mesh_filter=False,
            ),
        },
    ),
}


def get_search_source_capabilities(source: str) -> SearchSourceCapabilities:
    return CONNECTOR_CAPABILITIES[source]


def get_search_mode_capabilities(
    source: str,
    mode: str | None = None,
) -> SearchModeCapabilities:
    connector = get_search_source_capabilities(source)
    resolved_mode = mode or connector.default_mode
    return connector.modes[resolved_mode]
