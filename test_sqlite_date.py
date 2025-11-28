import sqlite3

conn = sqlite3.connect(":memory:")
cursor = conn.cursor()

dates = ["2023:10:27 12:34:56", "2023-10-27 12:34:56", "2023-10-27 12-34-56", "2023-10-27"]

print("Testing SQLite date() function:")
for d in dates:
    try:
        # Test simple replace
        replaced = d.replace(":", "-")

        # Test SQL query
        query = f"SELECT date('{replaced}')"
        result = cursor.execute(query).fetchone()[0]
        print(f"Original: '{d}' -> Replaced: '{replaced}' -> Result: {result}")
    except Exception as e:
        print(f"Original: '{d}' -> Replaced: '{replaced}' -> Error: {e}")

# Test substr approach
print("\nTesting substr approach:")
for d in dates:
    try:
        query = f"SELECT date(replace(substr('{d}', 1, 10), ':', '-'))"
        result = cursor.execute(query).fetchone()[0]
        print(f"Original: '{d}' -> Result: {result}")
    except Exception as e:
        print(f"Original: '{d}' -> Error: {e}")

conn.close()
