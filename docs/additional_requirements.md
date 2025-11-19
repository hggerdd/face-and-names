# Additional Requirements & Proposals

Use this as a backlog for the next iteration; fill in priorities and owners.

## High-Priority
- Faster startup: preload/check for `yolov11n-face.pt` and model artifacts at launch; parallelize font/load tasks where safe; keep heavy imports guarded.
- Better filtering/search:
  - Detection tab: filter by month/EXIF date (circles strip mentioned in README TODO).
  - Search images by person combinations (A & B but not C) at DB level with indexes; expose UI.
- Reliability: surface missing-model errors early; guard GPU/CPU device selection; retry or skip corrupt images with logging; ensure thumbnails always generated even when no faces.
- Consistent UX for long tasks: standardize QThread workers with progress/cancel, disable UI controls during work, auto-refresh data when threads finish; harmonize double-click semantics (accept prediction) across tabs.

## Medium-Priority
- Import robustness: resumable imports; track files processed per import_id and skip already-ingested ones even if rerun on the same folder.
- Data quality tools: duplicate filename report already present—add UI surfacing and one-click review; add “faces without thumbnails” fixer.
- Clustering improvements: persist clustering parameters per run; allow rerun on a saved face subset; expose noise/outlier review UI.
- Naming workflow: bulk-accept predictions above threshold; keyboard shortcuts for next/previous cluster and apply name.
- Prediction review: add filters to focus on low-confidence predictions; batch accept/reject.

## Low-Priority / Nice-to-Have
- Export/import: dump DB to JSON/CSV with thumbnails; restore into a fresh DB.
- Cloud/offline modes: optional remote storage for images; local-only toggle for privacy.
- Telemetry/lightweight metrics: optional anonymized timing and error stats for debugging (must be opt-in).
- Theming/accessibility: font scaling, high-contrast theme, larger hit targets for touch.

## Open Questions
- Do we keep SQLite or move to a different store for scalability? (Current schema is simple and tested.)
- How large can datasets get (images/faces)? Determines caching and batching strategies.
- Should training be in-app or external? Current training tab is a stub; encoder/classifier artifacts are expected to be prebuilt.

## Proposed Next Steps
1) Finalize target workflows (import → detect → cluster → name → predict/review) and agree on MVP scope.
2) Lock in data contracts (DB schema, model artifact formats, thumbnail specs) and publish as a separate doc.
3) Define a background task runner pattern (queue + worker) to standardize progress/cancel and state updates across tabs.
4) Add a lightweight health check at startup (models present, DB writable, CUDA availability) with a diagnostics panel in-app.
5) Write a concise developer guide: setup, running tests, where to place models, and how to run headless checks.
