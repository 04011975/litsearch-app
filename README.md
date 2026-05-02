LitSearch — Reproducible Literature Search Tool

Version: 0.3.0
Sources: PubMed • Europe PMC • OpenAlex • Semantic Scholar
Architecture: FastAPI • Redis • ARQ • Docker

1. Project Overview

LitSearch is a web-based literature search application designed to support reproducible and transparent academic literature retrieval using programmatic access to scientific literature databases.

The system currently integrates:

PubMed (NCBI E-utilities)
Europe PMC
OpenAlex
Semantic Scholar

LitSearch enables:

structured literature searching
deterministic query construction
reproducible result retrieval
export of bibliographic records
multi-source comparison

LitSearch performs literature identification and retrieval only.
Interpretation, screening, quality assessment, and inclusion decisions remain the responsibility of the researcher.

2. Research Context & Motivation

Systematic and semi-systematic literature searches are central to academic research. However, many searches are still performed through graphical interfaces of bibliographic databases, which makes:

precise documentation difficult
reproduction of queries challenging
methodological transparency limited

LitSearch addresses these problems by:

exposing all query parameters explicitly
enforcing deterministic query construction
supporting multi-source retrieval
providing containerized reproducible execution
enabling exportable search results

The system supports reproducible literature search workflows but does not automate interpretation or screening.

3. System Architecture

LitSearch is implemented as a containerized web application.

Core Components
FastAPI backend (Python, async)
Jinja2 templates for result rendering
Redis for caching and background task coordination
ARQ worker for asynchronous jobs
Docker / Docker Compose for reproducible deployment
External literature APIs
Architecture Overview
User Query
    ↓
FastAPI (main.py)
    ↓
Connector layer (per source)
    ↓
External APIs
    ↓
Canonical Paper model
    ↓
Template rendering (Jinja2)
    ↓
Optional export (CSV / RIS / XLSX)
Export Flow (Async)
POST /export/job
    ↓
Redis queue
    ↓
ARQ worker (run_export_job)
    ↓
Batch retrieval (API + cache)
    ↓
Deduplication (source-level where needed)
    ↓
File generation
    ↓
Download endpoint
Caching Strategy

LitSearch uses Redis-based caching for:

paginated API responses
export batches
cursor states (Europe PMC)

Two execution modes:

Cold cache → API-bound (slower)
Warm cache → cache-only (very fast)
4. Data Sources
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

Semantic Scholar is integrated via the Graph API.

Features:

free-text search
offset-based pagination
rich metadata (authors, abstract, venue, identifiers)

Known behavior:

duplicate records may occur across paginated results
LitSearch performs deduplication based on paperId during export

Limitations:

no controlled vocabulary
API latency higher than other sources
5. Query Construction & Filtering

LitSearch constructs queries using explicit parameters:

Parameter	Description
q	free-text search query
year_min	minimum publication year
year_max	maximum publication year
has_abstract	filter records with abstracts
mesh	MeSH refinement (PubMed only)
mesh_mode	AND / OR combination
page	pagination
n	records per page

Example:

/search?source=pubmed&q=type%202%20diabetes&year_min=2015&has_abstract=1&page=1

All parameters remain visible in the URL → full reproducibility.

6. Canonical Data Model

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
easy extensibility
7. Export Functionality

Supported formats:

CSV
RIS
XLSX

Scopes:

scope=page
scope=bulk

Exports are generated from normalized records.

Asynchronous Export Jobs

Large exports are handled asynchronously:

POST /export/job
    ↓
ARQ worker
    ↓
Batch retrieval
    ↓
File generation
    ↓
Download via token
Export Logging

Each export job logs:

batches processed
cache hits / misses
API fetches
total records
duplicates skipped (if applicable)
execution time
8. Performance Characteristics

Performance depends strongly on caching.

Cold Cache (API-bound)
Europe PMC: ~10s for 1000 records
Semantic Scholar: ~30s for 1000 records
Throughput: ~30–100 records/sec
Warm Cache (cache-only)
execution time: 0.04 – 0.3 seconds
throughput: up to ~25,000 records/sec
Observations
caching provides >100x speedup
no 429 (rate limit) or 5xx errors observed
system is stable under tested loads
9. Reproducibility

LitSearch ensures reproducibility through:

containerized execution (Docker)
explicit query parameters
deterministic pagination
canonical data model
exportable outputs

Configuration via .env:

NCBI_API_KEY=your_api_key
CONTACT_EMAIL=your_email@example.com
TOOL_NAME=LitSearch
10. Installation
Requirements
Docker
Docker Compose
Run
docker compose up --build

App:

http://localhost:8001

Health:

http://localhost:8001/health
11. Development Utilities
Sanity Check
pip install -r requirements-dev.txt
python scripts/sanity_check.py

Validates:

API connectivity
connectors
pagination
export
12. Golden Query Validation
PubMed
/search?source=pubmed&q=type%202%20diabetes&year_min=2015&has_abstract=1
Europe PMC
/search?source=europe_pmc&q=type%202%20diabetes
OpenAlex
/search?source=openalex&q=type%202%20diabetes
Semantic Scholar
/search?source=semantic_scholar&q=type%202%20diabetes
13. Limitations
external API rate limits
PubMed capped at 10,000 results
metadata completeness varies
OpenAlex / Semantic Scholar lack controlled vocabulary
Semantic Scholar returns duplicate records (handled via deduplication)
large exports depend on async workers
14. Development Architecture
app/
 ├── main.py
 ├── connectors/
 │    ├── pubmed.py
 │    ├── europe_pmc.py
 │    ├── openalex.py
 │    └── semantic_scholar.py
 │
 ├── models/
 │    └── paper.py
 │
 ├── workers/
 │    └── tasks.py
 │
 └── templates/
15. Future Extensions
cross-source deduplication (DOI + fuzzy matching)
improved export streaming
retry / rate-limit handling
additional literature databases
enhanced query logging
16. Citation & Reuse

Please cite LitSearch when used in academic work.
The tool is intended for research and educational purposes.

17. Summary

LitSearch operationalizes reproducible literature searching through:

deterministic query construction
multi-database integration
canonical normalization
asynchronous export workflows
high-performance caching
containerized reproducibility