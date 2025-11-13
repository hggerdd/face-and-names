import unittest
import sys
import types

if "cv2" not in sys.modules:
    sys.modules["cv2"] = types.SimpleNamespace(
        imencode=lambda *args, **kwargs: (True, None),
        IMWRITE_JPEG_QUALITY=1,
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


from src.core.database import DatabaseManager
from pathlib import Path
import tempfile

class DatabaseSmokeTests(unittest.TestCase):
    def test_can_initialize_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "faces.db"
            manager = DatabaseManager(db_path)
            self.assertTrue(db_path.exists())
            stats = manager.get_database_statistics()
            self.assertIn("Total Faces", stats)

if __name__ == "__main__":
    unittest.main()
