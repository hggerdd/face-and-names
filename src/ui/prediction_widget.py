from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                            QLabel, QProgressBar, QGroupBox, QCheckBox,
                            QTableWidget, QTableWidgetItem)
from PyQt6.QtCore import Qt, pyqtSignal, QThread
from PyQt6.QtGui import QPainter, QFont, QColor
from PyQt6.QtCharts import (QChart, QChartView, QBarSeries, QBarSet, 
                           QBarCategoryAxis, QValueAxis)  # More explicit imports
import logging
from pathlib import Path
import torch
import cv2
import numpy as np
from ..core.prediction_helper import PredictionHelper
from ..utils.face_preprocessing import preprocess_face_image

class PredictionWorker(QThread):
    progress = pyqtSignal(str, int)  # status message, progress percentage
    finished = pyqtSignal(bool)  # success status
    error = pyqtSignal(str)
    histogram_update = pyqtSignal(list)  # Add signal for histogram updates
    name_frequencies = pyqtSignal(dict)  # name -> count mapping

    def __init__(self, db_manager, only_process_without_name=False):  # Add parameter with default value
        super().__init__()
        self.db_manager = db_manager
        self.only_process_without_name = only_process_without_name  # Store the parameter
        self._is_running = True
        # Initialize prediction helper at creation
        self.prediction_helper = None
        if Path("face_recognition_models").exists():
            self.prediction_helper = PredictionHelper()
            logging.info("Created prediction helper")

    def run(self):
        try:
            if not self.prediction_helper:
                self.error.emit("No prediction models found!")
                return

            # Initialize models
            self.progress.emit("Initializing prediction models...", 0)
            if not self.prediction_helper.initialize():
                self.error.emit("Failed to initialize prediction models")
                return

            # Get faces to predict
            self.progress.emit("Loading faces...", 10)
            # Modify query based on flag
            if self.only_process_without_name:
                faces = self.db_manager.get_faces_without_names_for_prediction()  # You'll need to add this method
            else:
                faces = self.db_manager.get_faces_for_prediction()
            if not faces:
                self.error.emit("No faces found for prediction")
                return

            total = len(faces)
            self.progress.emit(f"Processing {total} faces...", 15)

            confidence_values = []  # Store confidence values for histogram
            name_counts = {}  # Track name frequencies

            # Process each face
            for idx, (face_id, face_data, current_name) in enumerate(faces, 1):
                if not self._is_running:
                    break

                try:
                    # Convert image bytes to tensor
                    img_array = np.frombuffer(face_data, np.uint8)
                    img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                    if img is None:
                        continue

                    # Preprocess image
                    face_tensor = preprocess_face_image(img)

                    # Get prediction
                    predicted_name, confidence = self.prediction_helper.predict_face(face_tensor)

                    if predicted_name and confidence:
                        # Update name frequencies
                        name_counts[predicted_name] = name_counts.get(predicted_name, 0) + 1
                        
                        # Save prediction result
                        self.db_manager.save_prediction_result(face_id, predicted_name, float(confidence))
                        confidence_values.append(float(confidence))  # Add confidence to list
                        logging.debug(f"Predicted {predicted_name} ({confidence:.2f}) for face {face_id}")

                    # Update progress
                    progress = 15 + int(85 * idx / total)
                    self.progress.emit(f"Processed {idx}/{total} faces...", progress)
                    # Update both histogram and name frequencies periodically
                    if len(confidence_values) % 10 == 0:  # Update every 10 faces
                        self.histogram_update.emit(confidence_values)
                        self.name_frequencies.emit(name_counts)

                except Exception as e:
                    logging.error(f"Error processing face {face_id}: {e}")
                    continue

            # Final updates
            if confidence_values:
                self.histogram_update.emit(confidence_values)
                self.name_frequencies.emit(name_counts)

            self.progress.emit("Prediction complete!", 100)
            self.finished.emit(True)

        except Exception as e:
            logging.error(f"Prediction error: {e}")
            self.error.emit(str(e))
            self.finished.emit(False)

    def stop(self):
        self._is_running = False

class PredictionWidget(QWidget):
    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.is_initialized = False
        self.setup_ui()  # Only set up the basic UI, don't initialize chart yet

    def setup_ui(self):
        """Set up basic UI elements with improved layout."""
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)

        # Top section: Controls and table in horizontal layout
        top_section = QHBoxLayout()
        
        # Left panel (controls)
        controls_group = QGroupBox("Controls")
        controls_group.setStyleSheet("""
            QGroupBox {
                background-color: #f8f9fa;
                border-radius: 6px;
                border: 1px solid #dee2e6;
            }
            QGroupBox::title {
                color: #495057;
            }
        """)
        controls_layout = QVBoxLayout(controls_group)
        controls_layout.setSpacing(8)

        # Progress section
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: #495057; font-weight: bold;")
        controls_layout.addWidget(self.status_label)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #ced4da;
                border-radius: 4px;
                text-align: center;
                height: 20px;
            }
            QProgressBar::chunk {
                background-color: #0d6efd;
                border-radius: 3px;
            }
        """)
        controls_layout.addWidget(self.progress_bar)

        # Control buttons with modern styling
        button_style = """
            QPushButton {
                background-color: #0d6efd;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px;
                min-width: 100px;
            }
            QPushButton:hover {
                background-color: #0b5ed7;
            }
            QPushButton:disabled {
                background-color: #6c757d;
            }
        """
        
        self.start_button = QPushButton("Start Prediction")
        self.start_button.setStyleSheet(button_style)
        self.start_button.clicked.connect(self.start_prediction)
        controls_layout.addWidget(self.start_button)
        
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setStyleSheet(button_style.replace("#0d6efd", "#dc3545"))
        self.cancel_button.clicked.connect(self.cancel_prediction)
        self.cancel_button.setEnabled(False)
        controls_layout.addWidget(self.cancel_button)

        self.filter_checkbox = QCheckBox("Only process images w/o name")
        self.filter_checkbox.setStyleSheet("color: #495057;")
        controls_layout.addWidget(self.filter_checkbox)
        
        controls_layout.addStretch()
        top_section.addWidget(controls_group, 1)

        # Right panel (name frequencies table)
        table_group = QGroupBox("Predicted Names")
        table_group.setStyleSheet("""
            QGroupBox {
                background-color: white;
                border-radius: 6px;
                border: 1px solid #dee2e6;
                margin-top: 8px;
            }
            QGroupBox::title {
                color: #495057;
                background-color: white;
                padding: 5px;
            }
        """)
        table_layout = QVBoxLayout(table_group)
        table_layout.setContentsMargins(10, 15, 10, 10)  # Increased margins
        
        self.name_table = QTableWidget()
        self.name_table.setColumnCount(2)
        self.name_table.setHorizontalHeaderLabels(["Name", "Count"])
        self.name_table.horizontalHeader().setStretchLastSection(True)
        self.name_table.setStyleSheet("""
            QTableWidget {
                background-color: white;
                border: none;
                gridline-color: #dee2e6;
            }
            QHeaderView::section {
                background-color: white;
                padding: 8px;
                border: none;
                border-bottom: 1px solid #dee2e6;
                color: #212529;
                font-weight: bold;
            }
            QTableWidget::item {
                padding: 5px;
                border: none;
                color: #212529;  /* Dark gray, almost black text */
            }
        """)
        table_layout.addWidget(self.name_table)
        
        top_section.addWidget(table_group, 2)  # Give table more space
        layout.addLayout(top_section)

        # Bottom section: Chart
        chart_group = QGroupBox("Confidence Distribution")
        chart_group.setStyleSheet("""
            QGroupBox {
                background-color: #f8f9fa;
                border-radius: 6px;
                border: 1px solid #dee2e6;
            }
            QGroupBox::title {
                color: #495057;
            }
        """)
        chart_layout = QVBoxLayout(chart_group)
        
        # Placeholder for chart (will be replaced in setup_histogram)
        self.chart_placeholder = QWidget()
        chart_layout.addWidget(self.chart_placeholder)
        
        layout.addWidget(chart_group, 2)  # Give chart more vertical space

    def showEvent(self, event):
        """Initialize components when tab becomes visible."""        
        super().showEvent(event)
        if not self.is_initialized:
            self.setup_histogram()
            self.is_initialized = True
        self.status_label.setText("Ready")

    def hideEvent(self, event):
        """Clean up when tab is hidden."""        
        super().hideEvent(event)
        # Clear all data
        self.progress_bar.setValue(0)
        self.status_label.setText("Ready")
        self.name_table.setRowCount(0)  # Clear the table
        # Cancel any ongoing prediction
        if hasattr(self, 'worker') and self.worker.isRunning():
            self.cancel_prediction()

    def setup_histogram(self):
        """Setup the confidence histogram chart with improved styling."""        
        if hasattr(self, 'chart_placeholder'):
            self.chart_placeholder.setParent(None)
            delattr(self, 'chart_placeholder')

        self.chart = QChart()
        self.chart.setTitle("Confidence Distribution")
        self.chart.setAnimationOptions(QChart.AnimationOption.SeriesAnimations)
        
        title_font = QFont("Arial", 12)
        title_font.setBold(True)
        self.chart.setTitleFont(title_font)
        
        # Create bar series
        self.bar_series = QBarSeries()
        self.bar_set = QBarSet("Confidence")
        self.bar_set.setColor(QColor("#0d6efd"))
        self.bar_set.append([0] * 10)
        self.bar_series.append(self.bar_set)
        self.chart.addSeries(self.bar_series)
        
        # Setup modern axes
        self.axis_x = QBarCategoryAxis()
        self.axis_x.append([f"{i/10:.1f}-{(i+1)/10:.1f}" for i in range(10)])
        self.axis_x.setLabelsColor(QColor("#495057"))
        
        self.axis_y = QValueAxis()
        self.axis_y.setTitleText("Number of Predictions")
        self.axis_y.setTitleFont(QFont("Arial", 10))
        self.axis_y.setLabelsColor(QColor("#495057"))
        
        self.chart.addAxis(self.axis_x, Qt.AlignmentFlag.AlignBottom)
        self.chart.addAxis(self.axis_y, Qt.AlignmentFlag.AlignLeft)
        self.bar_series.attachAxis(self.axis_x)
        self.bar_series.attachAxis(self.axis_y)
        
        # Create chart view
        self.chart_view = QChartView(self.chart)
        self.chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.chart_view.setMinimumHeight(300)
        
        # After initial setup, disable animations for updates
        self.chart.setAnimationOptions(QChart.AnimationOption.NoAnimation)
        
        self.layout().itemAt(1).widget().layout().addWidget(self.chart_view)

    def update_histogram(self, confidence_values):
        """Update histogram with new confidence values."""        
        if not confidence_values:
            return
            
        # Create histogram bins
        bins = [0] * 10
        for conf in confidence_values:
            bin_idx = min(int(conf * 10), 9)  # Values from 0.0-1.0 into 10 bins
            bins[bin_idx] += 1
        
        # Update bar set
        self.bar_set.remove(0, 10)
        self.bar_set.append(bins)
        
        # Adjust y-axis
        max_value = max(bins)
        self.chart.axes()[1].setRange(0, max_value + 1)

    def update_name_table(self, name_counts: dict):
        """Update the name frequency table."""        
        sorted_names = sorted(name_counts.items(), key=lambda x: x[1], reverse=True)
        self.name_table.setRowCount(len(sorted_names))
        
        for row, (name, count) in enumerate(sorted_names):
            # Name column
            name_item = QTableWidgetItem(name)
            name_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            name_item.setForeground(QColor("#212529"))  # Dark gray, almost black text
            
            # Count column
            count_item = QTableWidgetItem(str(count))
            count_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            count_item.setForeground(QColor("#212529"))  # Dark gray, almost black text
            
            self.name_table.setItem(row, 0, name_item)
            self.name_table.setItem(row, 1, count_item)
        
        self.name_table.resizeColumnsToContents()
        self.name_table.scrollToTop()
        self.name_table.show()

    def start_prediction(self):
        """Start the prediction process."""        
        self.start_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.progress_bar.setValue(0)
        
        # Reset histogram
        self.bar_set.remove(0, 10)
        self.bar_set.append([0] * 10)

        # Start prediction worker
        only_process_without_name = self.filter_checkbox.isChecked()
        self.worker = PredictionWorker(self.db_manager, only_process_without_name)
        self.worker.progress.connect(self.update_progress)
        self.worker.histogram_update.connect(self.update_histogram)
        self.worker.name_frequencies.connect(self.update_name_table)  # Add this connection
        self.worker.finished.connect(self.prediction_finished)
        self.worker.error.connect(self.prediction_error)
        self.worker.start()

    def cancel_prediction(self):
        """Cancel the prediction process."""        
        if hasattr(self, 'worker') and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait()
            self.status_label.setText("Prediction cancelled")
            self.progress_bar.setValue(0)
            self.start_button.setEnabled(True)
            self.cancel_button.setEnabled(False)

    def update_progress(self, message, progress):
        """Update progress bar and status message."""        
        self.status_label.setText(message)
        self.progress_bar.setValue(progress)

    def prediction_finished(self):
        """Handle prediction completion."""        
        self.status_label.setText("Prediction complete!")
        self.progress_bar.setValue(100)
        self.start_button.setEnabled(True)
        self.cancel_button.setEnabled(False)

    def prediction_error(self, error_msg):
        """Handle prediction error."""        
        self.status_label.setText(f"Error: {error_msg}")
        self.progress_bar.setValue(0)
        self.start_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
