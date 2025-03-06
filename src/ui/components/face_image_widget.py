from PyQt6.QtWidgets import QWidget, QLabel, QPushButton, QVBoxLayout
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap, QIcon, QFont

class FaceImageWidget(QWidget):
    deleteClicked = pyqtSignal(int)  # Signal emitted when delete button clicked
    clicked = pyqtSignal()  # For regular image click
    rightClicked = pyqtSignal(object)  # For right-click preview

    def __init__(self, face_id, pixmap, actual_name="Unknown", predicted_name=None, confidence=None, parent=None):
        super().__init__(parent)
        self.face_id = face_id
        self.setup_ui(pixmap, actual_name, predicted_name, confidence)

    def setup_ui(self, pixmap, actual_name, predicted_name, confidence):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # Container for image and delete button
        self.container = QWidget(self)
        self.container.setFixedSize(100, 100)
        
        # Image label with its container
        self.image_label = QLabel(self.container)
        self.image_label.setFixedSize(100, 100)
        self.image_label.setPixmap(pixmap.scaled(100, 100, Qt.AspectRatioMode.KeepAspectRatio))
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Delete button
        self.delete_button = QPushButton("🗑", self.container)
        self.delete_button.setFixedSize(20, 20)
        self.delete_button.setFont(QFont("Segoe UI Symbol", 10))
        self.delete_button.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 180);
                border-radius: 10px;
                border: none;
                color: #444;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 255);
                color: #000;
            }
        """)
        self.delete_button.move(76, 4)
        self.delete_button.clicked.connect(self._on_delete_clicked)

        layout.addWidget(self.container)

        # Add predicted name label with confidence if available
        if predicted_name and predicted_name != "Unknown":
            conf_text = f" ({confidence*100:.1f}%)" if confidence is not None else ""
            pred_text = f"{predicted_name}{conf_text}"
            self.pred_label = QLabel(pred_text)
            self.pred_label.setFixedWidth(100)
            self.pred_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.pred_label.setStyleSheet("""
                QLabel {
                    font-size: 10px;
                    color: white;
                    background-color: rgba(0, 0, 0, 0.7);
                    border-radius: 2px;
                    padding: 1px 3px;
                    margin: 0px;
                }
            """)
            self.pred_label.setWordWrap(True)
            layout.addWidget(self.pred_label)

        # Add actual name label
        self.name_label = QLabel(actual_name)
        self.name_label.setFixedWidth(100)
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_label.setStyleSheet("""
            QLabel {
                font-size: 10px;
                color: black;
                background-color: rgba(255, 255, 255, 0.9);
                border-radius: 2px;
                padding: 1px 3px;
                margin: 0px;
            }
        """)
        self.name_label.setWordWrap(True)
        layout.addWidget(self.name_label)

        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self.rightClicked.emit(event.globalPosition().toPoint())
        elif event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def _on_delete_clicked(self):
        self.deleteClicked.emit(self.face_id)
        self.hide()  # Hide the widget immediately
        self.deleteLater()  # Schedule widget for deletion
