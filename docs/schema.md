# Face-and-Names v2 – Proposed SQLite Schema

This document proposes the initial SQLite schema aligned to `docs/requirements.md`, `docs/plan.md`, and `docs/architecture.md`. DDL is illustrative; adjust naming as needed. Media (thumbnails/crops) are stored on disk under the DB Root cache to avoid DB bloat; paths are recorded. All image paths are relative to the DB Root.

## Tables

### import_session
- `id` INTEGER PRIMARY KEY
- `import_date` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
- `folder_count` INTEGER NOT NULL
- `image_count` INTEGER NOT NULL DEFAULT 0

### image
- `id` INTEGER PRIMARY KEY
- `import_id` INTEGER NOT NULL REFERENCES import_session(id) ON DELETE CASCADE
- `relative_path` TEXT NOT NULL -- full relative path including filename
- `sub_folder` TEXT NOT NULL -- folder portion relative to DB Root
- `filename` TEXT NOT NULL
- `content_hash` BLOB NOT NULL -- SHA-256 bytes
- `perceptual_hash` INTEGER NOT NULL -- 64-bit pHash stored as unsigned integer
- `width` INTEGER NOT NULL
- `height` INTEGER NOT NULL
- `orientation_applied` INTEGER NOT NULL DEFAULT 0 -- EXIF correction applied flag
- `has_faces` INTEGER NOT NULL DEFAULT 0
- `thumbnail_path` TEXT NOT NULL -- path under cache for thumbnail JPEG
- `size_bytes` INTEGER NOT NULL
- Unique constraint on (`content_hash`) to prevent duplicate ingest; index on `perceptual_hash` for near-duplicate search; index on `import_id`.

### metadata
- `id` INTEGER PRIMARY KEY
- `image_id` INTEGER NOT NULL REFERENCES image(id) ON DELETE CASCADE
- `key` TEXT NOT NULL
- `type` TEXT NOT NULL -- e.g., EXIF/IPTC
- `value` TEXT NOT NULL
- Index on (`image_id`, `key`).

### face
- `id` INTEGER PRIMARY KEY
- `image_id` INTEGER NOT NULL REFERENCES image(id) ON DELETE CASCADE
- `bbox_x` REAL NOT NULL
- `bbox_y` REAL NOT NULL
- `bbox_w` REAL NOT NULL
- `bbox_h` REAL NOT NULL
- `bbox_rel_x` REAL NOT NULL
- `bbox_rel_y` REAL NOT NULL
- `bbox_rel_w` REAL NOT NULL
- `bbox_rel_h` REAL NOT NULL
- `face_crop_path` TEXT NOT NULL -- path under cache for face JPEG
- `cluster_id` INTEGER
- `person_id` INTEGER REFERENCES person(id)
- `predicted_person_id` INTEGER REFERENCES person(id)
- `prediction_confidence` REAL
- `provenance` TEXT NOT NULL -- manual/predicted
- Indexes on `image_id`, `cluster_id`, `person_id`, `predicted_person_id`.

### person
- `id` INTEGER PRIMARY KEY
- `primary_name` TEXT NOT NULL UNIQUE
- `birthdate` TEXT -- ISO date string
- `notes` TEXT

### person_alias
- `id` INTEGER PRIMARY KEY
- `person_id` INTEGER NOT NULL REFERENCES person(id) ON DELETE CASCADE
- `name` TEXT NOT NULL
- `kind` TEXT NOT NULL -- alias or short
- Unique constraint on (`person_id`, `name`, `kind`); index on `person_id`.

### group
- `id` INTEGER PRIMARY KEY
- `name` TEXT NOT NULL UNIQUE
- `parent_group_id` INTEGER REFERENCES "group"(id)
- `description` TEXT
- `color` TEXT -- optional tag color

### person_group
- `person_id` INTEGER NOT NULL REFERENCES person(id) ON DELETE CASCADE
- `group_id` INTEGER NOT NULL REFERENCES "group"(id) ON DELETE CASCADE
- Primary key (`person_id`, `group_id`)

### stats
- `id` INTEGER PRIMARY KEY
- `computed_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
- `payload` TEXT NOT NULL -- JSON blob of aggregates for Data Insights

### audit_log
- `id` INTEGER PRIMARY KEY
- `timestamp` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
- `actor` TEXT -- user/system identifier
- `action` TEXT NOT NULL -- rename/merge/delete/accept_prediction/etc.
- `entity_type` TEXT NOT NULL -- person/face/image/etc.
- `entity_id` INTEGER
- `details` TEXT NOT NULL -- JSON payload for traceability
- Index on `timestamp`, `action`, `entity_type`.

## Media Cache Layout (under DB Root)
- `cache/thumbnails/{import_id}/{image_id}.jpg`
- `cache/faces/{import_id}/{face_id}.jpg`
- Paths stored in DB as relative cache paths; rebuild tools regenerate on demand.

## Identity and Relink
- Primary dedupe key: `content_hash` (SHA-256 of oriented image bytes).
- Secondary near-duplicate surface: `perceptual_hash` with Hamming distance search.
- Relink strategy when DB Root moves: scan for matching `content_hash` within new root; if missing, fallback to perceptual hash + filename/subfolder hints; log conflicts.

## Notes
- All paths stored relative to DB Root (FR-002).
- Use `PRAGMA foreign_keys = ON`.
- Consider `WITHOUT ROWID` only after profiling; default rowid tables for simplicity.
- BLOB storage in DB is avoided for thumbnails/crops to keep DB size manageable; switching to BLOB is possible if required by deployment constraints.
- Bounding boxes stored as numeric columns to simplify filtering/querying (e.g., min face size enforcement) and avoid JSON parsing overhead.
- Aliases/short names are normalized into `person_alias` to support uniqueness checks and merges without string parsing.
