# face-and-names (rewrite plan)

We’re starting fresh on branch `rewrite/next-gen`, using v1.0.0 as the frozen reference. This README tracks the greenfield plan; the legacy code and docs stay available for lookup.

## Goals
- Streamlined photo ingest → detect → cluster → name → predict/review → browse/annotate.
- Fast startup and responsive UI on large libraries.
- Clear, testable requirements (see `docs/functional_requirements.md` and `docs/face_detection_pipeline.md`).
- Clean data contracts and background task patterns defined up front.

## Immediate Steps
1) Finalize user stories and edge cases per flow (import, clustering, naming, prediction, browsing).
2) Set performance budgets (startup, ingest throughput, max UI stall) and agree on async/worker architecture.
3) Design the new schema and model artifact contracts after requirements are locked.
4) Define shared interaction rules (click/double-click, delete, preview, batch accept, progress/cancel).
5) Draft a minimal UX map/wireframe for the core tabs before coding.

## Reference
- Consolidated requirements: `docs/requirements.md`
- Tag `v1.0.0` marks the previous implementation for comparison.
