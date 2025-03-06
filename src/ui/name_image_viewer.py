from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QListWidget, 
                            QListWidgetItem, QLabel, QScrollArea, QMenu)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap, QImage
import logging
from pathlib import Path
import os
import sqlite3
from .prediction_review_widget import ReviewGridWidget, FaceGridItem  # Add this import
from .components.face_image_widget import FaceImageWidget

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
            conn = sqlite3.connect(self.db_manager.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT f.id, f.face_image, f.name, f.predicted_name, f.prediction_confidence, i.image_id
                FROM faces f
                JOIN images i ON f.image_id = i.image_id
                WHERE f.name = ?
                ORDER BY i.image_id
            ''', (name,))
            
            faces_data = cursor.fetchall()
            self.face_grid.load_faces(faces_data)

            # Set up deletion handler for the grid
            self.face_grid.item_widgets = [w for w in self.face_grid.item_widgets if w and not w.isHidden()]
            for widget in self.face_grid.item_widgets:
                if hasattr(widget, 'image_widget'):
                    widget.image_widget.deleteClicked.connect(self.on_face_deleted)

        except Exception as e:
            logging.error(f"Error loading images for name: {e}")
        finally:
            if 'conn' in locals():
                conn.close()

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
            conn = sqlite3.connect(self.db_manager.db_path)
            cursor = conn.cursor()
            
            # Get image path for this face
            cursor.execute('''
                SELECT i.base_folder, i.sub_folder, i.filename
                FROM faces f
                JOIN images i ON f.image_id = i.image_id
                WHERE f.id = ?
            ''', (face_id,))
            
            result = cursor.fetchone()
            if result:
                base_folder, sub_folder, filename = result
                image_path = Path(base_folder) / sub_folder / filename
                
                menu = QMenu(self)
                open_action = menu.addAction("Open Image")
                open_folder_action = menu.addAction("Open Containing Folder")
                
                action = menu.exec(self.sender().mapToGlobal(pos))
                if action == open_action:
                    os.startfile(str(image_path))
                elif action == open_folder_action:
                    os.startfile(str(image_path.parent))
                    
        except Exception as e:
            logging.error(f"Error in context menu: {e}")
        finally:
            if 'conn' in locals():
                conn.close()
