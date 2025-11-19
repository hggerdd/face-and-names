# Face Detection & Recognition Pipeline

Reference description of the working pipeline; use this as a foundation for the next iteration.

## Inputs
- Image path(s) selected from a folder (optionally recursive).
- YOLOv11 face model weights `yolov11n-face.pt`.
- Optional recognition assets in `face_recognition_models/`:
  - `mtcnn_complete.pth` (state_dict or module)
  - `face_encoder_complete.pth` (state_dict or module; InceptionResnetV1)
  - `face_classifier.joblib` (sklearn classifier)
  - `label_encoder.joblib` (sklearn label encoder)

## Preprocessing
- Load image with EXIF orientation correction; OpenCV BGR data (`correct_image_orientation` uses PIL rotation when EXIF says so).
- Detector padding: expand YOLO bbox by configurable percent before cropping; clamp to image bounds.
- Face crop normalization (shared for training/inference):
  - Convert BGR→RGB.
  - Resize to 160×160.
  - Normalize: `(x - 127.5) / 128.0`.
  - Convert to tensor CHW float32.

## Detection Flow
1) For each image: skip if already processed (DB lookup by `(base_folder, sub_folder, filename)`).
2) Extract EXIF/IPTC metadata; prepare DB image row and thumbnail (JPEG, max width 500) inside the same transaction.
3) Run YOLO on image; for each box:
   - Apply padding and clamp to image bounds.
   - Compute absolute bbox `(x, y, w, h)` and relative bbox `(x/width, y/height, w/width, h/height)`.
   - Crop face region (BGR).
   - Optionally run recognition (below).
4) If faces found: store face rows with bbox, encoded JPEG bytes, predicted_name/confidence if available; mark image has_faces.
5) If no faces: record image with has_faces = FALSE; still keep thumbnail + metadata.

## Recognition Flow (optional)
- Initialization:
  - Load MTCNN (if `mtcnn_complete.pth` exists) for compatibility; core detection currently YOLO-based, so MTCNN is mainly for legacy.
  - Load InceptionResnetV1 with state_dict or full module; move to CUDA if available.
  - Load sklearn classifier + label encoder.
- Per face:
  - Preprocess crop → tensor.
  - Forward through encoder to get embedding.
  - Classifier `predict_proba` → label + confidence.
  - Accept prediction only if confidence ≥ UI threshold; otherwise leave predicted_name empty.
- Output stored alongside face record.

## Outputs (Database)
- `imports`: rows per run (folder_count, image_count).
- `images`: base_folder, sub_folder, filename, import_id, has_faces flag, processed_date.
- `thumbnails`: JPEG thumbnail per image_id.
- `faces`: image_id, face_image (JPEG), bbox (x,y,w,h), predicted_name, prediction_confidence, cluster_id, name (manual).
- `image_metadata`: EXIF/IPTC key/value/type per image_id.

## Performance & UX Considerations
- Heavy models loaded lazily; detection runs in a QThread.
- Progress signals for file/folder counts; cancel stops loop early; per-folder reuse of detector to avoid reload overhead.
- Thumbnail and image detail caches avoid repeat DB BLOB fetches.
- Async loaders for prediction review to keep UI responsive on large sets; virtualized grid to render visible items only.
- Startup TODO: check presence of `yolov11n-face.pt` and auto-load on app start.

## Known Good Behaviors
- Handles flat and nested folder imports via `_get_image_location` using `(base_root, sub_folder, filename)` to avoid collisions.
- Works with state_dict or serialized modules for model artifacts (backward compatible).
- Uses shared preprocessing for detection-time prediction and batch prediction to avoid drift from training.
