# Training pipeline design (production, headless-first)

Goals
- Train a production-ready classifier using only verified faces (stable person IDs) stored as BLOBs in SQLite.
- Reuse the same embedding backbone as inference; keep model metadata/versioned artifacts under top-level `model/`.
- Provide a headless entry point (CLI/service) decoupled from UI, with clear logging/metrics and reproducible results.

Scope and inputs
- Data source: `face` table; one row per face with `face_crop_blob` BLOB and `person_id`.
- Verification filter: include only rows where `person_id` is set; if a `verified` column exists and is true, respect it; otherwise treat `person_id IS NOT NULL` as verified.
- Images: decode `face_crop_blob` from bytes → RGB PIL image; skip/log corrupt rows.

Embedding
- Backbone: `InceptionResnetV1(pretrained="vggface2")`, eval mode, device auto-select (CUDA if available).
- Preprocess: resize/pad to 160x160 RGB, normalize to [-1, 1].
- Interface: reusable embedder class with `embed_images(List[PIL.Image]) -> np.ndarray`, injectable for tests (dummy embedder).

Classifier
- Default: `StandardScaler` + `SVC(kernel="linear", probability=True, class_weight="balanced", random_state=42)`.
- Allow injectable classifier factory for testing/experimentation (e.g., NearestCentroid/kNN).

Splitting, metrics, logging
- Stratified train/validation split on person_id (per-class aware). Drop classes with <2 samples when a split is required; warn about discarded classes.
- Metrics: overall accuracy on validation split; include counts of classes/samples kept/dropped.
- Log skipped/failed rows and class distribution.

Artifacts (model/)
- Folder: top-level `model/` (created if missing).
- Files:
  - `classifier.pkl` (classifier + scaler bundle)
  - `person_id_mapping.json` (ordered mapping of label indices to person_id)
  - `embedding_config.json` (backbone name, image_size, normalization, device info)
  - `metrics.json` (train/val counts, accuracy, timestamp)
  - `version.txt` (timestamp/uuid + app version)
- Artifacts are deterministic per run (given seeds and data).

Inference compatibility
- Prediction service loads artifacts from `model/`, reconstructs embedder with stored config, and maps classifier outputs back to person_id + confidence.
- Clear errors if artifacts are missing or incompatible.

Testing strategy
- Unit: loader filters verified faces and decodes BLOBs; embedder interface; model IO round-trip.
- Integration (small synthetic): train using dummy embedder + simple classifier to ensure end-to-end save/load/predict paths without heavy models.
