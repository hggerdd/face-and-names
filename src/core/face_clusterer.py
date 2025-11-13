from pathlib import Path
import numpy as np
from typing import List, Dict, Tuple
import logging
from dataclasses import dataclass
from enum import Enum
from sklearn.cluster import DBSCAN, KMeans, AgglomerativeClustering
from facenet_pytorch import InceptionResnetV1
import torch
from PIL import Image
import io

class ClusteringAlgorithm(Enum):
    DBSCAN = "DBSCAN"
    KMEANS = "K-Means"
    HIERARCHICAL = "Hierarchical"

class ModelType(Enum):
    VGGFACE2 = "VGGFace2"
    CASIA_WEBFACE = "CASIA-WebFace"

@dataclass
class ClusteringResult:
    face_ids: List[int]
    labels: List[int]
    n_clusters: int
    algorithm: ClusteringAlgorithm

class FaceClusterer:
    def __init__(self, device=None, model_type: ModelType = ModelType.VGGFACE2):
        self.device = device or torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        self.model_type = model_type
        self._model = None
        logging.info(f"FaceClusterer initialized with device: {self.device} and model type: {model_type.value}")

    @property
    def model(self):
        """Lazy initialization of the face recognition model."""
        if self._model is None:
            logging.info(f"Loading face recognition model: {self.model_type.value}")
            pretrained = 'vggface2' if self.model_type == ModelType.VGGFACE2 else 'casia-webface'
            self._model = InceptionResnetV1(pretrained=pretrained).eval().to(self.device)
        return self._model

    def _get_face_embeddings(self, face_images: List[bytes], progress_callback=None) -> np.ndarray:
        """Convert face images to embeddings using FaceNet."""
        embeddings = []
        total = len(face_images)
        
        for idx, img_bytes in enumerate(face_images):
            try:
                if progress_callback:
                    # Adjust progress to be between 0-50%
                    progress = int(50 * idx/total)
                    progress_callback(f"Processing face {idx + 1}/{total}", progress)
                
                # Convert bytes to PIL Image
                img = Image.open(io.BytesIO(img_bytes)).convert('RGB')
                
                # Preprocess image
                img = self._preprocess_face(img)
                img = torch.from_numpy(img).float()
                img = img.permute(2, 0, 1).unsqueeze(0)
                img = img.to(self.device)
                
                # Get embedding using lazy-loaded model
                with torch.no_grad():
                    embedding = self.model(img)  # This will load model if needed
                embeddings.append(embedding.cpu().numpy().flatten())
                
            except Exception as e:
                logging.error(f"Error processing face {idx}: {e}")
                embeddings.append(np.zeros(512))

        if progress_callback:
            progress_callback(f"Processed all {total} faces", 50)
                
        embeddings = np.array(embeddings)
        embeddings = self._normalize_embeddings(embeddings)
        return embeddings

    def _preprocess_face(self, img: Image.Image) -> np.ndarray:
        """Preprocess face image for the model."""
        # Convert to numpy array
        img_np = np.array(img)
        
        # Standardize image
        img_np = (img_np - 127.5) / 128.0
        
        # Ensure correct size (160x160 for FaceNet)
        if img_np.shape[:2] != (160, 160):
            img = img.resize((160, 160), Image.Resampling.LANCZOS)
            img_np = np.array(img)
            img_np = (img_np - 127.5) / 128.0
            
        return img_np

    def _normalize_embeddings(self, embeddings: np.ndarray) -> np.ndarray:
        """Normalize embeddings using L2 normalization."""
        # Remove any zero embeddings
        valid_mask = ~np.all(embeddings == 0, axis=1)
        valid_embeddings = embeddings[valid_mask]
        
        if len(valid_embeddings) == 0:
            return embeddings
        
        # Normalize valid embeddings
        norms = np.linalg.norm(valid_embeddings, axis=1, keepdims=True)
        normalized = valid_embeddings / norms
        
        # Replace original embeddings with normalized ones
        embeddings[valid_mask] = normalized
        return embeddings

    def cluster_faces(self, 
                     face_ids: List[int],
                     face_images: List[bytes],
                     algorithm: ClusteringAlgorithm,
                     progress_callback=None,
                     **kwargs) -> ClusteringResult:
        """Cluster faces using the specified algorithm."""
        
        if progress_callback:
            progress_callback("Initializing face embeddings...", 0)
            
        # Get face embeddings (0-50% of progress)
        embeddings = self._get_face_embeddings(face_images, progress_callback)
        
        if progress_callback:
            progress_callback(f"Running {algorithm.value} clustering...", 50)
            
        # Apply clustering (50-90% of progress)
        if algorithm == ClusteringAlgorithm.DBSCAN:
            labels = self._dbscan_clustering(embeddings, **kwargs)
        elif algorithm == ClusteringAlgorithm.KMEANS:
            labels = self._kmeans_clustering(embeddings, **kwargs)
        elif algorithm == ClusteringAlgorithm.HIERARCHICAL:
            labels = self._hierarchical_clustering(embeddings, **kwargs)
        else:
            raise ValueError(f"Unknown clustering algorithm: {algorithm}")
            
        if progress_callback:
            progress_callback("Analyzing clustering results...", 90)
            
        # Final steps (90-100%)
        unique_labels = set(labels)
        n_clusters = len(unique_labels - {-1} if -1 in unique_labels else unique_labels)
        
        return ClusteringResult(
            face_ids=face_ids,
            labels=labels.tolist(),
            n_clusters=n_clusters,
            algorithm=algorithm
        )

    def _dbscan_clustering(self, embeddings: np.ndarray, eps: float = 0.3, 
                          min_samples: int = 3) -> np.ndarray:
        """DBSCAN clustering."""
        # Calculate distance matrix using cosine metric
        distances = 1 - np.dot(embeddings, embeddings.T)
        
        # Ensure distances are valid
        distances = np.clip(distances, 0, 2)
        
        # Apply DBSCAN
        clustering = DBSCAN(
            eps=eps,
            min_samples=min_samples,
            metric='precomputed',
            n_jobs=-1
        )
        return clustering.fit_predict(distances)

    def _kmeans_clustering(self, embeddings: np.ndarray, n_clusters: int = 10) -> np.ndarray:
        """K-means clustering."""
        # Initialize with better parameters
        clustering = KMeans(
            n_clusters=n_clusters,
            init='k-means++',
            n_init=10,
            max_iter=300,
            random_state=42
        )
        return clustering.fit_predict(embeddings)

    def _hierarchical_clustering(self, embeddings: np.ndarray, n_clusters: int = 10,
                               linkage: str = 'ward') -> np.ndarray:
        """Hierarchical clustering."""
        # For 'ward' linkage, we must use euclidean affinity and cannot specify it explicitly
        if linkage == 'ward':
            clustering = AgglomerativeClustering(
                n_clusters=n_clusters,
                linkage='ward'
            )
        else:
            # For other linkage methods, we can use cosine affinity
            clustering = AgglomerativeClustering(
                n_clusters=n_clusters,
                linkage=linkage,
                metric='cosine'  # Changed from affinity to metric
            )
        return clustering.fit_predict(embeddings)