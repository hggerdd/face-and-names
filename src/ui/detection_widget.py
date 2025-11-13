from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                            QLabel, QProgressBar, QFileDialog, QSpinBox, 
                            QCheckBox, QGroupBox, QLineEdit, QTreeWidget, QTreeWidgetItem, QMessageBox)
from PyQt6.QtCore import Qt, pyqtSignal, QThread
from pathlib import Path
import logging
import numpy as np
import cv2
import json
from ..core.face_detector import FaceDetectionProcessor  # Fix the import
from ..core.prediction_helper import PredictionHelper
from ..utils.image_utils import correct_image_orientation
from ..utils.metadata_utils import extract_image_metadata
from ..utils.face_preprocessing import preprocess_face_image


class FaceDetectionWorker(QThread):
    """Worker thread for face detection processing."""
    progress = pyqtSignal(str, int, int, bool)  # current_file, faces_in_file, total_faces, has_faces
    folder_progress = pyqtSignal(str, int, int)  # folder_name, current_folder_num, total_folders
    finished = pyqtSignal(int, int, int)  # total_images, total_faces, no_face_images
    error = pyqtSignal(str)

    def __init__(self, processor, directories: list, recursive: bool, prediction_threshold: float, enable_prediction: bool):
        super().__init__()
        self.processor = processor
        self.directories = directories
        self.recursive = recursive
        self.prediction_threshold = prediction_threshold
        self.enable_prediction = enable_prediction
        self._is_running = True
        
        # Initialize prediction helper only if model directory exists and prediction is enabled
        if Path("face_recognition_models").exists() and self.enable_prediction:
            self.prediction_helper = PredictionHelper()
            logging.info("Prediction helper created")
        else:
            self.prediction_helper = None
            logging.warning("No prediction models found or prediction disabled, face recognition disabled")

    def run(self):
        try:
            total_faces = 0
            processed_images = 0
            no_face_images = 0
            total_folders = len(self.directories)

            # Start new import session
            import_id = self.processor.db_manager.start_new_import(total_folders)
            if not import_id:
                self.error.emit("Failed to start import session")
                return

            # Initialize prediction helper if it exists
            if self.prediction_helper:
                initialized = self.prediction_helper.initialize()
                logging.info(f"Prediction helper initialized: {initialized}")
                if not initialized:
                    self.prediction_helper = None
                    logging.warning("Failed to initialize prediction helper")
            
            # Add debug logging
            logging.debug(f"Starting detection process with {len(self.directories)} directories")
            for directory in self.directories:
                logging.debug(f"Processing directory: {directory}")
                
            # Process one folder at a time
            for folder_idx, directory in enumerate(self.directories, 1):
                if not self._is_running:
                    break
                    
                self.folder_progress.emit(directory.name, folder_idx, total_folders)
                
                # Get list of files for current folder
                image_files = []
                if self.recursive:
                    for ext in ('*.jpg', '*.jpeg', '*.png'):
                        image_files.extend(directory.rglob(ext))
                else:
                    for ext in ('*.jpg', '*.jpeg', '*.png'):
                        image_files.extend(directory.glob(ext))

                # Process each file in current folder
                with self.processor.get_detector() as detector:
                    for img_path in image_files:
                        if not self._is_running:
                            break
                            
                        if self.processor.db_manager.is_image_processed(img_path):
                            continue
                        
                        try:
                            # Load image first
                            image = correct_image_orientation(img_path)
                            if image is None:
                                logging.error(f"Could not load image: {img_path}")
                                continue

                            # Extract and save metadata before face detection
                            metadata = extract_image_metadata(img_path)
                            
                            # Create image entry and save metadata with import_id
                            image_id = self.processor.db_manager.get_or_create_image_id(
                                img_path, 
                                image.copy(),
                                import_id,
                                base_root=directory
                            )
                            if not image_id:
                                logging.error(f"Failed to create image entry for {img_path}")
                                continue
                                
                            # Save metadata
                            self.processor.db_manager.save_image_metadata(image_id, metadata)

                            # Now detect faces using the same image
                            faces = detector.detect_faces(img_path, image)
                            if faces:
                                if self.enable_prediction:
                                    # For each detected face, try to predict name
                                    for face in faces:
                                        if self.prediction_helper and self.prediction_helper.is_initialized:
                                            try:
                                                face_tensor = preprocess_face_image(face.face_image)
                                                predicted_name, confidence = self.prediction_helper.predict_face(face_tensor)
                                                logging.info(f"Got prediction: {predicted_name} with confidence {confidence}")
                                                
                                                if confidence > self.prediction_threshold:
                                                    face.predicted_name = predicted_name
                                                    face.prediction_confidence = confidence
                                                else:
                                                    face.predicted_name = None
                                                    face.prediction_confidence = None
                                                
                                                logging.debug(f"Face {id(face)}: predicted={face.predicted_name}, conf={face.prediction_confidence}")
                                            except Exception as e:
                                                logging.error(f"Error predicting face: {e}")
                                                face.predicted_name = None
                                                face.prediction_confidence = None

                                    # Save faces with predictions
                                    saved = self.processor.db_manager.save_faces_with_predictions(faces, base_root=directory)
                                    if not saved:
                                        logging.error("Failed to save faces with predictions")
                                else:
                                    # Save faces without predictions
                                    saved = self.processor.db_manager.save_faces(faces, base_root=directory)
                                    if not saved:
                                        logging.error("Failed to save faces")

                                faces_count = len(faces)
                                total_faces += faces_count
                                processed_images += 1
                                self.progress.emit(
                                    str(img_path.relative_to(directory)), 
                                    faces_count,
                                    total_faces,
                                    True
                                )
                            else:
                                # Even if no faces found, ensure we have a thumbnail
                                self.processor.db_manager.record_no_face_image(img_path, base_root=directory)
                                no_face_images += 1
                                self.progress.emit(
                                    str(img_path.relative_to(directory)), 
                                    0,
                                    total_faces,
                                    False
                                )

                            # Update import image count after each image
                            self.processor.db_manager.update_import_image_count(import_id, processed_images)
                            
                        except Exception as e:
                            logging.error(f"Error processing {img_path}: {e}")
                            continue

            self.finished.emit(processed_images, total_faces, no_face_images)
            
        except Exception as e:
            self.error.emit(str(e))

    def stop(self):
        self._is_running = False

class FaceDetectionWidget(QWidget):
    """Widget for face detection interface."""
    
    CONFIG_FILE = Path.home() / ".face_and_names_config.json"
    
    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.last_folder = self.validate_last_folder()
        self.setup_ui()
        
    def validate_last_folder(self) -> str:
        """Load and validate the last used folder."""
        try:
            if self.CONFIG_FILE.exists():
                with open(self.CONFIG_FILE, 'r') as f:
                    config = json.load(f)
                    last_folder = config.get("last_folder", "")
                    if last_folder and Path(last_folder).exists():
                        return last_folder
            logging.info("No valid last folder found")
            return ""
        except Exception as e:
            logging.error(f"Error validating last folder: {e}")
            return ""
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Input section
        input_group = QGroupBox("Input Settings")
        input_layout = QVBoxLayout(input_group)
        
        # Folder selection
        folder_layout = QHBoxLayout()
        self.folder_edit = QLineEdit()
        self.folder_edit.setPlaceholderText("Select input folder...")
        self.folder_edit.setReadOnly(True)
        folder_layout.addWidget(self.folder_edit)
        
        folder_button = QPushButton("Browse...")
        folder_button.clicked.connect(self.select_folder)
        folder_layout.addWidget(folder_button)
        input_layout.addLayout(folder_layout)

        # Folder tree view
        self.folder_tree = QTreeWidget()
        self.folder_tree.setHeaderHidden(True)
        self.folder_tree.setRootIsDecorated(True)
        input_layout.addWidget(self.folder_tree)
        
        # Options
        options_layout = QHBoxLayout()
        self.recursive_check = QCheckBox("Process Subfolders")
        self.recursive_check.setChecked(True)
        options_layout.addWidget(self.recursive_check)
        
        self.confidence_spin = QSpinBox()
        self.confidence_spin.setRange(1, 100)
        self.confidence_spin.setValue(50)
        self.confidence_spin.setSuffix("%")
        options_layout.addWidget(QLabel("Min Confidence:"))
        options_layout.addWidget(self.confidence_spin)
        
        # Add prediction threshold spin box
        self.prediction_threshold_spin = QSpinBox()
        self.prediction_threshold_spin.setRange(1, 100)
        self.prediction_threshold_spin.setValue(50)
        self.prediction_threshold_spin.setSuffix("%")
        options_layout.addWidget(QLabel("Prediction Threshold:"))
        options_layout.addWidget(self.prediction_threshold_spin)
        
        # Add enable prediction checkbox
        self.enable_prediction_check = QCheckBox("Enable Prediction")
        self.enable_prediction_check.setChecked(True)
        options_layout.addWidget(self.enable_prediction_check)
        
        options_layout.addStretch()
        input_layout.addLayout(options_layout)
        
        layout.addWidget(input_group)
        
        # Progress section
        progress_group = QGroupBox("Progress")
        progress_layout = QVBoxLayout(progress_group)
        
        # Current file label
        self.current_file_label = QLabel("No file being processed")
        progress_layout.addWidget(self.current_file_label)
        
        # Add folder progress label after current file label
        self.folder_progress_label = QLabel("No folder being processed")
        progress_layout.insertWidget(1, self.folder_progress_label)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        progress_layout.addWidget(self.progress_bar)
        
        # Statistics labels
        stats_layout = QHBoxLayout()
        self.faces_current_label = QLabel("Faces in current file: 0")
        self.faces_total_label = QLabel("Total faces found: 0")
        self.no_face_label = QLabel("Images without faces: 0")
        stats_layout.addWidget(self.faces_current_label)
        stats_layout.addWidget(self.faces_total_label)
        stats_layout.addWidget(self.no_face_label)
        progress_layout.addLayout(stats_layout)
        
        # Status label
        self.status_label = QLabel("Ready")
        progress_layout.addWidget(self.status_label)
        
        layout.addWidget(progress_group)
        
        # Control buttons
        button_layout = QHBoxLayout()
        self.start_button = QPushButton("Start Detection")
        self.start_button.clicked.connect(self.start_detection)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.cancel_detection)
        self.cancel_button.setEnabled(False)
        
        # Add Clear Database button
        self.clear_db_button = QPushButton("Clear Database")
        self.clear_db_button.clicked.connect(self.clear_database)
        button_layout.addWidget(self.clear_db_button)
        
        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)
        
        layout.addStretch()
        
        # Now we can safely disable the start button if needed
        if not self.last_folder:
            self.start_button.setEnabled(False)

        # Populate folder tree at startup
        if self.last_folder:
            self.folder_edit.setText(self.last_folder)
            self.populate_folder_tree(Path(self.last_folder))
        
    def clear_database(self):
        """Clear all faces and no-face images from the database."""
        reply = QMessageBox.question(
            self, 
            'Clear Database',
            'Are you sure you want to clear all face data and no-face images? This cannot be undone.',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            if self.db_manager.clear_database():
                QMessageBox.information(self, "Success", "Database cleared successfully!")
            else:
                QMessageBox.warning(self, "Error", "Failed to clear database!")

    def load_last_folder(self) -> str:
        """Load the last selected folder from the configuration file.""" 
        if self.CONFIG_FILE.exists():
            try:
                with open(self.CONFIG_FILE, 'r') as f:
                    config = json.load(f)
                    return config.get("last_folder", "")
            except Exception as e:
                logging.error(f"Error loading config file: {e}")
        return ""
    
    def save_last_folder(self, folder: str):
        """Save the last selected folder to the configuration file.""" 
        try:
            with open(self.CONFIG_FILE, 'w') as f:
                json.dump({"last_folder": folder}, f)
        except Exception as e:
            logging.error(f"Error saving config file: {e}")

    def select_folder(self):
        # Use empty string as starting point if no valid last folder
        start_folder = self.last_folder if self.last_folder else str(Path.home())
        folder = QFileDialog.getExistingDirectory(
            self, "Select Input Folder", start_folder
        )
        if folder:
            self.folder_edit.setText(folder)
            self.last_folder = folder  # Update last_folder
            self.save_last_folder(folder)
            self.populate_folder_tree(Path(folder))
            self.start_button.setEnabled(True)  # Enable start button once a folder is selected
            
    def populate_folder_tree(self, folder_path):
        self.folder_tree.clear()
        root_item = QTreeWidgetItem([str(folder_path)])
        self.folder_tree.addTopLevelItem(root_item)
        self.add_subfolders(root_item, folder_path)
        
    def add_subfolders(self, tree_item, folder_path):
        for subfolder in folder_path.iterdir():
            if subfolder.is_dir():
                subfolder_item = QTreeWidgetItem([subfolder.name])
                subfolder_item.setCheckState(0, Qt.CheckState.Unchecked)
                tree_item.addChild(subfolder_item)
            
    def start_detection(self):
        if not self.folder_edit.text():
            self.status_label.setText("Please select an input folder")
            return
            
        self.start_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.progress_bar.setRange(0, 0)  # Indeterminate progress
        
        # Reset statistics
        self.faces_current_label.setText("Faces in current file: 0")
        self.faces_total_label.setText("Total faces found: 0")
        self.no_face_label.setText("Images without faces: 0")
        self.current_file_label.setText("Starting detection...")
        
        # Create processor directly without import
        processor = FaceDetectionProcessor(self.db_manager)
        
        selected_folders = self.get_selected_folders()
        logging.debug(f"Selected folders: {selected_folders}")  # Add debug logging
        
        if not selected_folders:
            self.status_label.setText("Please select at least one folder")
            self.reset_ui()
            return
        
        prediction_threshold = self.prediction_threshold_spin.value() / 100.0
        enable_prediction = self.enable_prediction_check.isChecked()
        
        self.worker = FaceDetectionWorker(
            processor,
            selected_folders,
            self.recursive_check.isChecked(),
            prediction_threshold,
            enable_prediction
        )
        self.worker.progress.connect(self.update_progress)
        self.worker.folder_progress.connect(self.update_folder_progress)
        self.worker.finished.connect(self.detection_finished)
        self.worker.error.connect(self.detection_error)
        self.worker.start()
        
    def get_selected_folders(self):
        """Get selected folders and ensure they exist.""" 
        selected_folders = []
        root_item = self.folder_tree.topLevelItem(0)
        if root_item:
            root_path = Path(self.folder_edit.text())
            for i in range(root_item.childCount()):
                child_item = root_item.child(i)
                if child_item.checkState(0) == Qt.CheckState.Checked:
                    folder_path = root_path / child_item.text(0)
                    if folder_path.exists():  # Verify folder exists
                        selected_folders.append(folder_path)
                        logging.debug(f"Added folder to process: {folder_path}")
                    else:
                        logging.warning(f"Folder not found: {folder_path}")
        return selected_folders

    def cancel_detection(self):
        if hasattr(self, 'worker') and self.worker.isRunning():
            self.worker.stop()  # Graceful stop
            self.worker.wait()
            self.status_label.setText("Detection cancelled")
            self.reset_ui()
            
    def update_progress(self, current_file, faces_in_file, total_faces, has_faces):
        self.current_file_label.setText(f"Processing: {current_file}")
        status = "Found faces" if has_faces else "No faces found"
        self.faces_current_label.setText(f"Current file: {status}")
        self.faces_total_label.setText(f"Total faces found: {total_faces}")
        self.status_label.setText("Detection in progress...")
        
    def update_folder_progress(self, folder_name, current, total):
        """Update folder processing progress.""" 
        self.folder_progress_label.setText(
            f"Processing folder {current} of {total}: {folder_name}"
        )

    def detection_finished(self, total_images, total_faces, no_face_images):
        self.status_label.setText(
            f"Detection complete: processed {total_images} images, "
            f"found {total_faces} faces, {no_face_images} images without faces"
        )
        self.current_file_label.setText("Processing complete")
        self.no_face_label.setText(f"Images without faces: {no_face_images}")
        self.reset_ui()
        
    def detection_error(self, error_msg):
        self.status_label.setText(f"Error: {error_msg}")
        self.reset_ui()
        
        self.progress_bar.setValue(0)
    def reset_ui(self):
        self.start_button.setEnabled(True)
        self.folder_progress_label.setText("No folder being processed")
        self.cancel_button.setEnabled(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.folder_progress_label.setText("No folder being processed")
        self.folder_progress_label.setText("No folder being processed")
        self.folder_progress_label.setText("No folder being processed")
