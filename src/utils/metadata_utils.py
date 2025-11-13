from PIL import Image, ExifTags
from PIL.ExifTags import TAGS, GPSTAGS
import iptcinfo3
import logging
from pathlib import Path
from typing import Dict, Tuple

def extract_image_metadata(image_path: Path) -> Dict[str, Tuple[str, str]]:
    """
    Extract EXIF and IPTC metadata from image.
    Returns dict with format: {key: (type, value)}
    """
    metadata = {}
    
    try:
        # Extract EXIF data
        with Image.open(image_path) as img:
            if hasattr(img, '_getexif') and img._getexif() is not None:
                exif = img._getexif()
                for tag_id, value in exif.items():
                    try:
                        tag = TAGS.get(tag_id, tag_id)
                        # Handle different types of EXIF data
                        if isinstance(value, bytes):
                            value = value.decode(errors='replace')
                        elif isinstance(value, tuple):
                            value = '/'.join(str(x) for x in value)
                        metadata[f"EXIF_{tag}"] = ("exif", str(value))
                    except Exception as e:
                        logging.debug(f"Error processing EXIF tag {tag_id}: {e}")

    except Exception as e:
        logging.error(f"Error extracting EXIF from {image_path}: {e}")

    try:
        # Extract IPTC data
        with open(image_path, 'rb') as f:
            iptc = iptcinfo3.IPTCInfo(f)
            for key, value in iptc.items():
                if isinstance(value, (str, bytes, list)):
                    if isinstance(value, bytes):
                        value = value.decode(errors='replace')
                    elif isinstance(value, list):
                        value = ', '.join(str(x) for x in value)
                    metadata[f"IPTC_{key}"] = ("iptc", str(value))

    except Exception as e:
        logging.error(f"Error extracting IPTC from {image_path}: {e}")

    return metadata
