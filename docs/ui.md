# Face-and-Names v2 – PyQt UI Outline

This document sketches the UI structure, interactions, and accessibility expectations. It maps to the requirements and architectural services; no code is produced.

## Shell Layout (Desktop, PyQt)
- Main window with header (global actions/status), left-side navigation, main content area, optional right-side contextual panel, and footer for job status.
- Global status badges for model availability, device selection, and background job indicators (start/stop clustering, start/stop batch prediction, progress bars) per FR-067.

## Navigation
- Sections: Faces (workspace), Import, Clustering, People, Prediction Review, Diagnostics, Data Insights, Export/Import, Settings.
- Faces workspace is primary; other sections provide focused workflows where needed (ingest setup, clustering configuration, export/import, diagnostics).

## Faces Workspace (FR-014..017, 023..029, 038..042, 064..067)
- Modes: Cluster, Prediction, Person, All (toggle in header).
- Shared filters: scope (DB Root/folders/latest import), confidence range, unnamed-only, differs-from-name, date range, groups/tags, name/alias substring (prediction review).
- Main area: virtualized grid of face tiles showing current name, predicted name+confidence, cluster badge; supports select-all/deselect-all and wrap-around navigation.
- Contextual side panel (right):
  - Cluster mode: cluster navigation, cluster size histogram, bulk assign/clear, delete selected.
  - Prediction mode: confidence histogram, name frequency, bulk accept/rename/delete.
  - Person mode: person metadata, timeline of capture dates, bulk rename/merge entry points.
  - All mode: summary stats (counts, duplicates, images without faces).
- Face tile interactions: single-click toggles selection (inactive styling); double-click accepts prediction or opens rename per mode; right-click opens preview (full image with bbox and labels); delete control removes face (FR-016/029).
- Image view overlay: shows stored bboxes; users can draw/edit bboxes and assign person ID (FR-015).
- Virtualization/pagination to maintain performance on large sets (NFR-015).

## Import (FR-001..009)
- Folder tree rooted at DB Root with recursive option and per-subfolder checkboxes; remembers last selection (FR-004/005).
- Options: inline prediction toggle, detector/model thresholds, min face size.
- Progress panel: file/folder counts, faces detected, no-face images; cancel; retry/skip list for failures; resume from last session state (FR-009, FR-051..053).

## Clustering (FR-018..022)
- Algorithm selection (DBSCAN/KMeans/Hierarchical) with parameter controls; scope filters (latest import/folders).
- Progress: faces processed, noise count, cluster size distribution; cancel.
- Post-process options: split oversized clusters, renumber sequentially.

## Prediction Review (FR-038..042)
- Async load of filtered faces; virtualized grid of face tiles with select-all default.
- Filters: name/alias substring, confidence min/max, unnamed-only, prediction differs from name.
- Bulk accept/rename/delete; reload action; live stats for filters.

## People & Groups (FR-030..033, 045..047, 068..070)
- People list with primary name, aliases/short names, optional birthdate, notes; CRUD forms.
- Merge workflow with conflict review; global rename operation cascades to linked faces (no model retrain).
- Groups/tags: hierarchy editor, color/description; assign multiple groups to person; filters feed back into Faces workspace.

## Diagnostics & Recovery (FR-048..054, 057)
- Panels for model presence/health (versions, devices), DB health, cache stats.
- Actions: rebuild thumbnails, review duplicates (hash/perceptual), retry/skip failed items.
- Environment self-test: runs sample detection/prediction with pass/fail output.

## Export/Import & Data Insights (FR-043..057)
- Data Insights: stats (faces, unique files/folders/names, predictions, clusters, images without faces, duplicates).
- Export/Import: JSON/CSV selectors for people/groups/stats; dry-run import with conflict prompts; relink helper for moved DB Root.

## Settings
- Global settings: device preference, thresholds defaults, worker caps, logging levels.
- DB-scoped settings: last import selection, per-DB thresholds, UI preferences.

## Accessibility (NFR-013)
- Keyboard navigation for tiles and lists; shortcuts for accept/rename/delete; focus order coherent across panes.
- Screen-reader labels for buttons, tiles, histograms; tooltips descriptive (NFR-006).
- Contrast and sizing aligned with WCAG 2.1 AA.

## Performance UX (NFR-001/003/015)
- Startup ≤2 seconds: defer heavy loads; lazy load tabs.
- Long operations run in workers; UI shows non-blocking progress and allows cancellation.
- Virtualization for lists/grids; avoid heavy recompute on tab change.
