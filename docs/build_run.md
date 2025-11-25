# Build & Run

## Environment
- Python 3.12; `uv` for env/deps. Create venv: `uv venv .venv` and activate.
- Install deps: `UV_LINK_MODE=copy uv sync --index-strategy unsafe-best-match` (needed for PyTorch CPU wheels + PyPI).
- Optional extras:
  - ArcFace ONNX: `uv sync --extra arcface` (installs onnxruntime/opencv; ArcFace model downloaded on first use or place `arcface_r100_v1.onnx` in cwd).

## Commands
- Run app: `uv run python -m face_and_names`
- Tests: `uv run --index-strategy unsafe-best-match pytest`
- Lint/format: `uv run ruff check .` / `uv run ruff format .`
- Training: `uv run python -m face_and_names.train_model` (uses verified faces in DB; artifacts to `model/`)

## Models & Data
- Detector weights: `yolov11n-face.pt` in repo; used by detector adapter.
- Prediction model: artifacts under `model/` (`classifier.pkl`, `person_id_mapping.json`, etc.).
- ArcFace clustering: ArcFace ONNX auto-download (or manual `arcface_r100_v1.onnx` alongside binary); falls back to FaceNet if missing.
- DB Root: `faces.db` plus images under same root; logs under `logs/`; registry under `persons/persons.json`.

## Notes
- Offline by default; no outbound calls except optional model downloads.
- Keep UI responsive: heavy tasks run via background workers; cancel/resume supported for ingest/prediction/clustering.
