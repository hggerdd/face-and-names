from PyQt6.QtWidgets import QMainWindow, QWidget, QTabWidget, QVBoxLayout
from .detection_widget import FaceDetectionWidget
from .clustering_widget import ClusteringWidget
from .naming_widget import NamingWidget
from .vggface_training_widget import VGGFaceTrainingWidget
from .prediction_widget import PredictionWidget
from .prediction_review_widget import PredictionReviewWidget
from .database_analysis_widget import DatabaseAnalysisWidget
from .thumbnail_viewer import ThumbnailViewer
from .name_analysis_widget import NameAnalysisWidget  # Add import
import logging

class MainWindow(QMainWindow):
    def __init__(self, db_manager):
        super().__init__()
        self.db_manager = db_manager
        self.previous_tab_index = -1
        self.setup_ui()

    def setup_ui(self):
        self.setWindowTitle("Face Recognition System")
        self.resize(1200, 800)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        self.tabs = QTabWidget()
        self.tabs.currentChanged.connect(self.on_tab_changed)
        
        # Add tabs
        self.tabs.addTab(FaceDetectionWidget(self.db_manager), "Detection")
        self.tabs.addTab(ThumbnailViewer(self.db_manager), "Thumbnails")
        self.tabs.addTab(ClusteringWidget(self.db_manager), "Clustering")
        self.tabs.addTab(NamingWidget(self.db_manager), "Naming")
        self.tabs.addTab(NameAnalysisWidget(self.db_manager), "Name Analysis")  # Add new tab
        self.tabs.addTab(VGGFaceTrainingWidget(self.db_manager), "VGGFace Training")
        self.tabs.addTab(PredictionWidget(self.db_manager), "Prediction")
        self.tabs.addTab(PredictionReviewWidget(self.db_manager), "Review Predictions")
        self.tabs.addTab(DatabaseAnalysisWidget(self.db_manager), "Database Analysis")

        main_layout.addWidget(self.tabs)

    def on_tab_changed(self, index):
        """Handle tab changes to refresh data."""
        try:
            # Only trigger showEvent if actually changing tabs
            if index != self.previous_tab_index:
                current_widget = self.tabs.widget(index)
                if current_widget and hasattr(current_widget, 'showEvent'):
                    current_widget.showEvent(None)
                self.previous_tab_index = index
        except Exception as e:
            logging.error(f"Error in tab change: {e}")