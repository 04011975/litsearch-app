# Main.py Modularization Next Review

## Current scan

`app/main.py` currently contains 12 FastAPI route decorators.

Async functions include:

- startup/shutdown lifecycle handlers
- request logging middleware
- Europe PMC helper functions
- detail lookup helper
- main search route
- paper detail routes
- async export job routes
- sync export route

## Main remaining large sections 

### Search route

Function:

- `search()`

Approximate location:

- starts around `app/main.py:1087`

Risk:

- High

Reason:

- Contains source-specific UI retrieval logic
- Handles multiple sources
- Interacts with pagination, filters, templates, warnings and cache behavior

Recommendation:

- Do not move directly yet
- Extract only small helper/service functions when clearly isolated

### Paper detail routes

Functions:

- `paper_detail()`
- `legacy_pubmed_detail()`
- `legacy_epmc_detail()`
- `legacy_semantic_scholar_detail()`

Approximate location:

- starts around `app/main.py:2143`

Risk:

- Low to medium

Recommendation:

- Candidate for later route module extraction into `app/routes/paper_routes.py`

### Export routes

Functions:

- `create_export_job()`
- `get_export_job()`
- `download_export()`
- `export()`

Approximate location:

- starts around `app/main.py:2196`

Risk:

- Medium

Current status:

- `app/services/export_service.py` already contains export request parsing and validation

Recommendation:

- Continue extracting export orchestration into `app/services/export_service.py`
- Move routes only after route handlers are thin

## Recommended next refactor order

1. Continue export-service extraction

2. Extract paper detail routes

   Status: Reviewed

   Findings:

   - paper_detail() is largely self-contained
   - legacy redirect routes are self-contained
   - primary dependency is _fetch_detail_by_source()
   - route extraction appears low risk

   Recommendation:

   Move paper detail routes after export route extraction is completed.

3. Review Europe PMC helper placement

4. Decompose `search()` last

## Conclusion

The safest next code refactor is not moving `search()`.

Continue with small export-service extractions or move the relatively isolated paper detail routes after export service stabilizes.