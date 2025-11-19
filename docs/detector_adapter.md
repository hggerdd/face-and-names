# Face-and-Names v2 – Detector Adapter (Conceptual)

Defines the contract for face detection backends (e.g., YOLO default, MTCNN optional). Aligns with ingestion and prediction pipelines.

## Goals
- Consistent bbox output (absolute and relative), with padding/clamping (FR-010).
- Reuse detector instances within batches to reduce reloads (FR-013).
- Support device selection/fallback similar to model runners (FR-060).

## Interface (conceptual)
- `load(device, options) -> DetectorHandle`
- `warmup(handle)`
- `detect_batch(handle, images: list[Image]) -> list[list[FaceDetection]]]`
- `metadata(handle) -> DetectorMetadata` (name, version, device, input_size, backend, threshold defaults).
- `available() -> bool`
- `close(handle)`

## FaceDetection structure
- `bbox_abs`: (x, y, w, h) in pixels, padded/clamped to image bounds.
- `bbox_rel`: (x, y, w, h) normalized [0,1] relative to image dimensions.
- `confidence`: float score.
- `crop`: image crop or reference for saving JPEG.

## Options
- Thresholds, min face size, padding amount, batch size (if supported), device preference.

## Error Handling
- Log errors with image id/path, detector name/version/device; worker marks failed items for retry/skip.
- If detector unavailable, ingest can proceed without detection only if explicitly allowed; otherwise, clear error surfaced to user.

## Performance
- Encourage batch processing where supported; reuse loaded handle across batch to reduce setup overhead.
- Warm-up to mitigate first-call latency.
