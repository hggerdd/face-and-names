import os
import sqlite3

# Create a temporary database
db_path = "reproduce_bug.db"
if os.path.exists(db_path):
    os.remove(db_path)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Create tables
cursor.execute("""
CREATE TABLE person (
    id INTEGER PRIMARY KEY,
    primary_name TEXT
)
""")

cursor.execute("""
CREATE TABLE import_session (
    id INTEGER PRIMARY KEY,
    import_date TEXT
)
""")

cursor.execute("""
CREATE TABLE image (
    id INTEGER PRIMARY KEY,
    import_id INTEGER,
    relative_path TEXT
)
""")

cursor.execute("""
CREATE TABLE face (
    id INTEGER PRIMARY KEY,
    image_id INTEGER,
    person_id INTEGER,
    prediction_confidence REAL,
    face_crop_blob BLOB,
    predicted_person_id INTEGER
)
""")

cursor.execute("""
CREATE TABLE metadata (
    image_id INTEGER,
    key TEXT,
    value TEXT
)
""")

# Insert test data
cursor.execute("INSERT INTO person (id, primary_name) VALUES (1, 'Test Person')")
cursor.execute("INSERT INTO import_session (id, import_date) VALUES (1, '2023-10-27 10:00:00')")
cursor.execute("INSERT INTO image (id, import_id, relative_path) VALUES (1, 1, 'test.jpg')")
cursor.execute("INSERT INTO face (id, image_id, person_id) VALUES (1, 1, 1)")
# Insert EXIF date with colons
cursor.execute(
    "INSERT INTO metadata (image_id, key, value) VALUES (1, 'DateTimeOriginal', '2023:10:27 12:34:56')"
)

conn.commit()

# Query with date filter (simulating the bug)
# The bug is that date() expects YYYY-MM-DD, but we have YYYY:MM:DD
# We want to filter for 2023-10-01 to 2023-10-31

img_alias = "i"
session_alias = "s"

shot_expr = f"""
    COALESCE(
        (
            SELECT value
            FROM metadata m2
            WHERE m2.image_id = {img_alias}.id
              AND m2.key IN ('DateTimeOriginal', 'DateTimeDigitized', 'DateTime', 'CreateDate')
            ORDER BY CASE m2.key
                WHEN 'DateTimeOriginal' THEN 1
                WHEN 'DateTimeDigitized' THEN 2
                WHEN 'DateTime' THEN 3
                WHEN 'CreateDate' THEN 4
                ELSE 5
            END
            LIMIT 1
        ),
        {session_alias}.import_date
    )
"""

# This is the fixed clause
date_clause = f"AND date(REPLACE(SUBSTR(COALESCE({shot_expr}, '1900-01-01'), 1, 10), ':', '-')) BETWEEN ? AND ?"

query = f"""
    SELECT f.id
    FROM face f
    JOIN image i ON i.id = f.image_id
    LEFT JOIN import_session s ON s.id = i.import_id
    WHERE f.person_id = ?
    {date_clause}
"""

params = [1, "2023-10-01", "2023-10-31"]

print(f"Querying with params: {params}")
rows = cursor.execute(query, params).fetchall()

print(f"Rows found: {len(rows)}")

if len(rows) == 1:
    print("SUCCESS: Fix verified, row found.")
else:
    print(f"FAILURE: Expected 1 row, found {len(rows)}.")

conn.close()
if os.path.exists(db_path):
    os.remove(db_path)
