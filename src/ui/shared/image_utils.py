from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtCore import Qt, QSize
from PIL import Image
import io
import logging

class ImageProcessor:
    """Shared utility class for image processing operations across widgets."""
    
    @staticmethod
    def create_pixmap_from_data(image_data: bytes, max_size: QSize = None) -> QPixmap:
        """Create a QPixmap from image data, optionally scaling to max_size.
        
        Args:
            image_data: Raw image data in bytes
            max_size: Optional QSize for maximum dimensions. Image will be scaled down if needed.
            
        Returns:
            QPixmap object or None if creation fails
        """
        try:
            if not isinstance(image_data, (bytes, bytearray)):
                logging.error(f"Invalid image data type: {type(image_data)}")
                return None

            # Ensure we have a fresh BytesIO object
            image_bytes = io.BytesIO(image_data)
            image = Image.open(image_bytes)
            
            # Convert to RGB to ensure consistent format
            if image.mode not in ('RGB', 'RGBA'):
                image = image.convert('RGB')
                
            if max_size:
                image.thumbnail((max_size.width(), max_size.height()))
                
            # Use tobytes() with 'raw' format for direct memory access
            img_data = image.tobytes('raw', 'RGB')
            qimage = QImage(img_data,
                          image.width, image.height,
                          3 * image.width,  # bytes per line
                          QImage.Format.Format_RGB888)
                          
            return QPixmap.fromImage(qimage)
            
        except Exception as e:
            logging.error(f"Error creating pixmap from image data: {e}")
            return None
            
    @staticmethod
    def scale_pixmap(pixmap: QPixmap, max_size: QSize, keep_aspect: bool = True) -> QPixmap:
        """Scale a QPixmap to fit within max_size.
        
        Args:
            pixmap: Source QPixmap
            max_size: Maximum size to scale to
            keep_aspect: Whether to maintain aspect ratio
            
        Returns:
            Scaled QPixmap
        """
        try:
            if not pixmap or pixmap.isNull():
                return pixmap
                
            if keep_aspect:
                return pixmap.scaled(
                    max_size,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
            else:
                return pixmap.scaled(
                    max_size,
                    Qt.AspectRatioMode.IgnoreAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                
        except Exception as e:
            logging.error(f"Error scaling pixmap: {e}")
            return pixmap