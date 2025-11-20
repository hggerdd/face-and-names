# Face-and-Names v2 – Build & Run Workflow (prep)

This is a pre-code checklist for environment and tooling. It assumes Python with `uv` for dependency/env management and PyQt for the UI. Update commands once `pyproject.toml` is added.

## Environment
- Python: target 3.11 (broad library support for PyQt and ML stacks).
- Create venv with uv: `uv venv .venv`
- Activate venv (shell-specific), then use `uv` for all installs/sync.

## Dependencies (to be defined in `pyproject.toml`)
- Core UI: PyQt (Qt6 if feasible).
- Imaging: Pillow; EXIF/IPTC (exifread or pillow-ExifTags); perceptual hash (ImageHash or equivalent), hashlib (stdlib) for SHA-256.
- ML/detection/prediction: torch/onnxruntime as needed by model runners; detector backend (e.g., MTCNN/YOLO wrapper aligned with shipped weights).
- Clustering: scikit-learn (DBSCAN/KMeans/Hierarchical).
- Data: SQLite (stdlib), possibly SQLAlchemy-lite or direct `sqlite3`.
- Tooling: ruff (lint/format), pytest, mypy (optional), coverage (optional), uv.

## Command Conventions (once pyproject exists)
- Install/sync deps: `uv sync`
- Run app: `uv run python -m face_and_names` (package entry to be defined)
- Lint: `uv run ruff check .`
- Format: `uv run ruff format .`
- Tests: `uv run pytest`
- CPU-only torch: use the PyTorch CPU wheel index wired in `pyproject.toml` and add `--index-strategy unsafe-best-match` when syncing/running to let uv mix PyPI with the PyTorch index, e.g., `UV_LINK_MODE=copy uv sync --index-strategy unsafe-best-match` and `uv run --index-strategy unsafe-best-match pytest`.

## Data & Models
- Detector default: YOLO via `ultralytics` using bundled `yolov11n-face.pt` (configure path).
- Recognition assets expected under `face_recognition_models/` and referenced via config; presence checks in diagnostics.
- DB Root holds SQLite DB and cache folders; paths stored relative to DB Root.

## Logging
- Structured logs with rotation; default log path under DB Root (`logs/` or similar); per-feature recent errors surfaced in UI.

## Configuration
- Human-readable config files (YAML/TOML/JSON) for global/DB settings; defaults should be safe and offline-first.

## Performance/UX Practices
- Keep startup lean: defer heavy loads; lazy-init models/detectors until needed.
- Use background workers for ingest/clustering/prediction; emit progress/cancel.
- Virtualize large lists/grids in PyQt; avoid blocking UI thread.

## Security/Privacy
- Offline by default; no outbound calls without explicit opt-in.
- Optional encryption for DB and media caches to be specified; audit action logging enabled by default.
