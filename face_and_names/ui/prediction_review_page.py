"""
Placeholder Prediction Review page.

Prevents import errors in the main window until the full feature is implemented.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget


class PredictionReviewPage(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout()
        layout.addWidget(QLabel("<b>Prediction Review</b>"), alignment=Qt.AlignmentFlag.AlignTop)
        layout.addWidget(QLabel("Coming soon: review and accept model predictions."))  # placeholder text
        layout.addStretch(1)
        self.setLayout(layout)
