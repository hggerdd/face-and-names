# Face-and-Names v2 – Dependency Choices (Draft)

Target Python 3.11; manage with `uv`. Finalize versions when creating `pyproject.toml`.

## Runtime
- UI: `PyQt6` (or `PyQt5` fallback if deployment requires). Include Qt SVG/webengine only if needed.
- Imaging/EXIF: `Pillow` (for load/resize/orientation); `exifread` or `piexif` for robust EXIF/IPTC extraction if Pillow tags are insufficient.
- Hashing: `hashlib` (stdlib) for SHA-256; `ImageHash` (pHash) for perceptual hash.
- Detection (default): YOLO via `ultralytics` using the bundled `yolov11n-face.pt` weights. Alternate: `facenet-pytorch` (MTCNN) as optional extra.
- Recognition: model runner interface; options:
  - `torch` for embedding models (e.g., face encoder pth)
  - `onnxruntime` (CPU/GPU) if using ONNX models
- Clustering: `scikit-learn` for DBSCAN/KMeans/Agglomerative.
- Data access: stdlib `sqlite3`; optional light query helper (not an ORM) if needed.

## Tooling
- Lint/format: `ruff`
- Tests: `pytest`
- Type checking: `mypy` (optional)
- Coverage: `coverage` (optional)

## Packaging
- `pyproject.toml` with explicit dependency pins/constraints; `uv lock` to produce `uv.lock`.

## Notes
- Avoid pulling heavy optional Qt modules unless required (keeps startup lean).
- Detector/recognition backends should be pluggable per the model runner interface; do not hardcode a single backend.
- Ensure CPU-first defaults; GPU optional when available and selected.
