from __future__ import annotations

from pathlib import Path

from PIL import Image

from face_and_names.models.db import initialize_database
from face_and_names.services.ingest_service import IngestOptions, IngestService
from face_and_names.services.people_service import PeopleService
from face_and_names.services.person_registry import default_registry_path


def _create_dummy_image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (100, 100), color="blue")
    img.save(path, format="JPEG")


def test_e2e_ingest_to_person_assignment(tmp_path: Path) -> None:
    # 1. Setup Environment
    db_root = tmp_path / "dbroot"
    db_path = db_root / "faces.db"
    photos = db_root / "photos"
    _create_dummy_image(photos / "me.jpg")

    # Initialize App Context manually to control DB path
    conn = initialize_database(db_path)
    registry_path = default_registry_path(db_root)
    people_service = PeopleService(conn, registry_path=registry_path)

    # 2. Ingest
    ingest = IngestService(db_root, conn)
    progress = ingest.start_session([photos], options=IngestOptions(recursive=True))
    assert progress.processed == 1

    # 3. Verify Image in DB
    row = conn.execute("SELECT id, filename FROM image").fetchone()
    assert row is not None
    image_id, filename = row
    assert filename == "me.jpg"

    # 4. Simulate Face Detection (insert manual face since we don't have models in test env)
    conn.execute(
        """
        INSERT INTO face (
            image_id, bbox_x, bbox_y, bbox_w, bbox_h, bbox_rel_x, bbox_rel_y, bbox_rel_w, bbox_rel_h,
            face_crop_blob, provenance
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (image_id, 10.0, 10.0, 20.0, 20.0, 0.1, 0.1, 0.2, 0.2, b"fakecrop", "detected"),
    )
    face_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()

    # 5. Create Person
    people_service = PeopleService(conn, registry_path=registry_path)
    person_id = people_service.create_person("John", "Doe")

    # 6. Assign Person to Face (mimic UI action)
    # In the real app, this happens via FaceRepository update
    from face_and_names.models.repositories import FaceRepository

    face_repo = FaceRepository(conn)
    face_repo.update_person(face_id, person_id)
    conn.commit()

    # 7. Verify Assignment
    stored_pid = conn.execute("SELECT person_id FROM face WHERE id = ?", (face_id,)).fetchone()[0]
    assert stored_pid == person_id

    # 8. Verify Person Stats (optional, if we had stats service running)
    # For now, just checking the link is enough for E2E
