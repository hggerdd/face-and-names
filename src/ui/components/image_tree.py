from PyQt6.QtWidgets import QTreeWidget, QTreeWidgetItem, QTreeWidgetItemIterator
from PyQt6.QtCore import Qt, pyqtSignal
from pathlib import Path

class ImageTreeWidget(QTreeWidget):
    folderSelected = pyqtSignal(Path)  # Emitted when folder is selected
    imageSelected = pyqtSignal(Path)   # Add new signal for image selection
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderLabel("Images by Folder")
        self.itemSelectionChanged.connect(self._on_selection_changed)
        
    def populate_tree(self, images_data):
        """Populate tree with image folders structure."""
        self.clear()
        folders = {}
        
        # Group images by base_folder and sub_folder
        for base_folder, sub_folder, filename in images_data:
            if base_folder not in folders:
                base_item = QTreeWidgetItem(self, [Path(base_folder).name])
                base_item.setData(0, Qt.ItemDataRole.UserRole, base_folder)
                folders[base_folder] = {"item": base_item, "subs": {}}
                
            base_dict = folders[base_folder]
            if sub_folder not in base_dict["subs"]:
                sub_item = QTreeWidgetItem(base_dict["item"], [sub_folder])
                sub_item.setData(0, Qt.ItemDataRole.UserRole, 
                               str(Path(base_folder) / sub_folder))
                base_dict["subs"][sub_folder] = {"item": sub_item, "files": []}
                
            # Add file under sub_folder
            file_item = QTreeWidgetItem(base_dict["subs"][sub_folder]["item"], 
                                      [filename])
            file_item.setData(0, Qt.ItemDataRole.UserRole, 
                            str(Path(base_folder) / sub_folder / filename))
                            
        self.expandToDepth(0)  # Expand base folders by default
        
    def select_image(self, image_path: Path):
        """Select an image in the tree without triggering signals."""
        self.blockSignals(True)
        self.clearSelection()
        
        # Find and select the item
        iterator = QTreeWidgetItemIterator(self)
        while iterator.value():
            item = iterator.value()
            item_path = Path(item.data(0, Qt.ItemDataRole.UserRole))
            if item_path == image_path:
                item.setSelected(True)
                self.scrollToItem(item)
                parent = item.parent()
                while parent:
                    parent.setExpanded(True)
                    parent = parent.parent()
                break
            iterator += 1
            
        self.blockSignals(False)

    def _on_selection_changed(self):
        """Handle selection changes."""
        selected = self.selectedItems()
        if not selected:
            return
            
        item = selected[0]
        path = Path(item.data(0, Qt.ItemDataRole.UserRole))
        if path.is_dir():
            self.folderSelected.emit(path)
        else:
            self.imageSelected.emit(path)
