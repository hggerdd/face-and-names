import tempfile
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch


class DummyEncoded:
    def __init__(self, payload: bytes = b"face-bytes"):
        self._payload = payload

    def tobytes(self) -> bytes:
        return self._payload


if "cv2" not in sys.modules:
    sys.modules["cv2"] = types.SimpleNamespace(
        imencode=lambda *args, **kwargs: (True, DummyEncoded()),
        IMWRITE_JPEG_QUALITY=1,
        resize=lambda image, size, interpolation=None: image,
    )

if "numpy" not in sys.modules:
    sys.modules["numpy"] = types.SimpleNamespace(
        ndarray=list,
        array=lambda *args, **kwargs: args[0] if args else [],
        zeros=lambda *args, **kwargs: 0,
        mean=lambda *args, **kwargs: 0,
        all=lambda *args, **kwargs: False,
        dot=lambda *args, **kwargs: 0,
        linalg=types.SimpleNamespace(norm=lambda *args, **kwargs: 1),
        clip=lambda *args, **kwargs: 0,
    )

if "PIL" not in sys.modules:
    pil_module = types.ModuleType("PIL")
    sys.modules["PIL"] = pil_module

if "PIL.Image" not in sys.modules:
    class _ImageStub:
        def __init__(self, *args, **kwargs):
            self.mode = "RGB"

        def rotate(self, *args, **kwargs):
            return self

        def convert(self, *args, **kwargs):
            return self

        def resize(self, *args, **kwargs):
            return self

        def save(self, *args, **kwargs):
            return None

    image_module = types.ModuleType("PIL.Image")
    image_module.open = lambda *args, **kwargs: _ImageStub()
    sys.modules["PIL.Image"] = image_module

if "PIL.ExifTags" not in sys.modules:
    sys.modules["PIL.ExifTags"] = types.ModuleType("PIL.ExifTags")
    sys.modules["PIL.ExifTags"].TAGS = {}
    sys.modules["PIL.ExifTags"].GPSTAGS = {}

if "PIL.ImageOps" not in sys.modules:
    sys.modules["PIL.ImageOps"] = types.ModuleType("PIL.ImageOps")
    sys.modules["PIL.ImageOps"].grayscale = lambda img: img

if "PIL.ImageEnhance" not in sys.modules:
    enhancer_module = types.ModuleType("PIL.ImageEnhance")

    class _Brightness:
        def __init__(self, image):
            self._image = image

        def enhance(self, _factor):
            return self._image

    enhancer_module.Brightness = _Brightness
    sys.modules["PIL.ImageEnhance"] = enhancer_module


from src.core.database import DatabaseManager  # noqa  E402


class DummyFace:
    def __init__(self, image_path: Path, predicted: str = "Test Person", confidence: float = 0.95):
        self.face_image = [[0]]
        self.original_file = image_path
        self.bbox_relative = (0.1, 0.1, 0.2, 0.2)
        self.predicted_name = predicted
        self.prediction_confidence = confidence


class DatabaseWriteTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        db_path = Path(self._tmpdir.name) / "faces.db"
        self.db = DatabaseManager(db_path)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_import_write_paths(self):
        import_id = self.db.start_new_import(folder_count=3)
        self.assertEqual(import_id, 1)
        self.assertTrue(self.db.update_import_image_count(import_id, 10))

        with self.db.get_connection() as (_, cursor):
            cursor.execute("SELECT folder_count, image_count FROM imports WHERE import_id = ?", (import_id,))
            self.assertEqual(cursor.fetchone(), (3, 10))

    def test_save_faces_with_predictions_persists_rows(self):
        image_path = Path(self._tmpdir.name) / "photos" / "event" / "person.jpg"
        image_path.parent.mkdir(parents=True, exist_ok=True)
        dummy_face = DummyFace(image_path)

        with patch("src.core.db.face_service.cv2.imencode", return_value=(True, DummyEncoded())):
            self.assertTrue(self.db.save_faces_with_predictions([dummy_face]))

        with self.db.get_connection() as (_, cursor):
            cursor.execute("SELECT COUNT(*), COUNT(predicted_name) FROM faces")
            count, predicted_count = cursor.fetchone()
            self.assertEqual(count, 1)
            self.assertEqual(predicted_count, 1)

            cursor.execute("SELECT has_faces FROM images LIMIT 1")
            self.assertEqual(cursor.fetchone()[0], 1)

    def test_save_image_metadata_replaces_existing_entries(self):
        image_path = Path(self._tmpdir.name) / "photos" / "trip" / "img.jpg"
        image_id = self.db.get_or_create_image_id(image_path)
        self.assertIsNotNone(image_id)

        first_meta = {"EXIF_DateTime": ("exif", "2020:01:01 10:00:00")}
        self.assertTrue(self.db.save_image_metadata(image_id, first_meta))

        updated_meta = {
            "EXIF_DateTime": ("exif", "2021:02:02 11:00:00"),
            "IPTC_Title": ("iptc", "Vacation"),
        }
        self.assertTrue(self.db.save_image_metadata(image_id, updated_meta))

        with self.db.get_connection() as (_, cursor):
            cursor.execute(
                "SELECT meta_key, meta_value FROM image_metadata WHERE image_id = ? ORDER BY meta_key",
                (image_id,),
            )
            rows = cursor.fetchall()
            self.assertEqual(rows, [("EXIF_DateTime", "2021:02:02 11:00:00"), ("IPTC_Title", "Vacation")])


if __name__ == "__main__":
    unittest.main()
