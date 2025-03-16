from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                            QLabel, QProgressBar, QComboBox, QSpinBox, 
                            QDoubleSpinBox, QGroupBox, QGridLayout, QMessageBox, QCheckBox,
                            QSplitter)
from PyQt6.QtCore import Qt, pyqtSignal, QThread
import logging
from pathlib import Path
from ..core.face_clusterer import ClusteringAlgorithm, FaceClusterer, ModelType
from .components.folder_tree import FolderTreeWidget

class ClusteringWorker(QThread):
    progress = pyqtSignal(str, int)  # status message, processed count
    stats = pyqtSignal(dict)  # clustering statistics
    finished = pyqtSignal(object)  # ClusteringResult
    error = pyqtSignal(str)

    def __init__(self, db_manager, algorithm, params, model_type, latest_import_only=False, selected_folders=None):
        super().__init__()
        self.db_manager = db_manager
        self.algorithm = algorithm
        self.params = params
        self.model_type = model_type
        self.latest_import_only = latest_import_only
        self.selected_folders = selected_folders
        self._clusterer = None  # Initialize later
        self._is_running = True

    @property
    def clusterer(self):
        """Lazy initialization of FaceClusterer."""
        if self._clusterer is None:
            self.progress.emit("Initializing face recognition model...", 0)
            self._clusterer = FaceClusterer(model_type=self.model_type)
        return self._clusterer

    def stop(self):
        """Safely stop the clustering process."""
        self._is_running = False
        self.progress.emit("Cancelling clustering...", 0)

    def run(self):
        try:
            # Clear existing cluster assignments if using latest import
            if self.latest_import_only:
                self.progress.emit("Clearing existing cluster assignments...", 0)
                self.db_manager.clear_cluster_assignments()

            # Load faces from database
            if not self._is_running:
                return
            self.progress.emit("Loading faces from database...", 0)
            faces = self.db_manager.get_faces_for_clustering(
                latest_import_only=self.latest_import_only,
                selected_folders=self.selected_folders
            )
            if not faces:
                self.error.emit("No faces found for clustering")
                return

            face_ids, face_images = zip(*faces)
            total_faces = len(faces)
            
            if not self._is_running:
                return
            self.progress.emit(f"Found {total_faces} faces to process", 5)

            # Run clustering with progress updates
            result = self.clusterer.cluster_faces(
                face_ids=list(face_ids),
                face_images=list(face_images),
                algorithm=self.algorithm,
                progress_callback=lambda msg, prog: self.progress.emit(msg, prog) if self._is_running else None,
                **self.params
            )

            if not self._is_running:
                return

            # Analyze results
            self.progress.emit("Analyzing cluster statistics...", 85)
            stats = self._analyze_clusters(result)
            self.stats.emit(stats)

            # Save results
            self.progress.emit(f"Saving {result.n_clusters} clusters to database...", 90)
            self.db_manager.save_clustering_results(result)
            
            # Final statistics
            noise_points = stats['noise_points']
            avg_size = stats['avg_cluster_size']
            self.progress.emit(
                f"Clustering complete! Found {result.n_clusters} clusters, "
                f"{noise_points} noise points, avg size {avg_size:.1f}", 100
            )
            self.finished.emit(result)
            
        except Exception as e:
            self.error.emit(str(e))

    def _analyze_clusters(self, result):
        """Analyze clustering results for statistics."""
        labels = result.labels
        unique_labels = set(labels)
        
        # Calculate statistics
        stats = {
            'total_faces': len(labels),
            'total_clusters': result.n_clusters,
            'noise_points': labels.count(-1) if -1 in unique_labels else 0,
            'min_cluster_size': 0,
            'max_cluster_size': 0,
            'avg_cluster_size': 0,
            'empty_clusters': 0
        }
        
        if stats['total_clusters'] > 0:
            cluster_sizes = [labels.count(i) for i in unique_labels if i != -1]
            if cluster_sizes:
                stats.update({
                    'min_cluster_size': min(cluster_sizes),
                    'max_cluster_size': max(cluster_sizes),
                    'avg_cluster_size': sum(cluster_sizes) / len(cluster_sizes),
                    'empty_clusters': sum(1 for size in cluster_sizes if size == 0)
                })
                
                # Add detailed cluster size distribution
                stats['size_distribution'] = {
                    'small (2-5)': len([s for s in cluster_sizes if 2 <= s <= 5]),
                    'medium (6-15)': len([s for s in cluster_sizes if 6 <= s <= 15]),
                    'large (>15)': len([s for s in cluster_sizes if s > 15])
                }
        
        return stats

class ClusteringWidget(QWidget):
    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.setup_ui()
        self.info_label.setText("Click 'Start Clustering' to begin")  # Default message

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # Create horizontal splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)

        # Left side - Folder selection
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)

        # Folder selection buttons
        folder_buttons = QHBoxLayout()
        self.select_all_button = QPushButton("Select All")
        self.select_all_button.clicked.connect(self._select_all_folders)
        self.deselect_all_button = QPushButton("Deselect All")
        self.deselect_all_button.clicked.connect(self._deselect_all_folders)
        folder_buttons.addWidget(self.select_all_button)
        folder_buttons.addWidget(self.deselect_all_button)
        left_layout.addLayout(folder_buttons)

        # Folder tree
        self.folder_tree = FolderTreeWidget()
        self.folder_tree.folderSelectionChanged.connect(self._on_folder_selection_changed)
        left_layout.addWidget(self.folder_tree)

        splitter.addWidget(left_widget)

        # Right side - Clustering controls
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)

        # Info section
        info_group = QGroupBox("Database Info")
        info_layout = QVBoxLayout(info_group)
        self.info_label = QLabel("No faces loaded")
        info_layout.addWidget(self.info_label)
        
        # Add Latest Import Only checkbox
        self.latest_import_checkbox = QCheckBox("Latest Import Only")
        self.latest_import_checkbox.setToolTip("Only cluster faces from the most recent import")
        info_layout.addWidget(self.latest_import_checkbox)
        
        # Add delete all names button
        self.delete_names_button = QPushButton("Delete All Names")
        self.delete_names_button.clicked.connect(self.confirm_delete_all_names)
        self.delete_names_button.setStyleSheet("background-color: #ffcccc")  # Light red background
        info_layout.addWidget(self.delete_names_button)
        
        right_layout.addWidget(info_group)

        # Advanced settings
        advanced_group = QGroupBox("Advanced Settings")
        advanced_layout = QGridLayout(advanced_group)
        
        self.max_cluster_size = QSpinBox()
        self.max_cluster_size.setRange(5, 100)
        self.max_cluster_size.setValue(30)  # Default value
        self.max_cluster_size.setToolTip("Maximum number of faces per cluster")
        advanced_layout.addWidget(QLabel("Max Cluster Size:"), 0, 0)
        advanced_layout.addWidget(self.max_cluster_size, 0, 1)
        
        right_layout.addWidget(advanced_group)

        # Model selection
        model_group = QGroupBox("Face Recognition Model")
        model_layout = QVBoxLayout(model_group)
        
        self.model_combo = QComboBox()
        for model in ModelType:
            self.model_combo.addItem(model.value, model)
        model_layout.addWidget(self.model_combo)
        
        right_layout.addWidget(model_group)

        # Algorithm selection
        algo_group = QGroupBox("Clustering Algorithm")
        algo_layout = QVBoxLayout(algo_group)
        
        self.algo_combo = QComboBox()
        for algo in ClusteringAlgorithm:
            self.algo_combo.addItem(algo.value, algo)
        self.algo_combo.currentIndexChanged.connect(self.on_algorithm_changed)
        algo_layout.addWidget(self.algo_combo)
        
        right_layout.addWidget(algo_group)

        # Parameters
        self.params_group = QGroupBox("Algorithm Parameters")
        self.params_layout = QGridLayout(self.params_group)
        right_layout.addWidget(self.params_group)
        
        # Statistics section
        stats_group = QGroupBox("Clustering Statistics")
        stats_layout = QGridLayout(stats_group)
        
        self.stats_labels = {
            'total_faces': QLabel("Total faces: -"),
            'total_clusters': QLabel("Total clusters: -"),
            'noise_points': QLabel("Noise points: -"),
            'min_cluster_size': QLabel("Min cluster size: -"),
            'max_cluster_size': QLabel("Max cluster size: -"),
            'avg_cluster_size': QLabel("Avg cluster size: -")
        }
        
        row = 0
        for label in self.stats_labels.values():
            stats_layout.addWidget(label, row // 2, row % 2)
            row += 1
            
        right_layout.addWidget(stats_group)

        # Progress section with detailed status
        progress_group = QGroupBox("Progress")
        progress_layout = QVBoxLayout(progress_group)
        
        self.status_label = QLabel("Ready")
        progress_layout.addWidget(self.status_label)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        progress_layout.addWidget(self.progress_bar)
        
        right_layout.addWidget(progress_group)

        # Control buttons
        button_layout = QHBoxLayout()
        
        self.start_button = QPushButton("Start Clustering")
        self.start_button.clicked.connect(self.start_clustering)
        button_layout.addWidget(self.start_button)
        
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.cancel_clustering)
        self.cancel_button.setEnabled(False)
        button_layout.addWidget(self.cancel_button)
        
        right_layout.addLayout(button_layout)
        right_layout.addStretch()

        # Initialize parameter widgets
        self.setup_parameter_widgets()
        self.on_algorithm_changed(0)

        splitter.addWidget(right_widget)

        # Set initial splitter sizes (30% left, 70% right)
        splitter.setSizes([300, 700])

        self.selected_folders = []  # Store selected folders

    def setup_parameter_widgets(self):
        """Initialize parameter widgets for each algorithm."""        
        self.param_widgets = {
            ClusteringAlgorithm.DBSCAN: {
                'eps': QDoubleSpinBox(),
                'min_samples': QSpinBox()
            },
            ClusteringAlgorithm.KMEANS: {
                'n_clusters': QSpinBox()
            },
            ClusteringAlgorithm.HIERARCHICAL: {
                'n_clusters': QSpinBox(),
                'linkage': QComboBox()
            }
        }

        # Configure DBSCAN parameters
        self.param_widgets[ClusteringAlgorithm.DBSCAN]['eps'].setRange(0.1, 1.0)
        self.param_widgets[ClusteringAlgorithm.DBSCAN]['eps'].setValue(0.3)  # Adjusted default
        self.param_widgets[ClusteringAlgorithm.DBSCAN]['eps'].setSingleStep(0.05)
        self.param_widgets[ClusteringAlgorithm.DBSCAN]['min_samples'].setRange(2, 20)
        self.param_widgets[ClusteringAlgorithm.DBSCAN]['min_samples'].setValue(3)  # Adjusted default

        # Configure K-means parameters
        self.param_widgets[ClusteringAlgorithm.KMEANS]['n_clusters'].setRange(2, 100)
        self.param_widgets[ClusteringAlgorithm.KMEANS]['n_clusters'].setValue(10)

        # Configure Hierarchical parameters
        self.param_widgets[ClusteringAlgorithm.HIERARCHICAL]['n_clusters'].setRange(2, 100)
        self.param_widgets[ClusteringAlgorithm.HIERARCHICAL]['n_clusters'].setValue(10)
        linkage_combo = self.param_widgets[ClusteringAlgorithm.HIERARCHICAL]['linkage']
        linkage_combo.addItems(['ward', 'complete', 'average', 'single'])

    def on_algorithm_changed(self, index):
        """Update parameter widgets when algorithm changes."""        
        # Clear current parameters
        for i in reversed(range(self.params_layout.count())): 
            self.params_layout.itemAt(i).widget().setParent(None)

        # Get current algorithm
        algorithm = self.algo_combo.currentData()
        
        # Add parameter widgets for current algorithm
        row = 0
        for param_name, widget in self.param_widgets[algorithm].items():
            self.params_layout.addWidget(QLabel(param_name.replace('_', ' ').title()), row, 0)
            self.params_layout.addWidget(widget, row, 1)
            row += 1

    def get_current_params(self):
        """Get current parameter values."""        
        algorithm = self.algo_combo.currentData()
        params = {}
        
        for param_name, widget in self.param_widgets[algorithm].items():
            if isinstance(widget, QComboBox):
                params[param_name] = widget.currentText()
            else:
                params[param_name] = widget.value()
                
        return params

    def update_info(self):
        """Update database info only when clustering starts."""        
        pass  # No longer automatically loads data

    def start_clustering(self):
        """Start the clustering process."""        
        self.start_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.progress_bar.setValue(0)
        
        # Now load the face count info when starting
        try:
            face_count = len(self.db_manager.get_faces_for_clustering(
                latest_import_only=self.latest_import_checkbox.isChecked(),
                selected_folders=self.selected_folders if self.selected_folders else None
            ))
            if face_count == 0:
                self.clustering_error("No faces found for clustering")
                return
            self.info_label.setText(f"Found {face_count} faces in database ready for clustering")
            self.status_label.setText("Initializing clustering...")
        except Exception as e:
            self.clustering_error(f"Error loading faces: {str(e)}")
            return
        
        # Reset statistics
        for label in self.stats_labels.values():
            label.setText(label.text().split(':')[0] + ": -")

        algorithm = self.algo_combo.currentData()
        params = self.get_current_params()
        model_type = self.model_combo.currentData()
        latest_import_only = self.latest_import_checkbox.isChecked()

        self.worker = ClusteringWorker(
            self.db_manager, 
            algorithm, 
            params, 
            model_type, 
            latest_import_only,
            self.selected_folders if self.selected_folders else None
        )
        self.worker.progress.connect(self.update_progress)
        self.worker.stats.connect(self.update_stats)
        self.worker.finished.connect(self.clustering_finished)
        self.worker.error.connect(self.clustering_error)
        self.worker.start()

    def update_progress(self, message, progress):
        """Update progress bar and status message."""        
        self.status_label.setText(message)
        self.progress_bar.setValue(progress)

    def update_stats(self, stats):
        """Update clustering statistics."""        
        self.stats_labels['total_faces'].setText(f"Total faces: {stats['total_faces']}")
        self.stats_labels['total_clusters'].setText(f"Total clusters: {stats['total_clusters']}")
        self.stats_labels['noise_points'].setText(f"Noise points: {stats['noise_points']}")
        self.stats_labels['min_cluster_size'].setText(f"Min cluster size: {stats['min_cluster_size']}")
        self.stats_labels['max_cluster_size'].setText(f"Max cluster size: {stats['max_cluster_size']}")
        self.stats_labels['avg_cluster_size'].setText(f"Avg cluster size: {stats['avg_cluster_size']:.1f}")

    def cancel_clustering(self):
        """Cancel the clustering process."""        
        if hasattr(self, 'worker') and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait()
            self.status_label.setText("Clustering cancelled")
            self.progress_bar.setValue(0)
            self.start_button.setEnabled(True)
            self.cancel_button.setEnabled(False)

    def split_large_clusters(self, result):
        """Split clusters larger than max_size faces into smaller chunks and renumber from 0."""        
        try:
            max_size = self.max_cluster_size.value()
            face_ids = result.face_ids
            labels = result.labels
            
            # First split oversized clusters
            cluster_sizes = {}
            for label in labels:
                cluster_sizes[label] = cluster_sizes.get(label, 0) + 1
            
            new_labels = labels.copy()
            next_cluster_id = max(labels) + 1
            changes_made = False
            
            # First pass: split large clusters
            for cluster_id, size in cluster_sizes.items():
                if size > max_size:
                    cluster_indices = [i for i, label in enumerate(labels) if label == cluster_id]
                    chunks = [cluster_indices[i:i + max_size] for i in range(0, len(cluster_indices), max_size)]
                    
                    for chunk in chunks[1:]:
                        for idx in chunk:
                            new_labels[idx] = next_cluster_id
                        next_cluster_id += 1
                    changes_made = True
                    logging.info(f"Split cluster {cluster_id} ({size} faces) into {len(chunks)} clusters")

            # Second pass: renumber all clusters starting from 0
            unique_labels = sorted(set(new_labels))
            label_mapping = {}
            
            # Start with noise points (if any)
            if -1 in unique_labels:
                unique_labels.remove(-1)
                label_mapping[-1] = 0
                next_new_id = 1
            else:
                next_new_id = 0

            # Map remaining clusters to sequential numbers
            for old_label in unique_labels:
                label_mapping[old_label] = next_new_id
                next_new_id += 1

            # Apply new numbering
            final_labels = [label_mapping[label] for label in new_labels]
            
            if changes_made or final_labels != labels:
                result.labels = final_labels
                result.n_clusters = len(set(final_labels))
                self.db_manager.save_clustering_results(result)
                
                self.status_label.setText(
                    f"Clusters have been processed (max {max_size} faces) and renumbered from 0. "
                    f"Total: {result.n_clusters} clusters"
                )
                
            return result
            
        except Exception as e:
            logging.error(f"Error splitting/renumbering clusters: {e}")
            return result

    def clustering_finished(self, result):
        """Handle clustering completion."""        
        try:
            # First split any large clusters
            result = self.split_large_clusters(result)
            
            # Update status with final cluster count
            self.status_label.setText(
                f"Clustering complete: {result.n_clusters} clusters found using {result.algorithm.value}"
            )
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(100)
            self.start_button.setEnabled(True)
            self.cancel_button.setEnabled(False)
            
        except Exception as e:
            logging.error(f"Error in clustering_finished: {e}")
            self.clustering_error(str(e))

    def clustering_error(self, error_msg):
        """Handle clustering error."""        
        self.status_label.setText(f"Error: {error_msg}")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.start_button.setEnabled(True)
        self.cancel_button.setEnabled(False)

    def confirm_delete_all_names(self):
        """Show confirmation dialog before deleting all names."""        
        reply = QMessageBox.question(
            self,
            'Confirm Delete',
            'Are you sure you want to delete all names?\nThis action cannot be undone.',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.delete_all_names()

    def delete_all_names(self):
        """Delete all names from the database."""        
        try:
            if self.db_manager.clear_all_names():
                self.status_label.setText("All names have been cleared")
                self.update_info()  # Refresh info to show updated face count
            else:
                self.status_label.setText("Error clearing names")
        except Exception as e:
            logging.error(f"Error clearing names: {e}")
            self.status_label.setText(f"Error: {str(e)}")

    def showEvent(self, event):
        """Initialize folder tree when widget is shown."""        
        super().showEvent(event)
        # Populate folder tree
        folder_data = self.db_manager.get_image_structure()
        self.folder_tree.populate_tree(folder_data)

    def hideEvent(self, event):
        """Handle widget being hidden."""        
        super().hideEvent(event)
        # Optional: Clear the info when hidden to ensure fresh load next time
        self.info_label.setText("No faces loaded")

    def _select_all_folders(self):
        """Select all folders in the tree."""        
        self.folder_tree.select_all()

    def _deselect_all_folders(self):
        """Deselect all folders in the tree."""        
        self.folder_tree.deselect_all()

    def _on_folder_selection_changed(self, selected_folders):
        """Handle folder selection changes."""        
        self.selected_folders = selected_folders
        # Update info if needed
        self.update_info()