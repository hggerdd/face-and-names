# Face-and-Names v2 – PyQt Layout Sketches (Textual Wireframes)

Textual wireframes to guide PyQt layouting. Components map to `docs/ui.md`.

## Main Window
- **Header (top bar)**: App title; mode toggle (Cluster/Prediction/Person/All); global status badges (model availability, device); action buttons (Start/Stop Clustering, Start/Stop Batch Prediction) with inline progress bars; quick filter pill for confidence range.
- **Left Nav (sidebar)**: Sections list: Faces, Import, Clustering, People, Prediction Review, Diagnostics, Data Insights, Export/Import, Settings. Compact icons+labels.
- **Footer**: Background job ticker (current job, percentage, ETA); log/error indicator with last severe error.
- **Content area**: Split into main pane + optional contextual side panel per view.

## Faces Workspace View
- **Main pane**: Virtualized grid of face tiles (responsive columns). Search/filter row above grid with scope selector, date range picker, confidence slider, unnamed-only toggle, differs-from-name toggle, group/tag multi-select.
- **Face tile**: Thumbnail crop; labels: current name, predicted name+confidence, cluster badge; action buttons (delete, accept) optional in hover. States: selected (highlight), inactive/unselected dim, prediction differing state badge.
- **Context panel (right)**:
  - *Cluster mode*: cluster list with counts, histogram, bulk assign/clear buttons, delete selection, wrap navigation controls.
  - *Prediction mode*: confidence histogram, predicted ID/name frequency list, bulk accept/rename/delete buttons.
  - *Person mode*: person card (name, aliases, birthdate, notes), timeline sparkline, merge trigger, bulk rename.
  - *All mode*: summary stats card (faces, unique files/folders/names, duplicates, images without faces).
- **Preview modal**: Full image with red bbox around selected face; labels for current/predicted name; zoom controls; right-click from tile opens this modal.
- **Overlay editor**: When active, image viewer with stored bboxes; toolbar to draw/edit bboxes, assign person ID, save/cancel.

## Import View
- **Left pane**: Folder tree rooted at DB Root with checkboxes; “select recursive” toggle; remembers last selection.
- **Right pane**: Options (inline prediction, thresholds, min face size). Progress box with counts (folders, files, faces, no-face), bar, cancel button. Table of errors with retry/skip controls. Resume prompt if previous session incomplete.

## Clustering View
- Parameter form: algorithm dropdown (DBSCAN/KMeans/Hierarchical), parameter inputs; scope selector (latest import/folders). Start/Stop buttons.
- Progress area: faces processed, noise count, cluster size histogram; cancellation control; post-process options (split oversized, renumber).

## Prediction Review View
- Filter row: name/alias substring, confidence range, unnamed-only, differs-from-name.
- Virtualized grid of face tiles (select-all by default). Bulk actions: accept predictions, rename, delete. Reload button. Live stats panel for filters.

## People & Groups View
- Split layout: left list of people (searchable) with primary name and alias summary; right detail pane with editable fields (primary, aliases, short names, birthdate, notes), group assignments, and a face list for that person.
- Merge workflow dialog: select target person, review conflicts; confirm merges cascade to faces.
- Groups tab/section: tree view for hierarchy, color/description fields; assignment checklist.

## Diagnostics View
- Cards for model health (presence/version/device), DB health (integrity, size), cache stats (thumbnails/crops footprint).
- Actions: rebuild thumbnails, duplicate review launcher, retry failed ingest/predict items. Self-test button with pass/fail results.

## Data Insights & Export/Import
- Data Insights: stats cards + charts (faces total, unique files/folders/names, predictions, clusters, images without faces, duplicates).
- Export/Import: selectors for data categories (people, groups, stats); dry-run option; conflict resolution prompts; relink helper for moved DB Root.

## Settings
- Global settings page: device preference, default thresholds, worker caps, logging level, theme/accessibility options.
- DB-scoped settings page: last import selection, per-DB thresholds, UI density preferences.
