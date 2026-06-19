# Export Route Review

## Current state

The `/export/{fmt}` endpoint contains:

- Request parsing
- Validation
- Cache handling
- Source-specific retrieval
- Export generation
- File response handling

## Dependencies

Uses:

- Redis cache helpers
- PubMed connector
- OpenAlex connector
- Europe PMC connector
- Semantic Scholar connector
- Export serializers

## Conclusion

The export endpoint currently mixes:

- Routing
- Orchestration
- Source retrieval
- Export generation

A direct move into `routes/export_routes.py` would be high risk.

Recommended next step:

1. Extract export orchestration service.
2. Keep route thin.
3. Move route only after orchestration extraction.