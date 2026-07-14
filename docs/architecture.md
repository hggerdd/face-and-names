# Face-and-Names v2 - Architecture

## Goals
- Keep the desktop UI understandable after long pauses in development.
- Keep data access, workflow logic, and Qt widget code separated.
- Make common face operations reusable across Faces, People, Prediction Review, and Clustering.
- Keep heavy work cancellable and outside the UI thread.

## Layers

### UI layer: `face_and_names/ui`
Qt pages and reusable widgets live here. UI classes are responsible for layout, widget state,
signals, dialogs, and user feedback only.

UI modules may:
- hold current filter/page/selection state,
- render controller records into widgets,
- call controller methods in response to user actions,
- construct controllers from the current `AppContext` or service provider.

UI modules must not:
- build page-level SQL queries,
- instantiate repositories directly,
- encode business rules for face assignment, prediction acceptance, clustering, or date lookup,
- open long-running database jobs on the UI thread.

Allowed exceptions:
- `ui/workers.py` contains Qt worker classes for long-running jobs. Workers may open their own
  SQLite connection when the work has to run off the UI thread. The worker should delegate the
  actual operation to a service.
- `main_window.py` owns application composition and can validate/recreate `AppContext`.

### Page controllers: `face_and_names/services/*_controller.py`
Page controllers are the boundary between Qt pages and the application model. They expose
view-shaped records and use repositories/services internally.

Current page controllers:
- `FacesWorkspaceController`: unified face grid, scope filters, workspace modes, summaries,
  bulk assignment, prediction acceptance, and original-image lookup.
- `PeopleGroupsController`: assigned face/image pagination, date filtering, timeline dates,
  mutation actions, and original-image lookup for the People & Groups page.
- `PredictionReviewController`: prediction review counts, filters, paging, mutation actions,
  bulk acceptance, and original-image lookup.
- `ClusteringPageController`: folder listing, cluster face records, batch assignment, mutation
  actions, and original-image lookup.
- `SettingsController`: settings-page destructive data reset action.

Controllers should return dataclasses or primitive values, not Qt widgets.

### Domain services: `face_and_names/services`
Domain services implement workflows that are not tied to one page.

- `IngestService`: imports scoped folders, extracts metadata/thumbnails/faces, and optionally
  applies inline prediction.
- `PredictionService`: loads model artifacts and predicts person candidates.
- `ClusteringService`: clusters faces using configured feature sources and writes cluster IDs.
- `VersionedEmbeddingService`: computes and reuses embeddings from `face_embedding`, keyed by
  face ID, crop hash, model name, and model version.
- `PeopleService`: CRUD, merge, aliases, groups, and registry synchronization.
- `AdvancedSearchService`: search query construction and image path resolution.
- `DiagnosticsService`: lightweight health checks for database, registry, models, and detector.
- `ExportImportService`: placeholder for portable export/import; currently raises
  `NotImplementedError`.

### Data layer: `face_and_names/models`
The data layer owns SQLite schema setup and repository primitives. Repositories are intentionally
small and should be used from services/controllers instead of UI pages.

- Schema source: `face_and_names/models/schema.sql`
- Database initialization: `face_and_names/models/db.py`
- Repository primitives: `face_and_names/models/repositories.py`

## Data Flow
- Ingest: UI starts worker -> worker opens its own DB connection -> `IngestService` imports
  images/faces -> worker reports progress.
- Face review: UI filter state -> page controller query -> view records -> reusable face tiles
  -> controller mutation methods.
- Prediction training/apply: UI starts worker -> worker delegates to prediction/training service
  -> embeddings are loaded from or written to `face_embedding` -> progress and final metrics
  return to the page.
- Clustering: UI starts worker -> worker delegates to `ClusteringService` -> controller-backed
  page actions handle review and assignment. FaceNet/ArcFace feature vectors are cached as
  versioned embeddings.
- People: UI person/date/view state -> `PeopleGroupsController` -> paged records and timeline
  dates -> controller mutation methods.

## Reusable UI Components
- `ui/components/face_tile.py` is the shared face tile for face grids and review pages.
- `ui/workers.py` is the shared home for Qt worker classes used by Import, Prediction Training,
  Prediction Apply, and Clustering.
- Pages should reuse `FaceTileData` instead of hand-building separate crop/name/prediction cards.
- Page-specific layout belongs in pages; face-level actions belong behind controller callbacks.

## Storage and Config
- Active database: `faces.db` under the selected DB Root.
- Versioned embeddings: `face_embedding` stores one vector per face, model version, and crop hash.
- Person registry: `persons/persons.json`, synchronized into the active database on open.
- Logs: `logs/` under the active DB Root.
- Detector weights: `yolov11n-face.pt`.
- Prediction artifacts: `model/classifier.pkl`, `model/person_id_mapping.json`,
  `model/embedding_config.json`, `model/metrics.json`, and `model/version.txt`.

Legacy artifacts under `face_recognition_models/` are not used by the current app.

## Testing Rules
- Controller behavior gets unit/integration tests without Qt where possible.
- UI tests should focus on wiring, rendering state, and interactions.
- Long-running workflows should be tested at service/worker boundaries, not by blocking UI pages.
- Before merging behavior changes, run:

```powershell
uv run ruff check .
uv run --extra dev pytest -q
```

## Current Status
The page architecture is now consistent across the current pages:
- Faces, People & Groups, Advanced Prediction Review, Advanced Clustering, Advanced Search,
  Diagnostics, and Settings route page-level logic through controllers/services.
- Import, Prediction Training, Prediction Apply, and Clustering start Qt workers from the page,
  but the worker classes live in `ui/workers.py` and delegate heavy workflow logic to services.
- The legacy Advanced Prediction Review and Advanced Clustering pages remain available while
  their workflows are gradually folded into the unified Faces workspace.

Planned cleanup:
- Add job status controls to the unified Faces workspace so users do not need advanced pages for
  common prediction and clustering flows.
- Standardize background-job orchestration further if ingest, prediction, and clustering need
  shared job history, retries, or global progress controls.
