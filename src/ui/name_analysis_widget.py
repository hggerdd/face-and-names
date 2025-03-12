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
import sqlite3
from .shared.face_image_widget import FaceImageWidget
from .shared.image_preview import ImagePreviewWindow

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
        left_layout.addWidget(self.names_list)
        
        # Add rename button below list
        self.rename_button = QPushButton("Rename")
        self.rename_button.clicked.connect(self.rename_person)
        self.rename_button.setEnabled(False)
        left_layout.addWidget(self.rename_button)
        
        # Right panel with face grid and preview
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        
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
    
    def load_faces_for_name(self, name):
        """Load and display all faces for the selected name."""
        try:
            self.clear_faces()
            if not name:
                return
                
            # Get faces with their image_ids
            conn = sqlite3.connect(self.db_manager.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT f.id, f.face_image, f.image_id
                FROM faces f
                WHERE f.name = ? AND f.face_image IS NOT NULL
                ORDER BY f.id
            ''', (name,))
            faces = cursor.fetchall()
            conn.close()

            if not faces:
                self.status_label.setText(f"No faces found for '{name}'")
                return
            
            # Calculate number of columns based on container width
            container_width = self.faces_container.width()
            face_width = 130  # Face widget width + spacing
            columns = max(1, container_width // face_width)
            
            for idx, (face_id, face_image, image_id) in enumerate(faces):
                row = idx // columns
                col = idx % columns
                face_widget = FaceImageWidget(face_id, face_image, name)
                face_widget.image_id = image_id  # Store image_id for later use
                face_widget.clicked.connect(self.on_face_clicked)
                face_widget.rightClicked.connect(self.show_full_image)
                self.faces_layout.addWidget(face_widget, row, col)
                
            self.status_label.setText(f"Found {len(faces)} faces for '{name}'")
        except Exception as e:
            self.status_label.setText(f"Error loading faces: {str(e)}")
    
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
                # Get original image from thumbnails table
                image_data = self.db_manager.get_image_data(widget.image_id)
                if image_data:
                    image = Image.open(io.BytesIO(image_data)).convert('RGB')
                    # Scale image to fit preview area while maintaining aspect ratio
                    preview_size = self.preview_label.size()
                    image.thumbnail((preview_size.width(), preview_size.height()))
                    qimage = QImage(image.tobytes('raw', 'RGB'),
                                  image.width, image.height,
                                  3 * image.width,
                                  QImage.Format.Format_RGB888)
                    pixmap = QPixmap.fromImage(qimage)
                    self.preview_label.setPixmap(pixmap)
                    self.preview_label.show()
            except Exception as e:
                logging.error(f"Error showing original image: {e}")
    
    def show_full_image(self, face_id, pos):
        """Show full-size original image preview."""
        widget = self.sender()
        if widget and hasattr(widget, 'image_id'):
            try:
                # Get original image from thumbnails table
                image_data = self.db_manager.get_image_data(widget.image_id)
                if image_data:
                    image = Image.open(io.BytesIO(image_data)).convert('RGB')
                    qimage = QImage(image.tobytes('raw', 'RGB'),
                                  image.width, image.height,
                                  3 * image.width,
                                  QImage.Format.Format_RGB888)
                    pixmap = QPixmap.fromImage(qimage)
                    self.preview_window.show_image(pixmap, pos)
            except Exception as e:
                logging.error(f"Error showing full image: {e}")