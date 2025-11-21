"""
Placeholder page for prediction model training.

Intentionally minimal: UI will be fleshed out in future work.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget


class PredictionTrainingPage(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout()
        layout.addWidget(QLabel("<b>Prediction model training</b>"), alignment=Qt.AlignmentFlag.AlignTop)
        layout.addWidget(QLabel("Coming soon: controls to prepare data and train prediction models."))
        layout.addStretch(1)
        self.setLayout(layout)
