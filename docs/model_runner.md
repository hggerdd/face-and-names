# Face-and-Names v2 – Model Runner Interface (Conceptual)

Defines the contract for pluggable recognition models. Detection is covered separately by the detector adapter.

## Goals
- Swap recognition backends without UI changes (NFR-007).
- Support CPU/GPU selection with fallback (FR-060, FR-063).
- Provide metadata for diagnostics (FR-048) and self-test (FR-057).

## Interface (conceptual)
- `load(device, options) -> ModelHandle`  
  Options: threshold defaults, batch size, warm-up.
- `warmup(handle)` optionally precomputes caches.
- `predict_embeddings(handle, faces) -> list[Embedding]` *or* `predict_ids(handle, faces) -> list[Prediction]` depending on runner type.
- `metadata(handle) -> ModelMetadata` where metadata includes:
  - `name`, `version`, `device`, `input_size`, `threshold_default`, `backend` (torch/onnx), `loaded_at`.
- `available() -> bool` to signal missing assets gracefully.
- `close(handle)` to free resources.

## Inputs/Outputs
- Input face: preprocessed tensor or image crop (normalized, resized).
- Prediction: either embedding vector (for downstream classification) or `(person_id, confidence)`.
- Thresholding: runner can return raw scores; PredictionService applies thresholds; per-model defaults are exposed via metadata.

## Error Handling
- Missing model files → runner reports unavailable; PredictionService surfaces “model unavailable” without breaking flows (FR-063).
- Inference errors logged with model name/version/device; worker retries according to ingest/batch job policies.

## Warm-up / Batching
- Runner supports batch inference to reduce overhead; exposed `batch_size` in options.
- Warm-up avoids first-call latency; triggered at job start or on demand.

## Device Selection
- Accepts `device` hint (cpu/gpu/auto). If GPU unavailable or fails, runner falls back to CPU and reports fallback in metadata/logs (FR-060).

## Self-Test
- Runner provides a lightweight self-test hook or supports known sample input to validate outputs for diagnostics (FR-057).

## Model Slots
- Allow multiple runner registrations keyed by name; PredictionService picks the active runner based on config or user choice.
