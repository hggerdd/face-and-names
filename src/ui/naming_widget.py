from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QLineEdit, QScrollArea, QGridLayout, QGroupBox, QSizePolicy, QListWidget, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QPoint
from PyQt6.QtGui import QPixmap, QImage, QFont
import logging
from pathlib import Path
import io
from PIL import Image, ImageOps, ImageEnhance
from .shared.image_preview import ImagePreviewWindow
from .shared.face_image_widget import FaceImageWidget

# Set up logging
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")

# Modify ClickableLabel to support right click
class ClickableLabel(QLabel):
    """A QLabel that emits signals when clicked."""
    clicked = pyqtSignal()
    rightClicked = pyqtSignal(object)  # will send global position (QPoint)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self.rightClicked.emit(event.globalPosition().toPoint())
            return  # Do not propagate further for right clicks
        elif event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

class FaceGridWidget(QWidget):
    """Widget to display a grid of faces from the same cluster."""
    
    # Static variable to track currently shown preview
    _current_preview = None

    def __init__(self, db_manager=None, parent=None):
        super().__init__(parent)
        self.face_states = {}
        self.current_faces = []
        self.face_size = 100
        self.min_column_width = 130
        self.selection_count_label = QLabel("0 faces selected")
        self.selection_count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setup_ui()
        self.db_manager = db_manager
        self.preview_window = ImagePreviewWindow()
        self.image_id = None
        self.setMouseTracking(True)

    @classmethod
    def close_all_previews(cls):
        """Close any open preview window"""
        if cls._current_preview and cls._current_preview.isVisible():
            cls._current_preview.hide_and_clear()
            cls._current_preview = None

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        self.grid_layout = QGridLayout()
        self.grid_layout.setSpacing(10)
        main_layout.addLayout(self.grid_layout)
        main_layout.addWidget(self.selection_count_label)

    def create_face_widget(self, face_id, image_data, name, predicted_name, full_image_id):
        """Create a widget to display a single face."""
        face_widget = FaceImageWidget(
            face_id=face_id,
            image_data=image_data,
            name=name,
            predicted_name=predicted_name,
            face_size=self.face_size,
            active=self.face_states.get(face_id, True)
        )
        face_widget.clicked.connect(lambda: self.toggle_face_selection(face_id))
        face_widget.rightClicked.connect(lambda _, pos: self.handle_right_click(face_id, pos, full_image_id))
        
        # Store full_image_id in the widget for later reuse
        face_widget.full_image_id = full_image_id
        return face_widget

    def handle_right_click(self, face_id, global_pos: QPoint, full_image_id):
        """Retrieve full image from database using full_image_id and show preview."""
        try:
            full_image_data = self.db_manager.get_image_data(full_image_id)
            if full_image_data:
                # Use shared preview window to display full image
                image = Image.open(io.BytesIO(full_image_data)).convert('RGB')
                qimage = QImage(image.tobytes('raw', 'RGB'),
                                image.width, image.height,
                                3 * image.width,
                                QImage.Format.Format_RGB888)
                pixmap = QPixmap.fromImage(qimage)
                self.preview_window.show_image(pixmap, global_pos)
                FaceGridWidget._current_preview = self.preview_window
                logging.debug(f"Preview shown for face {face_id} using image_id {full_image_id}")
            else:
                logging.warning(f"No full image found for image_id {full_image_id}")
        except Exception as e:
            logging.error(f"Error showing preview for face {face_id}: {e}")

    def toggle_face_selection(self, face_id):
        self.face_states[face_id] = not self.face_states.get(face_id, True)
        self.update_faces()
        self.update_selection_count()

    def update_faces(self):
        """Update face display states"""
        for face_widget in self.findChildren(FaceImageWidget):
            face_id = face_widget.face_id
            face_widget.set_active(self.face_states.get(face_id, True))

    def update_selection_count(self):
        selected_count = len(self.get_selected_faces())
        total_count = len(self.current_faces)
        self.selection_count_label.setText(f"{selected_count} of {total_count} faces selected")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.current_faces:
            width = event.size().width()
            columns = max(1, width // self.min_column_width)
            self.arrange_faces(columns)

    def load_faces(self, faces, columns=None):
        self.current_faces = faces
        # Update to use first element (face_id) from each face tuple
        self.face_states = {face[0]: True for face in faces}  

        if columns is None:
            width = self.size().width()
            columns = max(1, width // self.min_column_width)

        self.clear_layout()
        self.arrange_faces(columns)
        self.update_selection_count()

    def clear_layout(self):
        for i in reversed(range(self.grid_layout.count())): 
            widget = self.grid_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)

    def arrange_faces(self, columns):
        if not self.current_faces:
            return

        for idx, face_data in enumerate(self.current_faces):
            row = idx // columns
            col = idx % columns
            face_id, image_data, name, predicted_name, full_image_id = face_data
            face_widget = self.create_face_widget(face_id, image_data, name, predicted_name, full_image_id)
            self.grid_layout.addWidget(face_widget, row, col)

    def get_selected_faces(self):
        return [face_id for face_id, selected in self.face_states.items() if selected]

    def select_all_faces(self):
        for face_id in self.face_states:
            self.face_states[face_id] = True
        self.update_faces()
        self.update_selection_count()

    def deselect_all_faces(self):
        for face_id in self.face_states:
            self.face_states[face_id] = False
        self.update_faces()
        self.update_selection_count()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self.close_all_previews()
            self.show_preview(event.globalPosition().toPoint())
            FaceGridWidget._current_preview = self.preview_window
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            if self.preview_window.isVisible():
                self.preview_window.hide_and_clear()
                if FaceGridWidget._current_preview == self.preview_window:
                    FaceGridWidget._current_preview = None
        super().mouseReleaseEvent(event)

    def show_preview(self, global_pos):
        """Show preview at the specified position"""
        try:
            if self.db_manager and self.image_id:
                logging.debug(f"Showing preview for face ID {self.face_id}")
                full_image_data = self.db_manager.get_image_data(self.image_id)
                if full_image_data:
                    image = Image.open(io.BytesIO(full_image_data)).convert('RGB')
                    qimage = QImage(image.tobytes('raw', 'RGB'), 
                                  image.width, image.height,
                                  3 * image.width,
                                  QImage.Format.Format_RGB888)
                    pixmap = QPixmap.fromImage(qimage)
                    self.preview_window.show_image(pixmap, global_pos)
                else:
                    logging.warning(f"No image data found for image_id {self.image_id}")
        except Exception as e:
            logging.error(f"Error showing preview: {e}")

class NamingWidget(QWidget):
    """Widget for naming clustered faces."""

    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.current_cluster = 0
        self.clusters = {}
        self.last_cluster_id = None
        # Remove is_initialized flag as we'll load fresh data every time
        self.setup_ui()

    def setup_ui(self):
        layout = QHBoxLayout(self)

        names_group = QGroupBox("Existing Names")
        names_layout = QVBoxLayout(names_group)

        self.names_list = QListWidget()
        self.names_list.itemDoubleClicked.connect(self.use_selected_name)
        names_layout.addWidget(self.names_list)
        
        # Remove refresh button and its layout
        layout.addWidget(names_group)

        main_content = QWidget()
        main_layout = QVBoxLayout(main_content)

        controls_group = QGroupBox("Controls")
        controls_layout = QVBoxLayout(controls_group)

        # Add Delete button at the top
        delete_layout = QHBoxLayout()
        self.delete_button = QPushButton("Delete Selected Images")
        self.delete_button.clicked.connect(self.delete_selected_faces)
        self.delete_button.setStyleSheet("background-color: #ffcccc")  # Light red background
        delete_layout.addWidget(self.delete_button)
        delete_layout.addStretch()
        controls_layout.addLayout(delete_layout)

        selection_layout = QHBoxLayout()

        self.select_all_button = QPushButton("Select All")
        self.select_all_button.clicked.connect(self.select_all_faces)
        selection_layout.addWidget(self.select_all_button)

        self.deselect_all_button = QPushButton("Deselect All")
        self.deselect_all_button.clicked.connect(self.deselect_all_faces)
        selection_layout.addWidget(self.deselect_all_button)

        controls_layout.addLayout(selection_layout)

        nav_layout = QHBoxLayout()

        self.prev_button = QPushButton("Previous Cluster")
        self.prev_button.clicked.connect(self.show_previous_cluster)
        nav_layout.addWidget(self.prev_button)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Enter name for selected faces...")
        self.name_edit.returnPressed.connect(self.save_and_advance)
        nav_layout.addWidget(self.name_edit)

        self.save_button = QPushButton("Save Name")
        self.save_button.clicked.connect(self.save_names)
        nav_layout.addWidget(self.save_button)

        self.next_button = QPushButton("Next Cluster")
        self.next_button.clicked.connect(self.show_next_cluster)
        nav_layout.addWidget(self.next_button)

        controls_layout.addLayout(nav_layout)
        main_layout.addWidget(controls_group)

        faces_group = QGroupBox("Faces in Cluster")
        faces_layout = QVBoxLayout(faces_group)
        faces_layout.setSpacing(0)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        # Pass self.db_manager (not self) to FaceGridWidget:
        self.face_grid = FaceGridWidget(self.db_manager, self)
        scroll_area.setWidget(self.face_grid)

        faces_layout.addWidget(scroll_area)

        faces_group.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding
        )
        main_layout.addWidget(faces_group)

        # Add cluster position indicator above the status label
        self.cluster_indicator = QLabel("No clusters loaded")
        self.cluster_indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cluster_indicator.setStyleSheet("font-weight: bold; color: #0066cc;")
        main_layout.addWidget(self.cluster_indicator)

        self.status_label = QLabel("Ready")
        main_layout.addWidget(self.status_label)

        layout.addWidget(main_content, stretch=1)

    # Remove refresh_names_list method as it's no longer needed as a separate function
    # Its functionality is now part of showEvent

    def showEvent(self, event):
        """Called when the widget becomes visible."""
        super().showEvent(event)
        # Get and display names
        try:
            names = self.db_manager.get_unique_names()
            self.names_list.clear()
            self.names_list.addItems(sorted(names))
            logging.info(f"Loaded {len(names)} names")
        except Exception as e:
            logging.error(f"Error loading names: {e}")
            
        # Load clusters
        self.load_clusters()

    def hideEvent(self, event):
        """Called when the widget becomes hidden.""" 
        super().hideEvent(event)
        # Clear all data when tab is hidden
        self.clusters = {}
        self.current_cluster = 0
        self.last_cluster_id = None
        self.names_list.clear()
        if hasattr(self, 'face_grid'):
            self.face_grid.clear_layout()
        self.cluster_indicator.setText("No clusters loaded")
        self.status_label.setText("Ready")

    def load_clusters(self):
        """Load clusters and start with lowest available cluster number."""
        try:
            self.clusters = self.db_manager.get_face_clusters()
            if not self.clusters:
                self.status_label.setText("No clustered faces found")
                self.cluster_indicator.setText("No clusters loaded")
                self.update_controls(False)
                return

            # Always start with the lowest cluster number
            cluster_ids = sorted(self.clusters.keys())
            self.current_cluster = cluster_ids[0]
            self.last_cluster_id = self.current_cluster
            
            self.show_current_cluster()
            self.update_controls(True)

        except Exception as e:
            logging.error(f"Error loading clusters: {e}")
            self.status_label.setText(f"Error: {str(e)}")
            self.cluster_indicator.setText("No clusters loaded")
            self.update_controls(False)

    def show_current_cluster(self):
        if not self.clusters:
            self.cluster_indicator.setText("No clusters loaded")
            return

        faces = self.clusters[self.current_cluster]
        # No need to modify the face data here, just pass it directly
        self.face_grid.load_faces(faces)

        # Get total number of clusters and current position
        cluster_ids = sorted(self.clusters.keys())
        current_position = cluster_ids.index(self.current_cluster) + 1
        total_clusters = len(cluster_ids)

        # Update cluster indicator
        cluster_desc = "Noise Points" if self.current_cluster == -1 else f"Cluster {self.current_cluster}"
        self.cluster_indicator.setText(
            f"Viewing {cluster_desc} ({current_position} of {total_clusters} clusters)"
        )

        # Update status with face count
        self.status_label.setText(f"Found {len(faces)} faces in current cluster")

    def show_previous_cluster(self):
        """Show cluster with next lower number, wrap to highest if at lowest."""
        if not self.clusters:
            return

        cluster_ids = sorted(self.clusters.keys())
        current_idx = cluster_ids.index(self.current_cluster)
        
        if current_idx > 0:
            # There is a lower number available
            self.current_cluster = cluster_ids[current_idx - 1]
        else:
            # Wrap around to highest number
            self.current_cluster = cluster_ids[-1]
            
        self.show_current_cluster()
        self.name_edit.setFocus()

    def show_next_cluster(self):
        """Show cluster with next higher number, wrap to lowest if at highest."""
        if not self.clusters:
            return

        cluster_ids = sorted(self.clusters.keys())
        current_idx = cluster_ids.index(self.current_cluster)
        
        if current_idx < len(cluster_ids) - 1:
            # There is a higher number available
            self.current_cluster = cluster_ids[current_idx + 1]
        else:
            # Wrap around to lowest number
            self.current_cluster = cluster_ids[0]
            
        self.show_current_cluster()
        self.name_edit.setFocus()

    def save_and_advance(self):
        if self.save_names():
            self.name_edit.clear()
            self.name_edit.setFocus()

    def save_names(self) -> bool:
        name = self.name_edit.text().strip()
        if not name:
            self.status_label.setText("Please enter a name")
            return False

        face_ids = self.face_grid.get_selected_faces()
        if not face_ids:
            self.status_label.setText("No faces selected. Please select faces.")
            return False

        try:
            current_cluster_id = self.current_cluster

            if self.db_manager.update_face_names(face_ids, name):
                self.status_label.setText(f"Saved name '{name}' for {len(face_ids)} selected faces")

                # Get all current names and add the new one
                current_names = set(self.names_list.item(i).text() 
                                 for i in range(self.names_list.count()))
                current_names.add(name)
                
                # Clear and repopulate the list in sorted order
                self.names_list.clear()
                self.names_list.addItems(sorted(current_names))

                # Update clusters
                current_cluster_id = self.current_cluster
                self.clusters = self.db_manager.get_face_clusters()

                if not self.clusters:
                    self.status_label.setText("All faces have been named!")
                    self.update_controls(False)
                    return True

                # Get sorted cluster IDs
                available_clusters = sorted(self.clusters.keys())

                if current_cluster_id in self.clusters and self.clusters[current_cluster_id]:
                    # Stay on current cluster if it still has faces
                    self.current_cluster = current_cluster_id
                else:
                    # Find next higher cluster number
                    higher_clusters = [cid for cid in available_clusters if cid > current_cluster_id]
                    if higher_clusters:
                        self.current_cluster = higher_clusters[0]
                    else:
                        # Wrap to highest existing cluster
                        self.current_cluster = max(available_clusters)

                self.show_current_cluster()
                logging.info(f"After saving: Current cluster {self.current_cluster}, Available clusters: {available_clusters}")
                return True
            else:
                self.status_label.setText("Failed to save names")
                return False

        except Exception as e:
            logging.error(f"Error saving names: {e}")
            self.status_label.setText(f"Error saving names: {str(e)}")
            return False

    def select_all_faces(self):
        self.face_grid.select_all_faces()

    def deselect_all_faces(self):
        self.face_grid.deselect_all_faces()

    def update_controls(self, enabled: bool):
        """Enable or disable controls based on cluster availability"""
        self.prev_button.setEnabled(enabled)
        self.next_button.setEnabled(enabled)
        self.name_edit.setEnabled(enabled)
        self.save_button.setEnabled(enabled)
        self.select_all_button.setEnabled(enabled)
        self.deselect_all_button.setEnabled(enabled)

    def use_selected_name(self, item):
        """Apply selected name from list to current selection"""
        name = item.text()
        self.name_edit.setText(name)
        self.save_names()

    def delete_selected_faces(self):
        """Delete selected faces after confirmation."""
        selected_faces = self.face_grid.get_selected_faces()
        
        if not selected_faces:
            QMessageBox.warning(
                self,
                "No Selection",
                "Please select faces to delete first."
            )
            return

        reply = QMessageBox.question(
            self,
            'Confirm Delete',
            f'Are you sure you want to delete {len(selected_faces)} selected faces?\n'
            'This action cannot be undone.',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                current_cluster_id = self.current_cluster
                
                if self.db_manager.delete_faces(selected_faces):
                    self.status_label.setText(f"Successfully deleted {len(selected_faces)} faces")
                    
                    # Reload clusters
                    self.clusters = self.db_manager.get_face_clusters()
                    
                    if not self.clusters:
                        self.status_label.setText("No clusters remaining")
                        self.update_controls(False)
                        return

                    # Get sorted cluster IDs
                    available_clusters = sorted(self.clusters.keys())

                    # Try to stay on current cluster if it still exists and has faces
                    if current_cluster_id in self.clusters and self.clusters[current_cluster_id]:
                        self.current_cluster = current_cluster_id
                    else:
                        # Try to find next higher cluster
                        higher_clusters = [cid for cid in available_clusters if cid > current_cluster_id]
                        if higher_clusters:
                            self.current_cluster = higher_clusters[0]
                        else:
                            # If no higher cluster available, use highest existing cluster
                            self.current_cluster = max(available_clusters)

                    self.show_current_cluster()
                else:
                    self.status_label.setText("Error deleting faces")
            except Exception as e:
                logging.error(f"Error deleting faces: {e}")
                self.status_label.setText(f"Error: {str(e)}")