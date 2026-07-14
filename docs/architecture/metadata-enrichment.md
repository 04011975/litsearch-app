# Metadata Enrichment Architecture

## Goal

The metadata enrichment layer separates literature retrieval from external metadata augmentation.

Retrieval connectors remain responsible for discovering and normalizing papers. Enrichment providers add metadata to deduplicated `Paper` records without changing their retrieval identity.

## Pipeline

```text
Retrieval
    |
    v
Paper normalization
    |
    v
Deduplication
    |
    v
Metadata enrichment
    |
    v
Filtering and sorting
    |
    v
UI and export
```

Enrichment is performed after deduplication so that the same publication is not enriched multiple times through different retrieval sources.

## Core Components

### Paper Model

The `Paper` model contains both retrieval metadata and optional enrichment metadata.

Current enrichment-related fields:

- `mesh_terms`
- `concepts`
- `citation_count`
- `reference_count`
- `enrichment_sources`

The `source` field continues to represent the retrieval or canonical source of the record.

### EnrichmentProvider

Each provider implements a common asynchronous interface.

A provider:

- receives a `Paper`;
- performs metadata lookup;
- returns an `EnrichmentResult`;
- does not mutate the `Paper` directly.

### EnrichmentResult

An enrichment result contains:

- returned metadata values;
- provenance per metadata field;
- whether a reliable match was found.

### Merge Policy

All provider results are merged centrally.

Rules:

- existing scalar metadata is preserved;
- missing scalar metadata may be filled;
- list metadata is merged;
- list duplicates are removed case-insensitively;
- unsupported fields are ignored;
- identity fields such as `id`, `source`, `title`, and `doi` cannot be overwritten;
- provenance is recorded only for metadata that was actually added.

### Pipeline

The pipeline calls configured enrichment providers and applies the central merge policy.

The pipeline uses best-effort behavior:

- provider failures are logged;
- remaining providers continue;
- retrieval results are never discarded because enrichment failed.

### Cache Interface

The foundation defines a cache protocol independently of Redis.

Future providers may use positive and negative caching to reduce:

- repeated API calls;
- response latency;
- external API load;
- rate-limit exposure.

## Provenance

Enrichment provenance is stored separately from the retrieval source.

Example:

```python
paper.source = "crossref"

paper.mesh_terms = [
    "Breast Neoplasms",
    "Immunotherapy",
]

paper.enrichment_sources = {
    "mesh_terms": ["pubmed"],
}
```

This means that Crossref supplied the retrieved record, while PubMed supplied the MeSH metadata.

## Current Implementation Status

### Implemented

- enrichment package foundation;
- provider protocol;
- enrichment result model;
- centralized merge policy;
- best-effort pipeline;
- cache protocol;
- provenance fields in `Paper`;
- unit tests for merge and pipeline behavior.

### Not Yet Implemented

- PubMed MeSH provider;
- Redis cache implementation;
- All Sources runtime integration;
- enrichment UI;
- enrichment export columns;
- OpenAlex topic enrichment;
- OpenCitations enrichment.

## Planned Providers

### Initial Providers

1. PubMed MeSH
2. OpenAlex Topics / Concepts
3. OpenCitations citation metadata

### Possible Future Providers

- Europe PMC
- PubChem
- ChEMBL

## Design Constraints

The enrichment layer must:

- remain independent of retrieval connectors;
- preserve the retrieval source;
- never silently overwrite existing metadata;
- expose metadata provenance;
- tolerate unavailable external services;
- remain testable without live external APIs.