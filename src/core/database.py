import sqlite3
from pathlib import Path
import logging
from typing import List, Tuple
from .face_detector import DetectedFace
import cv2
import numpy as np
from .face_clusterer import ClusteringResult
from ..utils.image_utils import create_thumbnail

class DatabaseManager:
    """Manages database operations for the face recognition system."""
    
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.initialize_database()
    
    def initialize_database(self):
        """Initialize database with required tables and indexes."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Create images table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS images (
                    image_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    base_folder TEXT,
                    sub_folder TEXT,
                    filename TEXT,
                    processed_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    has_faces BOOLEAN,
                    UNIQUE(base_folder, sub_folder, filename)
                )
            ''')

            # Create thumbnails table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS thumbnails (
                    image_id INTEGER PRIMARY KEY,
                    thumbnail BLOB NOT NULL,
                    FOREIGN KEY (image_id) REFERENCES images(image_id)
                    ON DELETE CASCADE
                )
            ''')
            
            # Create faces table with image_id reference
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS faces (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    image_id INTEGER,
                    face_image BLOB,
                    name TEXT,
                    predicted_name TEXT,
                    prediction_confidence REAL,
                    cluster_id INTEGER,
                    bbox_x REAL,
                    bbox_y REAL,
                    bbox_w REAL,
                    bbox_h REAL,
                    FOREIGN KEY (image_id) REFERENCES images(image_id)
                )
            ''')
            
            # Modified image_metadata table to use a composite primary key instead
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS image_metadata (
                    image_id INTEGER NOT NULL,
                    meta_key TEXT NOT NULL,
                    meta_type TEXT,
                    meta_value TEXT,
                    PRIMARY KEY (image_id, meta_key),
                    FOREIGN KEY (image_id) REFERENCES images(image_id)
                    ON DELETE CASCADE
                ) WITHOUT ROWID
            ''')
            
            # Create indexes for sorted access
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_metadata_sorted ON image_metadata(image_id)')
            
            # Add index for metadata queries
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_metadata_image_id ON image_metadata(image_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_metadata_key ON image_metadata(meta_key)')
            
            # Create indexes
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_faces_name ON faces(name)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_faces_image_id ON faces(image_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_faces_cluster ON faces(cluster_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_images_path ON images(base_folder, sub_folder, filename)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_thumbnails_image_id ON thumbnails(image_id)')
            
            conn.commit()
            logging.info("Database initialized successfully")
            
        except Exception as e:
            logging.error(f"Database initialization failed: {e}")
            raise
        finally:
            conn.close()
    
    def get_or_create_image_id(self, image_path: Path, image_data: np.ndarray = None) -> int:
        """Get existing image ID or create new entry with thumbnail."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            base_folder = str(image_path.parent.parent)
            sub_folder = image_path.parent.name
            filename = image_path.name
            
            cursor.execute('''
                SELECT image_id, (SELECT 1 FROM thumbnails WHERE image_id = images.image_id)
                FROM images 
                WHERE base_folder = ? AND sub_folder = ? AND filename = ?
            ''', (base_folder, sub_folder, filename))
            result = cursor.fetchone()

            if result:
                image_id, has_thumbnail = result
                logging.debug(f"Found image entry {image_id}; has_thumbnail: {has_thumbnail}")
                if has_thumbnail is None and image_data is not None:
                    logging.debug(f"Image data shape for existing image {image_id}: {image_data.shape}")
                    thumbnail_data = create_thumbnail(image_data)
                    if thumbnail_data:
                        try:
                            cursor.execute('''
                                INSERT INTO thumbnails (image_id, thumbnail)
                                VALUES (?, ?)
                            ''', (image_id, thumbnail_data))
                            conn.commit()
                            logging.debug(f"Added thumbnail for existing image {image_id} ({len(thumbnail_data)} bytes)")
                        except Exception as e:
                            logging.error(f"Failed to save thumbnail for image {image_id}: {e}")
                    else:
                        logging.error(f"create_thumbnail returned None for image {image_id}")
                return image_id
            
            cursor.execute('''
                INSERT INTO images (base_folder, sub_folder, filename, has_faces)
                VALUES (?, ?, ?, ?)
            ''', (base_folder, sub_folder, filename, False))
            image_id = cursor.lastrowid
            logging.debug(f"Created new image entry {image_id}")

            if image_data is not None:
                logging.debug(f"Image data shape for new image {image_id}: {image_data.shape}")
                thumbnail_data = create_thumbnail(image_data)
                if (thumbnail_data):
                    try:
                        cursor.execute('''
                            INSERT INTO thumbnails (image_id, thumbnail)
                            VALUES (?, ?)
                        ''', (image_id, thumbnail_data))
                        logging.debug(f"Created thumbnail for new image {image_id} ({len(thumbnail_data)} bytes)")
                    except Exception as e:
                        logging.error(f"Failed to save thumbnail for new image {image_id}: {e}")
                else:
                    logging.error(f"Failed to create thumbnail data for new image {image_id}")
            
            conn.commit()
            return image_id
            
        except Exception as e:
            logging.error(f"Error in get_or_create image_id: {e}")
            conn.rollback()
            return None
        finally:
            conn.close()
    
    def get_thumbnail(self, image_id: int) -> bytes:
        """Retrieve thumbnail for an image."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('SELECT thumbnail FROM thumbnails WHERE image_id = ?', (image_id,))
            result = cursor.fetchone()
            
            return result[0] if result else None
            
        except Exception as e:
            logging.error(f"Error retrieving thumbnail: {e}")
            return None
        finally:
            conn.close()
    
    def is_image_processed(self, image_path: Path) -> bool:
        """Check if an image has already been processed."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            base_folder = str(image_path.parent.parent)
            sub_folder = image_path.parent.name
            filename = image_path.name
            
            cursor.execute('''
                SELECT image_id FROM images 
                WHERE base_folder = ? AND sub_folder = ? AND filename = ?
            ''', (base_folder, sub_folder, filename))
            
            return cursor.fetchone() is not None
            
        finally:
            conn.close()
    
    def save_faces_with_predictions(self, faces: List[DetectedFace]) -> bool:
        """Save detected faces to database with predictions and bounding boxes."""
        if not faces:
            return False
            
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            for face in faces:
                try:
                    image_id = self.get_or_create_image_id(face.original_file)
                    
                    # Convert face image to bytes
                    _, img_encoded = cv2.imencode('.jpg', face.face_image)
                    if img_encoded is None:
                        logging.error("Failed to encode face image")
                        continue
                        
                    img_bytes = img_encoded.tobytes()
                    
                    logging.debug(f"Saving face with bbox_relative: {face.bbox_relative}")
                    
                    cursor.execute('''
                        INSERT INTO faces (
                            image_id, 
                            face_image,
                            predicted_name,
                            prediction_confidence,
                            bbox_x,
                            bbox_y,
                            bbox_w,
                            bbox_h
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        image_id,
                        img_bytes,
                        getattr(face, 'predicted_name', None),
                        getattr(face, 'prediction_confidence', None),
                        face.bbox_relative[0],  # x
                        face.bbox_relative[1],  # y
                        face.bbox_relative[2],  # w
                        face.bbox_relative[3]   # h
                    ))
                    
                    # Update has_faces flag
                    cursor.execute('''
                        UPDATE images SET has_faces = TRUE
                        WHERE image_id = ?
                    ''', (image_id,))
                    
                except Exception as e:
                    logging.error(f"Error saving face: {e}")
                    continue
            
            conn.commit()
            return True
            
        except Exception as e:
            logging.error(f"Error in save_faces_with_predictions: {e}")
            return False
        finally:
            conn.close()

    def get_faces_for_clustering(self) -> List[Tuple[int, bytes]]:
        """Get faces without names for clustering."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Get only unnamed faces that have face_image data
            cursor.execute('''
                SELECT id, face_image 
                FROM faces 
                WHERE face_image IS NOT NULL
                AND name IS NULL
                ORDER BY id
            ''')
            
            faces = cursor.fetchall()
            if not faces:
                logging.warning("No unnamed faces found for clustering")
                return []
            
            logging.info(f"Found {len(faces)} unnamed faces for clustering")
            return faces
            
        except Exception as e:
            logging.error(f"Error getting faces for clustering: {e}")
            return []
        finally:
            conn.close()

    def save_clustering_results(self, result: 'ClusteringResult') -> bool:
        """Save clustering results to database."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # First reset all cluster IDs
            cursor.execute('UPDATE faces SET cluster_id = NULL')
            
            # Then update with new cluster IDs
            for face_id, cluster_id in zip(result.face_ids, result.labels):
                cursor.execute(
                    'UPDATE faces SET cluster_id = ? WHERE id = ?',
                    (int(cluster_id), face_id)
                )
            
            conn.commit()
            logging.info(f"Saved clustering results: {result.n_clusters} clusters")
            return True
            
        except Exception as e:
            logging.error(f"Error saving clustering results: {e}")
            return False
        finally:
            conn.close()

    def get_face_clusters(self) -> dict:
        """Get all faces grouped by cluster.
           Each face tuple now contains: (face_id, face_image, name, predicted_name, image_id)
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Select six values so we can group by cluster_id but return only five values per face
            cursor.execute('''
                SELECT id, face_image, name, predicted_name, image_id, cluster_id 
                FROM faces 
                WHERE cluster_id IS NOT NULL
                ORDER BY cluster_id, id
            ''')
            
            clusters = {}
            for row in cursor.fetchall():
                # row: (id, face_image, name, predicted_name, image_id, cluster_id)
                cluster_id = row[5]
                face_tuple = row[:5]  # (face_id, face_image, name, predicted_name, image_id)
                if cluster_id not in clusters:
                    clusters[cluster_id] = []
                clusters[cluster_id].append(face_tuple)
            
            return clusters
            
        except Exception as e:
            logging.error(f"Error getting face clusters: {e}")
            return {}
        finally:
            conn.close()

    def update_face_names(self, face_ids: List[int], name: str) -> bool:
        """Update names for given face IDs and remove their cluster IDs."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Update name and remove cluster_id for the selected faces
            cursor.executemany(
                'UPDATE faces SET name = ?, cluster_id = NULL WHERE id = ?',
                [(name, face_id) for face_id in face_ids]
            )
            
            conn.commit()
            return True
            
        except Exception as e:
            logging.error(f"Error updating face names: {e}")
            return False
        finally:
            conn.close()

    def clear_all_names(self) -> bool:
        """Clear all names from faces table."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('UPDATE faces SET name = NULL')
            conn.commit()
            
            # Get count of affected rows
            cursor.execute('SELECT COUNT(*) FROM faces WHERE face_image IS NOT NULL')
            count = cursor.fetchone()[0]
            
            logging.info(f"Cleared names from {count} faces")
            return True
            
        except Exception as e:
            logging.error(f"Error clearing names: {e}")
            return False
        finally:
            conn.close()

    def get_existing_names(self) -> set:
        """Get all unique names from the database."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT DISTINCT name 
                FROM faces 
                WHERE name IS NOT NULL
                ORDER BY name
            ''')
            
            names = {row[0] for row in cursor.fetchall()}
            return names
            
        except Exception as e:
            logging.error(f"Error getting existing names: {e}")
            return set()
        finally:
            conn.close()

    def get_faces_for_training(self) -> List[Tuple[int, bytes, str]]:
        """Get faces with assigned names for training."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT id, face_image, name 
                FROM faces 
                WHERE face_image IS NOT NULL
                AND name IS NOT NULL
                AND name != ''  -- Exclude empty names
                AND name != 'unknown'  -- Exclude unknown labels
                ORDER BY name, id
            ''')
            
            faces = cursor.fetchall()
            if not faces:
                logging.warning("No named faces found for training")
                return []
            
            # Log found faces per name for verification
            cursor.execute('''
                SELECT name, COUNT(*) as count
                FROM faces 
                WHERE face_image IS NOT NULL
                AND name IS NOT NULL
                AND name != ''
                AND name != 'unknown'
                GROUP BY name
                ORDER BY count DESC
            ''')
            name_counts = cursor.fetchall()
            logging.info(f"Found faces for training:")
            for name, count in name_counts:
                logging.info(f"  {name}: {count} images")
            
            logging.info(f"Total: {len(faces)} faces for {len(name_counts)} people")
            return faces
            
        except Exception as e:
            logging.error(f"Error getting faces for training: {e}")
            return []
        finally:
            conn.close()

    def get_faces_for_prediction(self) -> List[Tuple[int, bytes, str]]:
        """Get all faces for prediction testing."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT id, face_image, COALESCE(name, 'unknown') as name
                FROM faces 
                WHERE face_image IS NOT NULL
                ORDER BY RANDOM()
            ''')
            
            faces = cursor.fetchall()
            if not faces:
                logging.warning("No faces found in database for prediction")
                return []
            
            logging.info(f"Found {len(faces)} faces for prediction")
            return faces
            
        except Exception as e:
            logging.error(f"Error getting faces for prediction: {e}")
            return []
        finally:
            conn.close()

    def save_prediction_result(self, face_id: int, predicted_name: str, confidence: float) -> bool:
        """Save prediction result for a face."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Modified to include cluster_id reset when accepting prediction
            cursor.execute('''
                UPDATE faces 
                SET 
                    predicted_name = ?, 
                    prediction_confidence = ?,
                    cluster_id = CASE 
                        WHEN name IS NOT NULL THEN NULL  -- Only reset cluster_id if name is being set
                        ELSE cluster_id  -- Keep existing cluster_id if just updating prediction
                    END
                WHERE id = ?
            ''', (predicted_name, confidence, face_id))
            
            conn.commit()
            return True
            
        except Exception as e:
            logging.error(f"Error saving prediction result: {e}")
            return False
        finally:
            conn.close()

    def get_faces_with_predictions(self) -> List[Tuple[int, bytes, str, str, float, int]]:
        """Get faces with predictions including image_id"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT f.id, f.face_image, f.name, f.predicted_name, f.prediction_confidence, f.image_id
                FROM faces f
                WHERE f.face_image IS NOT NULL
                AND f.predicted_name IS NOT NULL
                ORDER BY f.prediction_confidence DESC NULLS LAST
            """)
            return cursor.fetchall()
        except Exception as e:
            logging.error(f"Error getting faces with predictions: {e}")
            return []
        finally:
            conn.close()

    def update_face_name(self, face_id: int, name: str) -> bool:
        """Update name for a single face and clear its cluster_id."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute(
                'UPDATE faces SET name = ?, cluster_id = NULL WHERE id = ?',  # Added cluster_id = NULL
                (name, face_id)
            )
            
            conn.commit()
            return True
            
        except Exception as e:
            logging.error(f"Error updating face name: {e}")
            return False
        finally:
            conn.close()

    def get_unique_names(self):
        """Get all unique names from faces table."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT DISTINCT name 
                FROM faces 
                WHERE name IS NOT NULL AND name != '' 
                UNION 
                SELECT DISTINCT predicted_name 
                FROM faces 
                WHERE predicted_name IS NOT NULL AND predicted_name != ''
                ORDER BY name
            """)
            names = [row[0] for row in cursor.fetchall()]
            logging.debug(f"Retrieved {len(names)} unique names from database")
            return names
        except Exception as e:
            logging.error(f"Error getting unique names: {e}")
            return []
        finally:
            conn.close()

    def clear_predictions_only(self) -> bool:
        """Clear only predicted_name and prediction_confidence, preserving the name column."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Get count before clearing
            cursor.execute('SELECT COUNT(*) FROM faces WHERE predicted_name IS NOT NULL')
            count_before = cursor.fetchone()[0]
            
            # Only clear predicted_name and prediction_confidence columns
            cursor.execute('''
                UPDATE faces 
                SET 
                    predicted_name = NULL,
                    prediction_confidence = NULL
                WHERE predicted_name IS NOT NULL
            ''')
            conn.commit()
            
            logging.info(f"Cleared {count_before} predictions while preserving names")
            return True
            
        except Exception as e:
            logging.error(f"Error clearing predictions: {e}")
            return False
        finally:
            conn.close()

    def record_no_face_image(self, image_path: Path) -> bool:
        """Record an image that contains no faces."""
        try:
            # Get or create image_id and store thumbnail
            image_id = self.get_or_create_image_id(image_path)
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE images 
                SET has_faces = FALSE
                WHERE image_id = ?
            ''', (image_id,))
            
            conn.commit()
            return True
            
        except Exception as e:
            logging.error(f"Error recording no-face image: {e}")
            return False
        finally:
            conn.close()

    def update_cluster_id(self, face_id: int, cluster_id: int) -> bool:
        """Update the cluster ID for a given face."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute(
                'UPDATE faces SET cluster_id = ? WHERE id = ?',
                (cluster_id, face_id)
            )
            
            conn.commit()
            return True
            
        except Exception as e:
            logging.error(f"Error updating cluster ID: {e}")
            return False
        finally:
            conn.close()

    def find_duplicate_filenames(self) -> dict:
        """Find files that exist in multiple folders."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Find filenames that appear in multiple folders
            cursor.execute('''
                WITH duplicates AS (
                    SELECT filename
                    FROM images
                    GROUP BY filename
                    HAVING COUNT(DISTINCT sub_folder) > 1
                )
                SELECT 
                    i.filename,
                    i.sub_folder,
                    COUNT(f.id) as face_count
                FROM images i
                LEFT JOIN faces f ON i.image_id = f.image_id
                INNER JOIN duplicates d ON i.filename = d.filename
                GROUP BY i.filename, i.sub_folder
                ORDER BY i.filename, i.sub_folder
            ''')
            
            results = cursor.fetchall()
            duplicates = {}
            
            for filename, folder, face_count in results:
                if filename not in duplicates:
                    duplicates[filename] = {}
                duplicates[filename][folder] = face_count
                
            return duplicates
            
        except Exception as e:
            logging.error(f"Error finding duplicates: {e}")
            return {}
        finally:
            conn.close()

    def get_database_statistics(self) -> dict:
        """Get various statistics about the database."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            stats = {}
            
            # Total faces
            cursor.execute('SELECT COUNT(*) FROM faces')
            stats['Total Faces'] = cursor.fetchone()[0]
            
            # Total unique filenames
            cursor.execute('SELECT COUNT(DISTINCT filename) FROM images')
            stats['Unique Files'] = cursor.fetchone()[0]
            
            # Total folders
            cursor.execute('SELECT COUNT(DISTINCT sub_folder) FROM images')
            stats['Source Folders'] = cursor.fetchone()[0]
            
            # Named faces
            cursor.execute('SELECT COUNT(*) FROM faces WHERE name IS NOT NULL AND name != ""')
            stats['Named Faces'] = cursor.fetchone()[0]
            
            # Unique names
            cursor.execute('SELECT COUNT(DISTINCT name) FROM faces WHERE name IS NOT NULL AND name != ""')
            stats['Unique Names'] = cursor.fetchone()[0]
            
            # Faces with predictions
            cursor.execute('SELECT COUNT(*) FROM faces WHERE predicted_name IS NOT NULL')
            stats['Faces with Predictions'] = cursor.fetchone()[0]
            
            # Faces in clusters
            cursor.execute('SELECT COUNT(*) FROM faces WHERE cluster_id IS NOT NULL')
            stats['Faces in Clusters'] = cursor.fetchone()[0]
            
            # Number of clusters
            cursor.execute('SELECT COUNT(DISTINCT cluster_id) FROM faces WHERE cluster_id IS NOT NULL')
            stats['Number of Clusters'] = cursor.fetchone()[0]
            
            # Images without faces
            cursor.execute('SELECT COUNT(*) FROM images WHERE has_faces = FALSE')
            stats['Images without Faces'] = cursor.fetchone()[0]
            
            # Duplicate files
            cursor.execute('''
                SELECT COUNT(*) FROM (
                    SELECT filename
                    FROM images
                    GROUP BY filename
                    HAVING COUNT(DISTINCT sub_folder) > 1
                )
            ''')
            stats['Files with Duplicates'] = cursor.fetchone()[0]
            
            return stats
            
        except Exception as e:
            logging.error(f"Error getting statistics: {e}")
            return {}
        finally:
            conn.close()

    def delete_faces(self, face_ids: List[int]) -> bool:
        """Delete faces from the database."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Delete the specified faces
            cursor.executemany(
                'DELETE FROM faces WHERE id = ?',
                [(face_id,) for face_id in face_ids]
            )
            
            conn.commit()
            logging.info(f"Deleted {len(face_ids)} faces from database")
            return True
            
        except Exception as e:
            logging.error(f"Error deleting faces: {e}")
            return False
        finally:
            conn.close()

    def get_faces_without_names_for_prediction(self) -> List[Tuple[int, bytes, str]]:
        """Get only faces without names for prediction."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT id, face_image, COALESCE(name, 'unknown') as name
                FROM faces 
                WHERE face_image IS NOT NULL
                AND (name IS NULL OR name = '')
                ORDER BY RANDOM()
            ''')
            
            faces = cursor.fetchall()
            if not faces:
                logging.warning("No unnamed faces found for prediction")
                return []
            
            logging.info(f"Found {len(faces)} unnamed faces for prediction")
            return faces
            
        except Exception as e:
            logging.error(f"Error getting unnamed faces for prediction: {e}")
            return []
        finally:
            conn.close()

    def clear_database(self) -> bool:
        """Clear all database files, including thumbnails and metadata."""
        logging.debug("Executing clear_database method")
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Clear all tables in correct order (respect foreign keys)
            cursor.execute('DELETE FROM image_metadata')  # Added this line
            cursor.execute('DELETE FROM faces')
            cursor.execute('DELETE FROM thumbnails')
            cursor.execute('DELETE FROM images')
            
            conn.commit()
            logging.info("Database cleared successfully (metadata, faces, thumbnails, and images)")
            return True
            
        except Exception as e:
            logging.error(f"Error clearing database: {e}")
            return False
        finally:
            conn.close()

    def save_image_metadata(self, image_id: int, metadata: dict) -> bool:
        """Save image metadata to database."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Clear existing metadata for this image
            cursor.execute('DELETE FROM image_metadata WHERE image_id = ?', (image_id,))
            
            # Insert new metadata
            for key, (value_type, value) in metadata.items():
                cursor.execute('''
                    INSERT INTO image_metadata (image_id, meta_key, meta_type, meta_value)
                    VALUES (?, ?, ?, ?)
                ''', (image_id, key, value_type, str(value)))
            
            conn.commit()
            return True
            
        except Exception as e:
            logging.error(f"Error saving metadata: {e}")
            return False
        finally:
            conn.close()

    def get_image_data(self, image_id):
        """Get full image data from thumbnails table"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT thumbnail FROM thumbnails WHERE image_id = ?", (image_id,))
            result = cursor.fetchone()
            if result:
                return result[0]
            # If not found in thumbnails, log warning
            logging.warning(f"No thumbnail found for image_id {image_id}")
            return None
        except Exception as e:
            logging.error(f"Error getting image data: {e}")
            return None
        finally:
            conn.close()

    def get_image_structure(self):
        """Get all images grouped by folders."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT base_folder, sub_folder, filename
                FROM images
                ORDER BY base_folder, sub_folder, filename
            ''')
            
            return cursor.fetchall()
            
        finally:
            conn.close()
            
    def get_images_in_folder(self, folder_path: Path):
        """Get all images in specific folder."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Split into base and sub folder
            if folder_path.parent.name:  # Is subfolder
                base_folder = str(folder_path.parent)
                sub_folder = folder_path.name
                
                cursor.execute('''
                    SELECT image_id, filename
                    FROM images
                    WHERE base_folder = ? AND sub_folder = ?
                    ORDER BY filename
                ''', (base_folder, sub_folder))
            else:  # Is base folder
                cursor.execute('''
                    SELECT image_id, filename
                    FROM images
                    WHERE base_folder = ?
                    ORDER BY sub_folder, filename
                ''', (str(folder_path),))
                
            return cursor.fetchall()
            
        finally:
            conn.close()