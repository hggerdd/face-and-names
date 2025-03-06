import sys
from PyQt6.QtWidgets import QApplication
from src.ui.main_window import MainWindow
from src.core.database import DatabaseManager  # We'll create this next
import logging
from pathlib import Path

def setup_logging():
    """Setup logging configuration."""
    logging.basicConfig(
        level=logging.DEBUG,
        # level=logging.INFO,
        format='%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
        handlers=[
            logging.FileHandler('face_recognition.log'),
            logging.StreamHandler()
        ]
    )

def main():
    setup_logging()
    logging.info("Starting Face Recognition System")
    
    try:
        app = QApplication(sys.argv)
        
        # Initialize database
        db_path = Path("faces.db")
        db_manager = DatabaseManager(db_path)
        
        # Create and show main window
        window = MainWindow(db_manager)
        window.show()
        
        sys.exit(app.exec())
        
    except Exception as e:
        logging.error("Application failed to start", exc_info=True)
        sys.exit(1)
    finally:
        logging.info("Application closed")

if __name__ == "__main__":
    main() 