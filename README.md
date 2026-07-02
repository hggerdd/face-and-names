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
   - Review faces: browse imported folders, images, and detected face tiles.
   - Manage people: create and edit people, aliases, groups, and assignments.
   - Train model: train predictions from verified named faces.
   - Review predictions: filter and accept model suggestions.

## Navigation

- Home: recommended workflow for returning users.
- Import: DB Root selection and photo ingestion.
- Faces: folder/image browser with face overlays and face tiles.
- People & Groups: people registry, aliases, groups, timelines, and assigned faces.
- Advanced Search: searches images by people, dates, and face counts.
- Prediction Model Training: trains model artifacts from verified faces.
- Prediction Review: reviews and accepts model predictions.
- Clustering: runs clustering jobs and reviews clusters.
- Diagnostics: checks database health, schema version, registry, model artifacts, and detector weights.
- Settings: app preferences, worker caps, and paths.

Pages that are only scaffolds are intentionally hidden from the main navigation until
they are implemented.

## Data and Models

- Active database: `faces.db` under the selected DB Root.
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

Additional documentation:

- `docs/requirements.md`: target-state requirements.
- `docs/architecture.md`: current architecture and implementation status.
- `docs/build_run.md`: environment, build, run, and model notes.
- `docs/linting.md`: Ruff commands and settings.
