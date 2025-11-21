from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image

from face_and_names.models.db import initialize_database
from face_and_names.services.clustering_service import ClusteringOptions, ClusteringService


def _insert_import_and_faces(conn, db_root: Path) -> None:
    conn.execute("INSERT INTO import_session (folder_count, image_count) VALUES (?, ?)", (1, 0))
    import_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
    conn.execute(
        """
        INSERT INTO image (
            import_id, relative_path, sub_folder, filename,
            content_hash, perceptual_hash, width, height,
            orientation_applied, has_faces, thumbnail_blob, size_bytes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            import_id,
            "photos/img.jpg",
            "photos",
            "img.jpg",
            b"\x00" * 32,
            1,
            10,
            10,
            1,
            1,
            b"\x00\x01",
            123,
        ),
    )
    image_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])

    def add_face(color: str, sub_folder: str = "photos") -> int:
        buf = BytesIO()
        Image.new("RGB", (10, 10), color=color).save(buf, format="JPEG")
        data = buf.getvalue()
        conn.execute(
            """
            INSERT INTO face (
                image_id, bbox_x, bbox_y, bbox_w, bbox_h,
                bbox_rel_x, bbox_rel_y, bbox_rel_w, bbox_rel_h,
                face_crop_blob, cluster_id, person_id, predicted_person_id,
                prediction_confidence, provenance
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                image_id,
                1.0,
                1.0,
                2.0,
                2.0,
                0.1,
                0.1,
                0.2,
                0.2,
                data,
                None,
                None,
                None,
                None,
                "detected",
            ),
        )
        return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])

    # Two red (should cluster together) and one blue (separate)
    add_face("red")
    add_face("red")
    add_face("blue")
    conn.commit()


def test_cluster_faces_groups_similar_phash(tmp_path: Path) -> None:
    conn = initialize_database(tmp_path / "faces.db")
    _insert_import_and_faces(conn, tmp_path)

    service = ClusteringService(conn)
    results = service.cluster_faces(ClusteringOptions(eps=0.05, min_samples=1))

    assert len(results) >= 2  # one cluster + noise or second cluster
    clusters = {c.cluster_id: [f.face_id for f in c.faces] for c in results if not c.is_noise}
    # Expect two faces in first cluster
    sizes = sorted(len(v) for v in clusters.values())
    assert sizes[0] >= 2

    # Cluster IDs persisted
    persisted = conn.execute("SELECT cluster_id FROM face").fetchall()
    assert all(row[0] is not None for row in persisted)
