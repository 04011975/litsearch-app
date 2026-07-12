from __future__ import annotations

from typing import Any, List, Set

from app.enrichment.base import EnrichmentResult
from app.models.paper import Paper

LIST_FIELDS = frozenset(
    {
        "mesh_terms",
        "concepts",
    }
)

SCALAR_FIELDS = frozenset(
    {
        "abstract",
        "citation_count",
        "reference_count",
    }
)

SUPPORTED_ENRICHMENT_FIELDS = LIST_FIELDS | SCALAR_FIELDS


def _as_string_list(value: Any) -> List[str]:
    if value is None:
        return []

    if isinstance(value, str):
        values = [value]
    elif isinstance(value, (list, tuple, set)):
        values = list(value)
    else:
        return []

    return [str(item).strip() for item in values if str(item or "").strip()]


def merge_unique_strings(existing: Any, incoming: Any) -> List[str]:
    """Merge string collections while preserving order and casing."""

    merged: List[str] = []
    seen: Set[str] = set()

    for value in [
        *_as_string_list(existing),
        *_as_string_list(incoming),
    ]:
        key = value.casefold()

        if key in seen:
            continue

        seen.add(key)
        merged.append(value)

    return merged


def _is_empty(value: Any) -> bool:
    if value is None:
        return True

    if isinstance(value, str):
        return value.strip() == ""

    if isinstance(value, (list, tuple, set, dict)):
        return len(value) == 0

    return False


def merge_enrichment_result(
    paper: Paper,
    result: EnrichmentResult,
) -> Set[str]:
    """
    Merge one provider result into a Paper.

    Existing scalar metadata is preserved.
    List metadata is merged without case-insensitive duplicates.
    Unsupported and identity fields are ignored.
    """

    changed_fields: Set[str] = set()

    if not result.matched:
        return changed_fields

    for field_name, incoming_value in result.values.items():
        if field_name not in SUPPORTED_ENRICHMENT_FIELDS:
            continue

        existing_value = getattr(paper, field_name)

        if field_name in LIST_FIELDS:
            merged_value = merge_unique_strings(
                existing_value,
                incoming_value,
            )

            if merged_value != existing_value:
                setattr(paper, field_name, merged_value)
                changed_fields.add(field_name)

            continue

        if _is_empty(existing_value) and not _is_empty(incoming_value):
            setattr(paper, field_name, incoming_value)
            changed_fields.add(field_name)

    for field_name in changed_fields:
        incoming_sources = result.sources.get(field_name, [])

        if not incoming_sources:
            continue

        existing_sources = paper.enrichment_sources.get(field_name, [])
        merged_sources = merge_unique_strings(
            existing_sources,
            incoming_sources,
        )

        if merged_sources:
            paper.enrichment_sources[field_name] = merged_sources

    return changed_fields
