import logging
import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication

if __package__ in (None, ""):
    # Allow running via `python src/main.py` by ensuring project root is importable.
    sys.path.append(str(Path(__file__).resolve().parent.parent))

from src.core.database import DatabaseManager
from src.ui.main_window import MainWindow
from src.ui.shared.font_config import FontConfig


def setup_logging() -> None:
    """Configure application logging (file + console)."""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_dir / "face_recognition.log"),
            logging.StreamHandler(sys.stdout),
        ],
    )

    logging.getLogger("PIL").setLevel(logging.INFO)
    logging.getLogger("tensorflow").setLevel(logging.INFO)
    logging.info("Logging initialized")


def _create_window() -> MainWindow:
    """Instantiate the main window with a shared DatabaseManager."""
    db_path = Path("faces.db")
    db_manager = DatabaseManager(db_path)
    return MainWindow(db_manager)


def main() -> int:
    """Application entrypoint that sets up logging, fonts, and UI."""
    setup_logging()
    logging.info("Starting Face Recognition System")

    try:
        app = QApplication(sys.argv)
        FontConfig.initialize()
        logging.info("Font configuration initialized")

        window = _create_window()
        window.show()
        return app.exec()
    except Exception as exc:
        logging.critical("Application failed to start", exc_info=True)
        logging.critical("Fatal error: %s", exc)
        return 1
    finally:
        logging.info("Application closed")


if __name__ == "__main__":
    sys.exit(main())
