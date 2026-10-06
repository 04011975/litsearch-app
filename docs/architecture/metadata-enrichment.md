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
Search / deduplication / filtering / sorting
    |
    v
Search results
    |
    v
Paper detail retrieval
    |
    v
Metadata enrichment
    |
    v
Paper detail UI
```

In the current v0.6.0 runtime, metadata enrichment is applied to paper detail requests rather than to the complete search result set. This keeps enrichment separate from primary retrieval and avoids enriching every candidate returned during search.

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
- best-effort enrichment pipeline;
- cache protocol;
- provenance fields in `Paper`;
- PubMed MeSH enrichment provider;
- OpenCitations enrichment provider;
- citation and reference count enrichment through OpenCitations;
- paper-detail runtime integration;
- enrichment metadata display on paper detail pages;
- unit tests for merge, pipeline, and provider behavior.

### Not Yet Implemented

- Redis-backed enrichment cache implementation;
- All Sources bulk enrichment;
- enrichment export columns;
- OpenAlex topic enrichment;
- PubChem enrichment;
- ChEMBL enrichment.

## Enrichment Providers

### Implemented Enrichment Providers

1. PubMed MeSH
2. OpenCitations citation metadata

### Possible Future Enrichment Providers

- OpenAlex Topics / Concepts
- Europe PMC metadata enrichment
- PubChem
- ChEMBL

OpenAlex and Europe PMC are already implemented as primary literature retrieval sources. Their inclusion above refers only to possible future use as metadata enrichment providers.

## Design Constraints

The enrichment layer must:

- remain independent of retrieval connectors;
- preserve the retrieval source;
- never silently overwrite existing metadata;
- expose metadata provenance;
- tolerate unavailable external services;
- remain testable without live external APIs.