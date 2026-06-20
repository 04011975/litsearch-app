# Architecture Decision Log

## ADR-001: Centralize All Sources retrieval

Status: Accepted

Reason:
Avoid duplicated retrieval logic between UI and export paths.

Result:
Introduced build_all_source_results().

---

## ADR-002: Parallel All Sources retrieval

Status: Accepted

Reason:
Sequential retrieval caused unnecessary latency.

Result:
All source retrieval runs concurrently.

---

## ADR-003: Keep candidate limit at 2000

Status: Accepted

Reason:
Investigation showed lower limits reduce result volume without improving warm-run latency.

Result:
ALL_SOURCES_CANDIDATE_LIMIT remains 2000.

---

## ADR-004: Introduce export service layer

Status: Accepted

Reason:
Reduce route complexity in main.py.

Result:
Export request parsing and validation moved into export_service.py.