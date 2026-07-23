# Build & Run

## Environment
- Python 3.14 is required by `.python-version` and `pyproject.toml`.
- Use `uv` for environment and dependency management.
- Create a virtual environment with `uv venv .venv`, then activate it.
- Install dependencies with `uv sync --index-strategy unsafe-best-match`.
- Optional ArcFace support: `uv sync --extra arcface`.

## Commands
- Run app: `uv run python -m face_and_names`
- Tests: `uv run --extra dev pytest -q`
- Lint: `uv run ruff check .`
- Format: `uv run ruff format .`
- Training: `uv run python -m face_and_names.train_model`

## Models & Data
- Detector weights: `yolov11n-face.pt`.
- Prediction artifacts: `model/classifier.pkl`, `model/person_id_mapping.json`,
  `model/embedding_config.json`, `model/metrics.json`, `model/version.txt`, and the copied
  backbone under `model/weights/`.
- Versioned embeddings: `face_embedding` in `faces.db` caches vectors by face ID,
  crop SHA-256, model name, and model version.
- Training, batch prediction, and embedding-based clustering reuse cached embeddings.
- ArcFace clustering uses an explicitly configured, already-installed `arcface_r100_v1.onnx`
  when available and falls back to explicitly configured FaceNet weights. No model is downloaded
  by the application.
- DB Root contains `faces.db` plus imported images; logs live under `logs/`; registry lives
  under `persons/persons.json`.
- Legacy artifacts under `face_recognition_models/` are kept for reference and are not used
  by the current code.

## Notes
- Offline by default; model files must be installed and configured separately.
- Training requires an explicit weights file:
  `uv run python -m face_and_names.train_model --weights-path PATH`.
- Training copies the configured embedding weights into the artifact directory and stores a
  relative path, so prediction does not depend on the process working directory.
- Heavy tasks run via background workers to keep the UI responsive.
