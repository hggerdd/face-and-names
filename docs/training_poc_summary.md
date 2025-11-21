# Legacy Training PoC (release v1.0.0)

Summary of the proof-of-concept training path found in tag `v1.0.0` (file `src/ui/vggface_training_widget.py` plus `DatabaseManager.get_faces_for_training`):

- Data source: `faces` table rows where `name` is non-empty and not `unknown`; uses `face_image` BLOBs. No person IDs; plain text names are labels.
- Preprocessing: each stored face crop is re-run through an in-memory `MTCNN` detector to extract a face tensor; device auto-picks CUDA if available.
- Embedding: `InceptionResnetV1(pretrained="vggface2")` forward pass per face tensor.
- Classifier: `sklearn.svm.SVC(kernel="linear", probability=True)` trained on embeddings; labels encoded via `LabelEncoder`.
- Persistence: saves `mtcnn` and encoder state_dicts (`.pth`), classifier and label encoder (`.joblib`), plus a JSON config into `face_recognition_models/`; also backs up existing files into `face_recognition_models/archive/<timestamp>/`.
- UX: a Qt worker/thread with a progress bar and Cancel button, and a “Clear Predictions” button that wipes predicted names/confidence.

Observed limitations:
- Labels use free-text names rather than stable person IDs; renames break the model mapping.
- No concept of “verified” faces; any non-empty name is used, even low-confidence predictions.
- Retriggering MTCNN on already-cropped faces wastes compute and can fail on tight crops.
- No train/validation split or metrics; no class-balance handling.
- Model location (`face_recognition_models/`) and file naming differ from current `model/` plan; no versioning/metadata beyond a simple JSON.
- Coupled tightly to the UI thread/worker; no headless/CLI path; no reusable training/inference interfaces.
- No error handling for missing/corrupt BLOBs beyond logging; no skip/stats reporting.
