from pathlib import Path
import cv2
import logging
import numpy as np
from dataclasses import dataclass
from typing import Optional, List, Tuple
from ultralytics import YOLO

@dataclass
class DetectedFace:
    """Data class to hold detected face information."""
    face_image: np.ndarray
    confidence: float
    original_file: Path
    bbox: Tuple[int, int, int, int]  # x, y, w, h in pixels
    bbox_relative: Tuple[float, float, float, float]  # x, y, w, h as ratios
    predicted_name: Optional[str] = None
    prediction_confidence: Optional[float] = None

class FaceDetector:
    def __init__(self, model_path: str = 'yolov11n-face.pt', increase_percent: float = 10.0):
        self.model = YOLO(model_path)
        self.increase_percent = increase_percent

    # Context manager: no extra resource to free
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def detect_faces(self, image_path: Path, image: np.ndarray = None) -> List[DetectedFace]:
        if image is None:
            image = correct_image_orientation(image_path)
        if image is None:
            logging.error(f"Could not load image: {image_path}")
            return []

        height, width = image.shape[:2]
        results = self.model(image)
        detected_faces = []

        for result in results:
            for box in result.boxes:
                try:
                    x1, y1, x2, y2 = box.xyxy[0]
                    confidence = box.conf[0]
                    
                    # Calculate padding
                    box_width = x2 - x1
                    box_height = y2 - y1
                    inc_x = box_width * (self.increase_percent / 100)
                    inc_y = box_height * (self.increase_percent / 100)
                    
                    # New coordinates with padding
                    x1_pad = max(0, x1 - inc_x)
                    y1_pad = max(0, y1 - inc_y)
                    x2_pad = min(width, x2 + inc_x)
                    y2_pad = min(height, y2 + inc_y)
                    
                    # Convert to integers for array indexing
                    x1_i, y1_i, x2_i, y2_i = map(int, [x1_pad, y1_pad, x2_pad, y2_pad])
                    
                    # Calculate relative coordinates
                    rel_x = float(x1_i) / width
                    rel_y = float(y1_i) / height
                    rel_w = float(x2_i - x1_i) / width
                    rel_h = float(y2_i - y1_i) / height

                    logging.debug(f"Face detected at pixel coords: {(x1_i, y1_i, x2_i, y2_i)}")
                    
                    face_img = image[y1_i:y2_i, x1_i:x2_i]
                    if face_img.size > 0:
                        detected_faces.append(DetectedFace(
                            face_image=face_img,
                            confidence=confidence,
                            original_file=image_path,
                            bbox=(x1_i, y1_i, x2_i - x1_i, y2_i - y1_i),  # pixel coordinates
                            bbox_relative=(rel_x, rel_y, rel_w, rel_h),     # relative coordinates
                            predicted_name=None,
                            prediction_confidence=None
                        ))
                        logging.debug(f"Face detected at relative coords: {(rel_x, rel_y, rel_w, rel_h)}")
                    else:
                        logging.warning(f"Empty face region in {image_path}")
                except Exception as e:
                    logging.error(f"Error processing face box: {e}")
                    continue

        return detected_faces

class FaceDetectionProcessor:
    def __init__(self, db_manager, model_path: str = 'yolov11n-face.pt', increase_percent: float = 10.0):
        self.db_manager = db_manager
        self.model_path = model_path
        self.increase_percent = increase_percent

    def get_detector(self) -> FaceDetector:
        return FaceDetector(model_path=self.model_path, increase_percent=self.increase_percent)
