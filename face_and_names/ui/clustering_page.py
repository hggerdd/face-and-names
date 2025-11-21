"""
Clustering page: select scope, run clustering, and browse clusters.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence

from PyQt6.QtCore import Qt, QObject, QThread, pyqtSignal
from PyQt6.QtGui import QPixmap, QIcon
from PyQt6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from face_and_names.app_context import AppContext
from face_and_names.models.db import connect
from face_and_names.services.clustering_service import (
    ClusteringOptions,
    ClusteringService,
    ClusterResult,
)


@dataclass
class ClusterState:
    clusters: List[ClusterResult]
    index: int = 0

    @property
    def current(self) -> ClusterResult | None:
        if not self.clusters:
            return None
        if self.index < 0 or self.index >= len(self.clusters):
            return None
        return self.clusters[self.index]


class ClusteringWorker(QObject):
    finished = pyqtSignal(object, object)  # result, error

    def __init__(self, db_path: Path, folders: Sequence[str], last_import_only: bool) -> None:
        super().__init__()
        self.db_path = db_path
        self.folders = folders
        self.last_import_only = last_import_only

    def run(self) -> None:
        try:
            conn = connect(self.db_path)
            service = ClusteringService(conn)
            options = ClusteringOptions(
                last_import_only=self.last_import_only,
                folders=self.folders,
                eps=0.15,
                min_samples=1,
            )
            result = service.cluster_faces(options)
            conn.close()
            self.finished.emit(result, None)
        except Exception as exc:  # pragma: no cover
            self.finished.emit([], exc)


class ClusteringPage(QWidget):
    """UI for clustering faces and browsing cluster results."""

    def __init__(self, context: AppContext) -> None:
        super().__init__()
        self.context = context
        self.folder_list = QListWidget()
        self.folder_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        self.last_import_checkbox = QCheckBox("Only last import session")
        self.status_label = QLabel("Select folders and run clustering.")
        self.run_btn = QPushButton("Run clustering")
        self.prev_btn = QPushButton("Previous cluster")
        self.next_btn = QPushButton("Next cluster")
        self.prev_btn.setEnabled(False)
        self.next_btn.setEnabled(False)
        self.cluster_label = QLabel("No clusters loaded")
        self.faces_list = QListWidget()
        self.faces_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.faces_list.setIconSize(QPixmap(96, 96).size())
        self.faces_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.faces_list.setMovement(QListWidget.Movement.Static)
        self.faces_list.setSpacing(8)
        self.state = ClusterState(clusters=[])

        self._build_ui()
        self._load_folders()

    def _build_ui(self) -> None:
        controls = QHBoxLayout()
        controls.addWidget(QLabel("Folders (multi-select):"))
        controls.addStretch(1)
        controls.addWidget(self.last_import_checkbox)

        buttons = QHBoxLayout()
        buttons.addWidget(self.run_btn)
        buttons.addStretch(1)
        buttons.addWidget(self.prev_btn)
        buttons.addWidget(self.next_btn)

        layout = QVBoxLayout()
        layout.addLayout(controls)
        layout.addWidget(self.folder_list)
        layout.addLayout(buttons)
        layout.addWidget(self.cluster_label)
        layout.addWidget(self.faces_list, stretch=1)
        layout.addWidget(self.status_label)
        self.setLayout(layout)

        self.run_btn.clicked.connect(self._run_clustering)
        self.prev_btn.clicked.connect(self._prev_cluster)
        self.next_btn.clicked.connect(self._next_cluster)

    def _load_folders(self) -> None:
        self.folder_list.clear()
        rows = self.context.conn.execute(
            "SELECT DISTINCT sub_folder FROM image WHERE sub_folder != '' ORDER BY sub_folder"
        ).fetchall()
        for (folder,) in rows:
            item = QListWidgetItem(folder)
            self.folder_list.addItem(item)

    def _selected_folders(self) -> list[str]:
        return [i.text() for i in self.folder_list.selectedItems()]

    def _run_clustering(self) -> None:
        folders = self._selected_folders()
        last_only = self.last_import_checkbox.isChecked()
        self.status_label.setText("Clustering…")
        self.run_btn.setEnabled(False)
        self.prev_btn.setEnabled(False)
        self.next_btn.setEnabled(False)

        self._thread = QThread(self)
        self._worker = ClusteringWorker(self.context.db_path, folders=folders, last_import_only=last_only)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_cluster_finished)
        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    def _on_cluster_finished(self, result, error) -> None:
        self.run_btn.setEnabled(True)
        if error:
            self.status_label.setText(f"Clustering failed: {error}")
            return
        self.state = ClusterState(clusters=result, index=0)
        if not result:
            self.status_label.setText("No faces to cluster.")
            self.cluster_label.setText("No clusters loaded")
            self.faces_list.clear()
            return
        self.status_label.setText(f"Clusters: {len(result)}")
        self.prev_btn.setEnabled(True)
        self.next_btn.setEnabled(True)
        self._show_cluster()

    def _prev_cluster(self) -> None:
        if not self.state.clusters:
            return
        self.state.index = max(0, self.state.index - 1)
        self._show_cluster()

    def _next_cluster(self) -> None:
        if not self.state.clusters:
            return
        self.state.index = min(len(self.state.clusters) - 1, self.state.index + 1)
        self._show_cluster()

    def _show_cluster(self) -> None:
        cluster = self.state.current
        if cluster is None:
            return
        label = f"Cluster {self.state.index + 1}/{len(self.state.clusters)}"
        label += f" ({len(cluster.faces)} faces)"
        if cluster.is_noise:
            label += " [noise]"
        self.cluster_label.setText(label)

        self.faces_list.clear()
        for face in cluster.faces:
            pix = QPixmap()
            if pix.loadFromData(face.crop):
                icon = QIcon(pix.scaled(96, 96, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            else:
                icon = QIcon()
            name = face.person_name or "(unnamed)"
            if face.predicted_name and not face.person_name:
                name = f"[pred] {face.predicted_name}"
            item = QListWidgetItem(icon, name)
            self.faces_list.addItem(item)
