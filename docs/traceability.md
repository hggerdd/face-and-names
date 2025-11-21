# Face-and-Names v2 — Requirements Traceability & Coverage Matrix

Purpose: ensure every requirement in `docs/requirements.md` is mapped to design artefacts, implementation areas, and tests (NFR-009).

## Process
- Maintain a single CSV/Markdown table (below) with one row per requirement ID.
- Columns: `Requirement ID`, `Design Docs`, `Implementation Areas`, `Tests`, `Status`.
- Update the matrix when adding/changing features, migrating schemas, or introducing new tests.
- Keep IDs in sync with `docs/requirements.md`; do not create ad-hoc IDs.

## Matrix (starter rows)

| Requirement ID | Design Docs | Implementation Areas | Tests | Status |
| --- | --- | --- | --- | --- |
| FR-001..009 | plan.md, architecture.md, ingest specs | services/ingest_service.py, ui/import_page.py | tests/test_ingest_service.py | cancel/resume + progress implemented; inline prediction pending |
| FR-010..013 | detector_adapter.md, model_runner.md, architecture.md | services/detector_adapter.py, prediction_service.py | tests/test_detector_adapter.py | partial (detection implemented, prediction stub) |
| FR-014..017, FR-064..067 | ui.md, ui_wireframes.md | ui/faces_page.py, faces workspace controller, ui/components/face_tile.py | tests (TBD) | paged folder view + face tile skeleton; full workspace pending |
| FR-018..022 | plan.md, architecture.md | services/clustering_service.py | tests (TBD) | not started |
| FR-030..033, FR-045..047, FR-068..070 | plan.md | services/people_service.py | tests/test_people_service.py | service hooks + merge/alias tests; UI pending |
| FR-048..054, FR-057 | diagnostics design | services/diagnostics_service.py | tests (TBD) | not started |
| FR-055..057, FR-058/059 | plan.md, hash_scheme.md | export_import_service.py, models/schema.sql | tests (TBD) | not started |
| NFR-001..015 | architecture.md, testing.md | app startup, UI components, worker layer | performance/a11y tests (TBD) | budgets draft only |

## Expectations
- Every new test links to one or more IDs via markers or naming.
- Release readiness requires no `Status` marked as “not started” for in-scope milestones.
- When a requirement is deferred, note it explicitly with rationale.
