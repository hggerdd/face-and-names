from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                            QLabel, QProgressBar, QGroupBox)
from PyQt6.QtCore import Qt, pyqtSignal, QThread
import torch
from facenet_pytorch import InceptionResnetV1, MTCNN
import numpy as np
from PIL import Image
import io
import logging
from pathlib import Path
from sklearn.preprocessing import LabelEncoder
from sklearn.svm import SVC
import joblib
import json
import shutil  # Add this import
from datetime import datetime

class VGGFaceTrainingWorker(QThread):
    progress = pyqtSignal(str, int)  # status message, progress percentage
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, db_manager, save_path):
        super().__init__()
        self.db_manager = db_manager
        self.save_path = save_path
        self._is_running = True
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

    def stop(self):
        self._is_running = False

    def backup_existing_model(self):
        """Backup existing model files to a timestamped archive folder."""
        try:
            # Check if there are any model files to backup
            model_files = [
                'mtcnn_complete.pth',
                'face_encoder_complete.pth',
                'face_classifier.joblib',
                'label_encoder.joblib',
                'model_config.json'
            ]
            
            # Check if any of the model files exist
            if not any((self.save_path / file).exists() for file in model_files):
                return  # No files to backup
            
            # Create archive directory if it doesn't exist
            archive_root = self.save_path / 'archive'
            archive_root.mkdir(parents=True, exist_ok=True)
            
            # Create timestamped folder for this backup
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_dir = archive_root / timestamp
            backup_dir.mkdir(parents=True, exist_ok=True)
            
            # Copy existing model files
            for file in model_files:
                src_file = self.save_path / file
                if src_file.exists():
                    shutil.copy2(src_file, backup_dir / file)
            
            self.progress.emit(f"Existing model backed up to archive/{timestamp}", 2)
            logging.info(f"Model backup created in archive/{timestamp}")
            
        except Exception as e:
            logging.error(f"Error backing up existing model: {e}")
            self.error.emit(f"Failed to backup existing model: {str(e)}")

    def run(self):
        try:
            self.progress.emit("Checking for existing model...", 0)
            self.backup_existing_model()
            
            self.progress.emit("Loading training data...", 5)
            faces = self.db_manager.get_faces_for_training()
            if not faces:
                self.error.emit("No faces found for training")
                return

            # Initialize models
            self.progress.emit("Initializing models...", 5)
            mtcnn = MTCNN(keep_all=False, device=self.device)
            resnet = InceptionResnetV1(pretrained='vggface2').to(self.device)
            resnet.eval()

            # Create models directory if it doesn't exist
            self.save_path.mkdir(parents=True, exist_ok=True)

            # Save initial weights
            self.progress.emit("Saving initial models...", 10)
            try:
                torch.save(mtcnn.state_dict(), self.save_path / 'mtcnn_complete.pth')
                torch.save(resnet.state_dict(), self.save_path / 'face_encoder_complete.pth')
            except Exception as e:
                logging.error(f"Error saving initial model weights: {e}")
                self.error.emit(f"Failed to save models: {str(e)}")
                return

            # Rest of the training process
            # Prepare data
            encodings = []
            labels = []
            processed = 0
            total = len(faces)

            for i, (_, img_bytes, name) in enumerate(faces):
                if not self._is_running:
                    return

                try:
                    img = Image.open(io.BytesIO(img_bytes)).convert('RGB')
                    face = mtcnn(img)

                    if face is not None:
                        with torch.no_grad():
                            encoding = resnet(face.unsqueeze(0).to(self.device)).cpu().numpy()
                        encodings.append(encoding[0])
                        labels.append(name)
                        processed += 1

                    # Update progress
                    progress = int((i + 1) / total * 100)
                    self.progress.emit(f"Processing face {i+1}/{total}", progress)

                except Exception as e:
                    logging.error(f"Error processing face: {e}")
                    continue

            if len(encodings) < 2:
                self.error.emit("Not enough valid face encodings for training")
                return

            self.progress.emit("Training classifier...", 95)

            # Train classifier
            label_encoder = LabelEncoder()
            y_encoded = label_encoder.fit_transform(labels)
            classifier = SVC(kernel='linear', probability=True)
            classifier.fit(encodings, y_encoded)

            # Save all necessary models and configurations
            self.progress.emit("Saving models and configurations...", 98)
            
            # Save classifier and label encoder
            joblib.dump(classifier, self.save_path / 'face_classifier.joblib')
            joblib.dump(label_encoder, self.save_path / 'label_encoder.joblib')

            # Save model configuration
            model_config = {
                'input_size': (160, 160),  # Standard size for VGGFace2
                'use_cuda': torch.cuda.is_available(),
                'labels': label_encoder.classes_.tolist(),
                'model_type': 'VGGFace2',
                'creation_date': str(datetime.now()),
                'saved_models': {
                    'mtcnn': 'mtcnn_complete.pth',
                    'face_encoder': 'face_encoder_complete.pth',
                    'classifier': 'face_classifier.joblib',
                    'label_encoder': 'label_encoder.joblib'
                }
            }
            
            with open(self.save_path / 'model_config.json', 'w') as f:
                json.dump(model_config, f, indent=4)

            self.progress.emit("Training complete!", 100)
            self.finished.emit()

        except Exception as e:
            logging.error(f"Training error: {e}")
            self.error.emit(str(e))

class VGGFaceTrainingWidget(QWidget):
    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # Progress
        progress_group = QGroupBox("Progress")
        progress_layout = QVBoxLayout(progress_group)
        
        self.status_label = QLabel("Ready")
        progress_layout.addWidget(self.status_label)
        
        self.progress_bar = QProgressBar()
        progress_layout.addWidget(self.progress_bar)
        
        layout.addWidget(progress_group)

        # Control buttons
        button_layout = QHBoxLayout()
        
        self.start_button = QPushButton("Start VGGFace2 Training")
        self.start_button.clicked.connect(self.start_training)
        button_layout.addWidget(self.start_button)
        
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.cancel_training)
        self.cancel_button.setEnabled(False)
        button_layout.addWidget(self.cancel_button)
        
        self.clear_button = QPushButton("Clear All Predictions")
        self.clear_button.clicked.connect(self.clear_predictions)
        button_layout.addWidget(self.clear_button)
        
        layout.addLayout(button_layout)

        self.setLayout(layout)  # Ensure the layout is set for the widget

    def start_training(self):
        """Start the training process."""
        self.start_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.progress_bar.setValue(0)
        
        # Save in face_recognition_models subfolder
        save_path = Path("face_recognition_models")
        save_path.mkdir(exist_ok=True)

        # Start training worker
        self.worker = VGGFaceTrainingWorker(self.db_manager, save_path)
        self.worker.progress.connect(self.update_progress)
        self.worker.finished.connect(self.training_finished)
        self.worker.error.connect(self.training_error)
        self.worker.start()

    def cancel_training(self):
        """Cancel the training process."""
        if hasattr(self, 'worker') and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait()
            self.status_label.setText("Training cancelled")
            self.progress_bar.setValue(0)
            self.start_button.setEnabled(True)
            self.cancel_button.setEnabled(False)

    def clear_predictions(self):
        """Clear predictions and confidence values."""
        try:
            if self.db_manager.clear_predictions_only():  # Using new method name
                self.status_label.setText("Predictions cleared")
            else:
                self.status_label.setText("Failed to clear predictions")
        except Exception as e:
            logging.error(f"Error clearing predictions: {e}")
            self.status_label.setText("Error clearing predictions")

    def update_progress(self, message, progress):
        """Update progress bar and status message."""
        self.status_label.setText(message)
        self.progress_bar.setValue(progress)

    def training_finished(self):
        """Handle training completion."""
        self.status_label.setText("Training complete!")
        self.progress_bar.setValue(100)
        self.start_button.setEnabled(True)
        self.cancel_button.setEnabled(False)

    def training_error(self, error_msg):
        """Handle training error."""
        self.status_label.setText(f"Error: {error_msg}")
        self.progress_bar.setValue(0)
        self.start_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
