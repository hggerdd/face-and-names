import logging
from pathlib import Path

import joblib
import torch
from facenet_pytorch import InceptionResnetV1, MTCNN

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

            self.mtcnn = self._load_mtcnn(self.model_dir / 'mtcnn_complete.pth')
            self.resnet = self._load_resnet(self.model_dir / 'face_encoder_complete.pth')
            if self.resnet is None:
                logging.error("Failed to load face encoder model")
                return False
            self.resnet.eval()

            self.classifier = joblib.load(self.model_dir / 'face_classifier.joblib')
            self.label_encoder = joblib.load(self.model_dir / 'label_encoder.joblib')
            
            self.is_initialized = True
            return True

        except Exception as e:
            logging.error(f"Error initializing prediction helper: {e}")
            return False

    def _load_mtcnn(self, path: Path):
        if not path.exists():
            logging.warning("MTCNN weights not found")
            return None
        state = torch.load(path, map_location=self.device)
        if isinstance(state, dict):
            mtcnn = MTCNN(keep_all=False, device=self.device)
            mtcnn.load_state_dict(state)
            return mtcnn
        return state  # backward compatibility

    def _load_resnet(self, path: Path):
        if not path.exists():
            logging.warning("Face encoder weights not found")
            return None
        state = torch.load(path, map_location=self.device)
        model = None
        if isinstance(state, dict):
            model = InceptionResnetV1(pretrained='vggface2')
            try:
                model.load_state_dict(state)
            except Exception as exc:
                logging.error("Failed to load resnet state dict: %s", exc)
                return None
        else:
            model = state  # fallback to pre-serialized module
        model = model.to(self.device)
        return model

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
