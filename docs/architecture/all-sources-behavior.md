# All Sources Behavior

## Oldest First Sorting

All Sources retrieval operates on a candidate pool retrieved from each source.

Pipeline:

1. Retrieve source candidates
2. Merge candidate sets
3. Deduplicate records
4. Apply sorting
5. Apply pagination

Implication:

Oldest-first sorting is performed after candidate retrieval and deduplication.

Therefore:

- All Sources oldest-first does not guarantee the globally oldest records available from each upstream source.
- Source-specific searches (e.g. OpenAlex oldest-first) may return older records than All Sources oldest-first.
- This is expected behavior and not considered a defect.

Rationale:

The All Sources pipeline is optimized for balanced cross-source retrieval and deduplication rather than exhaustive source-specific chronological retrieval.