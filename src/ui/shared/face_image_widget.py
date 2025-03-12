from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QFont, QPainter, QPen, QColor, QPixmap, QImage
from PIL import Image, ImageOps, ImageEnhance
import io
import sqlite3
import logging
from .image_utils import ImageProcessor
from .image_preview import ImagePreviewWindow

class FaceImageWidget(QWidget):
    """A widget that displays a face image with current and predicted names."""
    clicked = pyqtSignal(int)  # Emits face_id when clicked
    rightClicked = pyqtSignal(int, object)  # Emits face_id and global position
    
    # Static variables for shared preview handling
    _current_preview = None
    _shared_preview_window = None

    def __init__(self, face_id: int, image_data: bytes, name: str = None, 
                 predicted_name: str = None, face_size: int = 100, 
                 active: bool = True, prediction_confidence: float = None, 
                 parent=None, db_manager=None):
        super().__init__(parent)
        self.face_id = face_id
        self.face_size = face_size
        self.active = active
        self.image_data = image_data
        self.name = name
        self.predicted_name = predicted_name
        self.prediction_confidence = prediction_confidence
        self.db_manager = db_manager
        self.preview_window = None  # Only create when needed for right-click preview
        self.setup_ui()

    @classmethod
    def close_all_previews(cls):
        """Close any open preview window"""
        if cls._shared_preview_window and cls._shared_preview_window.isVisible():
            cls._shared_preview_window.hide_and_clear()
            cls._current_preview = None

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(2)
        layout.setContentsMargins(5, 5, 5, 5)

        # Create image container with fixed width
        self.image_container = QWidget(self)
        self.image_container.setFixedWidth(self.face_size)
        image_layout = QVBoxLayout(self.image_container)
        image_layout.setContentsMargins(0, 0, 0, 0)
        image_layout.setSpacing(0)
        
        # Create and setup main image label
        self.image_label = self._create_image_label()
        image_layout.addWidget(self.image_label)

        # Add overlaid info label (face ID)
        info_label = self._create_info_label()
        image_layout.addWidget(info_label)
        image_layout.setAlignment(Qt.AlignmentFlag.AlignBottom)
        
        layout.addWidget(self.image_container, alignment=Qt.AlignmentFlag.AlignHCenter)

        # Add fixed-width container for name labels
        labels_container = QWidget(self)
        labels_container.setFixedWidth(self.face_size)
        labels_layout = QVBoxLayout(labels_container)
        labels_layout.setContentsMargins(0, 0, 0, 0)
        labels_layout.setSpacing(2)

        # Add name label if provided
        if self.name:
            name_label = QLabel(f"Name: {self.name}", self)
            name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            name_label.setWordWrap(True)
            name_label.setStyleSheet("QLabel { background-color: rgba(220, 220, 220, 128); }")
            labels_layout.addWidget(name_label)

        # Add predicted name if provided
        if self.predicted_name:
            confidence = getattr(self, 'prediction_confidence', None)
            conf_text = f" ({confidence:.0%})" if confidence else ""
            pred_label = QLabel(f"Predicted: {self.predicted_name}{conf_text}", self)
            pred_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            pred_label.setWordWrap(True)
            pred_label.setStyleSheet("QLabel { background-color: rgba(200, 200, 255, 128); }")
            labels_layout.addWidget(pred_label)

        layout.addWidget(labels_container, alignment=Qt.AlignmentFlag.AlignHCenter)

    def _create_image_label(self) -> QLabel:
        """Create the image label with face thumbnail."""
        label = QLabel(self)
        if isinstance(self.image_data, (bytes, bytearray)):
            pixmap = ImageProcessor.create_pixmap_from_data(
                self.image_data,
                QSize(self.face_size, self.face_size)
            )
            
            if pixmap and not self.active:
                # Convert to grayscale and reuse original image data for inactive state
                try:
                    image = Image.open(io.BytesIO(self.image_data))
                    image = ImageOps.grayscale(image).convert('RGB')
                    enhancer = ImageEnhance.Brightness(image)
                    image = enhancer.enhance(1.5)
                    # Convert back to bytes
                    img_byte_arr = io.BytesIO()
                    image.save(img_byte_arr, format='PNG')
                    inactive_data = img_byte_arr.getvalue()
                    pixmap = ImageProcessor.create_pixmap_from_data(
                        inactive_data,
                        QSize(self.face_size, self.face_size)
                    )
                except Exception as e:
                    logging.error(f"Error creating inactive image: {e}")
                    # Fall back to active image if grayscale conversion fails
                    pixmap = ImageProcessor.create_pixmap_from_data(
                        self.image_data,
                        QSize(self.face_size, self.face_size)
                    )
            
            if pixmap:
                label.setPixmap(pixmap)
            
        label.setFixedSize(self.face_size, self.face_size)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setCursor(Qt.CursorShape.PointingHandCursor)
        label.mousePressEvent = self._handle_mouse_press
        return label

    def _create_info_label(self) -> QLabel:
        info_label = QLabel(f"ID: {self.face_id}", self)
        info_label.setAlignment(Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignCenter)
        info_label.setFont(QFont("Arial", 7))
        info_label.setStyleSheet("background-color: rgba(255, 255, 255, 128);")
        return info_label

    def _handle_mouse_press(self, event):
        """Handle mouse press events for the image label."""
        if event.button() == Qt.MouseButton.RightButton:
            # Close any existing previews first
            self.close_all_previews()
            # Show new preview with bounding box
            self.show_preview(event.globalPosition().toPoint())
            # Track this as current preview
            FaceImageWidget._current_preview = self
        elif event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.face_id)

    def show_preview(self, global_pos):
        """Show preview with highlighted face box."""
        try:
            if hasattr(self, 'image_id') and self.image_id and self.db_manager is not None:
                full_image_data = self.db_manager.get_image_data(self.image_id)
                if full_image_data:
                    # Create base image
                    image = Image.open(io.BytesIO(full_image_data)).convert('RGB')
                    qimage = QImage(image.tobytes('raw', 'RGB'), 
                                  image.width, image.height,
                                  3 * image.width,
                                  QImage.Format.Format_RGB888)
                    pixmap = QPixmap.fromImage(qimage)

                    # Create a copy to draw on
                    drawing_pixmap = QPixmap(pixmap)

                    # Draw bounding box
                    try:
                        conn = sqlite3.connect(self.db_manager.db_path)
                        cursor = conn.cursor()
                        cursor.execute('''
                            SELECT bbox_x, bbox_y, bbox_w, bbox_h
                            FROM faces
                            WHERE id = ?
                        ''', (self.face_id,))
                        result = cursor.fetchone()
                        
                        if result:
                            rel_x, rel_y, rel_w, rel_h = result
                            # Convert relative coordinates to actual pixels
                            x = int(rel_x * drawing_pixmap.width())
                            y = int(rel_y * drawing_pixmap.height())
                            w = int(rel_w * drawing_pixmap.width())
                            h = int(rel_h * drawing_pixmap.height())
                            
                            # Draw rectangle
                            painter = QPainter(drawing_pixmap)
                            pen = QPen(QColor(255, 0, 0))  # Red color
                            pen.setWidth(3)  # Make it thicker for visibility
                            painter.setPen(pen)
                            painter.drawRect(x, y, w, h)
                            painter.end()

                            # Create preview window if needed
                            if FaceImageWidget._shared_preview_window is None:
                                FaceImageWidget._shared_preview_window = ImagePreviewWindow()

                            # Show preview with bounding box
                            FaceImageWidget._shared_preview_window.show_image(drawing_pixmap, global_pos)
                    finally:
                        if 'conn' in locals():
                            conn.close()
                else:
                    logging.warning(f"No image data found for image_id {self.image_id}")
        except Exception as e:
            logging.error(f"Error showing preview: {e}")

    def mouseReleaseEvent(self, event):
        """Handle mouse release events."""
        if event.button() == Qt.MouseButton.RightButton:
            # Hide preview when right mouse button is released
            if FaceImageWidget._shared_preview_window and FaceImageWidget._shared_preview_window.isVisible():
                FaceImageWidget._shared_preview_window.hide_and_clear()
                if FaceImageWidget._current_preview == self:
                    FaceImageWidget._current_preview = None
        super().mouseReleaseEvent(event)

    def set_active(self, active: bool):
        """Update the active state and refresh the image"""
        if self.active != active:
            self.active = active
            self.image_label.setPixmap(self._create_image_label().pixmap())
