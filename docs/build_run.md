# Build & Run

## Environment
- Python **3.12** (required; enforced via `.python-version`, `pyproject.toml` `requires-python = ">=3.12"`, and `ruff.toml` `target-version = "py312"`). `uv` for env/deps. Create venv: `uv venv .venv` and activate.
- Install deps: `UV_LINK_MODE=copy uv sync --index-strategy unsafe-best-match` (needed for PyTorch CPU wheels + PyPI).
- Optional extras:
  - ArcFace ONNX: `uv sync --extra arcface` (installs onnxruntime/opencv; ArcFace model downloaded on first use or place `arcface_r100_v1.onnx` in cwd).

## Commands
- Run app: `uv run python -m face_and_names`
- Tests: `uv run --index-strategy unsafe-best-match pytest`
- Lint/format: `uv run ruff check .` / `uv run ruff format .`
- Training: `uv run python -m face_and_names.train_model` (uses verified faces in DB; artifacts to `model/`)

## Models & Data
- Detector weights: `yolov11n-face.pt` in repo; used by detector adapter (`DetectorAdapter` supports YOLO only; MTCNN is listed as an optional extra in `pyproject.toml` but not wired into the adapter).
- Prediction model: artifacts under `model/` — `classifier.pkl` (contains both the classifier and the `StandardScaler`), `person_id_mapping.json`, `embedding_config.json`, `metrics.json`, `version.txt`.
- ArcFace clustering: ArcFace ONNX auto-download (or manual `arcface_r100_v1.onnx` in cwd); falls back to FaceNet if missing.
- DB Root: `faces.db` plus images under same root; logs under `logs/`; registry under `persons/persons.json`.
- Legacy artifacts under `face_recognition_models/` (e.g., `face_classifier.joblib`, `face_encoder_complete.pth`, `mtcnn_complete.pth`, `label_encoder.joblib`, `model_config.json`) are **not** used by the current code and kept for reference only.

## Notes
- Offline by default; no outbound calls except optional model downloads.
- Keep UI responsive: heavy tasks run via background workers; cancel/resume supported for ingest/prediction/clustering.
