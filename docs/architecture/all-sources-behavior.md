# All Sources Behavior

## Retrieval Model

All Sources provides federated retrieval across six primary literature sources:

- PubMed
- Europe PMC
- OpenAlex
- Semantic Scholar
- Crossref
- DOAJ

The shared All Sources pipeline retrieves candidates from the configured
sources concurrently and isolates individual source failures so that one
unavailable source does not necessarily fail the complete federated search.

The pipeline operates on a bounded candidate pool rather than exhaustively
retrieving every record available from each upstream source.

## Processing Pipeline

The central All Sources workflow is:

1. Retrieve candidates from the participating sources
2. Merge the source candidate sets
3. Deduplicate records across sources
4. Apply the requested All Sources ordering
5. Store the ordered result set as a Redis-backed snapshot
6. Apply pagination to the stable snapshot

The same centralized All Sources retrieval logic is used to avoid separate,
diverging implementations of federated retrieval behavior.

## Relevance Ordering

Upstream relevance scores are not directly comparable across literature
sources.

For relevance sorting, LitSearch therefore uses deterministic source-balanced
interleaving after deduplication rather than treating source-specific relevance
scores as a single global score.

This provides stable cross-source ordering while avoiding a false assumption
that relevance scores from different APIs have equivalent meaning.

## Snapshot Pagination

All Sources uses snapshot-based pagination.

A snapshot stores the ordered deduplicated result set together with metadata
needed to identify the search request. Subsequent pages can therefore paginate
over the same result set instead of repeating federated retrieval for every
page request.

Snapshots also prevent normal upstream result changes between page requests
from immediately changing the composition and ordering of an active result
set.

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