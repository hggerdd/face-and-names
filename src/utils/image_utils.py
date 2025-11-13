from PIL import Image, ExifTags
import numpy as np
import cv2
import logging

def get_rotation_from_exif(image_path):
    """Get rotation angle from EXIF data."""
    try:
        image = Image.open(image_path)
        if not hasattr(image, '_getexif') or image._getexif() is None:
            return 0

        # Find orientation tag
        orientation = None
        for tag_id in ExifTags.TAGS:
            if ExifTags.TAGS[tag_id] == 'Orientation':
                try:
                    orientation = image._getexif().get(tag_id)
                except:
                    orientation = None
                break

        # Convert orientation to degrees
        if orientation == 3:
            return 180
        elif orientation == 6:
            return 270
        elif orientation == 8:
            return 90
        return 0

    except Exception as e:
        logging.warning(f"Could not get EXIF rotation for {image_path}: {e}")
        return 0

def correct_image_orientation(image_path) -> np.ndarray:
    """Load and correct image orientation based on EXIF data. Returns BGR format."""
    try:
        # Get rotation angle from EXIF
        rotation = get_rotation_from_exif(image_path)
        
        if rotation == 0:
            # No rotation needed, load normally with cv2 (returns BGR)
            img = cv2.imread(str(image_path))
            if img is None:
                raise ValueError("Failed to load image")
            return img
            
        # For rotated images, use PIL to load and rotate
        image = Image.open(image_path)
        if rotation > 0:
            image = image.rotate(rotation, expand=True)
            
        # Convert PIL image (RGB) to BGR for OpenCV
        image = np.array(image)
        if len(image.shape) == 3 and image.shape[2] == 3:
            image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
        return image

    except Exception as e:
        logging.error(f"Error correcting image orientation: {e}")
        return None

def create_thumbnail(image: np.ndarray, max_width: int = 500) -> bytes:
    """Create a thumbnail with max width while maintaining aspect ratio."""
    try:
        if image is None or not isinstance(image, np.ndarray) or image.size == 0:
            logging.error("Invalid image data for thumbnail creation")
            return None
            
        if len(image.shape) != 3 or image.shape[2] != 3:
            logging.error(f"Invalid image shape for thumbnail: {image.shape}")
            return None

        height, width = image.shape[:2]
        logging.debug(f"Thumbnail: original image size {width}x{height}")
        
        if width > max_width:
            ratio = max_width / width
            new_width = max_width
            new_height = int(height * ratio)
        else:
            new_width = width
            new_height = height

        logging.debug(f"Thumbnail: resizing to {new_width}x{new_height}")
        resized = cv2.resize(image, (new_width, new_height), interpolation=cv2.INTER_AREA)
        
        ret, img_encoded = cv2.imencode('.jpg', resized, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if not ret or img_encoded is None:
            logging.error("Failed to encode thumbnail")
            return None

        thumbnail_bytes = img_encoded.tobytes()
        logging.debug(f"Thumbnail created: {len(thumbnail_bytes)} bytes")
        return thumbnail_bytes
        
    except Exception as e:
        logging.error(f"Error creating thumbnail: {e}")
        return None

def image_is_rgb(image: np.ndarray) -> bool:
    """Helper function to check if image is in RGB format."""
    # Simple heuristic: check if the image has more red than blue on average
    # This isn't perfect but works for most natural images
    if len(image.shape) == 3 and image.shape[2] == 3:
        return np.mean(image[:, :, 0]) < np.mean(image[:, :, 2])  # Red channel > Blue channel
    return False
