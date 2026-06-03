LitSearch — Reproducible Literature Search Tool

Version: 0.4.0
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


### Europe PMC

Europe PMC is used as a complementary biomedical source.

Features:

- broader metadata coverage
- open access indicators
- full-text linking
- cursor-based deep paging

Current behavior:

- Europe PMC contributes relevance-ranked candidate records.
- Final ordering in All Sources is applied centrally after source merging.
- Cursor-based navigation supports deep retrieval.

Pagination:

- cursor-based navigation
- deep paging supported via cursor chaining

### Semantic Scholar

Semantic Scholar is integrated through the Graph API.

Supported modes:

#### Relevance mode

- ranked retrieval
- capped export depth
- intended for relevance-oriented searches

#### Chronological mode

- token-based bulk pagination
- supports larger exports
- used for Most recent and Oldest first sorting

Features:

- rich metadata
- author information
- abstract retrieval
- venue metadata

Limitations:

- no controlled vocabulary
- API latency may exceed other sources
- direct last-page navigation is unavailable in chronological mode


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

6. All Sources Aggregation

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
   - DOI matching
   - normalized title matching
4. Apply final global sorting:
   - Relevance → source-balanced interleaving
   - Most recent → publication year descending
   - Oldest first → publication year ascending
5. Paginate results.
6. Generate exports from the same candidate-generation pipeline.

This design ensures that All Sources exports and on-screen results are generated
from identical retrieval and deduplication logic.

7. Canonical Data Model

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


8. Export Functionality

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

### All Sources Export Consistency

All Sources exports use the same retrieval, merge,
deduplication, and sorting pipeline as the web interface.

Validated sort modes:

- Relevance
- Most recent
- Oldest first

Validated export scopes:

- First 100
- First 500
- First 1000
- First 2000


9. Performance Characteristics

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
10. Reproducibility

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

Additional reproducibility guarantees:

- canonical record normalization
- DOI-based cross-source deduplication
- normalized-title deduplication fallback
- deterministic export generation
- identical candidate generation for UI and exports

11. Installation
Requirements
Docker
Docker Compose
Run
docker compose up --build

App:

http://localhost:8001

Health:

http://localhost:8001/health
12. Development Utilities
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
14. Limitations
external API rate limits
PubMed capped at 10,000 results
metadata completeness varies
OpenAlex / Semantic Scholar lack controlled vocabulary
Semantic Scholar may return overlapping records across paginated retrieval.
LitSearch performs source-level and cross-source deduplication.
large exports depend on async workers
15. Development Architecture
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

16. Future Extensions

- helper centralization in all_sources.py
- improved export streaming
- additional literature databases
- enhanced monitoring and observability
- optional fuzzy-title similarity matching
- advanced ranking and relevance tuning

17. Citation & Reuse

Please cite LitSearch when used in academic work.
The tool is intended for research and educational purposes.

18. Summary

LitSearch operationalizes reproducible literature searching through:

deterministic query construction
multi-database integration
canonical normalization
asynchronous export workflows
high-performance caching
containerized reproducibility