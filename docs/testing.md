# Face-and-Names v2 — Testing Strategy (Pre-Code)

Requirement coverage aligns with `docs/requirements.md`. Tests are mapped by ID and type. This is a planning document; no code.

## Test Types
- **Functional**: per feature/flow (ingest, detection/prediction, clustering, faces workspace interactions, people/groups, export/import, diagnostics).
- **Performance**: startup time, ingest throughput, clustering/prediction rates, UI responsiveness under load (NFR-001/002/003/010/011/015).
- **Resilience/Recovery**: cancel/resume for ingest/clustering/prediction; identity collisions; duplicate handling; model-absent behavior (FR-052/053/063).
- **Accessibility**: keyboard navigation, focus order, screen-reader labels, contrast (NFR-013).
- **Security/Privacy**: offline-by-default behavior; no unexpected outbound calls; optional encryption hooks; audit logging (NFR-014, BR-006).

## Functional Coverage (examples)
- Ingest: FR-001..009, FR-011..013 — scope enforcement, dedupe by hash, EXIF orientation, metadata extraction, thumbnail size, zero-face images, inline prediction optional, progress/cancel/resume, retry/skip.
- Detection/Prediction: FR-010..013, FR-034..037, FR-060..063 — bbox storage, optional inline/batch prediction thresholds, device selection/fallback, min face size handling.
- Clustering: FR-018..022 — algorithm selection, parameter application, scope filters, post-process split/renumber, progress/cancel.
- Faces workspace: FR-014..017, FR-023..029, FR-038..042, FR-064..067 — filters, virtualization behavior, face tile interactions (single/double/right-click), bulk actions, previews, overlays.
- People/Groups: FR-030..033, FR-045..047, FR-068..070 — CRUD, merge, alias collisions, group hierarchy/inheritance, filters feeding workspace.
- Prediction review/naming: FR-023..029, FR-034..037, FR-038..042 — async load, filter correctness, bulk accept/rename/delete, stats updates.
- Diagnostics/Recovery: FR-048..054, FR-057 — health panels, self-test outcomes, repair tools, duplicate review workflows.
- Export/Import/Portability: FR-055..057, FR-058/059 — JSON/CSV schema adherence, dry-run conflicts, relink after DB Root move using hashes.
- Data Insights: FR-043/044 — stats correctness on representative DB.

## Performance Benchmarks (draft targets)
| Area | Target | Test IDs (examples) |
| --- | --- | --- |
| Startup | ≤2s with representative DB (NFR-001) | PERF-startup-001 |
| Ingest (no detection) | ~3–5 img/s; record throughput (OI-002) | PERF-ingest-CPU-001 |
| Ingest (detection+inline prediction) | ~1–2 img/s on modest CPU; document GPU uplift | PERF-ingest-det-001 |
| Clustering | 10k faces <2 min; noise/cluster histograms recorded | PERF-cluster-001 |
| Batch prediction | ~10 faces/s CPU, ~30 faces/s GPU; live histogram updates | PERF-predict-001 |
| UI responsiveness | Tab change <100ms; virtualized grids smooth at large counts | PERF-ui-001 |

## Resilience Cases
- Cancel mid-ingest/clustering/prediction → partial progress persists; resume continues remaining items (FR-052/053).
- Hash collisions/near-duplicates → conflict prompts and logging (FR-058/059).
- Model missing/unavailable → app remains usable with clear state (FR-063).
- Thumbnail/crop rebuild tools restore missing cache entries.

## Diagnostics & Recovery Coverage
| Requirement IDs | Checks | Test Types |
| --- | --- | --- |
| FR-048..054, FR-057 | Model presence/versions/devices, DB integrity, cache stats, self-test pass/fail, missing asset handling | automated diagnostics tests + manual UI smoke |
| FR-051..053 | Progress + cancel/resume semantics for ingest/clustering/prediction, retry/skip flows | automated resilience tests |
| FR-050, FR-058/059 | Duplicate/near-duplicate review and repair tools | automated + manual workflow tests |

## Accessibility Checks
- Keyboard shortcuts for accept/rename/delete/select; focus order predictable. (A11Y-nav-001)
- Screen-reader labels on tiles, buttons, sliders; tooltips descriptive (NFR-006/013). (A11Y-sr-001)
- Contrast ratios meeting WCAG 2.1 AA for text/icons. (A11Y-contrast-001)
- Face tile accessibility: announce current/predicted names, selection state, delete/preview controls. (A11Y-tile-001)

## Security/Privacy Checks
- Offline default verified; no network calls unless opt-in.
- Audit log entries for rename/merge/delete/accept actions (BR-006).
- Optional encryption paths tested when enabled.

## Tooling & Automation
- `pytest` for functional/resilience; fixtures for sample images/DB roots.
- Performance harness to measure startup and throughput; runs gated on target hardware profiles.
- Lint/format via `ruff`; optional type checks via `mypy`.
- Traceability matrix lives in `docs/traceability.md`; update it with test IDs and coverage status.

## Traceability
- Each test case tagged with requirement IDs for coverage matrix; maintain coverage table linking IDs to tests.
