from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                           QLabel, QScrollArea, QTableWidget, QTableWidgetItem, 
                           QSplitter, QMenu, QInputDialog, QRubberBand, QMessageBox,
                           QStyle)
from PyQt6.QtCore import Qt, QRect, QPoint, QSize
from PyQt6.QtGui import QPixmap, QImage, QPainter, QPen, QColor
from pathlib import Path
import logging
import io
import sqlite3
from .components.image_tree import ImageTreeWidget
from .shared.font_config import FontConfig

class ThumbnailViewer(QWidget):
    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.current_folder = None
        self.current_image_id = None
        self.current_images = []
        self.current_index = -1
        self.selected_images = []
        self.current_image_path = None
        self.face_boxes = []
        self.rubber_band = None
        self.drawing = False
        self.origin = None
        self.current_pixmap = None
        self.pixmap_rect = None
        self.setup_ui()

    def setup_ui(self):
        layout = QHBoxLayout(self)
        
        # Add tree view on the left
        self.image_tree = ImageTreeWidget()
        self.image_tree.setMinimumWidth(250)
        self.image_tree.folderSelected.connect(self.on_folder_selected)
        self.image_tree.imageSelected.connect(self.on_image_selected)
        layout.addWidget(self.image_tree)
        
        # Add splitter between tree and content
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)
        
        # Rest of existing UI in right panel
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        
        # Add help text at the top with standardized font
        help_label = QLabel(
            "Usage:\n"
            "• Right-click a face to edit name or delete\n"
            "• Left-click and drag to draw a new face box"
        )
        help_label.setFont(FontConfig.get_default_font())
        help_label.setStyleSheet("""
            QLabel {
                background-color: #f0f0f0;
                padding: 5px;
                border-radius: 3px;
                color: #666;
            }
        """)
        right_layout.addWidget(help_label)

        # Navigation buttons with standardized font
        nav_layout = QHBoxLayout()
        
        self.prev_button = QPushButton("Previous")
        self.prev_button.setFont(FontConfig.get_default_font())
        self.prev_button.clicked.connect(self.show_previous)
        nav_layout.addWidget(self.prev_button)
        
        self.next_button = QPushButton("Next")
        self.next_button.setFont(FontConfig.get_default_font())
        self.next_button.clicked.connect(self.show_next)
        nav_layout.addWidget(self.next_button)
        
        right_layout.addLayout(nav_layout)
        
        # Image info with standardized font
        self.info_label = QLabel()
        self.info_label.setFont(FontConfig.get_default_font())
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right_layout.addWidget(self.info_label)
        
        # Create splitter for image and metadata
        inner_splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left side: Scroll area for image
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        # Image label
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        scroll_area.setWidget(self.image_label)
        
        # Right side: Metadata table with standardized font
        self.metadata_table = QTableWidget()
        self.metadata_table.setFont(FontConfig.get_label_font())
        self.metadata_table.setColumnCount(2)
        self.metadata_table.setHorizontalHeaderLabels(["Key", "Value"])
        self.metadata_table.horizontalHeader().setFont(FontConfig.get_default_font())
        self.metadata_table.horizontalHeader().setStretchLastSection(True)
        
        # Add widgets to inner splitter
        inner_splitter.addWidget(scroll_area)
        inner_splitter.addWidget(self.metadata_table)
        
        # Set initial sizes (70% image, 30% metadata)
        inner_splitter.setSizes([700, 300])
        
        right_layout.addWidget(inner_splitter)
        
        # Set stretch factor for the splitter
        right_layout.setStretchFactor(inner_splitter, 1)
        
        splitter.addWidget(self.image_tree)
        splitter.addWidget(right_panel)
        splitter.setSizes([250, 750])  # Set initial split
        
        # Initial tree population
        self.populate_image_tree()

    def populate_image_tree(self):
        """Load image structure into tree."""
        images = self.db_manager.get_image_structure()
        self.image_tree.populate_tree(images)

    def on_folder_selected(self, folder_path: Path):
        """Handle folder selection in tree."""
        try:
            self.current_folder = folder_path
            images = self.db_manager.get_images_in_folder(folder_path)
            if images:
                self.selected_images = [img_id for img_id, _ in images]
                self.prev_button.setEnabled(len(self.selected_images) > 1)
                self.next_button.setEnabled(len(self.selected_images) > 1)
            else:
                self.clear_display()
        except Exception as e:
            logging.error(f"Error loading folder images: {e}")
            self.clear_display()

    def on_image_selected(self, image_path: Path):
        """Handle direct image selection from tree."""
        try:
            base_folder = str(image_path.parent.parent)
            sub_folder = image_path.parent.name
            filename = image_path.name
            
            if self.current_folder != image_path.parent:
                self.on_folder_selected(image_path.parent)
            
            conn = sqlite3.connect(self.db_manager.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT image_id FROM images 
                WHERE base_folder = ? AND sub_folder = ? AND filename = ?
            ''', (base_folder, sub_folder, filename))
            result = cursor.fetchone()
            
            if result:
                image_id = result[0]
                if image_id in self.selected_images:
                    self.current_index = self.selected_images.index(image_id)
                    self.current_image_id = image_id
                    self.show_current_image()
                    
        except Exception as e:
            logging.error(f"Error selecting image: {e}")
        finally:
            if 'conn' in locals():
                conn.close()

    def clear_display(self):
        """Clear the image display and disable navigation."""
        self.selected_images = []
        self.current_image_id = None
        self.current_index = -1
        self.image_label.clear()
        self.info_label.setText("No images in selected folder")
        self.metadata_table.setRowCount(0)
        self.prev_button.setEnabled(False)
        self.next_button.setEnabled(False)
        
    def load_images_for_folder(self, folder_path: Path):
        """Load images for selected folder."""
        images = self.db_manager.get_images_in_folder(folder_path)
        self.current_images = images
        self.current_index = 0
        self.show_current_image()
        
    def showEvent(self, event):
        super().showEvent(event)
        self.load_first_image()
        
    def load_first_image(self):
        """Load the first available image."""
        conn = None
        try:
            conn = sqlite3.connect(self.db_manager.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT MIN(image_id) 
                FROM thumbnails
            ''')
            result = cursor.fetchone()
            
            if result and result[0]:
                self.current_image_id = result[0]
                self.show_current_image()
            else:
                self.info_label.setText("No images found")
                self.image_label.clear()
                
        except Exception as e:
            logging.error(f"Error loading first image: {e}")
        finally:
            if conn:
                conn.close()
            
    def show_previous(self):
        """Show previous image and update tree selection."""
        if not self.selected_images:
            return
            
        self.current_index = (self.current_index - 1) % len(self.selected_images)
        self.current_image_id = self.selected_images[self.current_index]
        self._update_tree_selection()
        self.show_current_image()
            
    def show_next(self):
        """Show next image and update tree selection."""
        if not self.selected_images:
            return
            
        self.current_index = (self.current_index + 1) % len(self.selected_images)
        self.current_image_id = self.selected_images[self.current_index]
        self._update_tree_selection()
        self.show_current_image()
            
    def show_current_image(self):
        """Display current image and its info with face bounding boxes."""
        conn = None
        try:
            conn = sqlite3.connect(self.db_manager.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT t.thumbnail, i.base_folder, i.sub_folder, i.filename,
                       f.bbox_x, f.bbox_y, f.bbox_w, f.bbox_h, f.name, f.predicted_name,
                       f.id as face_id
                FROM thumbnails t
                JOIN images i ON t.image_id = i.image_id
                LEFT JOIN faces f ON i.image_id = f.image_id
                WHERE t.image_id = ?
            ''', (self.current_image_id,))
            
            results = cursor.fetchall()
            if not results:
                return

            thumbnail_data = results[0][0]
            base_folder, sub_folder, filename = results[0][1:4]
            
            cursor.execute('''
                SELECT meta_key, meta_type, meta_value
                FROM image_metadata
                WHERE image_id = ?
                ORDER BY meta_key
            ''', (self.current_image_id,))
            
            metadata = cursor.fetchall()
            
            self.metadata_table.setRowCount(len(metadata))
            for row, (key, type_, value) in enumerate(metadata):
                display_key = f"{type_}: {key}"
                
                key_item = QTableWidgetItem(display_key)
                value_item = QTableWidgetItem(value)
                
                self.metadata_table.setItem(row, 0, key_item)
                self.metadata_table.setItem(row, 1, value_item)
            
            self.metadata_table.resizeColumnsToContents()
            
            full_path = f"{base_folder}/{sub_folder}/{filename}"
            face_count = sum(1 for r in results if r[4] is not None)
            self.info_label.setText(
                f"Image ID: {self.current_image_id}\n"
                f"Path: {full_path}\n"
                f"Faces detected: {face_count}"
            )
            
            image = QImage.fromData(thumbnail_data)
            original_pixmap = QPixmap.fromImage(image)
            
            self.original_width = original_pixmap.width()
            self.original_height = original_pixmap.height()
            
            available_width = self.image_label.width()
            if original_pixmap.width() > available_width:
                pixmap = original_pixmap.scaledToWidth(available_width, Qt.TransformationMode.SmoothTransformation)
            else:
                pixmap = original_pixmap
                
            self.display_width = pixmap.width()
            self.display_height = pixmap.height()

            self.face_boxes = []
            
            painter = QPainter(pixmap)
            pen = QPen(QColor(255, 0, 0))
            pen.setWidth(2)
            painter.setPen(pen)
            
            for result in results:
                if result[4] is not None:
                    rel_x, rel_y, rel_w, rel_h = result[4:8]
                    face_id = result[10]
                    name = result[8] or result[9]
                    
                    x = int(rel_x * self.display_width)
                    y = int(rel_y * self.display_height)
                    w = int(rel_w * self.display_width)
                    h = int(rel_h * self.display_height)
                    
                    self.face_boxes.append({
                        'rect': (x, y, w, h),
                        'rel_coords': (rel_x, rel_y, rel_w, rel_h),
                        'face_id': face_id,
                        'name': name
                    })
                    
                    painter.drawRect(x, y, w, h)
                    
                    if name:
                        painter.drawText(x, y - 5, name)

            painter.end()
            self.image_label.setPixmap(pixmap)
            self._update_tree_selection()

            self.current_pixmap = pixmap
            label_size = self.image_label.size()
            x_offset = max(0, (label_size.width() - pixmap.width()) // 2)
            y_offset = max(0, (label_size.height() - pixmap.height()) // 2)
            self.pixmap_rect = QRect(x_offset, y_offset, pixmap.width(), pixmap.height())

            self.image_label.mousePressEvent = self.handle_image_click
            self.image_label.mouseMoveEvent = self.handle_mouse_move
            self.image_label.mouseReleaseEvent = self.handle_mouse_release
            
        except Exception as e:
            logging.error(f"Error showing current image: {e}")
        finally:
            if conn:
                conn.close()

    def handle_image_click(self, event):
        """Handle mouse press events."""
        if event.button() == Qt.MouseButton.LeftButton:
            if not self.rubber_band:
                self.rubber_band = QRubberBand(QRubberBand.Shape.Rectangle, self.image_label)
            self.origin = event.pos()
            self.rubber_band.setGeometry(QRect(self.origin, QSize()))
            self.rubber_band.show()
            self.drawing = True
        elif event.button() == Qt.MouseButton.RightButton:
            if not self.face_boxes:
                logging.debug("No face boxes available in current image")
                return

            pos = event.pos()
            if not self.pixmap_rect:
                return

            image_x = pos.x() - self.pixmap_rect.x()
            image_y = pos.y() - self.pixmap_rect.y()
            rel_click_x = image_x / self.pixmap_rect.width()
            rel_click_y = image_y / self.pixmap_rect.height()

            for face in self.face_boxes:
                rel_x, rel_y, rel_w, rel_h = face['rel_coords']
                
                if (rel_x <= rel_click_x <= rel_x + rel_w and 
                    rel_y <= rel_click_y <= rel_y + rel_h):
                    
                    menu = QMenu(self)
                    edit_action = menu.addAction("Edit Name")
                    delete_action = menu.addAction("Delete Face")
                    delete_action.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_TrashIcon))
                    
                    action = menu.exec(event.globalPosition().toPoint())
                    
                    if action == edit_action:
                        self.show_name_dialog(face)
                    elif action == delete_action:
                        self.delete_face(face)
                    break
            else:
                logging.debug("Click was not inside any face box")

    def delete_face(self, face):
        """Delete a face after confirmation."""
        if face['face_id'] is None:
            logging.error("Cannot delete face: No face_id available")
            return

        reply = QMessageBox.question(
            self,
            'Delete Face',
            f'Are you sure you want to delete this face{" of " + face["name"] if face["name"] else ""}?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                conn = sqlite3.connect(self.db_manager.db_path)
                cursor = conn.cursor()
                
                cursor.execute('DELETE FROM faces WHERE id = ?', (face['face_id'],))
                conn.commit()
                
                logging.info(f"Deleted face {face['face_id']}")
                self.show_current_image()
                
            except Exception as e:
                logging.error(f"Error deleting face: {e}")
            finally:
                if 'conn' in locals():
                    conn.close()

    def handle_mouse_move(self, event):
        """Handle mouse move events for drawing rectangle."""
        if self.drawing and self.rubber_band:
            rect = QRect(self.origin, event.pos()).normalized()
            if self.pixmap_rect:
                rect = rect.intersected(self.pixmap_rect)
            self.rubber_band.setGeometry(rect)

    def handle_mouse_release(self, event):
        """Handle mouse release events."""
        if event.button() == Qt.MouseButton.LeftButton and self.drawing:
            self.drawing = False
            if self.rubber_band and self.rubber_band.isVisible():
                rect = self.rubber_band.geometry()

                if self.pixmap_rect and not rect.isEmpty():
                    rel_rect = self.convert_to_relative_coords(rect)
                    if rel_rect:
                        self.prompt_face_name(rel_rect)
                    
            self.rubber_band.hide()

    def convert_to_relative_coords(self, rect):
        """Convert label coordinates to relative image coordinates."""
        if not self.pixmap_rect:
            return None
            
        x = (rect.x() - self.pixmap_rect.x()) / self.pixmap_rect.width()
        y = (rect.y() - self.pixmap_rect.y()) / self.pixmap_rect.height()
        w = rect.width() / self.pixmap_rect.width()
        h = rect.height() / self.pixmap_rect.height()
        
        if 0 <= x <= 1 and 0 <= y <= 1 and w > 0 and h > 0:
            return (x, y, w, h)
        return None

    def prompt_face_name(self, rel_coords):
        """Prompt user for face name and save if provided."""
        name, ok = QInputDialog.getText(
            self,
            'New Face',
            'Enter name for this face:',
            text=""
        )
        
        if ok and name:
            try:
                conn = sqlite3.connect(self.db_manager.db_path)
                cursor = conn.cursor()
                
                cursor.execute('''
                    INSERT INTO faces (image_id, name, bbox_x, bbox_y, bbox_w, bbox_h)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (self.current_image_id, name, *rel_coords))
                
                conn.commit()
                logging.info(f"Added new face with name '{name}' at {rel_coords}")
                
                self.show_current_image()
                
            except Exception as e:
                logging.error(f"Error saving new face: {e}")
            finally:
                if 'conn' in locals():
                    conn.close()

    def show_name_dialog(self, face):
        """Show dialog to edit face name."""
        if face['face_id'] is None:
            logging.error("Cannot update name: No face_id available")
            return
            
        current_name = face['name'] or "Unknown"
        logging.debug(f"Opening name dialog for face_id {face['face_id']}, current name: {current_name}")
        
        new_name, ok = QInputDialog.getText(
            self,
            'Edit Person Name',
            'Enter name for this person:',
            text=current_name
        )
        
        if ok and new_name:
            logging.debug(f"User entered new name: {new_name}")
            if new_name != current_name:
                try:
                    success = self.db_manager.update_face_name(face['face_id'], new_name)
                    if success:
                        logging.info(f"Successfully updated face {face['face_id']} name to: {new_name}")
                        self.show_current_image()
                    else:
                        logging.error(f"Database update failed for face {face['face_id']}")
                except Exception as e:
                    logging.error(f"Error updating face name: {e}")
            else:
                logging.debug("Name unchanged, no update needed")
        else:
            logging.debug("Name dialog cancelled")

    def _update_tree_selection(self):
        """Update tree selection to match current image."""
        try:
            conn = sqlite3.connect(self.db_manager.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT base_folder, sub_folder, filename
                FROM images
                WHERE image_id = ?
            ''', (self.current_image_id,))
            result = cursor.fetchone()
            
            if result:
                base_folder, sub_folder, filename = result
                image_path = Path(base_folder) / sub_folder / filename
                self.current_image_path = image_path
                self.image_tree.select_image(image_path)
                
        except Exception as e:
            logging.error(f"Error updating tree selection: {e}")
        finally:
            if 'conn' in locals():
                conn.close()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.current_image_id is not None:
            self.show_current_image()
