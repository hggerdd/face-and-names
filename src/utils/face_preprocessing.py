import cv2
import numpy as np
import torch


def preprocess_face_image(image: np.ndarray, target_size: int = 160) -> torch.Tensor:
    """Convert a face crop (BGR or RGB) into a normalized tensor for inference/training."""
    if image is None or not isinstance(image, np.ndarray) or image.size == 0:
        raise ValueError("Invalid face image for preprocessing")

    if image.ndim != 3 or image.shape[2] != 3:
        raise ValueError(f"Expected HxWx3 image, got shape {image.shape}")

    # Convert BGR (OpenCV) to RGB
    processed = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    processed = cv2.resize(processed, (target_size, target_size), interpolation=cv2.INTER_AREA)
    processed = processed.astype(np.float32)
    processed = (processed - 127.5) / 128.0

    tensor = torch.from_numpy(processed)
    tensor = tensor.permute(2, 0, 1)  # to CxHxW
    return tensor
