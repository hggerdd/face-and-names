from PyQt6.QtWidgets import QFrame, QVBoxLayout, QLabel, QApplication
from PyQt6.QtCore import Qt, QTimer, QSize
from PyQt6.QtGui import QPixmap
from .image_utils import ImageProcessor
from .font_config import FontConfig
import logging

class ImagePreviewWindow(QFrame):
    """Shared image preview component for face widgets"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        # Only set these flags if no parent is provided (for popup previews)
        if parent is None:
            self.setWindowFlags(
                Qt.WindowType.Tool |
                Qt.WindowType.FramelessWindowHint |
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
        self.image_label.setFont(FontConfig.get_default_font())
        layout.addWidget(self.image_label)
        
        self.info_label = QLabel()
        self.info_label.setFont(FontConfig.get_label_font())
        self.info_label.setStyleSheet("color: white;")
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.info_label)
        
        self.setMaximumSize(800, 600)

        self.close_timer = QTimer(self)
        self.close_timer.setSingleShot(True)
        self.close_timer.timeout.connect(self.hide_and_clear)
        
    def show_image(self, pixmap, pos):
        """Show preview with scaled image."""
        self.close_timer.stop()
        
        # Scale the pixmap if needed
        scaled_pixmap = ImageProcessor.scale_pixmap(
            pixmap,
            QSize(self.maximumSize()),
            keep_aspect=True
        )
        
        self.image_label.setPixmap(scaled_pixmap)
        
        # Update info label with image dimensions
        if scaled_pixmap:
            original_size = pixmap.size()
            scaled_size = scaled_pixmap.size()
            self.info_label.setText(
                f"Original: {original_size.width()}x{original_size.height()} "
                f"Scaled: {scaled_size.width()}x{scaled_size.height()}"
            )
        
        self.adjustSize()

        # Position the preview window
        screen = QApplication.primaryScreen().geometry()
        x = min(pos.x() + 10, screen.right() - self.width())
        y = min(pos.y() - self.height() // 2, screen.bottom() - self.height())
        y = max(y, screen.top())
        
        self.move(x, y)
        self.show()
        self.close_timer.start(10000)  # Auto-hide after 10 seconds
        
    def hide_and_clear(self):
        """Hide window and clear image."""
        self.hide()
        self.image_label.clear()
        self.info_label.clear()

    def closeEvent(self, event):
        """Handle window close event."""
        self.close_timer.stop()
        self.image_label.clear()
        self.info_label.clear()
        super().closeEvent(event)
