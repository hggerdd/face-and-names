from PyQt6.QtWidgets import QFrame, QVBoxLayout, QLabel, QApplication
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap
import logging

class ImagePreviewWindow(QFrame):
    """Shared image preview component for face widgets"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.Popup |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Tool |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setStyleSheet("""
            QFrame {
                background-color: #2b2b2b;
                border: 1px solid #404040;
                border-radius: 5px;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        
        self.image_label = QLabel()
        layout.addWidget(self.image_label)
        
        self.setMaximumSize(800, 600)

        self.close_timer = QTimer(self)
        self.close_timer.setSingleShot(True)
        self.close_timer.timeout.connect(self.hide_and_clear)
        
    def show_image(self, pixmap, pos):
        self.close_timer.stop()
        
        scaled_pixmap = pixmap.scaled(
            self.maximumSize(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self.image_label.setPixmap(scaled_pixmap)
        self.adjustSize()

        screen = QApplication.primaryScreen().geometry()
        x = min(pos.x() + 10, screen.right() - self.width())
        y = min(pos.y() - self.height() // 2, screen.bottom() - self.height())
        y = max(y, screen.top())
        
        self.move(x, y)
        self.show()
        self.close_timer.start(10000)
        
    def hide_and_clear(self):
        self.hide()
        self.image_label.clear()
        
    def closeEvent(self, event):
        self.close_timer.stop()
        self.image_label.clear()
        super().closeEvent(event)
