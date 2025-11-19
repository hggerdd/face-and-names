# Face-and-Names v2 – Kickoff Checklist (Pre-Code)

Use this to move from planning to initial scaffolding. No coding yet; this lists the first concrete actions once ready to implement.

1) Confirm detector and recognition backends for v2:
   - Detector: YOLO-based (matching `yolov11n-face.pt`) as default; optionally keep MTCNN fallback. Verify licensing and performance.
   - Recognition: choose runner using existing weights under `face_recognition_models/` (torch) or convert to ONNX if desired.
2) Pin dependency versions and create `pyproject.toml`; generate `uv.lock`.
3) Create initial project structure per `docs/directory_structure.md` with empty modules and wiring stubs (no business logic).
4) Embed SQLite schema DDL from `docs/schema.md` (numeric bbox, aliases table) and enable `PRAGMA foreign_keys = ON`.
5) Implement config file formats/namespaces (global + DB-scoped) per `docs/config.md`; set offline defaults.
6) Scaffold logging setup using JSON lines + rotation per `docs/logging.md`; hook into PyQt app entry.
7) Define worker controller skeleton per `docs/workers.md`; wire progress/cancel signals for PyQt.
8) Build PyQt main window layout per `docs/ui_wireframes.md` and `docs/ui_todo.md` with placeholder views and shared face tile widget shell.
9) Add testing harness basics: `pytest` config, sample fixtures folder, coverage/lint commands (ruff) per `docs/testing.md`.
10) Document model asset locations and expected filenames in config (detector/recognition weights).
11) Create traceability matrix skeleton mapping requirement IDs to planned tests and components.
12) Sanity-check performance targets and resource caps against chosen detector/model on target hardware; adjust thresholds/defaults if needed.
