from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QSizePolicy, QPushButton
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QPainter, QPen, QColor, QPixmap, QImage, QFont
from PIL import Image, ImageOps, ImageEnhance
import io
import sqlite3
import logging
from .image_utils import ImageProcessor
from .image_preview import ImagePreviewWindow
from .font_config import FontConfig

class FaceImageWidget(QWidget):
    """A widget that displays a face image with current and predicted names."""
    clicked = pyqtSignal(int)  # Emits face_id when clicked
    rightClicked = pyqtSignal(int, object)  # Emits face_id and global position
    deleteClicked = pyqtSignal(int)  # Emits face_id when delete button clicked
    
    # Static variables for shared preview handling
    _current_preview = None
    _shared_preview_window = None

    @classmethod
    def close_all_previews(cls):
        """Close any open preview windows."""
        if cls._shared_preview_window and cls._shared_preview_window.isVisible():
            cls._shared_preview_window.hide_and_clear()
            cls._shared_preview_window = None

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

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(2)
        layout.setContentsMargins(5, 5, 5, 5)

        # Create image container with fixed width and make it a parent for stacking
        self.image_container = QWidget(self)
        self.image_container.setFixedWidth(self.face_size)
        self.image_container.setFixedHeight(self.face_size)  # Also fix height to ensure proper stacking
        
        # Create and setup main image label
        self.image_label = self._create_image_label()
        self.image_label.setParent(self.image_container)  # Set parent directly
        self.image_label.move(0, 0)  # Position at top-left
        
        # Create delete button on top
        self.delete_button = QPushButton("🗑", self.image_container)
        self.delete_button.setFixedSize(20, 20)
        self.delete_button.setFont(QFont("Segoe UI Symbol", 10))
        self.delete_button.setStyleSheet("""\
            QPushButton {
                background-color: rgba(255, 255, 255, 180);
                border-radius: 10px;
                border: none;
                color: #444;
            }
            QPushButton:hover {
                background-color: rgba(255, 0, 0, 180);
                color: white;
            }
        """)
        self.delete_button.clicked.connect(self._on_delete_clicked)
        self.delete_button.move(self.face_size - 24, 4)  # Position in top-right corner
        self.delete_button.raise_()  # Ensure button stays on top

        layout.addWidget(self.image_container, alignment=Qt.AlignmentFlag.AlignHCenter)

        # Add fixed-width container for name labels
        labels_container = QWidget(self)
        labels_container.setFixedWidth(self.face_size)
        labels_layout = QVBoxLayout(labels_container)
        labels_layout.setContentsMargins(0, 0, 0, 0)
        labels_layout.setSpacing(2)

        # Add name label if provided
        if self.name:
            name_label = QLabel(self.name, self)
            name_label.setFixedHeight(20)  # Fixed height for consistency
            name_label.setFont(FontConfig.get_label_font())
            name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            name_label.setWordWrap(True)
            name_label.setStyleSheet("""\
                QLabel {
                    background-color: rgba(220, 220, 220, 128);
                    border-radius: 2px;
                    padding: 1px 3px;
                    margin: 0px;
                }
            """)
            labels_layout.addWidget(name_label)

        # Add predicted name if provided
        if self.predicted_name:
            confidence = getattr(self, 'prediction_confidence', None)
            conf_text = f" ({confidence:.0%})" if confidence else ""
            pred_label = QLabel(f"{self.predicted_name}{conf_text}", self)
            pred_label.setFixedHeight(20)  # Fixed height for consistency
            pred_label.setFont(FontConfig.get_label_font())
            pred_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            pred_label.setWordWrap(True)
            pred_label.setStyleSheet("""\
                QLabel {
                    background-color: rgba(200, 200, 255, 128);
                    border-radius: 2px;
                    padding: 1px 3px;
                    margin: 0px;
                }
            """)
            labels_layout.addWidget(pred_label)

        layout.addWidget(labels_container, alignment=Qt.AlignmentFlag.AlignHCenter)
        
        # Set widget's size policy to prevent unwanted stretching
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

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
        # Change to use the widget's event handlers instead
        return label

    def mousePressEvent(self, event):
        """Handle mouse press events for the widget."""
        if event.button() == Qt.MouseButton.RightButton:
            # Show preview when right button is pressed
            self.show_preview(event.globalPosition().toPoint())
        elif event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.face_id)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        """Handle mouse release events for the widget."""
        if event.button() == Qt.MouseButton.RightButton:
            # Hide preview when right button is released
            if FaceImageWidget._shared_preview_window:
                FaceImageWidget._shared_preview_window.hide_and_clear()
        super().mouseReleaseEvent(event)

    def _create_info_label(self) -> QLabel:
        """Create the face ID info label."""
        info_label = QLabel(f"ID: {self.face_id}", self)
        info_label.setAlignment(Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignCenter)
        info_label.setFont(FontConfig.get_label_font())
        info_label.setStyleSheet("background-color: rgba(255, 255, 255, 128);")
        return info_label

    def _on_delete_clicked(self):
        """Handle delete button click."""
        try:
            logging.debug(f"Delete button clicked for face_id: {self.face_id}")
            self.deleteClicked.emit(self.face_id)
        except Exception as e:
            logging.error(f"Error in delete click handler: {e}")

    def show_preview(self, global_pos):
        """Show preview with highlighted face box."""
        try:
            if hasattr(self, 'image_id') and self.image_id and self.db_manager is not None:
                image_data = self.db_manager.get_image_data(self.image_id)
                if image_data:
                    pixmap = ImageProcessor.create_pixmap_from_data(image_data)
                    if pixmap:
                        # Initialize shared preview window if needed
                        if FaceImageWidget._shared_preview_window is None:
                            FaceImageWidget._shared_preview_window = ImagePreviewWindow()
                        # Show preview
                        FaceImageWidget._shared_preview_window.show_image(pixmap, global_pos)
                else:
                    logging.warning(f"No image data found for image_id {self.image_id}")
        except Exception as e:
            logging.error(f"Error showing preview: {e}")

    def set_active(self, active: bool):
        """Update the active state and refresh the image."""
        if self.active != active:
            self.active = active
            if isinstance(self.image_data, (bytes, bytearray)):
                pixmap = ImageProcessor.create_pixmap_from_data(
                    self.image_data,
                    QSize(self.face_size, self.face_size)
                )
                if pixmap and not active:
                    # Convert to grayscale for inactive state
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
                        # Fall back to active image if conversion fails
                if pixmap:
                    self.image_label.setPixmap(pixmap)
