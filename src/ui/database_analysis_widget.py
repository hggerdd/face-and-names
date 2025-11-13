from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                            QLabel, QTreeWidget, QTreeWidgetItem, QTabWidget,
                            QTableWidget, QTableWidgetItem, QMessageBox, QMenu)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction
import logging
from pathlib import Path

class DuplicateFilesWidget(QWidget):
    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # Controls
        controls = QHBoxLayout()
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.load_duplicates)
        controls.addWidget(self.refresh_button)

        self.status_label = QLabel("Ready")
        controls.addWidget(self.status_label)
        controls.addStretch()

        layout.addLayout(controls)

        # Tree widget for showing duplicates
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Filename", "Folders", "Face Count"])
        self.tree.setColumnWidth(0, 300)
        self.tree.setColumnWidth(1, 400)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.show_context_menu)
        layout.addWidget(self.tree)

        self.load_duplicates()

    def load_duplicates(self):
        try:
            self.tree.clear()
            duplicates = self.db_manager.find_duplicate_filenames()
            
            for filename, folder_data in duplicates.items():
                item = QTreeWidgetItem([filename, str(len(folder_data)), ""])
                
                for folder, face_count in folder_data.items():
                    child = QTreeWidgetItem([
                        "",
                        str(folder),
                        str(face_count)
                    ])
                    item.addChild(child)
                
                self.tree.addTopLevelItem(item)
            
            self.status_label.setText(f"Found {len(duplicates)} files with duplicates")
            
        except Exception as e:
            logging.error(f"Error loading duplicates: {e}")
            self.status_label.setText(f"Error: {str(e)}")

    def show_context_menu(self, position):
        item = self.tree.itemAt(position)
        if not item:
            return

        menu = QMenu()
        if item.parent() is None:
            # Top level item (filename)
            compare_action = QAction("Compare All Versions", self)
            compare_action.triggered.connect(
                lambda: self.compare_versions(item))
            menu.addAction(compare_action)
        else:
            # Child item (folder)
            view_action = QAction("View Faces from This Source", self)
            view_action.triggered.connect(
                lambda: self.view_faces(item.parent().text(0), item.text(1)))
            menu.addAction(view_action)

        menu.exec(self.tree.viewport().mapToGlobal(position))

    def compare_versions(self, item):
        filename = item.text(0)
        QMessageBox.information(self, "Compare", 
                              f"Comparing versions of {filename}\n"
                              "This feature is not yet implemented")

    def view_faces(self, filename, folder):
        QMessageBox.information(self, "View Faces", 
                              f"Viewing faces from {filename} in {folder}\n"
                              "This feature is not yet implemented")

class DatabaseStatsWidget(QWidget):
    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # Controls
        controls = QHBoxLayout()
        self.refresh_button = QPushButton("Refresh Statistics")
        self.refresh_button.clicked.connect(self.load_statistics)
        controls.addWidget(self.refresh_button)
        controls.addStretch()
        layout.addLayout(controls)

        # Statistics table
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Metric", "Value"])
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)

        self.load_statistics()

    def load_statistics(self):
        try:
            stats = self.db_manager.get_database_statistics()
            
            self.table.setRowCount(len(stats))
            for row, (metric, value) in enumerate(stats.items()):
                self.table.setItem(row, 0, QTableWidgetItem(metric))
                self.table.setItem(row, 1, QTableWidgetItem(str(value)))
                
        except Exception as e:
            logging.error(f"Error loading statistics: {e}")

class DatabaseAnalysisWidget(QWidget):
    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # Create tabs for different analysis views
        tab_widget = QTabWidget()

        # Add Duplicate Files tab
        self.duplicates_widget = DuplicateFilesWidget(self.db_manager)
        tab_widget.addTab(self.duplicates_widget, "Duplicate Files")

        # Add Database Statistics tab
        self.stats_widget = DatabaseStatsWidget(self.db_manager)
        tab_widget.addTab(self.stats_widget, "Database Statistics")

        layout.addWidget(tab_widget)
