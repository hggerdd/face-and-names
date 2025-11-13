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
