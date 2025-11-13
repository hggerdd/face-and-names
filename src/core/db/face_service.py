from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Iterable, Optional

import cv2

from .context import DatabaseContext


class FaceWriteService:
    """Manages face-related write operations."""

    def __init__(
        self,
        context: DatabaseContext,
        image_id_resolver: Callable[[Path], Optional[int]],
        image_location_resolver: Callable[[Path], tuple[str, str, str]],
    ):
        self._context = context
        self._get_or_create_image_id = image_id_resolver
        self._get_image_location = image_location_resolver

    def save_faces(self, faces: Iterable, include_predictions: bool = False) -> bool:
        return self._persist_faces(faces, include_predictions)

    def save_faces_with_predictions(self, faces: Iterable) -> bool:
        return self._persist_faces(faces, include_predictions=True)

    def _persist_faces(self, faces: Iterable, include_predictions: bool) -> bool:
        faces = list(faces)
        if not faces:
            return False

        try:
            with self._context.transaction() as cursor:
                for face in faces:
                    try:
                        image_id = self._get_or_create_image_id(face.original_file)
                        if image_id is None:
                            continue

                        success, encoded = cv2.imencode(".jpg", face.face_image)
                        if not success or encoded is None:
                            logging.error("Failed to encode face image")
                            continue

                        predicted_name = getattr(face, "predicted_name", None) if include_predictions else None
                        prediction_confidence = (
                            getattr(face, "prediction_confidence", None) if include_predictions else None
                        )

                        cursor.execute(
                            """
                            INSERT INTO faces (
                                image_id,
                                face_image,
                                predicted_name,
                                prediction_confidence,
                                bbox_x,
                                bbox_y,
                                bbox_w,
                                bbox_h
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                image_id,
                                encoded.tobytes(),
                                predicted_name,
                                prediction_confidence,
                                face.bbox_relative[0],
                                face.bbox_relative[1],
                                face.bbox_relative[2],
                                face.bbox_relative[3],
                            ),
                        )

                        cursor.execute(
                            """
                            UPDATE images SET has_faces = TRUE
                            WHERE image_id = ?
                            """,
                            (image_id,),
                        )
                    except Exception as exc:
                        logging.error("Error saving face: %s", exc)
                        continue
            return True
        except Exception as exc:
            logging.error("Error saving faces: %s", exc)
            return False

    def record_no_face_image(self, image_path: Path) -> bool:
        try:
            with self._context.transaction() as cursor:
                image_id = self._get_or_create_image_id(image_path)
                if image_id is None:
                    return False
                cursor.execute(
                    """
                    UPDATE images
                    SET has_faces = FALSE
                    WHERE image_id = ?
                    """,
                    (image_id,),
                )
            return True
        except Exception as exc:
            logging.error("Error recording no-face image: %s", exc)
            return False

    def add_face_annotation(
        self,
        image_id: int,
        name: str,
        bbox: tuple[float, float, float, float],
    ) -> bool:
        try:
            with self._context.transaction() as cursor:
                cursor.execute(
                    """
                    INSERT INTO faces (image_id, name, bbox_x, bbox_y, bbox_w, bbox_h)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (image_id, name, *bbox),
                )
                cursor.execute(
                    """
                    UPDATE images SET has_faces = TRUE
                    WHERE image_id = ?
                    """,
                    (image_id,),
                )
            return True
        except Exception as exc:
            logging.error("Error saving manual face annotation: %s", exc)
            return False
