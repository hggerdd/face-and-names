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
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QScrollArea,
    QHBoxLayout,
    QDialog,
    QMessageBox,
    QGridLayout,
)

from face_and_names.app_context import AppContext
from face_and_names.models.db import connect
from face_and_names.models.repositories import FaceRepository
from face_and_names.services.clustering_service import (
    ClusteringOptions,
    ClusteringService,
    ClusterResult,
)
from face_and_names.services.people_service import PeopleService
from face_and_names.ui.components.face_tile import FaceTile, FaceTileData, PersonSelectDialog
from face_and_names.ui.faces_page import FaceImageView


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

    def __init__(
        self,
        db_path: Path,
        folders: Sequence[str],
        last_import_only: bool,
        exclude_named: bool,
        algorithm: str,
        eps: float,
        min_samples: int,
        feature_source: str,
    ) -> None:
        super().__init__()
        self.db_path = db_path
        self.folders = folders
        self.last_import_only = last_import_only
        self.exclude_named = exclude_named
        self.algorithm = algorithm
        self.eps = eps
        self.min_samples = min_samples
        self.feature_source = feature_source

    def run(self) -> None:
        try:
            conn = connect(self.db_path)
            service = ClusteringService(conn)
            options = ClusteringOptions(
                last_import_only=self.last_import_only,
                exclude_named=self.exclude_named,
                folders=self.folders,
                eps=self.eps,
                min_samples=self.min_samples,
                algorithm=self.algorithm,
                feature_source=self.feature_source,
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
        self.people_service = PeopleService(context.conn)
        self.face_repo = FaceRepository(context.conn)
        self.folder_list = QListWidget()
        self.folder_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        self.last_import_checkbox = QCheckBox("Only last import session")
        self.exclude_named_checkbox = QCheckBox("Exclude faces with names")
        self.algorithm_combo = QComboBox()
        self.algorithm_combo.addItems(["dbscan", "kmeans"])
        self.eps_spin = QDoubleSpinBox()
        self.eps_spin.setRange(0.01, 1.0)
        self.eps_spin.setSingleStep(0.01)
        self.eps_spin.setValue(0.15)
        self.min_samples_spin = QDoubleSpinBox()
        self.min_samples_spin.setRange(1, 100)
        self.min_samples_spin.setSingleStep(1)
        self.min_samples_spin.setValue(1)
        self.kmeans_clusters_spin = QDoubleSpinBox()
        self.kmeans_clusters_spin.setRange(1, 500)
        self.kmeans_clusters_spin.setSingleStep(1)
        self.kmeans_clusters_spin.setValue(50)
        self.kmeans_clusters_spin.setEnabled(False)
        self.status_label = QLabel("Select folders and run clustering.")
        self.run_btn = QPushButton("Run clustering")
        self.set_name_btn = QPushButton("Set name")
        self.set_name_btn.setVisible(False)  # keep code path but hide per latest UX
        self.prev_btn = QPushButton("Previous cluster")
        self.next_btn = QPushButton("Next cluster")
        self.prev_btn.setEnabled(False)
        self.next_btn.setEnabled(False)
        self.cluster_label = QLabel("No clusters loaded")
        self.feature_source_combo = QComboBox()
        self.feature_source_combo.addItems(["pHash (normalized)", "pHash (raw)", "Raw (downscaled)", "Embedding (FaceNet)"])
        self.faces_area = QScrollArea()
        self.faces_area.setWidgetResizable(True)
        self.faces_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.faces_inner = QWidget()
        self.faces_layout = QGridLayout()
        self.faces_layout.setContentsMargins(8, 8, 8, 8)
        self.faces_layout.setSpacing(12)
        self.faces_inner.setLayout(self.faces_layout)
        self.faces_area.setWidget(self.faces_inner)
        self.names_list = QListWidget()
        self.names_list.setFixedWidth(180)
        self.state = ClusterState(clusters=[])
        self.current_tiles: list[FaceTile] = []

        self._build_ui()
        self._load_folders()

    def _build_ui(self) -> None:
        controls = QHBoxLayout()
        controls.addWidget(QLabel("Folders (multi-select):"))
        controls.addStretch(1)
        controls.addWidget(self.last_import_checkbox)
        controls.addWidget(self.exclude_named_checkbox)

        algo_row = QHBoxLayout()
        algo_row.addWidget(QLabel("Algorithm:"))
        algo_row.addWidget(self.algorithm_combo)
        algo_row.addWidget(QLabel("eps:"))
        algo_row.addWidget(self.eps_spin)
        algo_row.addWidget(QLabel("min_samples:"))
        algo_row.addWidget(self.min_samples_spin)
        algo_row.addWidget(QLabel("k (kmeans):"))
        algo_row.addWidget(self.kmeans_clusters_spin)
        algo_row.addWidget(QLabel("Feature:"))
        algo_row.addWidget(self.feature_source_combo)
        algo_row.addStretch(1)

        buttons = QHBoxLayout()
        buttons.addWidget(self.run_btn)
        buttons.addStretch(1)
        buttons.addWidget(self.set_name_btn)
        buttons.addWidget(self.prev_btn)
        buttons.addWidget(self.next_btn)

        layout = QVBoxLayout()
        layout.addLayout(controls)
        layout.addLayout(algo_row)
        layout.addWidget(self.folder_list)
        layout.addLayout(buttons)
        layout.addWidget(self.cluster_label)
        faces_row = QHBoxLayout()
        faces_row.addWidget(self.names_list)
        faces_row.addWidget(self.faces_area, stretch=1)
        layout.addLayout(faces_row)
        layout.addWidget(self.status_label)
        self.setLayout(layout)

        self.run_btn.clicked.connect(self._run_clustering)
        self.set_name_btn.clicked.connect(self._batch_set_name)
        self.prev_btn.clicked.connect(self._prev_cluster)
        self.next_btn.clicked.connect(self._next_cluster)
        self.names_list.itemDoubleClicked.connect(self._on_name_double_clicked)
        self.algorithm_combo.currentTextChanged.connect(self._on_algorithm_changed)
        self._on_algorithm_changed(self.algorithm_combo.currentText())

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
        exclude_named = self.exclude_named_checkbox.isChecked()
        algorithm = self.algorithm_combo.currentText()
        eps = float(self.eps_spin.value())
        min_samples = int(self.min_samples_spin.value())
        k_clusters = int(self.kmeans_clusters_spin.value())
        idx = self.feature_source_combo.currentIndex()
        feature_source = {0: "phash", 1: "phash_raw", 2: "raw", 3: "embedding"}.get(idx, "phash")
        self.status_label.setText("Clustering…")
        self.run_btn.setEnabled(False)
        self.prev_btn.setEnabled(False)
        self.next_btn.setEnabled(False)

        self._thread = QThread(self)
        self._worker = ClusteringWorker(
            self.context.db_path,
            folders=folders,
            last_import_only=last_only,
            exclude_named=exclude_named,
            algorithm=algorithm,
            eps=eps,
            min_samples=min_samples,
            k_clusters=k_clusters,
            feature_source=feature_source,
        )
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
            try:
                import logging

                logging.getLogger(__name__).error("Clustering failed", exc_info=error)
            except Exception:
                pass
            return
        self.state = ClusterState(clusters=result, index=0)
        if not result:
            self.status_label.setText("No faces to cluster.")
            self.cluster_label.setText("No clusters loaded")
            self._clear_faces()
            return
        self.status_label.setText(f"Clusters: {len(result)}")
        self.prev_btn.setEnabled(True)
        self.next_btn.setEnabled(True)
        self._show_cluster()
        try:
            self.context.events.emit("clustering_completed")
        except Exception:
            pass

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
        self._refresh_people_list()
        label = f"Cluster {self.state.index + 1}/{len(self.state.clusters)}"
        label += f" ({len(cluster.faces)} faces)"
        if cluster.is_noise:
            label += " [noise]"
        self.cluster_label.setText(label)
        self._render_faces(cluster)

    def _clear_faces(self) -> None:
        self.current_tiles = []
        while self.faces_layout.count():
            item = self.faces_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _render_faces(self, cluster: ClusterResult) -> None:
        self._clear_faces()
        people = {p["id"]: p for p in self.people_service.list_people()}
        max_cols = 4
        for idx, face in enumerate(cluster.faces):
            info = self._face_record(face.face_id)
            person_id = info["person_id"] if info else None
            predicted_person_id = info["predicted_person_id"] if info else None
            person_name = self._display_for(person_id, people)
            predicted_name = face.predicted_name or self._display_for(predicted_person_id, people)
            tile = FaceTile(
                FaceTileData(
                    face_id=face.face_id,
                    person_id=person_id,
                    person_name=person_name,
                    predicted_person_id=predicted_person_id,
                    predicted_name=predicted_name,
                    confidence=face.confidence,
                    crop=face.crop,
                ),
                delete_face=self._delete_face,
                assign_person=self._assign_person,
                list_persons=self.people_service.list_people,
                create_person=lambda first, last, short: self.people_service.create_person(first, last, short),
                rename_person=self.people_service.rename_person,
                open_original=self._open_original_image,
            )
            tile.deleteCompleted.connect(lambda fid, self=self: self._on_tile_deleted(fid))
            tile.dataChanged.connect(lambda fid, self=self: self._on_tile_deleted(fid))
            row, col = divmod(idx, max_cols)
            self.faces_layout.addWidget(tile, row, col, alignment=Qt.AlignmentFlag.AlignTop)
            self.current_tiles.append(tile)

    def _face_record(self, face_id: int) -> dict:
        row = self.context.conn.execute(
            "SELECT person_id, predicted_person_id FROM face WHERE id = ?",
            (face_id,),
        ).fetchone()
        if row is None:
            return {}
        return {"person_id": row[0], "predicted_person_id": row[1]}

    def _display_for(self, person_id: int | None, people: dict) -> str | None:
        if person_id is None:
            return None
        person = people.get(person_id)
        if not person:
            return None
        return person.get("display_name") or person.get("primary_name")

    def _delete_face(self, face_id: int) -> None:
        self.face_repo.delete(face_id)
        self.context.conn.commit()

    def _on_tile_deleted(self, face_id: int) -> None:
        # Remove deleted face from in-memory cluster state and refresh view
        self._prune_face_from_state(face_id)
        self._show_cluster()

    def _prune_face_from_state(self, face_id: int) -> None:
        if not self.state.clusters:
            return
        for cluster in self.state.clusters:
            cluster.faces = [f for f in cluster.faces if f.face_id != face_id]
        # Drop empty clusters except noise (cluster_id 0)
        self.state.clusters = [c for c in self.state.clusters if c.is_noise or c.faces]
        if self.state.index >= len(self.state.clusters):
            self.state.index = max(0, len(self.state.clusters) - 1)

    def _assign_person(self, face_id: int, person_id: int | None) -> None:
        self.face_repo.update_person(face_id, person_id)
        self.context.conn.commit()
        # refresh current cluster tiles/view
        self._show_cluster()

    def _open_original_image(self, face_id: int) -> None:
        row = self.face_repo.get_face_with_image(face_id)
        if row is None:
            return
        _, image_id, x, y, w, h, rel_path, img_w, img_h = row
        img_path = self.context.db_path.parent / rel_path
        if not img_path.exists():
            QMessageBox.warning(self, "Image missing", f"File not found: {img_path}")
            return
        pix = QPixmap(str(img_path))
        window = QDialog(self)
        window.setWindowTitle("Original image")
        view = FaceImageView()
        view.show_image(pix, [(float(x), float(y), float(w), float(h))])
        layout = QVBoxLayout()
        layout.addWidget(view)
        window.setLayout(layout)
        window.resize(800, 600)
        window.exec()

    def _on_algorithm_changed(self, algo: str) -> None:
        is_dbscan = algo.lower() == "dbscan"
        self.eps_spin.setEnabled(is_dbscan)
        self.min_samples_spin.setEnabled(is_dbscan)
        self.kmeans_clusters_spin.setEnabled(not is_dbscan)

    def _selected_tiles(self) -> list[FaceTile]:
        return [t for t in self.current_tiles if t.is_selected()]

    def _batch_set_name(self) -> None:
        cluster = self.state.current
        if cluster is None:
            return
        tiles = self._selected_tiles()
        if not tiles:
            QMessageBox.information(self, "No selection", "Select one or more faces to set a name.")
            return
        persons = list(self.people_service.list_people())
        dlg = PersonSelectDialog(
            persons=persons,
            create_person=self.people_service.create_person,
            rename_person=self.people_service.rename_person,
            parent=self,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted or dlg.selected_person_id is None:
            return
        pid = dlg.selected_person_id
        try:
            for tile in tiles:
                self.face_repo.update_person(tile.data.face_id, pid)
            self.context.conn.commit()
            self._show_cluster()
        except Exception as exc:  # pragma: no cover - UI guardrail
            QMessageBox.critical(self, "Assign failed", str(exc))


    def _refresh_people_list(self) -> None:
        people = sorted(self.people_service.list_people(), key=lambda p: p.get("display_name") or p.get("primary_name") or "")
        self.names_list.clear()
        for person in people:
            name = person.get("display_name") or person.get("primary_name") or "(unnamed)"
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, person.get("id"))
            self.names_list.addItem(item)

    def _on_name_double_clicked(self, item: QListWidgetItem) -> None:
        try:
            pid = item.data(Qt.ItemDataRole.UserRole)
            if pid is None:
                return
            tiles = self._selected_tiles()
            if not tiles:
                QMessageBox.information(self, "No selection", "Select one or more faces to set a name.")
                return
            for tile in tiles:
                self.face_repo.update_person(tile.data.face_id, int(pid))
            self.context.conn.commit()
            self._show_cluster()
        except Exception as exc:  # pragma: no cover - safety
            QMessageBox.critical(self, "Assign failed", str(exc))
