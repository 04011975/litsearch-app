
# LitSearch — API & Licensing Compliance Matrix

**Project:** LitSearch
**Scope:** Entire application
**Commercial models:** SaaS subscriptions and paid literature search services
**Initial assessment date:** 2026-10-12
**Status:** Preliminary assessment — verification required

## 1. Purpose

This document tracks API access conditions, licensing restrictions,
metadata reuse rights, and commercial-use requirements for LitSearch.

The assessment applies to:

- Literature Search (individual sources and All Sources)
- Exact DOI Lookup
- Metadata enrichment
- Cross-source deduplication
- CSV, RIS, and XLSX exports
- SaaS subscriptions
- Paid literature search services

Technical API availability does not imply permission for commercial use.


| Provider | SaaS | Paid search services | Metadata reuse and export | Status |
|---|---|---|---|---|
| PubMed / NCBI | Permitted in principle under NLM conditions | Permitted in principle under NLM conditions | Subject to applicable rights; abstracts require separate review | Conditionally approved |
| Europe PMC | Commercial conditions to verify | Commercial conditions to verify | Metadata and content rights require verification | Verification required |
| OpenAlex | Written contractual clarification required | Written contractual clarification required | CC0 metadata; redistribution terms require clarification | Verification required |
| Crossref | Permitted in principle for CC0 metadata | Permitted in principle for CC0 metadata | CC0 metadata; abstracts require separate review | Conditionally approved |
| DOAJ | Permitted in principle for CC0 metadata | Permitted in principle for CC0 metadata | CC0 metadata; article content requires separate review | Conditionally approved |
| Semantic Scholar | Commercial licence required | Commercial permission required | Storage, reuse and export rights require confirmation | Elevated risk |
| OpenCitations | Permitted for covered CC0 datasets | Permitted for covered CC0 datasets | CC0 citation metadata may be reused and exported | Conditionally approved |


## 3. Assessment Criteria

For every provider, verify:

1. Official API terms and applicable licences.
2. Permission for commercial SaaS use.
3. Permission for paid literature search services.
4. Rights to retrieve, store, display, combine, and deduplicate metadata.
5. Rights to export metadata as CSV, RIS, and XLSX.
6. Attribution requirements.
7. API rate limits, authentication, and production-use requirements.
8. Costs, subscriptions, or commercial agreements.
9. Restrictions applying to abstracts and full-text content.
10. Applicable terms version, official source URL, and verification date.

## 4. Assessment Status Definitions

- **Pending:** Not yet assessed.
- **Verification required:** Initial information exists but is not sufficient.
- **Elevated risk:** Potential restrictions requiring investigation.
- **Conditionally approved:** Requirements identified but not yet fully satisfied.
- **Approved:** Applicable permissions and obligations have been verified for the defined use case.
- **Not approved:** The intended use is prohibited or necessary permission is absent.

Approval must be assessed separately for SaaS and paid search services.

## 5. Implementation Principles

- Keep existing Literature Search and export functionality unchanged during this documentation phase.
- Record metadata provenance where technically possible.
- Respect provider-specific rate limits and access requirements.
- Do not assume that abstracts or full texts have the same reuse rights as bibliographic metadata.
- Support disabling individual providers if commercial permissions are insufficient.
- Review licensing requirements before commercial launch.
- Reassess the matrix when provider terms or LitSearch functionality change.

## 6. Provider Reviews


### 6.1 PubMed / NCBI

**Assessment date:** 2026-10-12
**Status:** Conditionally approved — implementation and content review required
**Commercial SaaS:** Permitted in principle under NLM conditions
**Paid search services:** Permitted in principle under NLM conditions
**Metadata export:** Permitted in principle, subject to applicable rights
**Abstract reuse:** Separate copyright assessment required

#### Official sources

- https://www.ncbi.nlm.nih.gov/books/NBK25497/
- https://www.ncbi.nlm.nih.gov/home/about/policies/
- https://www.nlm.nih.gov/databases/download.html
- https://www.nlm.nih.gov/databases/download/terms_and_conditions.html
- https://support.nlm.nih.gov/knowledgebase/article/KA-03504/en-us

#### Findings

1. PubMed citation data can be obtained without a separate
   signed NLM data licence.
2. NLM permits reuse of publicly available citation data
   subject to applicable terms and conditions.
3. Commercial use does not eliminate copyright obligations.
4. PubMed abstracts may be copyrighted by authors or publishers.
5. NLM must be acknowledged as a source of data.
6. LitSearch must not imply NLM endorsement.
7. Redistributed data must be kept current or clearly
   identified as potentially outdated.
8. NCBI requires responsible automated API usage.
9. The standard E-utilities limit is 3 requests per second
   without an API key and generally 10 with an API key.
10. Tool and email identification should follow NCBI guidelines.
11. Large retrieval jobs should respect NCBI scheduling guidance.

#### LitSearch implications

- PubMed may remain a candidate for commercial Literature Search,
  All Sources, Exact DOI Lookup and bibliographic exports.
- Review whether abstracts are stored, displayed or exported.
- Provide appropriate NLM acknowledgement and disclaimers.
- Retain source provenance when combining PubMed records.
- Apply rate limiting across concurrent LitSearch requests.
- Review API-key handling and client identification.
- Distinguish bibliographic metadata from copyrighted content.

#### Outstanding actions

- [ ] Inspect PubMed connector API-key configuration.
- [ ] Verify tool and email identification in E-utilities requests.
- [ ] Check global rate limiting across concurrent users and jobs.
- [ ] Review NLM acknowledgement and disclaimer presentation.
- [ ] Review freshness notices for cached or exported records.
- [ ] Inspect abstract storage, display and export behaviour.
- [ ] Confirm commercial redistribution obligations.
- [ ] Recheck applicable conditions before commercial launch.

#### Decision

PubMed is a promising provider for commercial LitSearch usage.

Commercial production approval remains conditional on compliance
with NLM requirements, API usage policies and applicable
third-party copyright restrictions.


### 6.2 Europe PMC

**Assessment date:** 2026-10-12
**Status:** Verification required — commercial use and content rights
**Commercial SaaS:** To be confirmed
**Paid search services:** To be confirmed
**Metadata export:** Generally feasible for bibliographic data,
subject to applicable rights and contractual terms
**Abstract and full-text reuse:** Article-specific rights assessment required

#### Official sources

- https://europepmc.org/RestfulWebService
- https://europepmc.org/developers
- https://europepmc.org/Copyright
- https://europepmc.org/downloads/openaccess

#### Findings

1. Europe PMC provides a public REST API for publication metadata.
2. Europe PMC offers dedicated services for automated data retrieval.
3. Free access does not automatically grant unrestricted reuse rights.
4. Copyright may remain with authors, publishers or other rights holders.
5. Open access articles may have different Creative Commons licences.
6. Some licences restrict commercial reuse.
7. Systematic bulk downloading through the regular website is prohibited.
8. The relationship between API access and commercial SaaS
   redistribution requires further verification.
9. Abstracts and full texts require particular attention.
10. No definitive commercial production approval is established.

#### LitSearch implications

- Europe PMC remains a candidate for commercial Literature Search,
  All Sources and Exact DOI Lookup.
- Bibliographic metadata, abstracts and full texts must be
  treated as distinct content categories.
- Retain source provenance when combining publication records.
- Review whether abstracts are displayed, stored or exported.
- Use the official API rather than automated website scraping.
- Respect API usage limits and applicable content licences.

#### Outstanding actions

- [ ] Confirm commercial SaaS API usage conditions.
- [ ] Confirm paid literature search service usage conditions.
- [ ] Verify rights for bibliographic metadata redistribution.
- [ ] Review CSV, RIS and XLSX export contents.
- [ ] Review abstract storage, display and redistribution.
- [ ] Inspect current Europe PMC connector rate-limit handling.
- [ ] Determine whether written clarification is needed.
- [ ] Recheck applicable terms before commercial launch.

#### Decision

Europe PMC is a promising metadata provider for LitSearch.

Commercial deployment remains pending verification of applicable
API terms, metadata reuse rights and content-specific licences.



### 6.3 OpenAlex

**Assessment date:** 2026-10-12
**Status:** Verification required — contractual clarification
**Commercial SaaS:** CC0 metadata reuse appears permitted;
API service terms require clarification
**Paid search services:** CC0 metadata reuse appears permitted;
API service terms require clarification
**Metadata export:** Generally supported by CC0 declaration;
contractual restrictions require clarification
**Abstract and full-text reuse:** Separate rights assessment required

#### Official sources

- https://openalex.org/OpenAlex_termsofservice.pdf
- https://help.openalex.org/access/pricing/
- https://openalex.org/
- https://help.openalex.org/access/fulltext/

#### Findings

1. OpenAlex publicly describes its dataset as CC0.
2. OpenAlex offers free and paid API access.
3. Commercial reuse of CC0 metadata is generally permitted.
4. The Terms of Service revised on 2026-10-02 contain
   restrictions concerning unauthorized reproduction,
   modification, distribution and republication of data.
5. The relationship between the CC0 declaration and
   API contractual restrictions requires clarification.
6. Abstracts and full texts may have separate third-party rights.
7. API usage and costs must be assessed for SaaS scale.

#### LitSearch implications

- OpenAlex remains a candidate for commercial Literature Search,
  All Sources, Exact DOI Lookup and metadata exports.
- Commercial production approval is not yet granted.
- Preserve source provenance for OpenAlex-derived records.
- Assess API authentication, rate limits, caching and costs.
- Review handling of abstracts in displays and exports.

#### Outstanding actions

- [ ] Request written clarification from OpenAlex concerning
      paid SaaS and commercial metadata redistribution.
- [ ] Confirm permission for paid literature search services.
- [ ] Confirm CSV, RIS and XLSX export conditions.
- [ ] Inspect API authentication and rate-limit handling.
- [ ] Review abstract and full-text rights.
- [ ] Evaluate API costs for expected customer usage.

#### Decision

OpenAlex is technically and economically promising for LitSearch.

Commercial deployment remains pending clarification of the
relationship between the CC0 metadata declaration and the
current Terms of Service.



### 6.4 Crossref

**Assessment date:** 2026-10-12
**Status:** Conditionally approved — implementation review required
**Commercial SaaS:** Permitted in principle for reusable bibliographic metadata
**Paid search services:** Permitted in principle for reusable bibliographic metadata
**Metadata export:** Permitted in principle for reusable bibliographic metadata
**Abstract reuse:** Requires separate copyright/licence assessment

#### Official sources

- https://www.crossref.org/documentation/retrieve-metadata/
- https://www.crossref.org/documentation/retrieve-metadata/rest-api/
- https://www.crossref.org/documentation/retrieve-metadata/rest-api/access-and-authentication/
- https://www.crossref.org/documentation/metadata-plus/

#### Findings

1. Crossref provides a publicly accessible REST API.
2. Almost all bibliographic metadata is reusable without restriction.
3. Bibliographic metadata is generally treated as factual information
   not subject to copyright.
4. Crossref-generated data is released under CC0.
5. Abstracts may remain subject to publisher or author copyright.
6. Public API access does not require registration.
7. Crossref recommends identifying API clients using an email address.
8. API rate limits and concurrency limits depend on the access pool.
9. Metadata Plus is an optional paid service offering enhanced access,
   higher limits and support.
10. Metadata exports should distinguish reusable bibliographic fields
    from potentially copyrighted abstracts.

#### LitSearch implications

- Crossref may be used as a metadata provider for Literature Search,
  All Sources and Exact DOI Lookup, subject to API operational limits.
- Bibliographic metadata may generally be displayed and exported
  in CSV, RIS and XLSX formats.
- Abstract storage, display, redistribution and AI processing require
  separate rights assessment.
- API requests should use appropriate identification, caching,
  rate limiting and retry handling.
- Provider provenance should be retained when combining metadata.
- The existing connector and export implementations must be reviewed
  before commercial production deployment.

#### Outstanding actions

- [ ] Inspect current Crossref API client identification.
- [ ] Verify rate-limit and retry handling in LitSearch.
- [ ] Review abstract fields in search results and exports.
- [ ] Confirm metadata provenance and attribution handling.
- [ ] Assess whether public API capacity is sufficient for SaaS usage.
- [ ] Recheck applicable conditions before commercial launch.

#### Decision

Crossref is a suitable candidate for commercial LitSearch usage
based on its published metadata reuse policy.

Commercial production approval remains conditional on verification
of the actual LitSearch implementation and handling of abstracts.



### 6.5 DOAJ

**Assessment date:** 2026-10-12
**Status:** Conditionally approved — implementation review required
**Commercial SaaS:** Permitted in principle for CC0 metadata
**Paid search services:** Permitted in principle for CC0 metadata
**Metadata export:** Permitted in principle for CC0 metadata
**Abstract and full-text reuse:** Separate rights assessment required

#### Official sources

- https://doaj.org/terms/
- https://doaj.org/docs/api/
- https://doaj.org/docs/premium
- https://doaj.org/docs/public-data-dump/
- https://doaj.org/apply/copyright-and-licensing/

#### Findings

1. DOAJ's current terms describe journal-level and
   article-level metadata as available under CC0.
2. CC0 generally permits commercial metadata reuse.
3. DOAJ metadata is available through official APIs
   and other supported distribution services.
4. Article content may have separate publisher or
   author copyright and licence restrictions.
5. DOAJ offers regular and premium metadata services.
6. Premium services provide access to more current
   metadata and may involve additional costs.
7. Bulk data dump access may require an application.
8. DOAJ's trade names, branding and website content
   are not automatically covered by metadata CC0.
9. Earlier DOAJ publications describe journal metadata
   under CC BY-SA. The applicable current terms and
   dataset-specific licence should be reconfirmed.
10. Commercial production approval requires a review
    of the actual LitSearch implementation.

#### LitSearch implications

- DOAJ is a suitable candidate for commercial
  Literature Search, All Sources and Exact DOI Lookup.
- CC0 bibliographic metadata may generally be displayed,
  combined, deduplicated and exported.
- Preserve source provenance in combined records.
- Review abstracts separately from bibliographic metadata.
- Respect API access conditions and operational limits.
- Evaluate whether premium metadata services are needed.
- Avoid implying DOAJ endorsement of LitSearch.

#### Outstanding actions

- [ ] Verify current API access and rate limits.
- [ ] Confirm the applicable licence for each metadata
      category, including journal-level metadata.
- [ ] Review abstract storage, display and export.
- [ ] Confirm CSV, RIS and XLSX export contents.
- [ ] Check DOAJ attribution and branding requirements.
- [ ] Assess regular versus premium metadata access.
- [ ] Review the existing DOAJ connector implementation.
- [ ] Recheck applicable terms before commercial launch.

#### Decision

DOAJ is a promising provider for commercial LitSearch use.

Commercial production approval remains conditional on
implementation review, content rights verification and
compliance with applicable API service conditions.



### 6.6 Semantic Scholar

**Assessment date:** 2026-10-12
**Status:** Elevated risk — commercial licence required; API access unresolved
**Commercial SaaS:** Not cleared under the standard API licence
**Paid search services:** Not cleared; written permission required
**Metadata export:** Commercial redistribution rights require explicit confirmation
**Abstract reuse:** Separate copyright and contractual review required
**Technical API access:** Unresolved HTTP 403 issue

#### Official sources

- https://api.semanticscholar.org/license/
- https://www.semanticscholar.org/product/api
- https://api.semanticscholar.org/api-docs/

#### Findings

1. The standard Semantic Scholar API licence restricts
   permitted use to specified non-commercial purposes.
2. Commercial subscription-based SaaS use is not
   cleared under the standard licence.
3. Paid literature search services require separate
   contractual clarification.
4. An expanded licence may be requested for uses
   outside the standard licence.
5. Commercial redistribution, storage and export
   of API data require explicit rights verification.
6. Public display and attribution obligations must
   be reviewed before deployment.
7. Abstracts and other third-party content may be
   subject to additional copyright restrictions.
8. Previous LitSearch tests returned HTTP 403
   with the configured API key.
9. Requests without an API key previously returned
   HTTP 429.
10. Semantic Scholar previously communicated a
    one-request-per-second rate-limit policy.
    Current applicable limits require reconfirmation.
11. API access and commercial licensing are
    separate requirements.

#### LitSearch implications

- Retain the existing Semantic Scholar connector.
- Do not enable it for commercial LitSearch users
  without an appropriate licence.
- Request permission for subscription-based SaaS.
- Request permission for paid literature search services.
- Explicitly include CSV, RIS and XLSX exports
  in the commercial licence request.
- Clarify whether combining and deduplicating
  Semantic Scholar metadata with other sources
  is permitted.
- Review storage, caching, attribution and
  source provenance obligations.
- Keep connector failures isolated from other
  literature sources.
- Do not assume that possession of an API key
  grants commercial rights.

#### Outstanding actions

- [ ] Obtain written commercial-use authorisation.
- [ ] Confirm SaaS subscription rights.
- [ ] Confirm paid literature search service rights.
- [ ] Confirm metadata display, storage and export rights.
- [ ] Confirm cross-source deduplication and combination rights.
- [ ] Assess abstract reuse and third-party copyrights.
- [ ] Verify attribution and branding obligations.
- [ ] Determine commercial API pricing and quotas.
- [ ] Resolve the existing HTTP 403 API-key issue.
- [ ] Verify applicable rate limits and concurrency requirements.
- [ ] Document the applicable agreement and approval date.
- [ ] Complete implementation review before commercial launch.

#### Decision

Semantic Scholar is not approved for commercial
LitSearch deployment under the standard API licence.

Commercial activation requires appropriate written
permission and functional API access.

The existing connector will be retained without
changing its implementation during this compliance review.



### 6.7 OpenCitations

**Assessment date:** 2026-10-12
**Status:** Conditionally approved — implementation review required
**Commercial SaaS:** Permitted for covered CC0 datasets
**Paid search services:** Permitted for covered CC0 datasets
**Citation metadata export:** Permitted for covered CC0 datasets
**Abstract and full-text reuse:** Not covered by this assessment
**Technical API access:** Implementation review required

#### Official sources

- https://opencitations.net/mission/
- https://opencitations.net/
- https://api.opencitations.net/index/v2
- https://opencitations.net/accesstoken/
- https://opencitations.net/opencitations-brand-guidelines-and-logo/

#### Findings

1. OpenCitations makes its citation datasets available
   under the Creative Commons CC0 waiver.
2. CC0 permits commercial reuse, modification,
   combination and redistribution of covered data.
3. OpenCitations data may therefore be incorporated
   into commercial literature search applications.
4. The Index V2 API documentation specifies a limit
   of 180 requests per minute per IP address.
   Current limits must be reconfirmed before launch.
5. API access tokens are available free of charge
   and are recommended for identifying API users.
6. OpenCitations provides REST APIs and data dumps.
7. Attribution is not legally required by CC0,
   but source acknowledgement is recommended.
8. Website content and branding are not automatically
   covered by the dataset's CC0 waiver.
9. Abstracts and full-text articles from third-party
   providers require separate rights assessment.
10. The applicable API version and operational
    conditions must be checked against the actual
    LitSearch implementation.

#### LitSearch implications

- Retain OpenCitations as a metadata enrichment provider.
- Allow covered citation data to be combined with
  bibliographic records from other sources, subject
  to those sources' applicable terms.
- Preserve enrichment provenance in the Paper model.
- Distinguish citation counts from complete citation
  coverage across all scholarly publications.
- Review API concurrency, caching, retries and
  rate limiting across users and background jobs.
- Verify whether citation and reference fields are
  included in CSV, RIS and XLSX exports.
- Provide appropriate source acknowledgement.
- Avoid implying endorsement by OpenCitations.
- Do not treat third-party article content as CC0.

#### Outstanding actions

- [ ] Verify the OpenCitations API version in use.
- [ ] Confirm current rate limits and access requirements.
- [ ] Review access-token configuration.
- [ ] Verify rate limiting across concurrent requests.
- [ ] Review retry, caching and error handling.
- [ ] Verify citation and reference field provenance.
- [ ] Check enrichment display in paper details.
- [ ] Review CSV, RIS and XLSX export behaviour.
- [ ] Verify attribution and branding compliance.
- [ ] Recheck official conditions before commercial launch.

#### Decision

OpenCitations is provisionally suitable for
commercial metadata enrichment within LitSearch.

Commercial deployment is conditionally approved
at the documentation level, subject to technical
implementation review and confirmation of current
API conditions.

This assessment does not constitute final legal
or contractual approval.



## 7. Open Questions and Pre-Launch Actions

The following actions must be resolved or explicitly
accepted through a documented risk decision before
commercial deployment of the relevant provider.

### 7.1 High Priority — Commercial Licensing

#### Semantic Scholar

- [ ] Obtain written permission for subscription-based SaaS.
- [ ] Confirm permission for paid literature search services.
- [ ] Confirm metadata storage, combination and redistribution rights.
- [ ] Confirm CSV, RIS and XLSX export permissions.
- [ ] Determine commercial licence fees and API quotas.
- [ ] Resolve the existing HTTP 403 API access issue.

#### OpenAlex

- [ ] Obtain written clarification of commercial SaaS rights.
- [ ] Confirm applicability of the current Terms of Service.
- [ ] Clarify metadata redistribution and export permissions.
- [ ] Confirm rights for paid literature search services.
- [ ] Document the provider's written response.

#### Europe PMC

- [ ] Verify commercial API usage conditions.
- [ ] Confirm rights to display and export bibliographic metadata.
- [ ] Clarify abstract storage, display and export permissions.
- [ ] Verify attribution and third-party content restrictions.
- [ ] Document applicable official terms.

### 7.2 Medium Priority — Implementation Compliance

#### PubMed / NCBI

- [ ] Verify E-utilities rate limiting and API-key configuration.
- [ ] Review abstract reuse and export rights.
- [ ] Verify attribution and data freshness requirements.

#### Crossref

- [ ] Review API identification and rate-limit handling.
- [ ] Verify abstract and third-party metadata rights.
- [ ] Review commercial export behaviour.

#### DOAJ

- [ ] Verify API access conditions and current rate limits.
- [ ] Confirm metadata licence scope and abstract rights.
- [ ] Review regular versus premium metadata access.

#### OpenCitations

- [ ] Verify API version, token configuration and rate limits.
- [ ] Review enrichment provenance and caching.
- [ ] Confirm citation metadata display and export behaviour.

### 7.3 Application-Wide Compliance

- [ ] Verify source-specific licensing in All Sources.
- [ ] Review metadata combination and deduplication rights.
- [ ] Verify Exact DOI Lookup respects provider restrictions.
- [ ] Audit CSV, RIS and XLSX fields by source.
- [ ] Review abstract storage, display and export.
- [ ] Verify attribution and provenance in the user interface.
- [ ] Confirm rate limiting across concurrent users and jobs.
- [ ] Implement or verify provider-level disabling controls.
- [ ] Document commercial launch decisions per provider.
- [ ] Recheck current official terms before production launch.

### 7.4 Commercial Launch Gate

A provider must not be marked Approved until:

1. Applicable commercial-use permissions are verified.
2. Metadata reuse and export rights are documented.
3. Abstract and third-party content restrictions are addressed.
4. API access, quotas and operational requirements are satisfied.
5. Required attribution and provenance are implemented.
6. Outstanding blocking issues are resolved.
7. The final decision and supporting evidence are recorded.

Providers without sufficient permission must remain
disabled for commercial use until approval is obtained.


## 8. Review History


| Date | Change |
|---|---|
| 2026-10-12 | Initial API and licensing compliance matrix created |
| 2026-10-12 | Preliminary assessment of PubMed / NCBI completed |
| 2026-10-12 | Preliminary assessment of Europe PMC completed |
| 2026-10-12 | Preliminary assessment of OpenAlex completed; contractual clarification required |
| 2026-10-12 | Preliminary assessment of Crossref completed |
| 2026-10-12 | Preliminary assessment of DOAJ completed |
| 2026-10-12 | Preliminary assessment of Semantic Scholar completed; commercial licensing and API access unresolved |
| 2026-10-12 | Preliminary assessment of OpenCitations completed |
| 2026-10-12 | Compliance overview matrix updated for all seven providers |
