from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap, QFont
from PIL import Image, ImageOps, ImageEnhance
import io

class FaceImageWidget(QWidget):
    """A widget that displays a face image with current and predicted names."""
    clicked = pyqtSignal(int)  # Emits face_id when clicked
    rightClicked = pyqtSignal(int, object)  # Emits face_id and global position

    def __init__(self, face_id: int, image_data: bytes, name: str = None, 
                 predicted_name: str = None, face_size: int = 100, 
                 active: bool = True, prediction_confidence: float = None, 
                 parent=None):
        super().__init__(parent)
        self.face_id = face_id
        self.face_size = face_size
        self.active = active
        self.image_data = image_data
        self.name = name
        self.predicted_name = predicted_name
        self.prediction_confidence = prediction_confidence
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(2)
        layout.setContentsMargins(5, 5, 5, 5)

        # Create image container with fixed width
        self.image_container = QWidget()
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
        labels_container = QWidget()
        labels_container.setFixedWidth(self.face_size)
        labels_layout = QVBoxLayout(labels_container)
        labels_layout.setContentsMargins(0, 0, 0, 0)
        labels_layout.setSpacing(2)

        # Add name label if provided
        if self.name:
            name_label = QLabel(f"Name: {self.name}")
            name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            name_label.setWordWrap(True)
            name_label.setStyleSheet("QLabel { background-color: rgba(220, 220, 220, 128); }")
            labels_layout.addWidget(name_label)

        # Add predicted name if provided
        if self.predicted_name:
            confidence = getattr(self, 'prediction_confidence', None)
            conf_text = f" ({confidence:.0%})" if confidence else ""
            pred_label = QLabel(f"Predicted: {self.predicted_name}{conf_text}")
            pred_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            pred_label.setWordWrap(True)
            pred_label.setStyleSheet("QLabel { background-color: rgba(200, 200, 255, 128); }")
            labels_layout.addWidget(pred_label)

        layout.addWidget(labels_container, alignment=Qt.AlignmentFlag.AlignHCenter)

    def _create_image_label(self) -> QLabel:
        # Process image
        image = Image.open(io.BytesIO(self.image_data)).convert('RGB')
        image = image.resize((self.face_size, self.face_size), Image.Resampling.LANCZOS)
        
        if not self.active:
            image = ImageOps.grayscale(image).convert('RGB')
            enhancer = ImageEnhance.Brightness(image)
            image = enhancer.enhance(1.5)
            
        # Convert to QImage/QPixmap
        qimage = QImage(image.tobytes('raw', 'RGB'),
                       self.face_size, self.face_size,
                       self.face_size * 3,
                       QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(qimage)

        # Create and setup label
        label = QLabel()
        label.setPixmap(pixmap)
        label.setFixedSize(self.face_size, self.face_size)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setCursor(Qt.CursorShape.PointingHandCursor)
        label.mousePressEvent = self._handle_mouse_press
        return label

    def _create_info_label(self) -> QLabel:
        info_label = QLabel(f"ID: {self.face_id}")
        info_label.setAlignment(Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignCenter)
        info_label.setFont(QFont("Arial", 7))
        info_label.setStyleSheet("background-color: rgba(255, 255, 255, 128);")
        return info_label

    def _handle_mouse_press(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self.rightClicked.emit(self.face_id, event.globalPosition().toPoint())
        elif event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.face_id)

    def set_active(self, active: bool):
        """Update the active state and refresh the image"""
        if self.active != active:
            self.active = active
            self.image_label.setPixmap(self._create_image_label().pixmap())
