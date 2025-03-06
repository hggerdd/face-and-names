import torch
import logging
from pathlib import Path
from enum import Enum
from facenet_pytorch import InceptionResnetV1
from PyQt6.QtCore import QSettings
from torchvision import models
from torch import nn

class ModelManager:
    """Manages model loading, saving, and configuration."""
    
    def __init__(self):
        self.settings = QSettings('FaceRecognitionApp', 'Training')
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        
    def get_latest_model_path(self) -> Path:
        """Get path to the latest trained model."""
        save_path = self.settings.value('save_path', '')
        model_name = self.settings.value('model_name', '')
        
        if save_path and model_name:
            return Path(save_path) / f"{model_name}.pth"
        return None
        
    def load_model(self, model_path: Path = None):
        """Load a trained model."""
        try:
            if model_path is None:
                model_path = self.get_latest_model_path()
                
            if not model_path or not model_path.exists():
                logging.warning("No model found")
                return None
                
            checkpoint = torch.load(model_path, map_location=self.device)
            
            # Check if it's a simple model (from simple training)
            if 'model_type' not in checkpoint:
                # Simple model format
                model = models.resnet18(pretrained=True)
                model.fc = nn.Linear(512, checkpoint['n_classes'])
                model.load_state_dict(checkpoint['model_state_dict'])
                model.to(self.device)
                model.eval()
                
                logging.info(f"Loaded simple model with {checkpoint['n_classes']} classes")
                logging.info(f"Class mapping: {checkpoint['class_mapping']}")
                
                return {
                    'model': model,
                    'class_mapping': checkpoint['class_mapping'],
                    'accuracy': checkpoint.get('accuracy', 0.0),
                    'model_type': 'Simple ResNet18'
                }
            
            # Regular model format
            model_type = checkpoint['model_type']
            n_classes = checkpoint['n_classes']
            class_mapping = checkpoint['class_mapping']
            
            if "FaceNet" in model_type:
                model = InceptionResnetV1(pretrained='vggface2')
                model.logits = nn.Linear(512, n_classes)
                model.load_state_dict(checkpoint['model_state_dict'])
                model.to(self.device)
                model.eval()
                
                logging.info(f"Loaded model with {n_classes} classes")
                logging.info(f"Class mapping: {class_mapping}")
                
                return {
                    'model': model,
                    'class_mapping': class_mapping,
                    'accuracy': checkpoint['accuracy'],
                    'model_type': model_type
                }
                
            elif "VGGFace2" in model_type:
                model = InceptionResnetV1(pretrained='vggface2')
                # Freeze feature extraction layers
                for param in model.parameters():
                    param.requires_grad = False
                # Replace final layer
                model.logits = nn.Linear(512, n_classes)
                model.load_state_dict(checkpoint['model_state_dict'])
                model.to(self.device)
                model.eval()
                
                logging.info(f"Loaded VGGFace2 model with {n_classes} classes")
                logging.info(f"Class mapping: {class_mapping}")
                
                return {
                    'model': model,
                    'class_mapping': class_mapping,
                    'accuracy': checkpoint['accuracy'],
                    'model_type': model_type
                }
                
            elif "VGG-Face" in model_type:
                model = models.vgg16_bn(pretrained=True)
                model.classifier[6] = torch.nn.Linear(4096, n_classes)
                model.load_state_dict(checkpoint['model_state_dict'])
                model.to(self.device)
                model.eval()
                
                return {
                    'model': model,
                    'class_mapping': checkpoint['class_mapping'],
                    'accuracy': checkpoint['accuracy'],
                    'model_type': model_type
                }
                
            elif "ResNet50" in model_type:
                model = models.resnet50(pretrained=True)
                model.fc = torch.nn.Linear(2048, n_classes)
                model.load_state_dict(checkpoint['model_state_dict'])
                model.to(self.device)
                model.eval()
                
                return {
                    'model': model,
                    'class_mapping': checkpoint['class_mapping'],
                    'accuracy': checkpoint['accuracy'],
                    'model_type': model_type
                }
                
            else:
                logging.error(f"Unsupported model type: {model_type}")
                return None
                
        except Exception as e:
            logging.error(f"Error loading model: {str(e)}")
            return None 