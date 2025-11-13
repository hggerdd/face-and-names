from PyQt6.QtCore import QThread, pyqtSignal


class ThumbnailLoadWorker(QThread):
    loaded = pyqtSignal(int, dict, list)
    error = pyqtSignal(int, str)

    def __init__(self, db_manager, image_id: int):
        super().__init__()
        self.db_manager = db_manager
        self.image_id = image_id

    def run(self):
        try:
            details = self.db_manager.get_image_details(self.image_id)
            metadata = self.db_manager.get_image_metadata_entries(self.image_id)
            if details is None:
                self.error.emit(self.image_id, "No details found")
                return
            if self.isInterruptionRequested():
                return
            self.loaded.emit(self.image_id, details, metadata)
        except Exception as exc:
            self.error.emit(self.image_id, str(exc))
