"""Training package for Face-and-Names."""

from face_and_names.training.data_loader import load_verified_faces
from face_and_names.training.embedding import EmbeddingConfig, FacenetEmbedder
from face_and_names.training.model_io import load_artifacts, save_artifacts
from face_and_names.training.trainer import TrainingConfig, train_model_from_db

__all__ = [
    "TrainingConfig",
    "train_model_from_db",
    "load_verified_faces",
    "EmbeddingConfig",
    "FacenetEmbedder",
    "load_artifacts",
    "save_artifacts",
]
