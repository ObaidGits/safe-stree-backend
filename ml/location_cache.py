import sqlite3
import time
import os
from pathlib import Path

# Ensure cache directory exists
Path("data/cache").mkdir(parents=True, exist_ok=True)
DB_NAME = "data/cache/location_cache.db"
MAX_LOCATION_AGE_SECONDS = int(os.environ.get("LOCATION_CACHE_MAX_AGE_SECONDS", "300"))


def get_connection():
    return sqlite3.connect(DB_NAME, check_same_thread=False)


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS location (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            latitude REAL,
            longitude REAL,
            accuracy REAL,
            timestamp INTEGER
        )
    """)
    
    # Migration: Add timestamp column if it doesn't exist (for old databases)
    try:
        cur.execute("SELECT timestamp FROM location LIMIT 1")
    except sqlite3.OperationalError:
        print("[DB] Migrating database: adding timestamp column")
        cur.execute("ALTER TABLE location ADD COLUMN timestamp INTEGER")
        cur.execute("UPDATE location SET timestamp = ?" , (int(time.time()),))
        conn.commit()

    conn.commit()
    conn.close()


def save_location(lat, lon, acc=0):
    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute("DELETE FROM location")  # always store latest only
        cur.execute(
            "INSERT INTO location(latitude, longitude, accuracy, timestamp) VALUES(?,?,?,?)",
            (lat, lon, acc, int(time.time()))
        )

        conn.commit()
        conn.close()

        print(f"[DB] Location cached: {lat}, {lon}")

    except Exception as e:
        print(f"[DB ERROR] Failed to save location: {e}")


def get_last_location():
    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute("SELECT latitude, longitude, accuracy, timestamp FROM location ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()
        conn.close()

        if not row:
            print("[DB] No cached location found")
            return None

        timestamp = row[3] or 0
        if MAX_LOCATION_AGE_SECONDS > 0:
            age_seconds = int(time.time()) - int(timestamp)
            if age_seconds > MAX_LOCATION_AGE_SECONDS:
                print(f"[DB] Cached location is stale ({age_seconds}s old). Ignoring.")
                return None

        return {
            "latitude": row[0],
            "longitude": row[1],
            "accuracy": row[2]
        }

    except Exception as e:
        print(f"[DB ERROR] Failed to read location: {e}")
        return None
