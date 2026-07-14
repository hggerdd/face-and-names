# Face-and-Names

Face-and-Names is a local desktop app for managing photo libraries with face detection,
person naming, clustering, and prediction review. The app stores its working data in a
SQLite database under the selected DB Root and keeps processing local by default.

## Quick Start

1. Install dependencies:

   ```powershell
   uv sync --index-strategy unsafe-best-match
   ```

2. Start the app:

   ```powershell
   uv run python -m face_and_names
   ```

3. In the app, use the workflow on the Home page:

   - Import photos: choose a DB Root and ingest folders under that root.
   - Review faces: filter the unified face grid, inspect originals, and act on selected faces.
   - Manage people: create and edit people, aliases, groups, and assignments.
   - Train model: train predictions from verified named faces.
   - Review predictions: filter and accept model suggestions.

## Navigation

- Home: recommended workflow for returning users.
- Import: DB Root selection and photo ingestion.
- Faces: unified face workspace with scope filters, face grid, selection, bulk actions, and original-image preview.
- People & Groups: people registry, aliases, groups, timelines, and assigned faces.
- Advanced Search: searches images by people, dates, and face counts.
- Prediction Model Training: trains model artifacts from verified faces.
- Advanced Prediction Review: legacy prediction review tools while the Faces workspace absorbs this workflow.
- Advanced Clustering: legacy clustering tools while the Faces workspace absorbs this workflow.
- Diagnostics: checks database health, schema version, registry, model artifacts, and detector weights.
- Settings: app preferences, worker caps, and paths.

Pages that are only scaffolds are intentionally hidden from the main navigation until
they are implemented.

## Data and Models

- Active database: `faces.db` under the selected DB Root.
- Versioned embeddings: stored in `face_embedding` inside `faces.db` and reused by training, batch prediction, and embedding-based clustering.
- Person registry: `persons/persons.json`.
- Logs: `logs/` under the active DB Root.
- Detector weights: `yolov11n-face.pt`.
- Prediction artifacts: `model/classifier.pkl`, `model/person_id_mapping.json`,
  `model/embedding_config.json`, `model/metrics.json`, and `model/version.txt`.

Legacy artifacts in `face_recognition_models/` are kept for reference and are not used
by the current app.

## Development

Run tests and linting before changing behavior:

```powershell
uv run --extra dev pytest -q
uv run ruff check .
```

Architecture rule of thumb: Qt pages render state and handle user interaction; page-level data
access and mutations belong in service controllers under `face_and_names/services`; long-running
Qt workers live in `face_and_names/ui/workers.py`. See `docs/architecture.md` before adding new
page logic.

Additional documentation:

- `docs/requirements.md`: target-state requirements.
- `docs/architecture.md`: current architecture and implementation status.
- `docs/build_run.md`: environment, build, run, and model notes.
- `docs/linting.md`: Ruff commands and settings.
