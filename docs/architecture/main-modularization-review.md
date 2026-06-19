# Main.py Modularization Review

Date: 2026-06-17

## Current State

main.py contains:

- application startup/shutdown
- middleware
- helper functions
- search route
- detail routes
- export routes

## Recommended Refactor Order

### Phase 1

Move export endpoints:

- create_export_job()
- get_export_job()
- download_export()
- export()

Target:

app/routes/export_routes.py

Risk: Low

### Phase 2

Move paper detail endpoints.

Target:

app/routes/paper_routes.py

Risk: Low

### Phase 3

Review Europe PMC cursor helpers.

Risk: Medium

### Phase 4

Break search() into service layer components.

Risk: High

Not recommended until after v0.5.0 stabilization.