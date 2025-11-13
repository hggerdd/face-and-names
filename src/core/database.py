from contextlib import contextmanager
import sqlite3
from pathlib import Path
import logging
from typing import List, Tuple, Optional, Generator
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
        
    @contextmanager
    def get_connection(self) -> Generator[tuple[sqlite3.Connection, sqlite3.Cursor], None, None]:
        """Context manager for database connections."""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute('PRAGMA foreign_keys = ON')  # Enable foreign key support
            cursor = conn.cursor()
            yield conn, cursor
        except Exception as e:
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                conn.close()

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Cursor, None, None]:
        """Context manager for database transactions.
        
        Usage:
            with self.transaction() as cursor:
                cursor.execute(...)

                # Auto-commits if no exception, rolls back if exception occurs
        """
        with self.get_connection() as (conn, cursor):
            try:
                yield cursor
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def _get_image_location(self, image_path: Path) -> tuple[str, str, str]:
        """Extract standardized location components from an image path."""
        return (
            str(image_path.parent.parent),  # base_folder
            image_path.parent.name,         # sub_folder
            image_path.name                 # filename
        )

    def _save_thumbnail(self, cursor: sqlite3.Cursor, image_id: int, image_data: np.ndarray) -> bool:
        """Save thumbnail for an image."""
        try:
            if image_data is None:
                return False
                
            thumbnail_data = create_thumbnail(image_data)
            if not thumbnail_data:
                logging.error(f"Failed to create thumbnail for image {image_id}")
                return False

            cursor.execute('''
                INSERT OR REPLACE INTO thumbnails (image_id, thumbnail)
                VALUES (?, ?)
            ''', (image_id, thumbnail_data))
            
            logging.debug(f"Saved thumbnail for image {image_id} ({len(thumbnail_data)} bytes)")
            return True
            
        except Exception as e:
            logging.error(f"Error saving thumbnail: {e}")
            return False

    def get_or_create_image_id(self, image_path: Path, image_data: np.ndarray = None, import_id: int = None) -> Optional[int]:
        """Get existing image ID or create new entry with thumbnail."""
        try:
            base_folder, sub_folder, filename = self._get_image_location(image_path)
            
            with self.transaction() as cursor:
                # Try to find existing image
                cursor.execute('''
                    SELECT image_id, 
                           (SELECT 1 FROM thumbnails WHERE image_id = images.image_id) as has_thumbnail
                    FROM images 
                    WHERE base_folder = ? AND sub_folder = ? AND filename = ?
                ''', (base_folder, sub_folder, filename))
                
                result = cursor.fetchone()
                
                if result:
                    image_id, has_thumbnail = result
                    if not has_thumbnail and image_data is not None:
                        self._save_thumbnail(cursor, image_id, image_data)
                    return image_id
                
                # Create new image entry
                cursor.execute('''
                    INSERT INTO images (base_folder, sub_folder, filename, has_faces, import_id)
                    VALUES (?, ?, ?, ?, ?)
                ''', (base_folder, sub_folder, filename, False, import_id))
                
                image_id = cursor.lastrowid
                
                if image_data is not None:
                    self._save_thumbnail(cursor, image_id, image_data)
                
                return image_id
                
        except Exception as e:
            logging.error(f"Error in get_or_create_image_id: {e}")
            return None

    def save_faces_with_predictions(self, faces: List[DetectedFace]) -> bool:
        """Save detected faces to database with predictions and bounding boxes."""
        if not faces:
            return False
            
        try:
            with self.transaction() as cursor:
                for face in faces:
                    try:
                        image_id = self.get_or_create_image_id(face.original_file)
                        if image_id is None:
                            continue
                            
                        # Convert face image to bytes
                        _, img_encoded = cv2.imencode('.jpg', face.face_image)
                        if img_encoded is None:
                            logging.error("Failed to encode face image")
                            continue
                            
                        img_bytes = img_encoded.tobytes()
                        
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
                            face.bbox_relative[0],
                            face.bbox_relative[1],
                            face.bbox_relative[2],
                            face.bbox_relative[3]
                        ))
                        
                        # Update has_faces flag
                        cursor.execute('''
                            UPDATE images SET has_faces = TRUE
                            WHERE image_id = ?
                        ''', (image_id,))
                        
                    except Exception as e:
                        logging.error(f"Error saving face: {e}")
                        continue
                        
                return True
                
        except Exception as e:
            logging.error(f"Error in save_faces_with_predictions: {e}")
            return False

    def get_faces_query(self, conditions: str = "", params: tuple = ()) -> List[tuple]:
        """Generic method for retrieving faces with specified conditions."""
        try:
            with self.get_connection() as (_, cursor):
                query = f'''
                    SELECT id, face_image, COALESCE(name, 'unknown') as name 
                    FROM faces 
                    WHERE face_image IS NOT NULL
                    {conditions}
                '''
                cursor.execute(query, params)
                faces = cursor.fetchall()
                
                if not faces:
                    logging.warning(f"No faces found matching conditions: {conditions}")
                    return []
                    
                logging.info(f"Found {len(faces)} faces matching conditions: {conditions}")
                return faces
                
        except Exception as e:
            logging.error(f"Error getting faces: {e}")
            return []

    def get_faces_for_clustering(self, latest_import_only: bool = False, selected_folders: List[Tuple[str, str]] = None) -> List[Tuple[int, bytes]]:
        """Get faces without names for clustering.
        Args:
            latest_import_only: If True, only return faces from the latest import
            selected_folders: List of (base_folder, sub_folder) tuples to filter by
        """
        try:
            query_parts = []
            params = []
            
            if latest_import_only:
                # First get the latest import_id
                with self.get_connection() as (_, cursor):
                    cursor.execute('SELECT MAX(import_id) FROM imports')
                    latest_import = cursor.fetchone()[0]
                    if latest_import is not None:
                        query_parts.append("i.import_id = ?")
                        params.append(latest_import)

            if selected_folders:
                # Build folder filter condition
                folder_conditions = []
                for base_folder, sub_folder in selected_folders:
                    folder_conditions.append("(i.base_folder = ? AND i.sub_folder = ?)")
                    params.extend([base_folder, sub_folder])
                if folder_conditions:
                    query_parts.append(f"({' OR '.join(folder_conditions)})")

            base_query = '''
                SELECT f.id, f.face_image 
                FROM faces f
                JOIN images i ON f.image_id = i.image_id
                WHERE (f.name IS NULL OR f.name = '')
                AND f.face_image IS NOT NULL
            '''
            
            if query_parts:
                base_query += " AND " + " AND ".join(query_parts)
                
            base_query += " ORDER BY f.id"
            
            with self.get_connection() as (_, cursor):
                cursor.execute(base_query, params)
                faces = cursor.fetchall()
                logging.info(f"Retrieved {len(faces)} faces for clustering{' (latest import only)' if latest_import_only else ''}{' (folder filtered)' if selected_folders else ''}")
                return faces
                
        except Exception as e:
            logging.error(f"Error getting faces for clustering: {e}")
            return []

    def get_faces_for_prediction(self) -> List[Tuple[int, bytes, str]]:
        """Get all faces for prediction testing."""
        return self.get_faces_query(
            "ORDER BY RANDOM()",
            ()
        )

    def get_faces_without_names_for_prediction(self) -> List[Tuple[int, bytes, str]]:
        """Get only faces without names for prediction."""
        return self.get_faces_query(
            " AND (name IS NULL OR name = '') ORDER BY RANDOM()",
            ()
        )

    def get_faces_for_training(self) -> List[Tuple[int, bytes, str]]:
        """Get faces with assigned names for training."""
        try:
            with self.transaction() as cursor:
                cursor.execute('''
                    SELECT id, face_image, name 
                    FROM faces 
                    WHERE face_image IS NOT NULL
                    AND name IS NOT NULL
                    AND name != ''
                    AND name != 'unknown'
                    ORDER BY name, id
                ''')
                faces = cursor.fetchall()
                
                if not faces:
                    logging.warning("No named faces found for training")
                    return []

                # Log statistics
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
                logging.info("Found faces for training:")
                for name, count in name_counts:
                    logging.info(f"  {name}: {count} images")
                
                logging.info(f"Total: {len(faces)} faces for {len(name_counts)} people")
                return faces
                
        except Exception as e:
            logging.error(f"Error getting faces for training: {e}")
            return []

    def _update_face_names(self, cursor: sqlite3.Cursor, updates: List[tuple]) -> int:
        """Update names for faces and clear their cluster IDs."""
        cursor.executemany(
            'UPDATE faces SET name = ?, cluster_id = NULL WHERE id = ?',
            updates
        )
        return cursor.rowcount

    def _clear_face_predictions(self, cursor: sqlite3.Cursor) -> int:
        """Clear predictions from faces table."""
        cursor.execute('''
            UPDATE faces 
            SET predicted_name = NULL,
                prediction_confidence = NULL
            WHERE predicted_name IS NOT NULL
        ''')
        return cursor.rowcount

    def save_clustering_results(self, result: 'ClusteringResult') -> bool:
        """Save clustering results to database."""
        try:
            with self.transaction() as cursor:
                # First reset all cluster IDs
                cursor.execute('UPDATE faces SET cluster_id = NULL')
                
                # Then update with new cluster IDs
                cursor.executemany(
                    'UPDATE faces SET cluster_id = ? WHERE id = ?',
                    zip(result.labels, result.face_ids)
                )
                
                logging.info(f"Saved clustering results: {result.n_clusters} clusters")
                return True
                
        except Exception as e:
            logging.error(f"Error saving clustering results: {e}")
            return False

    def get_face_clusters(self) -> dict:
        """Get all faces grouped by cluster.
        Each face tuple contains: (face_id, face_image, name, predicted_name, image_id)
        """
        try:
            with self.get_connection() as (_, cursor):
                cursor.execute('''
                    SELECT id, face_image, name, predicted_name, image_id, cluster_id 
                    FROM faces 
                    WHERE cluster_id IS NOT NULL
                    ORDER BY cluster_id, id
                ''')
                
                clusters = {}
                for row in cursor.fetchall():
                    cluster_id = row[5]
                    face_tuple = row[:5]  # (face_id, face_image, name, predicted_name, image_id)
                    if cluster_id not in clusters:
                        clusters[cluster_id] = []
                    clusters[cluster_id].append(face_tuple)
                
                return clusters
                
        except Exception as e:
            logging.error(f"Error getting face clusters: {e}")
            return {}

    def update_person_name(self, old_name: str, new_name: str) -> bool:
        """Update all faces with a specific name to have a new name."""
        try:
            with self.transaction() as cursor:
                cursor.execute('''
                    UPDATE faces 
                    SET name = ?
                    WHERE name = ?
                ''', (new_name, old_name))
                
                updated_count = cursor.rowcount
                logging.info(f"Updated {updated_count} faces from '{old_name}' to '{new_name}'")
                return True
                
        except Exception as e:
            logging.error(f"Error updating person name: {e}")
            return False

    def clear_predictions_only(self) -> bool:
        """Clear only predicted_name and prediction_confidence, preserving the name column."""
        try:
            with self.transaction() as cursor:
                # Get count before clearing
                cursor.execute('SELECT COUNT(*) FROM faces WHERE predicted_name IS NOT NULL')
                count_before = cursor.fetchone()[0]
                
                cleared_count = self._clear_face_predictions(cursor)
                logging.info(f"Cleared {cleared_count} predictions while preserving names")
                return True
                
        except Exception as e:
            logging.error(f"Error clearing predictions: {e}")
            return False

    def save_image_metadata(self, image_id: int, metadata: dict) -> bool:
        """Save image metadata to database."""
        try:
            with self.transaction() as cursor:
                # Clear existing metadata for this image
                cursor.execute('DELETE FROM image_metadata WHERE image_id = ?', (image_id,))
                
                # Insert new metadata
                cursor.executemany(
                    '''INSERT INTO image_metadata (image_id, meta_key, meta_type, meta_value)
                       VALUES (?, ?, ?, ?)''',
                    [(image_id, key, value_type, str(value)) 
                     for key, (value_type, value) in metadata.items()]
                )
                return True
                
        except Exception as e:
            logging.error(f"Error saving metadata: {e}")
            return False

    def get_database_statistics(self) -> dict:
        """Get various statistics about the database."""
        try:
            with self.get_connection() as (_, cursor):
                stats = {}
                
                # Define statistics queries
                queries = {
                    'Total Faces': 'SELECT COUNT(*) FROM faces',
                    'Unique Files': 'SELECT COUNT(DISTINCT filename) FROM images',
                    'Source Folders': 'SELECT COUNT(DISTINCT sub_folder) FROM images',
                    'Named Faces': 'SELECT COUNT(*) FROM faces WHERE name IS NOT NULL AND name != ""',
                    'Unique Names': 'SELECT COUNT(DISTINCT name) FROM faces WHERE name IS NOT NULL AND name != ""',
                    'Faces with Predictions': 'SELECT COUNT(*) FROM faces WHERE predicted_name IS NOT NULL',
                    'Faces in Clusters': 'SELECT COUNT(*) FROM faces WHERE cluster_id IS NOT NULL',
                    'Number of Clusters': 'SELECT COUNT(DISTINCT cluster_id) FROM faces WHERE cluster_id IS NOT NULL',
                    'Images without Faces': 'SELECT COUNT(*) FROM images WHERE has_faces = FALSE',
                    'Files with Duplicates': '''
                        SELECT COUNT(*) FROM (
                            SELECT filename
                            FROM images
                            GROUP BY filename
                            HAVING COUNT(DISTINCT sub_folder) > 1
                        )
                    '''
                }
                
                # Execute all queries
                for stat_name, query in queries.items():
                    cursor.execute(query)
                    stats[stat_name] = cursor.fetchone()[0]
                
                return stats
                
        except Exception as e:
            logging.error(f"Error getting statistics: {e}")
            return {}

    def clear_database(self) -> bool:
        """Clear all database files, including thumbnails and metadata."""
        try:
            with self.transaction() as cursor:
                # Clear all tables in correct order (respect foreign keys)
                tables = ['image_metadata', 'faces', 'thumbnails', 'images']
                for table in tables:
                    cursor.execute(f'DELETE FROM {table}')
                    
                logging.info("Database cleared successfully (metadata, faces, thumbnails, and images)")
                return True
                
        except Exception as e:
            logging.error(f"Error clearing database: {e}")
            return False

    def initialize_database(self):
        """Initialize database with required tables and indexes."""
        with self.transaction() as cursor:
            # First check if import_id column exists in images table
            cursor.execute("PRAGMA table_info(images)")
            columns = [col[1] for col in cursor.fetchall()]
            has_import_id = 'import_id' in columns

            # Create imports history table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS imports (
                    import_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    import_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    folder_count INTEGER,
                    image_count INTEGER
                )
            ''')

            # For existing databases, create images table with base columns
            if not has_import_id:
                # Create basic images table if not exists
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
                
                # Then add import_id column to existing table
                try:
                    cursor.execute('ALTER TABLE images ADD COLUMN import_id INTEGER REFERENCES imports(import_id)')
                    logging.info("Added import_id column to images table")
                except Exception as e:
                    if 'duplicate column name' not in str(e).lower():
                        raise
            else:
                # For new databases, create complete images table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS images (
                        image_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        base_folder TEXT,
                        sub_folder TEXT,
                        filename TEXT,
                        processed_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        has_faces BOOLEAN,
                        import_id INTEGER,
                        UNIQUE(base_folder, sub_folder, filename),
                        FOREIGN KEY (import_id) REFERENCES imports(import_id)
                    )
                ''')

            # Create remaining tables
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS thumbnails (
                    image_id INTEGER PRIMARY KEY,
                    thumbnail BLOB NOT NULL,
                    FOREIGN KEY (image_id) REFERENCES images(image_id)
                    ON DELETE CASCADE
                )
            ''')
            
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
            
            # Create indexes
            # Add index for import_id
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_images_import ON images(import_id)')
            
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_metadata_sorted ON image_metadata(image_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_metadata_image_id ON image_metadata(image_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_metadata_key ON image_metadata(meta_key)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_faces_name ON faces(name)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_faces_image_id ON faces(image_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_faces_cluster ON faces(cluster_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_images_path ON images(base_folder, sub_folder, filename)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_thumbnails_image_id ON thumbnails(image_id)')
            
            logging.info("Database initialized successfully")

    def start_new_import(self, folder_count: int) -> int:
        """Start a new import session and return its ID.
        
        Args:
            folder_count: Number of folders being processed
            
        Returns:
            int: The new import ID
        """
        try:
            with self.transaction() as cursor:
                cursor.execute('''
                    INSERT INTO imports (folder_count, image_count)
                    VALUES (?, 0)
                ''', (folder_count,))
                import_id = cursor.lastrowid
                logging.info(f"Started new import session with ID: {import_id}")
                return import_id
        except Exception as e:
            logging.error(f"Error starting new import: {e}")
            return None

    def update_import_image_count(self, import_id: int, image_count: int) -> bool:
        """Update the image count for an import session.
        
        Args:
            import_id: The import session ID
            image_count: Total number of images processed
            
        Returns:
            bool: True if successful
        """
        try:
            with self.transaction() as cursor:
                cursor.execute('''
                    UPDATE imports 
                    SET image_count = ?
                    WHERE import_id = ?
                ''', (image_count, import_id))
                return True
        except Exception as e:
            logging.error(f"Error updating import image count: {e}")
            return False

    def get_image_data(self, image_id: int) -> Optional[bytes]:
        """Get full image data from thumbnails table"""
        try:
            with self.get_connection() as (_, cursor):
                cursor.execute("SELECT thumbnail FROM thumbnails WHERE image_id = ?", (image_id,))
                result = cursor.fetchone()
                if not result:
                    logging.warning(f"No thumbnail found for image_id {image_id}")
                    return None
                return result[0]
        except Exception as e:
            logging.error(f"Error getting image data: {e}")
            return None

    def get_image_structure(self) -> List[Tuple[str, str, str]]:
        """Get all images grouped by folders."""
        try:
            with self.get_connection() as (_, cursor):
                cursor.execute('''
                    SELECT base_folder, sub_folder, filename
                    FROM images
                    ORDER BY base_folder, sub_folder, filename
                ''')
                return cursor.fetchall()
        except Exception as e:
            logging.error(f"Error getting image structure: {e}")
            return []

    def get_images_in_folder(self, folder_path: Path) -> List[Tuple[int, str]]:
        """Get all images in specific folder."""
        try:
            with self.get_connection() as (_, cursor):
                if folder_path.parent.name:  # Is subfolder
                    cursor.execute('''
                        SELECT image_id, filename
                        FROM images
                        WHERE base_folder = ? AND sub_folder = ?
                        ORDER BY filename
                    ''', (str(folder_path.parent), folder_path.name))
                else:  # Is base folder
                    cursor.execute('''
                        SELECT image_id, filename
                        FROM images
                        WHERE base_folder = ?
                        ORDER BY sub_folder, filename
                    ''', (str(folder_path),))
                return cursor.fetchall()
        except Exception as e:
            logging.error(f"Error getting images in folder: {e}")
            return []

    def get_faces_by_name(self, name: str) -> List[Tuple[int, bytes, int]]:
        """Get all faces for a given name, returning (face_id, face_image, image_id)."""
        try:
            with self.get_connection() as (_, cursor):
                cursor.execute('''
                    SELECT id, face_image, image_id
                    FROM faces 
                    WHERE name = ? AND face_image IS NOT NULL
                    ORDER BY id
                ''', (name,))
                faces = cursor.fetchall()
                logging.info(f"Found {len(faces)} faces for name '{name}'")
                return faces
        except Exception as e:
            logging.error(f"Error getting faces by name: {e}")
            return []

    def record_no_face_image(self, image_path: Path) -> bool:
        """Record an image that contains no faces."""
        try:
            with self.transaction() as cursor:
                image_id = self.get_or_create_image_id(image_path)
                if image_id is None:
                    return False
                    
                cursor.execute('''
                    UPDATE images 
                    SET has_faces = FALSE
                    WHERE image_id = ?
                ''', (image_id,))
                return True
        except Exception as e:
            logging.error(f"Error recording no-face image: {e}")
            return False

    def get_thumbnail(self, image_id: int) -> Optional[bytes]:
        """Retrieve thumbnail for an image."""
        try:
            with self.get_connection() as (_, cursor):
                cursor.execute('SELECT thumbnail FROM thumbnails WHERE image_id = ?', (image_id,))
                result = cursor.fetchone()
                return result[0] if result else None
        except Exception as e:
            logging.error(f"Error retrieving thumbnail: {e}")
            return None

    def is_image_processed(self, image_path: Path) -> bool:
        """Check if an image has already been processed."""
        try:
            base_folder, sub_folder, filename = self._get_image_location(image_path)
            with self.get_connection() as (_, cursor):
                cursor.execute('''
                    SELECT image_id FROM images 
                    WHERE base_folder = ? AND sub_folder = ? AND filename = ?
                ''', (base_folder, sub_folder, filename))
                return cursor.fetchone() is not None
        except Exception as e:
            logging.error(f"Error checking if image is processed: {e}")
            return False

    def get_faces_with_predictions(self) -> List[Tuple[int, bytes, str, str, float, int]]:
        """Get faces with predictions including image_id"""
        try:
            with self.get_connection() as (_, cursor):
                cursor.execute("""
                    SELECT f.id, f.face_image, f.name, f.predicted_name, 
                           f.prediction_confidence, f.image_id
                    FROM faces f
                    WHERE f.face_image IS NOT NULL
                    AND f.predicted_name IS NOT NULL
                    ORDER BY f.prediction_confidence DESC NULLS LAST
                """)
                return cursor.fetchall()
        except Exception as e:
            logging.error(f"Error getting faces with predictions: {e}")
            return []

    def update_face_name(self, face_id: int, name: str) -> bool:
        """Update name for a single face and clear its cluster_id."""
        try:
            with self.transaction() as cursor:
                cursor.execute(
                    'UPDATE faces SET name = ?, cluster_id = NULL WHERE id = ?',
                    (name, face_id)
                )
                return True
        except Exception as e:
            logging.error(f"Error updating face name: {e}")
            return False

    def get_existing_names(self) -> set:
        """Get all unique names from the database."""
        try:
            with self.get_connection() as (_, cursor):
                cursor.execute('''
                    SELECT DISTINCT name 
                    FROM faces 
                    WHERE name IS NOT NULL
                    ORDER BY name
                ''')
                return {row[0] for row in cursor.fetchall()}
        except Exception as e:
            logging.error(f"Error getting existing names: {e}")
            return set()

    def get_unique_names(self) -> List[str]:
        """Get all unique names from faces table (excluding predicted names)."""
        try:
            with self.get_connection() as (_, cursor):
                cursor.execute("""
                    SELECT DISTINCT name 
                    FROM faces 
                    WHERE name IS NOT NULL AND name != '' 
                    ORDER BY name
                """)
                names = [row[0] for row in cursor.fetchall()]
                logging.debug(f"Retrieved {len(names)} unique names from database")
                return names
        except Exception as e:
            logging.error(f"Error getting unique names: {e}")
            return []

    def update_cluster_id(self, face_id: int, cluster_id: int) -> bool:
        """Update the cluster ID for a given face."""
        try:
            with self.transaction() as cursor:
                cursor.execute(
                    'UPDATE faces SET cluster_id = ? WHERE id = ?',
                    (cluster_id, face_id)
                )
                return True
        except Exception as e:
            logging.error(f"Error updating cluster ID: {e}")
            return False

    def get_face_dates_by_name(self, name: str) -> List[str]:
        """Get EXIF dates of images containing faces for a given name."""
        try:
            with self.get_connection() as (_, cursor):
                cursor.execute('''
                    SELECT DISTINCT m.meta_value
                    FROM faces f
                    JOIN images i ON f.image_id = i.image_id
                    LEFT JOIN image_metadata m ON i.image_id = m.image_id
                    WHERE f.name = ?
                    AND m.meta_key = 'EXIF_DateTime'
                    ORDER BY m.meta_value
                ''', (name,))
                return [row[0] for row in cursor.fetchall()]
        except Exception as e:
            logging.error(f"Error getting face dates: {e}")
            return []

    def find_duplicate_filenames(self) -> dict:
        """Find files that exist in multiple folders.
        
        Returns:
            dict: A dictionary where keys are filenames and values are dictionaries
                 mapping folders to face counts for that file in that folder.
        """
        try:
            with self.get_connection() as (_, cursor):
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
                
                logging.info(f"Found {len(duplicates)} files with duplicates")
                return duplicates
                
        except Exception as e:
            logging.error(f"Error finding duplicates: {e}")
            return {}
    
    def update_face_names(self, updates: List[tuple]) -> bool:
        """Update names for multiple faces at once.
        
        Args:
            updates: List of tuples (name, face_id) to update
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            with self.transaction() as cursor:
                updated_count = self._update_face_names(cursor, updates)
                logging.info(f"Updated {updated_count} face names")
                return True
        except Exception as e:
            logging.error(f"Error updating face names: {e}")
            return False

    def delete_faces(self, face_ids: List[int]) -> bool:
        """Delete faces from the database by their IDs."""
        try:
            logging.debug(f"Starting face deletion for IDs: {face_ids}")
            with self.transaction() as cursor:
                # First verify the faces exist
                face_id_list = ','.join('?' * len(face_ids))
                cursor.execute(f'SELECT COUNT(*) FROM faces WHERE id IN ({face_id_list})', face_ids)
                count = cursor.fetchone()[0]
                logging.debug(f"Found {count} faces to delete out of {len(face_ids)} requested")

                # Delete faces
                cursor.executemany(
                    'DELETE FROM faces WHERE id = ?',
                    [(face_id,) for face_id in face_ids]
                )
                deleted_count = cursor.rowcount
                logging.debug(f"Successfully deleted {deleted_count} faces")
                return deleted_count > 0
        except Exception as e:
            logging.error(f"Error deleting faces: {e}")
            return False

    def save_prediction_result(self, face_id: int, predicted_name: str, confidence: float) -> bool:
        """Save prediction result for a face.
        
        Args:
            face_id: ID of the face to update
            predicted_name: Predicted name
            confidence: Prediction confidence score
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            with self.transaction() as cursor:
                cursor.execute('''
                    UPDATE faces 
                    SET predicted_name = ?,
                        prediction_confidence = ?
                    WHERE id = ?
                ''', (predicted_name, confidence, face_id))
                return True
        except Exception as e:
            logging.error(f"Error saving prediction result: {e}")
            return False

    def clear_cluster_assignments(self) -> bool:
        """Clear all cluster assignments from faces."""
        try:
            with self.transaction() as cursor:
                cursor.execute('UPDATE faces SET cluster_id = NULL')
            return True
        except Exception as e:
            logging.error(f"Error clearing cluster assignments: {e}")
            return False

    def search_images_by_people(self, names: List[str], match_all: bool = False) -> List[Tuple[int, bytes, List[str]]]:
        """Search for images containing specific people.
        
        Args:
            names: List of names to search for
            match_all: If True, return only images containing all specified people
                      If False, return images containing any of the specified people
        
        Returns:
            List of tuples (image_id, thumbnail_data, list_of_names_in_image)
        """
        try:
            if not names:
                return []

            with self.get_connection() as (_, cursor):
                # Build query based on match type
                if match_all:
                    # For match_all, we need a subquery that counts matches
                    query = '''
                        WITH image_matches AS (
                            SELECT i.image_id, i.filename, 
                                   COUNT(DISTINCT f.name) as name_matches,
                                   GROUP_CONCAT(DISTINCT f.name) as names_in_image
                            FROM images i
                            JOIN faces f ON i.image_id = f.image_id
                            WHERE f.name IN ({})
                            GROUP BY i.image_id
                            HAVING name_matches = ?
                        )
                        SELECT m.image_id, t.thumbnail, m.names_in_image
                        FROM image_matches m
                        JOIN thumbnails t ON m.image_id = t.image_id
                        ORDER BY m.image_id
                    '''.format(','.join('?' * len(names)))
                    params = [*names, len(names)]
                else:
                    # For match_any, a simple WHERE IN clause
                    query = '''
                        SELECT DISTINCT i.image_id, t.thumbnail,
                               (SELECT GROUP_CONCAT(DISTINCT name)
                                FROM faces
                                WHERE image_id = i.image_id
                                AND name IN ({})) as names_in_image
                        FROM images i
                        JOIN faces f ON i.image_id = f.image_id
                        JOIN thumbnails t ON i.image_id = t.image_id
                        WHERE f.name IN ({})
                        ORDER BY i.image_id
                    '''.format(','.join('?' * len(names)), 
                             ','.join('?' * len(names)))
                    params = names + names

                cursor.execute(query, params)
                results = cursor.fetchall()
                
                # Convert results to the expected format
                processed_results = []
                for image_id, thumbnail, names_str in results:
                    names_in_image = names_str.split(',') if names_str else []
                    processed_results.append((image_id, thumbnail, names_in_image))

                logging.info(f"Found {len(processed_results)} images matching search criteria")
                return processed_results

        except Exception as e:
            logging.error(f"Error searching images by people: {e}")
            return []