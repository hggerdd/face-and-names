from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QListWidget, 
                            QListWidgetItem, QLabel, QScrollArea, QMenu)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap, QImage
import logging
from pathlib import Path
from .prediction_review_widget import ReviewGridWidget, FaceGridItem  # Add this import
from .components.face_image_widget import FaceImageWidget
from ..utils.platform import open_file, open_folder

class NameImageViewer(QWidget):
    def __init__(self, db_manager):
        super().__init__()
        self.db_manager = db_manager
        self.current_faces = []
        self.setup_ui()

    def setup_ui(self):
        layout = QHBoxLayout(self)
        
        # Names list on the left
        self.names_list = QListWidget()
        self.names_list.setMaximumWidth(200)
        self.names_list.itemClicked.connect(self.load_images_for_name)
        layout.addWidget(self.names_list)

        # Grid area on the right
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        
        # Use ReviewGridWidget for the face grid
        self.face_grid = ReviewGridWidget(db_manager=self.db_manager)
        right_layout.addWidget(self.face_grid)
        
        layout.addWidget(right_widget)

    def showEvent(self, event):
        self.load_names()

    def load_names(self):
        try:
            self.names_list.clear()
            names = self.db_manager.get_unique_names()
            self.names_list.addItems(names)
        except Exception as e:
            logging.error(f"Error loading names: {e}")

    def load_images_for_name(self, item):
        try:
            name = item.text()
            faces_data = self.db_manager.get_faces_by_name(name)
            self.face_grid.load_faces(faces_data)

            # Set up deletion handler for the grid
            self.face_grid.item_widgets = [w for w in self.face_grid.item_widgets if w and not w.isHidden()]
            for widget in self.face_grid.item_widgets:
                if hasattr(widget, 'image_widget'):
                    widget.image_widget.deleteClicked.connect(self.on_face_deleted)

        except Exception as e:
            logging.error(f"Error loading images for name: {e}")

    def on_face_deleted(self, face_id):
        try:
            if self.db_manager.delete_faces([face_id]):
                # Remove the face from the grid
                self.face_grid.all_faces = [f for f in self.face_grid.all_faces if f[0] != face_id]
                # Refresh the names list as counts might have changed
                self.load_names()
                # Refresh the grid if needed
                if not self.face_grid.all_faces:
                    self.names_list.takeItem(self.names_list.currentRow())
                else:
                    self.face_grid.update_visible_items()
        except Exception as e:
            logging.error(f"Error handling face deletion: {e}")

    def show_context_menu(self, pos, face_id):
        try:
            result = self.db_manager.get_image_path_for_face(face_id)
            if result:
                base_folder, sub_folder, filename = result
                image_path = Path(base_folder) / sub_folder / filename
                
                menu = QMenu(self)
                open_action = menu.addAction("Open Image")
                open_folder_action = menu.addAction("Open Containing Folder")
                
                action = menu.exec(self.sender().mapToGlobal(pos))
                if action == open_action:
                    open_file(image_path)
                elif action == open_folder_action:
                    open_folder(image_path.parent)
                    
        except Exception as e:
            logging.error(f"Error in context menu: {e}")
