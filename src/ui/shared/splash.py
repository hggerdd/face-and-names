from PyQt6.QtWidgets import QSplashScreen, QApplication
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap, QFont
import time


class StartupSplash(QSplashScreen):
    """Lightweight splash screen that appears quickly while heavy resources load."""

    def __init__(self):
        pixmap = QPixmap(400, 200)
        pixmap.fill(Qt.GlobalColor.white)
        super().__init__(pixmap)
        self.setFont(QFont("Segoe UI", 10))
        self.showMessage(
            "Loading Face & Names...",
            Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignBottom,
            Qt.GlobalColor.darkGray,
        )
        self._shown_at = time.monotonic()

    def ensure_minimum_display(self, minimum_ms: int = 100):
        elapsed_ms = int((time.monotonic() - self._shown_at) * 1000)
        remaining = max(0, minimum_ms - elapsed_ms)
        if remaining:
            loop = QTimer()
            loop.setSingleShot(True)
            loop.start(remaining)
            while loop.remainingTime() > 0:
                QApplication.processEvents()
