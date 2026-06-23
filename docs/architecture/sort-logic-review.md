# Sort Logic Review

Date: 2026-06-23

## Findings

Sort normalization currently exists in multiple locations:

- app/main.py
- app/jobs/export_tasks.py

The following mappings are already shared through app/all_sources.py:

- all_sources_pubmed_sort()
- all_sources_openalex_sort()
- all_sources_semantic_scholar_sort_mode()

However export_tasks.py still contains additional sort alias normalization logic.

## Recommendation

Create a single shared sort-normalization module.

Possible target:

app/core/sorting.py

Candidate functions:

- normalize_sort()
- normalize_export_sort()
- pubmed_sort()
- openalex_sort()
- semantic_scholar_sort_mode()

## Priority

Medium

This is the remaining open refactoring item in the v0.5.0 roadmap.