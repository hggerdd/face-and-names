-- SQLite schema for Face-and-Names v2
-- Source of truth: docs/schema.md / docs/plan.md

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_version (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS import_session (
    id INTEGER PRIMARY KEY,
    import_date DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    folder_count INTEGER NOT NULL,
    image_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS image (
    id INTEGER PRIMARY KEY,
    import_id INTEGER NOT NULL REFERENCES import_session(id) ON DELETE CASCADE,
    relative_path TEXT NOT NULL,
    sub_folder TEXT NOT NULL,
    filename TEXT NOT NULL,
    content_hash BLOB NOT NULL,
    perceptual_hash INTEGER NOT NULL,
    width INTEGER NOT NULL,
    height INTEGER NOT NULL,
    orientation_applied INTEGER NOT NULL DEFAULT 0,
    has_faces INTEGER NOT NULL DEFAULT 0,
    thumbnail_blob BLOB NOT NULL,
    size_bytes INTEGER NOT NULL,
    UNIQUE (content_hash)
);

CREATE INDEX IF NOT EXISTS idx_image_import_id ON image(import_id);
CREATE INDEX IF NOT EXISTS idx_image_perceptual_hash ON image(perceptual_hash);

CREATE TABLE IF NOT EXISTS metadata (
    id INTEGER PRIMARY KEY,
    image_id INTEGER NOT NULL REFERENCES image(id) ON DELETE CASCADE,
    key TEXT NOT NULL,
    type TEXT NOT NULL,
    value TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_metadata_image_id_key ON metadata(image_id, key);

CREATE TABLE IF NOT EXISTS face (
    id INTEGER PRIMARY KEY,
    image_id INTEGER NOT NULL REFERENCES image(id) ON DELETE CASCADE,
    bbox_x REAL NOT NULL,
    bbox_y REAL NOT NULL,
    bbox_w REAL NOT NULL,
    bbox_h REAL NOT NULL,
    bbox_rel_x REAL NOT NULL,
    bbox_rel_y REAL NOT NULL,
    bbox_rel_w REAL NOT NULL,
    bbox_rel_h REAL NOT NULL,
    face_crop_blob BLOB NOT NULL,
    face_detection_index REAL,
    cluster_id INTEGER,
    person_id INTEGER REFERENCES person(id),
    predicted_person_id INTEGER REFERENCES person(id),
    prediction_confidence REAL,
    provenance TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_face_image_id ON face(image_id);
CREATE INDEX IF NOT EXISTS idx_face_cluster_id ON face(cluster_id);
CREATE INDEX IF NOT EXISTS idx_face_person_id ON face(person_id);
CREATE INDEX IF NOT EXISTS idx_face_predicted_person_id ON face(predicted_person_id);

CREATE TABLE IF NOT EXISTS person (
    id INTEGER PRIMARY KEY,
    primary_name TEXT NOT NULL UNIQUE,
    first_name TEXT NOT NULL DEFAULT '',
    last_name TEXT NOT NULL DEFAULT '',
    short_name TEXT,
    birthdate TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS person_alias (
    id INTEGER PRIMARY KEY,
    person_id INTEGER NOT NULL REFERENCES person(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    UNIQUE (person_id, name, kind)
);

CREATE INDEX IF NOT EXISTS idx_person_alias_person_id ON person_alias(person_id);

CREATE TABLE IF NOT EXISTS "group" (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    parent_group_id INTEGER REFERENCES "group"(id),
    description TEXT,
    color TEXT
);

CREATE TABLE IF NOT EXISTS person_group (
    person_id INTEGER NOT NULL REFERENCES person(id) ON DELETE CASCADE,
    group_id INTEGER NOT NULL REFERENCES "group"(id) ON DELETE CASCADE,
    PRIMARY KEY (person_id, group_id)
);

CREATE TABLE IF NOT EXISTS stats (
    id INTEGER PRIMARY KEY,
    computed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    payload TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY,
    timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actor TEXT,
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id INTEGER,
    details TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp ON audit_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_log_action ON audit_log(action);
CREATE INDEX IF NOT EXISTS idx_audit_log_entity_type ON audit_log(entity_type);
