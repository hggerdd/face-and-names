## Feature Summary – `db-api-cleanup`

- **DatabaseManager overhaul**  
  - Added a generic `save_faces` flow, `clear_all_names`, and numerous helper queries (image lookup, metadata, face bbox/path access, manual annotations).  
  - Heavy imports (YOLO, clustering) now guarded by `TYPE_CHECKING`, so using the DB layer no longer pulls GPU/ML dependencies at import time.

- **UI refactors to remove raw `sqlite3` usage**  
  - `ThumbnailViewer` now loads images, metadata, and face edits exclusively through the DB manager.  
  - `NameImageViewer`, shared face widgets, and prediction previews were updated to leverage the new helpers.

- **Prediction Review tab stability**  
  - Added a `PredictionDataLoader` `QThread`, reload button, and UI locking while predictions load; prevents the tab from freezing on large datasets.  
  - Filters refresh automatically once async loading finishes.

These changes prepare the codebase for future database changes, reduce duplication, and eliminate UI freezes when reviewing predictions.

## Feature Summary – `db-service-refactor`

- **Database services split**  
  - Introduced `DatabaseContext`, `ImportService`, `MetadataService`, and `FaceWriteService` under `src/core/db`.  
  - `DatabaseManager` now composes these helpers, delegating import tracking, metadata writes, and face persistence to focused classes.

- **Unit tests for write paths**  
  - Added `tests/test_db_services.py` covering import creation, face saves (with prediction data), and metadata replacement using an in-memory SQLite DB with lightweight `cv2` stubs.

This refactor keeps the heavy DB logic isolated behind small services and gives us automated safety nets for the highest-risk write operations.

## Feature Summary – `ml-pipeline-alignment`

- **Shared face preprocessing**  
  - Added `src/utils/face_preprocessing.py` and wired both detection-time predictions and the batch prediction worker to use the same normalization (BGR→RGB, resize to 160, `(x-127.5)/128`). This keeps inference consistent with training.

- **state_dict model artifacts**  
  - Training now saves MTCNN and FaceNet encoder weights via `state_dict`; `PredictionHelper` auto-detects whether the files contain full modules or weight dictionaries for backward compatibility.

- **Robust path handling**  
  - `_get_image_location` accepts the import root to compute `(base_folder, sub_folder, filename)` reliably, even for flat folder structures, and README documents the expected layout. Tests cover the new behavior.

## Feature Summary – `platform-fixes`

- Explicitly added `torch>=2.3.0` to `pyproject.toml` so environments that rely on `uv`/PEP 517 tooling install PyTorch instead of inheriting it transitively from `facenet-pytorch`.
- Introduced `src/utils/platform.py` with `open_file` / `open_folder` helpers and updated `NameImageViewer` to call them; Windows/macOS/Linux now open files/folders via the right command instead of hard-coded `os.startfile`.
- Added `tests/test_regressions.py`, a headless smoke test that spins up `DatabaseManager` to ensure schema creation still succeeds even without UI dependencies (external libs are stubbed just like in `tests/test_db_services.py`).
