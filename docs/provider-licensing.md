# LitSearch Provider Licensing Audit

Last reviewed: 2026-08-18

## Purpose

This document tracks API access, commercial-use considerations,
content-licensing caveats, and operational requirements for external
scholarly data providers used or considered by LitSearch.

The purpose is to prevent LitSearch from depending on a provider whose
API or data cannot sustainably be used if the application later offers
paid functionality.

This document is an engineering and product-planning record. It is not
legal advice.

## Status definitions

- **GREEN** — no known provider-level restriction preventing commercial
  use of the metadata/API for the currently intended LitSearch use case.
- **YELLOW** — API access appears usable, but individual content fields
  or downstream uses require additional licensing/copyright care.
- **RED** — standard access is explicitly limited to non-commercial use,
  or commercial use requires a separate licence or agreement.
- **PENDING** — clarification from the provider is still required.

## Current providers

### PubMed / NCBI

**Status:** YELLOW

**LitSearch use:**
- literature search
- bibliographic metadata retrieval
- abstracts
- identifiers
- deduplication
- export

**Current assessment:**

NCBI provides E-utilities as the public programmatic interface to PubMed
and other Entrez databases.

The main licensing concern is not use of E-utilities itself, but
copyright in content returned through PubMed. NLM states that it does
not claim copyright in PubMed abstracts, while publishers or authors
may hold those rights.

Software using E-utilities must make the NCBI Disclaimer and Copyright
notice evident to users.

**Commercial-use implication:**

Bibliographic retrieval and metadata processing appear compatible with
LitSearch's architecture, but commercial reproduction, redistribution,
AI processing, or other reuse of abstracts must not be assumed to be
unrestricted.

**Action:**
- keep PubMed enabled
- review how abstracts are displayed, exported, cached, and potentially
  processed by future AI functionality
- ensure required NCBI disclaimer/copyright notice is visible where
  applicable

**Official references:**
- https://www.ncbi.nlm.nih.gov/home/develop/api/
- https://www.ncbi.nlm.nih.gov/home/about/policies/
- https://www.ncbi.nlm.nih.gov/books/NBK25497/

---

### Europe PMC

**Status:** YELLOW

**LitSearch use:**
- literature search
- metadata retrieval
- abstracts
- open-access indicators
- identifiers
- deduplication
- export

**Current assessment:**

Europe PMC provides developer interfaces for building applications
using its literature and metadata services.

However, copyright and reuse rights may differ between individual
publications. Users remain responsible for complying with applicable
copyright and licence conditions.

Open-access availability does not by itself mean that every work has
identical reuse rights.

**Commercial-use implication:**

Metadata retrieval can remain part of LitSearch, but abstracts and
full-text content must be treated separately from bibliographic
metadata. Future redistribution, AI processing, or commercial reuse
should respect the licence of the underlying work.

**Action:**
- keep Europe PMC enabled
- preserve article-level licence information where available
- separately review abstract/full-text use before adding AI or
  content-republication functionality

**Official references:**
- https://europepmc.org/developers
- https://europepmc.org/Copyright

---

### OpenAlex

**Status:** GREEN

**LitSearch use:**
- literature search
- metadata retrieval
- concepts
- citations and identifiers
- deduplication
- export

**Current assessment:**

OpenAlex states that its data is released under CC0 / public-domain
terms without a personal-use-only restriction.

API access itself has usage-based pricing and free allowances that may
change independently of the data licence.

**Commercial-use implication:**

OpenAlex is currently one of the strongest candidates for a long-term
core LitSearch provider because the underlying OpenAlex data is
explicitly intended for broad reuse, including commercial downstream
applications.

This does not automatically grant additional rights to external
full-text works or third-party content merely linked from OpenAlex.

**Action:**
- retain as a core provider
- monitor API pricing and rate-limit changes
- distinguish OpenAlex metadata from linked third-party publication
  content

**Official references:**
- https://help.openalex.org/access/pricing/
- https://help.openalex.org/api/
- https://help.openalex.org/hc/en-us/articles/28926392245399-How-is-OpenAlex-open

---

### Crossref

**Status:** GREEN

**LitSearch use:**
- literature search
- DOI metadata
- bibliographic metadata
- deduplication
- export

**Current assessment:**

Crossref states that its metadata records can be retrieved and used
without restriction and without a metadata-use fee.

The public REST API is available for metadata retrieval. Crossref also
offers paid Metadata Plus services for users requiring additional
performance, predictability, bulk data, or support.

Some deposited metadata fields may contain material for which
underlying rights remain with publishers or other rights holders.

**Commercial-use implication:**

Crossref metadata is currently suitable as a long-term LitSearch
retrieval and deduplication source.

Commercial use of LitSearch does not by itself appear to require
Metadata Plus, although operational scale may eventually make a paid
Crossref service desirable.

**Action:**
- retain as a core provider
- continue polite API identification
- monitor API operational requirements
- treat embedded abstracts or linked publication content separately
  where applicable

**Official references:**
- https://www.crossref.org/services/metadata-retrieval/
- https://www.crossref.org/documentation/retrieve-metadata/rest-api/
- https://www.crossref.org/community/developers/

---

### Semantic Scholar

**Status:** RED / PENDING

**LitSearch use:**
- literature search
- metadata retrieval
- chronological/bulk retrieval
- detail pages
- deduplication
- export

**Current assessment:**

Semantic Scholar's standard API License Agreement restricts API use
according to the terms of that agreement. The standard licence contains
non-commercial research and educational-use provisions, while uses
outside the standard licence may require a separate or expanded
licence.

LitSearch also currently has an unresolved API-access issue: the
existing API key returns HTTP 403 Forbidden. A request without the key
reaches Semantic Scholar but is rate-limited with HTTP 429.

Semantic Scholar support has been contacted regarding the API key.

**Commercial-use implication:**

Do not assume that the standard Semantic Scholar API licence permits
Semantic Scholar data to be incorporated into a paid LitSearch service.

A commercial/expanded licence or written clarification may be required.

**Action:**
- await Semantic Scholar support response concerning the existing API key
- obtain explicit clarification regarding commercial LitSearch use
- investigate an Expanded Licence if required
- do not build commercial product assumptions around Semantic Scholar
  until clarified
- separately improve the current process-local 1 QPS limiter to a
  cross-process/global limiter if Semantic Scholar remains enabled

**Official reference:**
- https://api.semanticscholar.org/license/

---

## Candidate providers

### CORE

**Status:** RED / PENDING

**Current assessment:**

CORE supports commercial API use under its licensing arrangements.

A Non-Academic 30-day trial API key has been issued for LitSearch. The
trial expires on 2026-09-14. CORE stated that a licence is required
after that date for continued use under the supplied access arrangement.

CORE Enterprise has been contacted for pricing and licensing
information.

During initial testing, the API key successfully accessed the CORE v3
works search endpoint. Rate limiting was observed during testing.

**Commercial-use implication:**

CORE could potentially be used commercially, but long-term inclusion
depends on licensing cost, permitted use, operational limits, and the
additional retrieval value CORE provides compared with existing
LitSearch sources.

**Action:**
- keep CORE implementation paused
- await Enterprise pricing/licensing response
- reconsider integration only after cost and licence terms are known

**Official references:**
- https://core.ac.uk/services/api
- https://core.ac.uk/terms
- https://core.ac.uk/faq

---

### BASE

**Status:** RED

**Current assessment:**

The BASE Interface Guide version 1.29 (April 2026) states that the BASE
HTTP API may be used for non-commercial purposes only.

The API otherwise appears technically well suited to LitSearch. It
supports:
- `PerformSearch`
- JSON responses
- SOLR query syntax
- pagination
- relevance sorting
- year sorting
- DOI
- titles
- authors
- abstracts
- publication dates
- URLs
- open-access indicators
- subjects
- document types
- facets

The documented rate limit is 1 request per second.

An API key is mandatory.

**Commercial-use implication:**

Because LitSearch may later charge users for functionality such as
cross-source deduplication, BASE should not be integrated under the
current non-commercial-only API terms without explicit permission or an
alternative commercial licence.

Even if BASE search itself were offered for free, BASE records
participating in a paid downstream LitSearch workflow could potentially
constitute commercial use and should not be assumed to be permitted.

**Action:**
- do not request or integrate BASE for production use under the current
  terms
- contact BASE first if commercial integration is still desired
- ask whether a commercial licence or written permission is available

**Reference:**
- BASE Interface Guide, version 1.29, April 2026
- https://api.base-search.net/

---

## Provider strategy

### Preferred long-term core

At present, the strongest candidates for a commercially sustainable
metadata core are:

1. OpenAlex
2. Crossref

PubMed and Europe PMC remain important providers but require more
careful separation between bibliographic metadata and copyrighted
article content.

### Conditional providers

The following should remain conditional until licensing is resolved:

- Semantic Scholar
- CORE
- BASE

A provider must not become essential to paid LitSearch functionality
unless its commercial-use status is documented.

## Engineering requirements

Every external provider integrated into LitSearch should have the
following information recorded before implementation or commercial
release:

- provider name
- official API documentation
- applicable terms/licence
- commercial-use status
- authentication requirements
- API pricing
- rate limits
- attribution requirements
- metadata/content copyright caveats
- permitted caching/storage
- permitted redistribution/export
- AI/text-and-data-mining implications where relevant
- date last reviewed
- action required before commercial launch

Licensing status must be treated separately from connector
implementation status.

A technically working connector does not imply that the provider is
approved for commercial production use.

## Review trigger

This document should be reviewed:

- before adding a new retrieval provider
- before changing LitSearch from non-commercial development to a paid
  service
- before introducing AI summarisation, evidence extraction, or other
  processing of abstracts/full text
- when a provider changes its terms, API access model, or pricing
- at least periodically before major LitSearch releases