# Face-and-Names v2 – Configuration Outline

Proposed configuration layout and keys (human-readable files). Actual file formats can be TOML/YAML/JSON; keep consistent across global and DB-scoped configs.

## Locations
- Global config: user config dir (e.g., `~/.config/face-and-names/config.toml`).
- DB-scoped config: under DB Root (e.g., `config.toml`), alongside SQLite DB.

## Global Config (examples)
- `ui.theme` (light/dark/system)
- `ui.density` (comfortable/compact)
- `device.preferred` (cpu/gpu/auto)
- `workers.cpu_max` (int), `workers.gpu_max` (int)
- `logging.level` (info/warn/error)
- `logging.retention_days` (int)
- `models.path` (override to model assets)
- `telemetry.offline` (bool, default true)
- `detector.default` (e.g., "yolo")
- `detector.yolo.weights_path` (path to `yolov11n-face.pt`)

## DB-Scoped Config (examples)
- `db_root.path` (recorded for relink detection)
- `import.last_selection` (folders list)
- `import.recursive_default` (bool)
- `import.inline_prediction_default` (bool)
- `thresholds.detector` (float), `thresholds.predict` (float), `thresholds.min_face_size` (pixels)
- `faces.filters.default_scope` (all/latest import/saved folders)
- `faces.filters.default_confidence` (min/max)
- `faces.filters.unnamed_only` (bool)
- `people.groups.default_filters` (list)
- `export.default_format` (json/csv)

## Secrets/PII
- No secrets required by default; configs avoid storing personal data beyond names/aliases/birthdates/notes that are already in DB. If encryption is enabled, store key references securely (outside repo).

## Behavior
- Safe defaults favor offline mode, minimal background load, and conservative thresholds.
- On DB Root move, use stored `db_root.path` plus hash-based relink to detect changes; prompt user to confirm new root.
- Config merges: global settings provide defaults; DB-scoped overrides per database.
