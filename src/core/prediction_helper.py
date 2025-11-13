import torch
import logging
from pathlib import Path
import joblib
from facenet_pytorch import InceptionResnetV1

class PredictionHelper:
    def __init__(self):
        self.model_dir = Path("face_recognition_models")
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        self.mtcnn = None
        self.resnet = None
        self.classifier = None
        self.label_encoder = None
        self.is_initialized = False

    def initialize(self):
        try:
            if not self.model_dir.exists():
                logging.warning("Model directory not found")
                return False

            # Load MTCNN and ResNet models
            self.mtcnn = torch.load(self.model_dir / 'mtcnn_complete.pth', map_location=self.device)
            self.resnet = torch.load(self.model_dir / 'face_encoder_complete.pth', map_location=self.device)
            self.resnet.eval()

            # Load classifier and label encoder
            self.classifier = joblib.load(self.model_dir / 'face_classifier.joblib')
            self.label_encoder = joblib.load(self.model_dir / 'label_encoder.joblib')
            
            self.is_initialized = True
            return True

        except Exception as e:
            logging.error(f"Error initializing prediction helper: {e}")
            return False

    def predict_face(self, face_tensor):
        if not self.is_initialized:
            if not self.initialize():
                return None, 0.0

        try:
            with torch.no_grad():
                encoding = self.resnet(face_tensor.unsqueeze(0).to(self.device)).cpu().numpy()
            probabilities = self.classifier.predict_proba(encoding)[0]
            predicted_label = self.classifier.predict(encoding)[0]
            confidence = probabilities.max()
            predicted_name = self.label_encoder.inverse_transform([predicted_label])[0]
            
            return predicted_name, confidence

        except Exception as e:
            logging.error(f"Error predicting face: {e}")
            return None, 0.0
