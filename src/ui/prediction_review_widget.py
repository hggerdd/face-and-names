from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton,
    QLabel, QGroupBox, QLineEdit, QCheckBox, QStyle,
    QListWidget, QSplitter, QScrollArea, QInputDialog, QFrame,
    QApplication
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal, QRect, QTimer, QThread
from PyQt6.QtGui import QPixmap, QImage, QFont, QColor, QCursor, QPainter, QPen
import cv2
import numpy as np
import logging
from pathlib import Path
import io
from PIL import Image, ImageOps, ImageEnhance
from .shared.image_preview import ImagePreviewWindow

class PredictionDataLoader(QThread):
    loaded = pyqtSignal(list, list)
    failed = pyqtSignal(str)

    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager

    def run(self):
        try:
            faces = self.db_manager.get_faces_with_predictions()
            unique_names = self.db_manager.get_unique_names()
            self.loaded.emit(faces, unique_names)
        except Exception as e:
            logging.error(f"Error loading prediction data: {e}", exc_info=True)
            self.failed.emit(str(e))


class EditableLabel(QLabel):
    nameChanged = pyqtSignal(str)  # Signal emitted when the name is edited

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            current_text = self.text()
            new_name, ok = QInputDialog.getText(self, 'Edit Name', 'Enter name:', text=current_text)
            if ok and new_name:
                self.setText(new_name)
                self.nameChanged.emit(new_name)

class FaceGridItem(QWidget):
    nameUpdated = pyqtSignal(int, str)  # face_id, new_name
    selectionChanged = pyqtSignal(int, bool)  # face_id, selected
    predictionAccepted = pyqtSignal(int, str)  # Signal for double-click acceptance

    # Static variable to track currently shown preview
    _current_preview = None

    def __init__(self, db_manager=None, parent=None):
        super().__init__(parent)
        self.face_id = None
        self._image_data = None
        self._predicted_name = None
        self._confidence = None
        self._image_loaded = False
        self.selected = True  # Default to selected
        self._last_click = 0
        self.db_manager = db_manager
        self.preview_window = ImagePreviewWindow()
        self.image_id = None  # Store the image_id
        self.setMouseTracking(True)
        self.setup_ui()

        # Track mouse enter state
        self._mouse_over = False

    @classmethod
    def close_all_previews(cls):
        """Close any open preview window"""
        if cls._current_preview and cls._current_preview.isVisible():
            cls._current_preview.hide_and_clear()
            cls._current_preview = None

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(2)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        container = QWidget()
        container.setFixedWidth(120)
        container_layout = QVBoxLayout(container)
        container_layout.setSpacing(2)
        container_layout.setContentsMargins(0, 0, 0, 0)

        image_container = QWidget()
        image_container.setFixedSize(100, 100)
        image_layout = QVBoxLayout(image_container)
        image_layout.setContentsMargins(0, 0, 0, 0)
        image_layout.setSpacing(0)

        self.image_label = QLabel()
        self.image_label.setFixedSize(100, 100)
        self.image_label.setText("Loading...")  # Placeholder until image is loaded
        self.image_label.setCursor(Qt.CursorShape.PointingHandCursor)
        image_layout.addWidget(self.image_label)

        self.pred_label = QLabel()
        self.pred_label.setStyleSheet("""
            QLabel {
                background-color: rgba(0, 0, 0, 0.7);
                color: white;
                padding: 2px 4px;
                border-radius: 2px;
                font-size: 10px;
            }
        """)
        self.pred_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        image_layout.addWidget(self.pred_label)
        image_layout.setAlignment(self.pred_label, Qt.AlignmentFlag.AlignBottom)

        container_layout.addWidget(image_container)

        self.name_label = EditableLabel("Unknown")
        self.name_label.setFixedWidth(100)
        self.name_label.nameChanged.connect(self.update_name)
        container_layout.addWidget(self.name_label)

        layout.addWidget(container)
        layout.addStretch()

    def set_data(self, face_id, image_data, actual_name, predicted_name, confidence, image_id, selected=True):
        # Updated to accept image_id as the 6th parameter and default selected to True
        self.face_id = face_id
        self._image_data = image_data
        self._predicted_name = predicted_name
        self._confidence = confidence
        self.selected = selected
        self.image_id = image_id  # Store the image_id
        self.name_label.setText(actual_name or "Unknown")
        if predicted_name and predicted_name != "Unknown":
            confidence_text = f" ({confidence*100:.1f}%)" if confidence else ""
            self.pred_label.setText(f"{predicted_name}{confidence_text}")
        else:
            self.pred_label.setText("")
        self.update_image()

    def update_image(self):
        if self._image_data:
            image = Image.open(io.BytesIO(self._image_data)).convert('RGB')
            image = image.resize((100, 100), Image.Resampling.LANCZOS)
            if not self.selected:
                image = ImageOps.grayscale(image).convert('RGB')
                enhancer = ImageEnhance.Brightness(image)
                image = enhancer.enhance(1.5)
            qimage = QImage(image.tobytes('raw', 'RGB'), 100, 100, 300, QImage.Format.Format_RGB888)
            self.image_label.setPixmap(QPixmap.fromImage(qimage))
        else:
            self.image_label.clear()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            current_time = event.timestamp()
            if current_time - self._last_click < 250:  # Double-click
                if self._predicted_name and self._predicted_name != "Unknown":
                    self.predictionAccepted.emit(self.face_id, self._predicted_name)
            else:  # Single click
                self.selected = not self.selected
                self.update_image()
                self.selectionChanged.emit(self.face_id, self.selected)
            self._last_click = current_time
        elif event.button() == Qt.MouseButton.RightButton:
            # Close any existing previews first
            self.close_all_previews()
            # Show new preview
            self.show_preview(event.globalPosition().toPoint())
            # Track this as current preview
            FaceGridItem._current_preview = self.preview_window

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            # Hide preview when right mouse button is released
            if self.preview_window.isVisible():
                self.preview_window.hide_and_clear()
                if FaceGridItem._current_preview == self.preview_window:
                    FaceGridItem._current_preview = None
        super().mouseReleaseEvent(event)

    def update_name(self, new_name):
        self.name_label.setText(new_name)
        self.nameUpdated.emit(self.face_id, new_name)

    def show_preview(self, global_pos):
        """Show preview with highlighted face box"""
        try:
            if hasattr(self, 'image_id') and self.image_id and self.db_manager is not None:
                logging.debug(f"Showing preview for face {self.face_id}, image {self.image_id}")
                full_image_data = self.db_manager.get_image_data(self.image_id)
                if full_image_data:
                    image = Image.open(io.BytesIO(full_image_data)).convert('RGB')
                    qimage = QImage(image.tobytes('raw', 'RGB'), 
                                  image.width, image.height,
                                  3 * image.width,
                                  QImage.Format.Format_RGB888)
                    pixmap = QPixmap.fromImage(qimage)

                    # Create a copy of the pixmap to draw on
                    drawing_pixmap = QPixmap(pixmap)

                    # Draw bounding box on the copy
                    painter = QPainter(drawing_pixmap)
                    pen = QPen(QColor(255, 0, 0))  # Red color
                    pen.setWidth(3)  # Make it thicker for visibility
                    painter.setPen(pen)

                    bbox = self.db_manager.get_face_bbox(self.face_id) if self.db_manager else None
                    if bbox:
                        rel_x, rel_y, rel_w, rel_h = bbox
                        x = int(rel_x * drawing_pixmap.width())
                        y = int(rel_y * drawing_pixmap.height())
                        w = int(rel_w * drawing_pixmap.width())
                        h = int(rel_h * drawing_pixmap.height())
                        painter.drawRect(x, y, w, h)
                    painter.end()

                    # Show preview with the drawn rectangle
                    self.preview_window.show_image(drawing_pixmap, global_pos)
                else:
                    logging.warning(f"No image data found for image_id {self.image_id}")
        except Exception as e:
            logging.error(f"Error showing preview: {e}")
            raise

class ReviewGridWidget(QWidget):
    nameChanged = pyqtSignal(int, str)  # face_id, new_name
    selectionChanged = pyqtSignal(list)  # List of selected face_ids
    predictionAccepted = pyqtSignal(int, str)  # Signal for acceptance

    def __init__(self, db_manager=None, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.all_faces = []
        self.selected_faces = set()
        self.item_widgets = []
        self.item_width = 130
        self.item_height = 130
        self.columns = 1
        self.rows_total = 0
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.container = QWidget()
        # FIX: Use a proper layout instead of None
        container_layout = QVBoxLayout(self.container)
        # Set zero margins to allow manual positioning of child widgets
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)
        self.scroll_area.setWidget(self.container)
        layout.addWidget(self.scroll_area)
        self.scroll_area.verticalScrollBar().valueChanged.connect(self.on_scroll)

    def load_faces(self, faces):
        self.all_faces = faces
        # Initialize all faces as selected by default
        self.selected_faces = set(face[0] for face in faces)  # Select all faces by default
        self.columns = max(1, (self.scroll_area.width() - 20) // self.item_width)
        self.rows_total = (len(faces) + self.columns - 1) // self.columns
        self.container.setFixedHeight(self.rows_total * self.item_height)
        self.create_item_widgets()
        self.update_visible_items()
        # Emit the initial selection
        self.selectionChanged.emit(list(self.selected_faces))

    def create_item_widgets(self):
        # Create enough widgets to cover the viewport plus buffer
        viewport_height = self.scroll_area.viewport().height()
        visible_rows = (viewport_height // self.item_height) + 2
        total_widgets = visible_rows * self.columns
        while len(self.item_widgets) < total_widgets:
            widget = FaceGridItem(db_manager=self.db_manager, parent=self.container)
            widget.nameUpdated.connect(self.nameChanged.emit)
            widget.selectionChanged.connect(self.on_item_selection_changed)
            widget.predictionAccepted.connect(self.predictionAccepted.emit)
            self.item_widgets.append(widget)
        while len(self.item_widgets) > total_widgets:
            widget = self.item_widgets.pop()
            widget.deleteLater()

    def on_scroll(self):
        self.update_visible_items()

    def update_visible_items(self):
        scroll_pos = self.scroll_area.verticalScrollBar().value()
        viewport_height = self.scroll_area.viewport().height()
        start_row = scroll_pos // self.item_height
        end_row = min(start_row + (viewport_height // self.item_height) + 2, self.rows_total)

        widget_index = 0
        for row in range(start_row, end_row):
            for col in range(self.columns):
                index = row * self.columns + col
                if index < len(self.all_faces):
                    if widget_index < len(self.item_widgets):
                        widget = self.item_widgets[widget_index]
                        face_data = self.all_faces[index]
                        # Get face_id which is the first element
                        face_id = face_data[0]
                        # Check if this face is selected
                        selected = face_id in self.selected_faces
                        # Pass the face data and selected state separately
                        # This ensures all elements in face_data are unpacked correctly
                        widget.set_data(*face_data, selected=selected)
                        widget.setGeometry(col * self.item_width, row * self.item_height, self.item_width, self.item_height)
                        widget.show()
                        widget_index += 1
        # Hide remaining widgets
        while widget_index < len(self.item_widgets):
            self.item_widgets[widget_index].hide()
            widget_index += 1

    def on_item_selection_changed(self, face_id, selected):
        if selected:
            self.selected_faces.add(face_id)
        else:
            self.selected_faces.discard(face_id)
        self.selectionChanged.emit(list(self.selected_faces))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.all_faces:
            self.load_faces(self.all_faces)

class PredictionReviewWidget(QWidget):
    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self._faces_data = []
        self._unique_names = None
        self._is_data_loaded = False
        self._last_selected_name = ""  # Store the last selected filter name
        self._data_loader = None
        self._filter_controls = []
        self.setup_ui()

    def setup_ui(self):
        try:
            main_layout = QHBoxLayout(self)
            splitter = QSplitter(Qt.Orientation.Horizontal)
            
            names_widget = QWidget()
            names_layout = QVBoxLayout(names_widget)
            names_layout.setContentsMargins(0, 0, 0, 0)
            
            self.names_list = QListWidget()
            self.names_list.setMaximumWidth(200)
            self.names_list.itemClicked.connect(self.on_name_selected)
            names_layout.addWidget(self.names_list)
            
            right_widget = QWidget()
            right_layout = QVBoxLayout(right_widget)
            right_layout.setContentsMargins(0, 0, 0, 0)

            filter_group = QGroupBox("Filters")
            filter_layout = QGridLayout(filter_group)
            
            filter_layout.addWidget(QLabel("Filter by name:"), 0, 0)
            self.name_filter = QLineEdit()
            self.name_filter.setPlaceholderText("Enter name to filter...")
            self.name_filter.textChanged.connect(self.apply_filters)
            filter_layout.addWidget(self.name_filter, 0, 1)
            
            filter_layout.addWidget(QLabel("Confidence range:"), 1, 0)
            confidence_layout = QHBoxLayout()
            
            self.min_confidence = QLineEdit()
            self.min_confidence.setPlaceholderText("Min %")
            self.min_confidence.setMaximumWidth(60)
            self.min_confidence.textChanged.connect(self.apply_filters)
            confidence_layout.addWidget(self.min_confidence)
            
            confidence_layout.addWidget(QLabel("-"))
            
            self.max_confidence = QLineEdit()
            self.max_confidence.setPlaceholderText("Max %")
            self.max_confidence.setMaximumWidth(60)
            self.max_confidence.textChanged.connect(self.apply_filters)
            confidence_layout.addWidget(self.max_confidence)
            
            confidence_layout.addStretch()
            filter_layout.addLayout(confidence_layout, 1, 1)
            
            self.unnamed_check = QCheckBox("Show only unnamed faces")
            self.unnamed_check.stateChanged.connect(self.apply_filters)
            filter_layout.addWidget(self.unnamed_check, 2, 0)
            
            self.different_check = QCheckBox("Show only different predictions")
            self.different_check.stateChanged.connect(self.apply_filters)
            filter_layout.addWidget(self.different_check, 2, 1)
            
            accept_button = QPushButton("Accept Predictions for Selected")
            accept_button.clicked.connect(self.accept_selected_predictions)
            accept_button.setStyleSheet("""
                QPushButton {
                    background-color: #28a745;
                    color: white;
                    padding: 5px;
                    border: none;
                    border-radius: 3px;
                }
                QPushButton:hover {
                    background-color: #218838;
                }
            """)
            filter_layout.addWidget(accept_button, 3, 0, 1, 2)

            self.filter_stats = QLabel("Showing all faces")
            filter_layout.addWidget(self.filter_stats, 4, 0, 1, 2)

            reload_button = QPushButton("Reload Predictions")
            reload_button.clicked.connect(lambda: self._start_data_load(force=True))
            filter_layout.addWidget(reload_button, 5, 0, 1, 2)
            self.reload_button = reload_button
            
            right_layout.addWidget(filter_group)

            grid_group = QGroupBox("Predictions")
            grid_layout = QVBoxLayout(grid_group)
            
            scroll_area = QScrollArea()
            scroll_area.setWidgetResizable(True)
            scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            
            # Pass the db_manager to ReviewGridWidget
            self.face_grid = ReviewGridWidget(db_manager=self.db_manager)
            self.face_grid.nameChanged.connect(self.on_name_changed)
            self.face_grid.selectionChanged.connect(self.on_selection_changed)
            self.face_grid.predictionAccepted.connect(self.on_prediction_accepted)
            scroll_area.setWidget(self.face_grid)
            
            grid_layout.addWidget(scroll_area)
            right_layout.addWidget(grid_group)

            self.status_label = QLabel("Ready")
            right_layout.addWidget(self.status_label)

            splitter.addWidget(names_widget)
            splitter.addWidget(right_widget)
            splitter.setSizes([200, 400])
            
            main_layout.addWidget(splitter)

            self._filter_controls = [
                self.names_list,
                self.name_filter,
                self.min_confidence,
                self.max_confidence,
                self.unnamed_check,
                self.different_check,
                accept_button,
                self.reload_button,
                self.face_grid,
            ]
            
        except Exception as e:
            logging.error(f"Error in setup_ui: {e}")
            raise

    def showEvent(self, event):
        """Called when the widget becomes visible"""
        super().showEvent(event)
        if not self._is_data_loaded:
            self._start_data_load(force=True)
        else:
            self.status_label.setText("Ready")

    def load_predictions(self):
        """Trigger an asynchronous reload of prediction data."""
        self._start_data_load(force=True)

    def _start_data_load(self, force: bool = False):
        if self._data_loader and self._data_loader.isRunning():
            return
        if self._is_data_loaded and not force:
            return

        self.status_label.setText("Loading predictions...")
        self._set_filter_controls_enabled(False)

        self._data_loader = PredictionDataLoader(self.db_manager)
        self._data_loader.loaded.connect(self._on_data_loaded)
        self._data_loader.failed.connect(self._on_data_load_failed)
        self._data_loader.start()

    def _on_data_loaded(self, faces_data, unique_names):
        self._faces_data = faces_data
        self._unique_names = unique_names
        self._is_data_loaded = True

        logging.info(f"Loaded {len(self._faces_data)} predictions")
        self.status_label.setText(f"Loaded {len(self._faces_data)} predictions")

        self.load_names()
        self.apply_filters()
        self._set_filter_controls_enabled(True)

        if self._data_loader:
            self._data_loader.deleteLater()
            self._data_loader = None

    def _on_data_load_failed(self, message: str):
        logging.error(f"Failed to load prediction data: {message}")
        self.status_label.setText(f"Error loading predictions: {message}")
        self._set_filter_controls_enabled(True)
        if self._data_loader:
            self._data_loader.deleteLater()
            self._data_loader = None

    def _set_filter_controls_enabled(self, enabled: bool):
        for widget in self._filter_controls:
            widget.setEnabled(enabled)

    def load_names(self):
        try:
            if self._unique_names is None:
                self._unique_names = self.db_manager.get_unique_names()
                logging.debug(f"Retrieved {len(self._unique_names)} unique names from database")
            self.names_list.clear()
            self.names_list.addItem("All")

            name_counts = {}
            for face_tuple in self._faces_data:
                # Fixed: Unpack 6 values instead of 5
                face_id, image_data, actual_name, predicted_name, confidence, image_id = face_tuple
                actual_name = actual_name or "Unknown"
                predicted_name = predicted_name or "Unknown"
                if actual_name == "Unknown" and predicted_name != "Unknown":
                    name_counts[predicted_name] = name_counts.get(predicted_name, 0) + 1

            unique_names = sorted(set(name for name in self._unique_names if name and name.lower() != 'unknown'))
            for name in unique_names:
                count = name_counts.get(name, 0)
                display_text = f"{name} ({count})" if count > 0 else name
                self.names_list.addItem(display_text)
            logging.info(f"Loaded {len(unique_names)} unique names into list")
        except Exception as e:
            logging.error(f"Error loading names: {e}")
            self.status_label.setText("Error loading names")

    def on_name_selected(self, item):
        name = item.text()
        if name == "All":
            self.name_filter.setText("")
        else:
            name = name.split(" (")[0]
            self.name_filter.setText(name)
        self.apply_filters()

    def accept_selected_predictions(self):
        try:
            selected_items = [item for item in self.face_grid.item_widgets if item.selected and item._predicted_name and item._predicted_name != "Unknown"]
            if not selected_items:
                self.status_label.setText("No faces selected or no valid predictions")
                return

            success_count = 0
            for item in selected_items:
                if self.db_manager.update_face_name(item.face_id, item._predicted_name):
                    success_count += 1
                    for i, face in enumerate(self._faces_data):
                        if face[0] == item.face_id:
                            # Fixed: Preserve all values in the tuple including image_id
                            self._faces_data[i] = (face[0], face[1], item._predicted_name, face[3], face[4], face[5])
                            break
            if success_count > 0:
                self.status_label.setText(f"Updated {success_count} faces with predicted names")
                self._unique_names = None  # Invalidate cache
                self.load_names()
                self.apply_filters()
            else:
                self.status_label.setText("No predictions were accepted")
        except Exception as e:
            logging.error(f"Error accepting predictions: {e}")
            self.status_label.setText("Error accepting predictions")

    def apply_filters(self, *args):
        try:
            if not self._faces_data:
                return

            name_filter = self.name_filter.text().strip().lower()
            only_unnamed = self.unnamed_check.isChecked()
            only_different = self.different_check.isChecked()
            min_conf = self._parse_confidence(self.min_confidence.text())
            max_conf = self._parse_confidence(self.max_confidence.text())

            filtered_faces = []
            for face_data in self._faces_data:
                # Fixed: Unpack 6 values instead of 5
                face_id, image_data, actual_name, predicted_name, confidence, image_id = face_data
                actual_name = actual_name or "Unknown"
                predicted_name = predicted_name or "Unknown"

                if name_filter and name_filter not in actual_name.lower() and name_filter not in predicted_name.lower():
                    continue
                if only_unnamed and actual_name != "Unknown":
                    continue
                if only_different and actual_name == predicted_name:
                    continue
                if min_conf is not None and (confidence is None or confidence < min_conf):
                    continue
                if max_conf is not None and (confidence is None or confidence > max_conf):
                    continue

                filtered_faces.append(face_data)

            self.face_grid.load_faces(filtered_faces)
            self.filter_stats.setText(
                f"Showing {len(filtered_faces)} of {len(self._faces_data)} faces"
                if len(filtered_faces) != len(self._faces_data) else "Showing all faces"
            )
        except Exception as e:
            logging.error(f"Error applying filters: {e}")
            self.status_label.setText("Error applying filters")

    def _parse_confidence(self, text):
        try:
            return float(text.strip()) / 100.0 if text.strip() else None
        except ValueError:
            return None

    def on_name_changed(self, face_id: int, new_name: str):
        try:
            if self.db_manager.update_face_name(face_id, new_name):
                self.status_label.setText(f"Updated name for face {face_id}")
                for i, face in enumerate(self._faces_data):
                    if face[0] == face_id:
                        # Fixed: Create a new tuple with the updated name while preserving image_id
                        self._faces_data[i] = (face[0], face[1], new_name, face[3], face[4], face[5])
                        break
                self._unique_names = None  # Invalidate cache
                self.load_names()
                self.apply_filters()
            else:
                self.status_label.setText("Failed to update name")
        except Exception as e:
            logging.error(f"Error updating name: {e}")
            self.status_label.setText("Error updating name")

    def on_selection_changed(self, selected_faces: list):
        self.status_label.setText(f"Selected {len(selected_faces)} faces")

    def on_prediction_accepted(self, face_id: int, predicted_name: str):
        self.on_name_changed(face_id, predicted_name)
