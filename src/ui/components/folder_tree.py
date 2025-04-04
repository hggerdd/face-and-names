from PyQt6.QtWidgets import QTreeWidget, QTreeWidgetItem
from PyQt6.QtCore import Qt, pyqtSignal
from pathlib import Path

class FolderTreeWidget(QTreeWidget):
    """Tree widget for selecting folders with checkboxes."""
    
    folderSelectionChanged = pyqtSignal(list)  # Emits list of (base_folder, sub_folder) tuples
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderLabel("Folders")
        self.itemChanged.connect(self._on_item_changed)
        self.setColumnCount(1)
        # Block signals during initial population
        self._populating = False
        
    def populate_tree(self, folder_data):
        """Populate tree with folder structure.
        Args:
            folder_data: List of (base_folder, sub_folder, filename) tuples
        """
        self._populating = True
        self.clear()
        folders = {}
        
        # Group by base_folder and sub_folder
        for base_folder, sub_folder, _ in folder_data:
            if base_folder not in folders:
                base_item = QTreeWidgetItem(self)
                base_item.setText(0, Path(base_folder).name)
                base_item.setData(0, Qt.ItemDataRole.UserRole, base_folder)
                base_item.setFlags(base_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                base_item.setCheckState(0, Qt.CheckState.Checked)  # Default to checked
                folders[base_folder] = {"item": base_item, "subs": {}}
                
            base_dict = folders[base_folder]
            if sub_folder not in base_dict["subs"]:
                sub_item = QTreeWidgetItem(base_dict["item"])
                sub_item.setText(0, sub_folder)
                sub_item.setData(0, Qt.ItemDataRole.UserRole, str(Path(base_folder) / sub_folder))
                sub_item.setFlags(sub_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                sub_item.setCheckState(0, Qt.CheckState.Checked)  # Default to checked
                base_dict["subs"][sub_folder] = sub_item
                
        self.expandToDepth(0)
        self._populating = False
        self._emit_selected_folders()
    
    def _on_item_changed(self, item, column):
        """Handle checkbox state changes."""
        if self._populating:
            return

        # If parent item was clicked, update all children
        if item.childCount() > 0:
            for i in range(item.childCount()):
                child = item.child(i)
                if child.checkState(0) != item.checkState(0):
                    child.setCheckState(0, item.checkState(0))
        
        # Only emit changes if we're not populating the tree
        if not self._populating:
            self._emit_selected_folders()
    
    def _emit_selected_folders(self):
        """Emit list of selected folders."""
        selected = []
        for i in range(self.topLevelItemCount()):
            base_item = self.topLevelItem(i)
            base_folder = base_item.data(0, Qt.ItemDataRole.UserRole)
            
            for j in range(base_item.childCount()):
                sub_item = base_item.child(j)
                if sub_item.checkState(0) == Qt.CheckState.Checked:
                    sub_folder = sub_item.text(0)
                    selected.append((base_folder, sub_folder))
                    
        self.folderSelectionChanged.emit(selected)
    
    def select_all(self):
        """Check all folders."""
        self._populating = True
        self._set_all_check_states(Qt.CheckState.Checked)
        self._populating = False
        self._emit_selected_folders()
        
    def deselect_all(self):
        """Uncheck all folders."""
        self._populating = True
        self._set_all_check_states(Qt.CheckState.Unchecked)
        self._populating = False
        self._emit_selected_folders()
        
    def _set_all_check_states(self, state):
        """Set check state for all items."""
        for i in range(self.topLevelItemCount()):
            base_item = self.topLevelItem(i)
            base_item.setCheckState(0, state)
            for j in range(base_item.childCount()):
                base_item.child(j).setCheckState(0, state)