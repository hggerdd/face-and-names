"""
Main window scaffold for Face-and-Names v2.
Layouts and views will follow `docs/ui.md` and `docs/ui_wireframes.md`.
"""

from __future__ import annotations

from PyQt6.QtWidgets import QLabel, QMainWindow, QWidget
from PyQt6.QtWidgets import QVBoxLayout


class MainWindow(QMainWindow):
    """Placeholder main window."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Face-and-Names v2 (placeholder)")
        self._init_ui()

    def _init_ui(self) -> None:
        """Set up a minimal central widget placeholder."""
        central = QWidget(self)
        layout = QVBoxLayout()
        layout.addWidget(QLabel("TODO: Implement UI per docs/ui_wireframes.md"))
        central.setLayout(layout)
        self.setCentralWidget(central)
