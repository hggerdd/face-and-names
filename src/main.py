import sys
import logging
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from .ui.main_window import MainWindow
from .ui.shared.font_config import FontConfig

def setup_logging():
    # Create logs directory if it doesn't exist
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    # Configure logging to both file and console
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_dir / "face_recognition.log"),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    # Add specific loggers for different components if needed
    logging.getLogger('PIL').setLevel(logging.INFO)  # Reduce Pillow debug messages
    logging.getLogger('tensorflow').setLevel(logging.INFO)  # Reduce TF debug messages
    
    logging.info("Logging initialized")

def main():
    setup_logging()
    
    try:
        app = QApplication(sys.argv)
        
        # Initialize font configuration before creating any widgets
        FontConfig.initialize()
        logging.info("Font configuration initialized")
        
        window = MainWindow()
        window.show()
        return app.exec()
    except Exception as e:
        logging.critical(f"Application failed to start: {e}", exc_info=True)
        return 1

if __name__ == "__main__":
    sys.exit(main())
