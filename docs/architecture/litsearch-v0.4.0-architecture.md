LitSearch v0.4.0 Architecture

Version: v0.4.0
Date: June 2026

Overview

LitSearch is a containerized literature search platform designed for reproducible and transparent retrieval of scientific literature from multiple sources.

Supported sources:

PubMed
Europe PMC
OpenAlex
Semantic Scholar

Supported retrieval modes:

Source-specific search
All Sources aggregation

Supported exports:

CSV
RIS
XLSX
High-Level Architecture

User Query
↓
FastAPI Application
↓
Source Connectors
↓
External Literature APIs
↓
Canonical Paper Model
↓
Rendering / Export Pipeline

Core Components
FastAPI Application

Main entry point:

app/main.py

Responsibilities:

query handling
pagination
source routing
detail pages
export initiation
UI rendering
Source Connectors

Location:

app/connectors/

Implemented connectors:

pubmed.py
europe_pmc.py
openalex.py
semantic_scholar.py

Responsibilities:

API interaction
pagination handling
source-specific mapping
normalization input
Canonical Model

Location:

app/models/

Primary model:

Paper

Common fields:

id
source
title
authors
journal
year
abstract
doi
url

Purpose:

source-independent processing
source-independent exports
source-independent rendering
All Sources Architecture

The All Sources workflow retrieves records from multiple sources and combines them into a unified result set.

Workflow:

Source Retrieval
↓
Normalization
↓
Aggregation
↓
Cross-Source Deduplication
↓
Centralized Sorting
↓
Pagination
↓
Export Generation

Integrated sources:

PubMed
Europe PMC
OpenAlex
Semantic Scholar
Deduplication Strategy

Source-level deduplication:

Semantic Scholar duplicate removal where required

Cross-source deduplication:

Primary:

DOI matching

Fallback:

normalized title matching

Purpose:

reduce duplicate retrieval
preserve export consistency
maintain UI/export parity
Sorting Architecture

Supported sort modes:

Relevance

Source-balanced interleaving after aggregation.

Most Recent

Publication year descending.

Oldest First

Publication year ascending.

Sorting is applied centrally after source merging.

Export Architecture

Export formats:

CSV
RIS
XLSX

Export scopes:

Page
Bulk

Large exports:

POST /export/job
↓
Redis Queue
↓
ARQ Worker
↓
Retrieval Pipeline
↓
File Generation
↓
Download Endpoint

Caching Architecture

Technology:

Redis

Cached elements:

paginated API responses
export batches
Europe PMC cursor chains

Execution modes:

Cold Cache

API-bound execution.

Warm Cache

Cache-assisted execution.

Validation Status

Validated for v0.4.0:

All Sources
Relevance
Most Recent
Oldest First
Export scopes
100
500
1000
2000

Validation outcome:

UI/export parity confirmed
source counts verified
cross-source deduplication verified
Known Architectural Limitations
PubMed limited to first 10,000 results
external API rate limits apply
metadata completeness varies by source
Semantic Scholar metadata quality varies
large exports depend on Redis and ARQ workers
Future Refactoring Candidates

Planned for post-v0.4.0 development:

helper centralization in all_sources.py
further reduction of duplicated sorting logic
additional source integrations
monitoring and observability improvements
Release Snapshot

This document represents the architecture of LitSearch at release v0.4.0 and serves as a reference baseline for future development and architectural changes.