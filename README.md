# LitSearch — Reproducible Literature Search Tool

Version: 0.1.0 (PubMed + Europe PMC)

## 1. Project Overview

LitSearch is a web-based literature search application designed to support
reproducible and transparent academic literature retrieval using
programmatic access to biomedical literature databases.

The system currently integrates:
- PubMed (NCBI E-utilities)
- Europe PMC

LitSearch allows structured querying, filtering, pagination, and export
of bibliographic records for use in academic research workflows.

LitSearch performs literature identification and research only; interpretation, 
quality assessment, and inclusion decisions remain the responsibility of the user.

---

## 2. Research Context & Motivation

Systematic and semi-systematic literature searches are a core component
of academic research. However, many literature searches are performed
manually via graphical interfaces, which limits reproducibility,
traceability, and transparency.

LitSearch was developed to:
- Make literature searches reproducible
- Explicitly document query parameters
- Support structured filtering (years, MeSH terms, abstracts)
- Enable export for downstream academic analysis

This tool is intended to complement — not replace —
manual review and expert judgement.

---

## 3. System Architecture

LitSearch is implemented as a containerized web application.

### Components
- **FastAPI** backend (Python)
- **Jinja2** templates for rendering results
- **Docker & Docker Compose** for reproducibility
- **External APIs** (PubMed, Europe PMC)

### High-level flow

1. User submits a query via the web interface  
2. Query parameters are normalized and validated  
3. External literature APIs are queried  
4. Results are fetched, parsed, and normalized  
5. Results are displayed and optionally exported (CSV / RIS)  

---

## 4. Data Sources

### PubMed
- Accessed via NCBI E-utilities (ESearch + EFetch)
- Supports MeSH terms, publication date filtering, and abstract availability
- Pagination limited to the first 10,000 results (NCBI constraint)

### Europe PMC
- Used as an alternative source and for full-text availability
- Supports broader metadata retrieval

All data remains subject to the terms of the respective APIs.

---

## 5. Query Construction & Filtering

LitSearch explicitly constructs queries using:
- Free-text search terms
- Publication year ranges
- Abstract availability
- MeSH terms (AND-combined refinement)

This design ensures that:
- Queries are explicit and inspectable
- Search parameters can be documented in a thesis
- Results can be reproduced by rerunning the same query

---

## 6. Reproducibility & Configuration

Reproducibility is ensured through:
- Docker-based execution
- Explicit environment configuration via `.env`
- Fixed API interaction logic
- Deterministic pagination behavior 

### Environment variables

```env
NCBI_API_KEY=your_api_key_here
CONTACT_EMAIL=your_email@example.com
TOOL_NAME=LitSearch```

A template is provided in .env.example.

## Methods — Literature Search Procedure

The literature search was conducted using *LitSearch*, a custom-built,
web-based literature retrieval tool designed to support reproducible
and transparent academic searching.

### Search Environment

All searches were executed using a containerized deployment of LitSearch,
ensuring consistent runtime conditions across search sessions.
Configuration parameters, including API credentials and tool identifiers,
were supplied via environment variables defined in a `.env` file.
A template configuration is provided in `.env.example` to support
reproducibility.

### Data Sources

The search was performed across two biomedical literature databases:

1. **PubMed**, accessed via the NCBI E-utilities API (ESearch and EFetch),
   enabling structured querying with MeSH terms, publication year filters,
   and abstract availability constraints.

2. **Europe PMC**, used as a complementary source to enhance metadata
   coverage and identify full-text availability where applicable.

Both databases were queried programmatically, and all retrieved records
remain subject to the terms and limitations of the respective APIs.

### Query Construction

Search queries consisted of a combination of:

- Free-text search terms (`q`)
- Optional publication year limits (`year_min`, `year_max`)
- Abstract availability filtering (`has_abstract`)
- MeSH term refinement (`mesh`), combined using logical AND operations

All query parameters were explicitly constructed by the application and
exposed in the request URL, allowing exact reconstruction of the search
strategy.

### Result Retrieval and Pagination

For PubMed searches, result identifiers were obtained via ESearch and
resolved to full bibliographic records using EFetch.
Pagination followed NCBI constraints, with a maximum of 10,000 retrievable
records per query.

Europe PMC results were retrieved using page-based querying and normalized
to a common internal data structure.

### Data Normalization and Presentation

Retrieved records were normalized into a unified schema including
identifiers, titles, authors, journals, publication years, abstracts,
DOI information, and MeSH terms where available.

Results were rendered through a server-side templating system and could
optionally be exported in CSV or RIS format for downstream analysis.

### Reproducibility Considerations

The combination of explicit query parameterization, deterministic API
interaction logic, containerized execution, and documented configuration
ensures that all searches conducted using LitSearch can be reproduced
by rerunning the same query under equivalent conditions.

LitSearch is intended to support systematic and semi-systematic literature
search workflows and does not perform study quality assessment or bias
evaluation.

---

## 7. Limitations

- API rate limits may restrict large-scale querying
- PubMed pagination is limited to 10,000 records
- Results depend on external database availability
- This tool does not assess study quality or bias

LitSearch should be used as part of a broader systematic review methodology.

---

## 8. Ethical & API Considerations

- API usage complies with NCBI and Europe PMC guidelines
- A contact email is recommended by NCBI for responsible usage
- No personal data is collected or stored

---

## 9. Installation & Execution

Requirements
- Docker
- Docker Compose

Run the application:

```bash
docker compose up --build

The application will be available at:
http://localhost:8001

---

## 10. Citation & Reuse

If you use or adapt LitSearch in academic work, please cite the software
appropriately and acknowledge the underlying literature databases.

This software is intended for research and educational purposes.

---

## 11. Implementing the Methodology in the Application

A README is academically meaningful only if the application adheres
to the described methodology.

Explicit parameters
- q, year_min, mesh, has_abstract
- Parameters are visible in the URL, ensuring reproducibility

Environment separation
- Configuration via .env
- Template provided in .env.example

Separation of concerns
- connectors/ → external data sources
- main.py → orchestration and control flow
- templates/ → presentation layer

Optional thesis-level extensions
- Query parameter logging (e.g. JSON export)
- Method summary export per search
- Version tagging (Git) for experimental reproducibility

---

## 12. Recommended Academic Workflow

1. Document current methodology (README)
2. Add a new literature source
3. Update Data Sources and Limitations
4. Reference the specific software version in the thesis
This ensures methodological transparency and defensibility.

---

## 13. Validation / Golden Query

To validate core application functionality without formal unit tests,
a single reproducible “golden query” can be used.

Example test query:

- Query: `"type 2 diabetes"`
- Parameters:
  - year_min = 2015
  - has_abstract = 1
  - source = pubmed

Expected behavior:
- Number of results > 0
- MeSH-based refinement options are available
- Export (CSV / RIS) functions correctly

This query serves as a lightweight functional validation of:
query construction, API interaction, MeSH extraction, and export logic.

## 14. Summary

- The README is part of the research methodology
- The application operationalizes academic reproducibility
- This level of documentation is sufficient for thesis-level work
- Future extensions can be incorporated without redesign

---






