from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
    QLineEdit, QScrollArea, QGridLayout, QGroupBox, QSizePolicy, 
    QListWidget, QMessageBox, QInputDialog
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QPixmap, QImage
from PIL import Image, ImageOps, ImageEnhance
import io
import logging
from .shared.face_image_widget import FaceImageWidget
from .shared.image_preview import ImagePreviewWindow

# Set up logging
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")

class FaceGridWidget(QWidget):
    """Widget to display a grid of faces from the same cluster."""

    # Signal definitions
    imageDoubleClicked = pyqtSignal(int, str)  # Emits face_id and predicted_name when image is double-clicked
    clicked = pyqtSignal(int)  # Emits face_id when clicked
    nameDoubleClicked = pyqtSignal(int, str)  # Emits face_id and current_name when name is double-clicked
    
    def __init__(self, db_manager=None, parent=None):
        super().__init__(parent)
        self.face_states = {}
        self.current_faces = []
        self.face_size = 100
        self.min_column_width = 130
        self.selection_count_label = QLabel("0 faces selected")
        self.selection_count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.db_manager = db_manager
        self.resize_timer = None  # Will be initialized in setup_ui
        self.setup_ui()

    def hideEvent(self, event):
        """Close any open previews when widget is hidden."""
        self.clear_layout()  # Clear layout when hidden
        FaceImageWidget.close_all_previews()
        super().hideEvent(event)

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Create a widget to hold the grid
        self.grid_container = QWidget(self)
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setSpacing(10)

        main_layout.addWidget(self.grid_container)
        main_layout.addWidget(self.selection_count_label)

        # Setup resize timer to prevent multiple rapid updates
        self.resize_timer = QTimer(self)
        self.resize_timer.setSingleShot(True)
        self.resize_timer.timeout.connect(self._delayed_resize)

    def update_selection_count(self):
        """Update the selection count label."""
        selected_count = len(self.get_selected_faces())
        total_count = len(self.current_faces)
        self.selection_count_label.setText(f"{selected_count} of {total_count} faces selected")

    def on_face_deleted(self, face_id):
        """Handle face deletion from grid."""
        try:
            logging.debug(f"FaceGridWidget received delete signal for face_id: {face_id}")
            # Delete the face from database first
            if self.db_manager.delete_faces([face_id]):
                logging.debug(f"Successfully deleted face_id {face_id} from database")
                # Remove face from current faces list
                self.current_faces = [face for face in self.current_faces if face[0] != face_id]
                logging.debug(f"Removed face_id {face_id} from current_faces")
                
                # Remove face from states
                if face_id in self.face_states:
                    del self.face_states[face_id]
                    logging.debug(f"Removed face_id {face_id} from face_states")
                
                # Update the grid with the modified face list
                self.update_faces(force=True)
                self.update_selection_count()
                logging.debug(f"Grid updated after deleting face_id {face_id}")
            else:
                logging.error(f"Database deletion failed for face_id {face_id}")
                
        except Exception as e:
            logging.error(f"Error deleting face {face_id}: {e}")
            QMessageBox.warning(self, "Error", f"Failed to delete face: {str(e)}")

    def create_face_widget(self, face_id, image_data, name, predicted_name, full_image_id):
        """Create a widget to display a single face."""
        try:
            bbox = None
            # Get the bounding box data using proper connection handling
            with self.db_manager.get_connection() as (_, cursor):
                cursor.execute('''
                    SELECT bbox_x, bbox_y, bbox_w, bbox_h 
                    FROM faces 
                    WHERE id = ?
                ''', (face_id,))
                bbox = cursor.fetchone()

            face_widget = FaceImageWidget(
                face_id=face_id,
                image_data=image_data,
                name=name,
                predicted_name=predicted_name,
                face_size=self.face_size,
                active=self.face_states.get(face_id, True),
                db_manager=self.db_manager,
                bbox=bbox,
                parent=self
            )
            face_widget.image_id = full_image_id
            face_widget.clicked.connect(lambda: self.toggle_face_selection(face_id))
            face_widget.deleteClicked.connect(self.on_face_deleted)
            
            # Connect and log name double click
            logging.debug(f"Connecting nameDoubleClicked signal for face_id={face_id}")
            face_widget.nameDoubleClicked.connect(lambda fid, name: self.on_name_double_clicked(fid, name))
            face_widget.nameDoubleClicked.connect(lambda fid, name: self.nameDoubleClicked.emit(fid, name))
            
            # Forward the imageDoubleClicked signal
            face_widget.imageDoubleClicked.connect(lambda fid, pred: self.imageDoubleClicked.emit(fid, pred))
            return face_widget
        except Exception as e:
            logging.error(f"Error creating face widget: {e}")
            return None

    def on_name_double_clicked(self, face_id, current_name):
        """Handle double-click on name label."""
        logging.debug(f"FaceGridWidget.on_name_double_clicked called for face_id={face_id}, current_name='{current_name}'")
        try:
            new_name, ok = QInputDialog.getText(
                self,
                'Rename Face',
                'Enter new name:',
                text=current_name
            )
            
            if ok and new_name and new_name != current_name:
                if self.db_manager.update_face_name(face_id, new_name):
                    # Update the face widget's name
                    logging.debug(f"Updated name for face {face_id} from '{current_name}' to '{new_name}'")
                    # Reload faces to reflect the change
                    self.update_faces(force=True)
                else:
                    QMessageBox.warning(self, "Error", "Failed to update name")
        except Exception as e:
            logging.error(f"Error renaming face: {e}")
            QMessageBox.warning(self, "Error", f"Failed to rename face: {str(e)}")

    def on_image_double_clicked(self, face_id, predicted_name):
        """Handle double-click on face image."""
        try:
            if not predicted_name:
                return

            if self.db_manager.update_face_name(face_id, predicted_name):
                logging.debug(f"Updated name for face {face_id} to predicted name '{predicted_name}'")
                
                # Reload clusters to reflect changes
                current_cluster_id = self.current_cluster
                self.clusters = self.db_manager.get_face_clusters()

                if not self.clusters:
                    self.status_label.setText("All faces have been named!")
                    self.update_controls(False)
                    return

                # Try to stay on current cluster if it still has faces
                if current_cluster_id in self.clusters and self.clusters[current_cluster_id]:
                    self.current_cluster = current_cluster_id
                else:
                    # Find next available cluster
                    available_clusters = sorted(self.clusters.keys())
                    higher_clusters = [cid for cid in available_clusters if cid > current_cluster_id]
                    if higher_clusters:
                        self.current_cluster = higher_clusters[0]
                    else:
                        # If no higher cluster available, use highest existing cluster
                        self.current_cluster = max(available_clusters)

                # Show updated cluster
                self.show_current_cluster()
                self.name_edit.setFocus()
            else:
                QMessageBox.warning(self, "Error", "Failed to update name")
        except Exception as e:
            logging.error(f"Error setting predicted name: {e}")
            QMessageBox.warning(self, "Error", f"Failed to set predicted name: {str(e)}")

    def toggle_face_selection(self, face_id):
        self.face_states[face_id] = not self.face_states.get(face_id, True)
        self._update_widget_states()
        self.update_selection_count()

    def _update_widget_states(self):
        """Update only the active states of existing widgets without recreating them."""
        for i in range(self.grid_layout.count()):
            widget = self.grid_layout.itemAt(i).widget()
            if isinstance(widget, FaceImageWidget):
                widget.set_active(self.face_states.get(widget.face_id, True))

    def update_faces(self, force=False):
        """Update the grid layout with current faces."""
        if not self.current_faces:
            return

        # Calculate columns based on container width
        width = self.grid_container.width()
        columns = max(1, width // self.min_column_width)
        
        # Only recreate widgets if force=True or column count changed
        current_columns = self.grid_layout.columnCount()
        if force or columns != current_columns:
            self.clear_layout()
            
            for idx, face_data in enumerate(self.current_faces):
                row = idx // columns
                col = idx % columns
                face_id, image_data, name, predicted_name, full_image_id = face_data
                face_widget = self.create_face_widget(face_id, image_data, name, predicted_name, full_image_id)
                if face_widget:
                    self.grid_layout.addWidget(face_widget, row, col)
        else:
            # Just update widget states if layout hasn't changed
            self._update_widget_states()

    def _delayed_resize(self):
        """Handle resize after a delay to prevent rapid updates."""
        if self.current_faces:
            self.update_faces(force=False)

    def resizeEvent(self, event):
        """Handle resize events with debouncing."""
        super().resizeEvent(event)
        if self.resize_timer:
            self.resize_timer.start(100)  # 100ms delay

    def load_faces(self, faces):
        """Load new faces into the grid."""
        self.current_faces = faces
        self.face_states = {face[0]: True for face in faces}
        self.update_faces(force=True)
        self.update_selection_count()

    def clear_layout(self):
        while self.grid_layout.count():
            child = self.grid_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

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

class NamingWidget(QWidget):
    """Widget for naming clustered faces."""

    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.current_name = None
        self.preview_window = ImagePreviewWindow()
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
        faces_layout.setContentsMargins(0, 0, 0, 0)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        # Pass self.db_manager (not self) to FaceGridWidget:
        self.face_grid = FaceGridWidget(self.db_manager, self)
        logging.debug("Creating FaceGridWidget in NamingWidget")
        
        # Connect grid signals including image double click and name double click
        self.face_grid.imageDoubleClicked.connect(self.on_image_double_clicked)
        logging.debug("Connected imageDoubleClicked signal in NamingWidget")
        
        self.face_grid.nameDoubleClicked.connect(self.on_name_double_clicked)
        logging.debug("Connected nameDoubleClicked signal in NamingWidget")
        
        scroll_area.setWidget(self.face_grid)

        faces_layout.addWidget(scroll_area)

        faces_group.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding
        )
        main_layout.addWidget(faces_group, stretch=1)

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
        """Load clusters (such as face groups from db_manager) and start with lowest cluster number."""
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
        self.status_label.setText(f"Found {len(faces)} faces in cluster")

    def show_previous_cluster(self):
        """Show cluster with next lower number, wrap to highest if at lowest."""
        if not self.clusters:
            return

        cluster_ids = sorted(self.clusters.keys())
        current_idx = cluster_ids.index(self.current_cluster)
        
        if (current_idx > 0):
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
            self.status_label.setText("No faces selected. Select faces first.")
            return False

        try:
            current_cluster_id = self.current_cluster
            
            # Create list of (name, face_id) tuples for update
            updates = [(name, face_id) for face_id in face_ids]
            
            if self.db_manager.update_face_names(updates):
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
                    
            logging.info(f"Saved name: {name} - {len(face_ids)} faces selected.")

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
            logging.info(f"Current cluster: {self.current_cluster}, Available clusters: {available_clusters}")
            return True
        except Exception as e:
            logging.error(f"Error saving name: {e}")
            self.status_label.setText(f"Error saving name: {str(e)}")
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

    def on_image_double_clicked(self, face_id, predicted_name):
        """Handle double-click on face image."""
        try:
            if not predicted_name:
                return

            if self.db_manager.update_face_name(face_id, predicted_name):
                logging.debug(f"Updated name for face {face_id} to predicted name '{predicted_name}'")
                
                # Reload clusters to reflect changes
                current_cluster_id = self.current_cluster
                self.clusters = self.db_manager.get_face_clusters()

                if not self.clusters:
                    self.status_label.setText("All faces have been named!")
                    self.update_controls(False)
                    return

                # Try to stay on current cluster if it still has faces
                if current_cluster_id in self.clusters and self.clusters[current_cluster_id]:
                    self.current_cluster = current_cluster_id
                else:
                    # Find next available cluster
                    available_clusters = sorted(self.clusters.keys())
                    higher_clusters = [cid for cid in available_clusters if cid > current_cluster_id]
                    if higher_clusters:
                        self.current_cluster = higher_clusters[0]
                    else:
                        # If no higher cluster available, use highest existing cluster
                        self.current_cluster = max(available_clusters)

                # Show updated cluster
                self.show_current_cluster()
                self.name_edit.setFocus()
            else:
                QMessageBox.warning(self, "Error", "Failed to update name")
        except Exception as e:
            logging.error(f"Error setting predicted name: {e}")
            QMessageBox.warning(self, "Error", f"Failed to set predicted name: {str(e)}")

    def on_name_double_clicked(self, face_id, current_name):
        """Handle double-click on name label to rename face."""
        logging.debug(f"NamingWidget.on_name_double_clicked called with face_id={face_id}, current_name='{current_name}'")
        try:
            new_name, ok = QInputDialog.getText(
                self,
                'Rename Face',
                'Enter new name:',
                text=current_name
            )
            
            if ok and new_name and new_name != current_name:
                if self.db_manager.update_face_name(face_id, new_name):
                    logging.debug(f"Updated name for face {face_id} from '{current_name}' to '{new_name}'")
                    
                    # Reload clusters to reflect changes
                    current_cluster_id = self.current_cluster
                    self.clusters = self.db_manager.get_face_clusters()

                    if not self.clusters:
                        self.status_label.setText("All faces have been named!")
                        self.update_controls(False)
                        return

                    # Try to stay on current cluster if it still has faces
                    if current_cluster_id in self.clusters and self.clusters[current_cluster_id]:
                        self.current_cluster = current_cluster_id
                    else:
                        # Find next available cluster
                        available_clusters = sorted(self.clusters.keys())
                        higher_clusters = [cid for cid in available_clusters if cid > current_cluster_id]
                        if higher_clusters:
                            self.current_cluster = higher_clusters[0]
                        else:
                            # If no higher cluster available, use highest existing cluster
                            self.current_cluster = max(available_clusters)

                    # Get all current names and add the new one
                    current_names = set(self.names_list.item(i).text() 
                                    for i in range(self.names_list.count()))
                    current_names.add(new_name)
                    
                    # Clear and repopulate the list in sorted order
                    self.names_list.clear()
                    self.names_list.addItems(sorted(current_names))

                    # Show updated cluster
                    self.show_current_cluster()
                    self.status_label.setText(f"Renamed face to '{new_name}'")
                    self.name_edit.setFocus()
                else:
                    QMessageBox.warning(self, "Error", "Failed to update name")
        except Exception as e:
            logging.error(f"Error renaming face: {e}")
            QMessageBox.warning(self, "Error", f"Failed to rename face: {str(e)}")