from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
    QLineEdit, QScrollArea, QComboBox, QMessageBox, QInputDialog,
    QListWidget, QSplitter, QGridLayout
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap, QImage
from PIL import Image, ImageOps, ImageEnhance
import io
import logging
from .shared.face_image_widget import FaceImageWidget
from .shared.image_preview import ImagePreviewWindow
from .shared.image_utils import ImageProcessor
from .components.timeline_widget import TimelineWidget

class NameAnalysisWidget(QWidget):
    """Widget for analyzing faces by name and managing name changes."""
    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.current_name = None
        self.preview_window = ImagePreviewWindow()
        self.setup_ui()
        
    def setup_ui(self):
        layout = QHBoxLayout(self)
        
        # Create splitter for left/right panels
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left panel with name list
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        
        # Add name list
        self.names_list = QListWidget()
        self.names_list.currentTextChanged.connect(self.on_name_selected)
        self.names_list.setCursor(Qt.CursorShape.PointingHandCursor)
        left_layout.addWidget(self.names_list)
        
        # Add rename button below list
        self.rename_button = QPushButton("Rename")
        self.rename_button.clicked.connect(self.rename_person)
        self.rename_button.setEnabled(False)
        left_layout.addWidget(self.rename_button)
        
        # Right panel with timeline, face grid and preview
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        
        # Add timeline widget
        self.timeline = TimelineWidget()
        right_layout.addWidget(self.timeline)
        
        # Add scrollable face grid area
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        self.faces_container = QWidget()
        self.faces_layout = QGridLayout(self.faces_container)
        self.faces_layout.setSpacing(10)
        scroll_area.setWidget(self.faces_container)
        
        # Add original image preview area
        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumHeight(200)
        self.preview_label.hide()  # Initially hidden
        
        right_layout.addWidget(scroll_area, stretch=2)
        right_layout.addWidget(self.preview_label, stretch=1)
        
        # Add panels to splitter
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        
        # Set initial split sizes (1/4 for list, 3/4 for faces)
        splitter.setSizes([200, 600])
        
        # Status label at bottom
        self.status_label = QLabel("Select a name to view faces")
        right_layout.addWidget(self.status_label)
        
        layout.addWidget(splitter)
    
    def showEvent(self, event):
        """Called when the widget becomes visible."""
        super().showEvent(event)
        self.refresh_names()
    
    def hideEvent(self, event):
        """Called when the widget becomes hidden."""
        super().hideEvent(event)
        self.clear_faces()
        # Ensure any open previews are closed
        FaceImageWidget.close_all_previews()
        
    def refresh_names(self):
        """Update the list of available names."""
        try:
            self.names_list.clear()
            names = self.db_manager.get_unique_names()
            self.names_list.addItems(sorted(names))
            self.status_label.setText(f"Found {len(names)} unique names")
        except Exception as e:
            self.status_label.setText(f"Error loading names: {str(e)}")
    
    def on_name_selected(self, name):
        """Handle name selection from list."""
        self.current_name = name
        self.rename_button.setEnabled(bool(name))
        self.load_faces_for_name(name)
        self.preview_label.hide()
        
        # Update timeline
        if name:
            dates = self.db_manager.get_face_dates_by_name(name)
            self.timeline.update_data(dates)
        else:
            self.timeline.update_data([])
    
    def load_faces_for_name(self, name):
        """Load and display all faces for the selected name."""
        try:
            self.clear_faces()
            if not name:
                return
                
            # Get faces with bounding box data
            with self.db_manager.get_connection() as (_, cursor):
                cursor.execute('''
                    SELECT id, face_image, image_id, bbox_x, bbox_y, bbox_w, bbox_h
                    FROM faces 
                    WHERE name = ? AND face_image IS NOT NULL
                    ORDER BY id
                ''', (name,))
                faces = cursor.fetchall()

            if not faces:
                self.status_label.setText(f"No faces found for '{name}'")
                return
            
            # Calculate number of columns based on container width
            container_width = self.faces_container.width()
            face_width = 130  # Face widget width + spacing
            columns = max(1, container_width // face_width)
            
            for idx, (face_id, face_image, image_id, bbox_x, bbox_y, bbox_w, bbox_h) in enumerate(faces):
                row = idx // columns
                col = idx % columns
                bbox = (bbox_x, bbox_y, bbox_w, bbox_h) if bbox_x is not None else None
                face_widget = FaceImageWidget(
                    face_id=face_id,
                    image_data=face_image,
                    name=name,
                    predicted_name=None,
                    db_manager=self.db_manager,
                    bbox=bbox
                )
                face_widget.image_id = image_id
                face_widget.clicked.connect(self.on_face_clicked)
                face_widget.rightClicked.connect(self.show_full_image)
                face_widget.deleteClicked.connect(self.on_face_deleted)
                face_widget.nameDoubleClicked.connect(self.on_name_double_clicked)
                self.faces_layout.addWidget(face_widget, row, col)
                
            self.status_label.setText(f"Found {len(faces)} faces for '{name}'")
        except Exception as e:
            self.status_label.setText(f"Error loading faces: {str(e)}")
            logging.error(f"Error loading faces: {e}")

    def on_face_deleted(self, face_id):
        """Handle face deletion from grid."""
        try:
            logging.debug(f"NameAnalysisWidget received delete signal for face_id: {face_id}")
            # Delete the face from database first
            if self.db_manager.delete_faces([face_id]):
                logging.debug(f"Successfully deleted face_id {face_id} from database")
                # Reload faces for the current name
                self.load_faces_for_name(self.current_name)
            else:
                logging.error(f"Database deletion failed for face_id {face_id}")
                
        except Exception as e:
            logging.error(f"Error deleting face {face_id}: {e}")
            QMessageBox.warning(self, "Error", f"Failed to delete face: {str(e)}")

    def clear_faces(self):
        """Remove all faces from the display."""
        while self.faces_layout.count():
            child = self.faces_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
    
    def rename_person(self):
        """Rename the current person across all their faces."""
        if not self.current_name:
            return
            
        new_name, ok = QInputDialog.getText(
            self, 'Rename Person', 
            'Enter new name:', 
            text=self.current_name
        )
        
        if ok and new_name and new_name != self.current_name:
            try:
                # Update all faces with exact name match
                self.db_manager.update_person_name(self.current_name, new_name)
                self.refresh_names()
                self.status_label.setText(f"Successfully renamed '{self.current_name}' to '{new_name}'")
                # Select the new name in the list
                items = self.names_list.findItems(new_name, Qt.MatchFlag.MatchExactly)
                if items:
                    self.names_list.setCurrentItem(items[0])
            except Exception as e:
                self.status_label.setText(f"Error renaming person: {str(e)}")
                QMessageBox.critical(self, "Error", f"Failed to rename person: {str(e)}")
    
    def on_face_clicked(self, face_id):
        """Handle face click to show original image."""
        widget = self.sender()
        if widget and hasattr(widget, 'image_id'):
            try:
                image_data = self.db_manager.get_image_data(widget.image_id)
                preview_size = self.preview_label.size()
                pixmap = ImageProcessor.create_pixmap_from_data(image_data, preview_size)
                if pixmap:
                    self.preview_label.setPixmap(pixmap)
                    self.preview_label.show()
            except Exception as e:
                logging.error(f"Error showing original image: {e}")
    
    def show_full_image(self, face_id, pos):
        """Show full-size original image preview."""
        widget = self.sender()
        if widget and hasattr(widget, 'image_id'):
            try:
                image_data = self.db_manager.get_image_data(widget.image_id)
                pixmap = ImageProcessor.create_pixmap_from_data(image_data)
                if pixmap:
                    # Store preview window reference in the widget
                    if not hasattr(widget, 'preview_window'):
                        widget.preview_window = self.preview_window
                    widget.preview_window.show_image(pixmap, pos)
            except Exception as e:
                logging.error(f"Error showing full image: {e}")

    def on_name_double_clicked(self, face_id, current_name):
        """Handle double-click on name label."""
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
                    # Refresh names list and reload faces
                    self.refresh_names()
                    self.load_faces_for_name(new_name)
                else:
                    QMessageBox.warning(self, "Error", "Failed to update name")
        except Exception as e:
            logging.error(f"Error renaming face: {e}")
            QMessageBox.warning(self, "Error", f"Failed to rename face: {str(e)}")