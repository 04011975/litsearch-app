LitSearch — Reproducible Literature Search Tool

Version: 0.4.0

Sources:
- PubMed
- Europe PMC
- OpenAlex
- Semantic Scholar

Architecture:
- FastAPI
- Redis
- ARQ
- Docker

## 1. Project Overview

LitSearch is a web-based literature search application designed to support reproducible, transparent, and multi-source academic literature retrieval through programmatic access to scientific literature databases.

The system currently integrates:

- PubMed (NCBI E-utilities)
- Europe PMC
- OpenAlex
- Semantic Scholar

LitSearch enables:

- structured literature searching
- deterministic query construction
- reproducible result retrieval
- export of bibliographic records
- cross-source deduplication
- multi-source comparison
- aggregated searching across multiple literature databases

LitSearch performs literature identification and retrieval only.

Interpretation, screening, quality assessment, evidence synthesis, and inclusion decisions remain the responsibility of the researcher.

## 2. Research Context & Motivation

Systematic, semi-systematic, and exploratory literature searches are central to academic research. However, many searches are still performed through graphical interfaces of bibliographic databases, which can make:
	• precise documentation difficult
	• reproduction of queries challenging
	• methodological transparency limited
	• comparison across literature sources cumbersome
LitSearch addresses these challenges by:
	• exposing all query parameters explicitly
	• enforcing deterministic query construction
	• supporting retrieval from multiple literature databases
	• providing cross-source aggregation and deduplication
	• enabling reproducible exports
	• supporting containerized and reproducible execution environments
By maintaining explicit search parameters, normalized record structures, and reproducible export workflows, LitSearch helps researchers document and reproduce literature searches more reliably.
The system supports literature identification and retrieval but does not automate study screening, critical appraisal, evidence synthesis, or interpretation of results. These activities remain the responsibility of the researcher.


## 3. System Architecture

LitSearch is implemented as a containerized web application designed for reproducible literature retrieval across multiple scientific literature databases.

Core Components
FastAPI backend (Python, asynchronous)
Jinja2 templates for result rendering
Redis for caching and background task coordination
ARQ worker for asynchronous export jobs
Docker / Docker Compose for reproducible deployment
Source-specific connector layer
Cross-source aggregation and deduplication pipeline
Architecture Overview

Search Flow

User Query
↓
FastAPI (main.py)
↓
Connector Layer
↓
PubMed / Europe PMC / OpenAlex / Semantic Scholar
↓
Canonical Paper Model
↓
Optional All Sources Aggregation
↓
Cross-Source Deduplication
↓
Global Sorting
↓
Template Rendering (Jinja2)

All Sources Processing

The All Sources workflow performs:

Candidate retrieval from multiple literature sources.
Merge of source-specific result sets.
Cross-source deduplication:
DOI matching
normalized title matching
Final result ordering:
Relevance → source-balanced interleaving
Most recent → publication year descending
Oldest first → publication year ascending
Pagination and export generation.
Export Flow (Asynchronous)

POST /export/job
↓
Redis Queue
↓
ARQ Worker (run_export_job)
↓
Batch Retrieval (API + Cache)
↓
Merge and Deduplication
↓
File Generation (CSV / RIS / XLSX)
↓
Download Endpoint

Caching Strategy

LitSearch uses Redis-based caching for:

paginated API responses
export batches
Europe PMC cursor states
export candidate retrieval

Two execution modes are supported:

Cold cache

API-bound retrieval
higher latency

Warm cache

cache-assisted retrieval
significantly faster execution
Design Principle

LitSearch uses a canonical Paper model to normalize metadata from all supported sources. This enables:

source-agnostic rendering
consistent export behavior
cross-source deduplication
unified filtering and sorting
reproducible search workflows

## 4. Data Sources

PubMed

Accessed through NCBI E-utilities (ESearch + EFetch).

Supported features:

free-text search
publication year filtering
abstract availability filtering
MeSH-based refinement

Limitations:

pagination limited to 10,000 results
Europe PMC

Europe PMC is used as a complementary biomedical source.

Features:

broader metadata coverage
open access indicators
full-text linking
cursor-based deep paging

Current behavior:

Europe PMC contributes relevance-ranked candidate records.
Final ordering in All Sources is applied centrally after source merging.
Cursor-based navigation supports deep retrieval.

Pagination:

cursor-based navigation
deep paging supported via cursor chaining
OpenAlex

OpenAlex is an open multidisciplinary scholarly database.

Advantages:

strong DOI metadata
broad interdisciplinary coverage
citation-rich metadata

Limitations:

no controlled vocabulary (e.g. MeSH)
Semantic Scholar

Semantic Scholar is integrated through the Graph API.

Supported modes:

Relevance mode
ranked retrieval
capped export depth
intended for relevance-oriented searches
Chronological mode
token-based bulk pagination
supports larger exports
used for Most recent and Oldest first sorting

Features:

rich metadata
author information
abstract retrieval
venue metadata

Limitations:

no controlled vocabulary
API latency may exceed other sources
direct last-page navigation is unavailable in chronological mode


## 5. Query Construction & Filtering

LitSearch constructs searches using explicit URL parameters. All search parameters remain visible and reproducible, enabling transparent documentation of search strategies.

Parameter	Description
source	literature source (PubMed, Europe PMC, OpenAlex, Semantic Scholar, or All Sources)
q	free-text search query
year_min	minimum publication year
year_max	maximum publication year
has_abstract	filter records with abstracts
mesh	MeSH refinement (PubMed only)
mesh_mode	AND / OR combination for MeSH terms
sort	relevance, most recent, or oldest first
page	pagination
n	records per page

Example:

/search?source=pubmed&q=type%202%20diabetes&year_min=2015&has_abstract=1&page=1

All parameters remain visible in the URL, enabling:

reproducible search execution
transparent documentation of search strategies
consistent export generation
repeatable retrieval across supported literature sources

## 6. All Sources Aggregation

LitSearch supports a multi-source search mode ("All Sources") that retrieves
candidate records from:

- PubMed
- Europe PMC
- OpenAlex
- Semantic Scholar

Workflow:

1. Retrieve source-specific candidate sets.
2. Merge candidate records.
3. Deduplicate records:
   - DOI-based matching
   - normalized-title matching (fallback)
4. Apply final global sorting:
   - Relevance → source-balanced interleaving
   - Most recent → publication year descending
   - Oldest first → publication year ascending
5. Paginate results.
6. Generate exports from the same candidate-generation pipeline.

This design ensures that All Sources exports and on-screen results are generated
from identical retrieval and deduplication logic.

## 7. Canonical Data Model

All records are normalized into a unified schema.

Model: Paper

Core fields:

id
source
title
authors
journal
year
abstract
doi
url
pmcid
mesh_terms
has_full_text

Benefits:

source-agnostic rendering
consistent export behavior
cross-source deduplication
unified filtering and sorting
easier integration of additional literature sources
simplified maintenance and extensibility

## 8. Export Functionality

Supported formats:

CSV
RIS
XLSX

Exports are generated from normalized records.

Asynchronous Export Jobs

Large exports are processed asynchronously:

POST /export/job
↓
Redis Queue
↓
ARQ Worker
↓
Batch Retrieval (API + Cache)
↓
Merge and Deduplication
↓
Sorting
↓
File Generation
↓
Download Endpoint

Export Logging

Each export job records:

batches processed
cache hits and misses
API fetches
total records collected
duplicates removed (when applicable)
execution time
All Sources Export Consistency

All Sources exports use the same retrieval, merge, deduplication, and sorting pipeline as the web interface.

Validated sort modes:

Relevance
Most recent
Oldest first

Validated export scopes:

First 100
First 500
First 1000
First 2000


## 9. Performance Characteristics

Performance depends strongly on caching, source latency, and external API responsiveness.

Cold Cache (API-bound)

When records must be retrieved from external APIs:

execution time depends on source-specific latency
throughput varies by source and query complexity
large exports may require multiple API requests
Warm Cache (cache-assisted)

When results are available from Redis cache:

substantially lower response times
reduced external API traffic
significantly higher throughput
Observations
caching provides substantial performance improvements
export performance scales with cache availability
system stability has been validated under tested export workloads
external API rate limits and latency remain outside application control

## 10. Reproducibility

LitSearch ensures reproducibility through:

containerized execution (Docker)
explicit query parameters
deterministic query construction
canonical data model
exportable outputs

Configuration via .env:

NCBI_API_KEY=your_api_key
CONTACT_EMAIL=your_email@example.com
TOOL_NAME=LitSearch

Additional reproducibility guarantees:

- canonical record normalization
- DOI-based cross-source deduplication
- normalized-title deduplication fallback
- deterministic export generation
- identical candidate generation for UI and exports

## 11. Installation

Requirements
Docker
Docker Compose
Run
docker compose up --build
Application
http://localhost:8001
Health Check
http://localhost:8001/health
First Startup

On first startup, LitSearch will:

Start the FastAPI application.
Initialize Redis connectivity.
Start background export workers.
Connect to external literature APIs as needed.

The application is ready when the health endpoint returns a successful response.

## 12. Development Utilities

Sanity Check
Install development dependencies:
pip install -r requirements-dev.txt
Run the sanity check suite:
python scripts/sanity_check.py
Validation Coverage
The sanity check validates:
	• application availability
	• external API connectivity
	• PubMed connector
	• Europe PMC connector
	• OpenAlex connector
	• Semantic Scholar connector
	• pagination behavior
	• Europe PMC deep paging
	• CSV and RIS exports
	• asynchronous export jobs
	• export download functionality
	• Redis availability
The utility provides a lightweight regression test for verifying that the application and its external integrations are functioning correctly after configuration changes or code updates.

## 13. Golden Query Validation

The following reference queries can be used for manual validation of source connectivity, pagination, result rendering, and export functionality.

PubMed
/search?source=pubmed&q=type%202%20diabetes&year_min=2015&has_abstract=1
Europe PMC
/search?source=europe_pmc&q=type%202%20diabetes
OpenAlex
/search?source=openalex&q=type%202%20diabetes
Semantic Scholar
/search?source=semantic_scholar&q=type%202%20diabetes

These queries are intended as stable regression checks and can be used after code changes, dependency upgrades, or infrastructure updates.

## 14. Limitations

external API rate limits remain outside application control
PubMed retrieval is limited to the first 10,000 records
metadata completeness varies across literature sources
OpenAlex and Semantic Scholar do not provide controlled vocabularies comparable to MeSH
Semantic Scholar may return overlapping records across paginated retrieval
LitSearch performs source-level and cross-source deduplication, but upstream data quality may affect matching
large exports depend on Redis and asynchronous worker availability
external API latency may influence search and export performance

## 15. Development Architecture

```text
app/
├── main.py
├── all_sources.py
├── redis_client.py
│
├── connectors/
│   ├── pubmed.py
│   ├── europe_pmc.py
│   ├── openalex.py
│   └── semantic_scholar.py
│
├── core/
│   ├── deduplication.py
│   └── retry.py
│
├── jobs/
│   ├── arq_worker.py
│   ├── epmc_tasks.py
│   └── export_tasks.py
│
├── models/
│   └── paper.py
│
├── enrichers/
├── services/
├── specializations/
└── templates/

Key responsibilities:

main.py — FastAPI application, request handling, search orchestration, and UI rendering
all_sources.py — shared All Sources helper logic
redis_client.py — Redis connection management
connectors/ — source-specific API integrations
core/deduplication.py — DOI/title-based deduplication utilities
core/retry.py — retry helpers for external API calls
jobs/arq_worker.py — ARQ worker configuration
jobs/epmc_tasks.py — Europe PMC background/cursor tasks
jobs/export_tasks.py — asynchronous export generation
models/paper.py — canonical Paper data model
templates/ — Jinja2 user interface templates

## 16. Future Extensions

- further helper centralization in all_sources.py
- improved export streaming
- additional literature databases
- enhanced monitoring and observability
- optional fuzzy-title similarity matching
- advanced ranking and relevance tuning

## 17. Citation & Reuse

LitSearch is intended for research, educational, and methodological purposes.

If LitSearch contributes to published research, systematic reviews, evidence syntheses, or academic coursework, please acknowledge or cite the project where appropriate.

Users remain responsible for the design, execution, interpretation, and reporting of literature searches conducted with the software.

## 18. Summary

LitSearch operationalizes reproducible literature searching through:
	• deterministic query construction
	• multi-database integration
	• All Sources aggregation
	• cross-source deduplication
	• canonical record normalization
	• unified filtering and sorting
	• consistent UI and export generation
	• asynchronous export workflows
	• Redis-based caching
	• containerized reproducibility
The system provides a transparent and reproducible framework for literature identification and retrieval across multiple scientific literature databases while remaining source-agnostic and extensible.
