import os, sqlite3, json, numpy as np

# ─── Database Path (Handles Persistent Storage Automatically) ──
# Hugging Face provides persistent storage at /data if enabled in settings.
# This approach works both locally (ephemeral) and on HF (persistent).
DATA_DIR = "/data"
if os.path.isdir(DATA_DIR) and os.access(DATA_DIR, os.W_OK):
    DB = os.path.join(DATA_DIR, "attendance.db")
    STORAGE_MODE = "Persistent (Hugging Face)"
else:
    DB = "attendance.db"
    STORAGE_MODE = "Ephemeral (Local/Container)"

print(f"[DB] Storage Mode: {STORAGE_MODE}")
print(f"[DB] Current Path: {DB}")
# ──────────────────────────────────────────────────────────────




def init_db():
    os.makedirs(os.path.dirname(DB) or ".", exist_ok=True)
    conn = sqlite3.connect(DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            name     TEXT,
            rfid     TEXT,
            encoding TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            name      TEXT,
            rfid      TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def save_user(name, rfid, encoding):
    conn = sqlite3.connect(DB)
    conn.execute(
        "INSERT INTO users (name, rfid, encoding) VALUES (?, ?, ?)",
        (name, rfid, json.dumps(encoding.tolist()))
    )
    conn.commit()
    conn.close()


def get_all_users():
    conn = sqlite3.connect(DB)
    rows = conn.execute("SELECT name, rfid, encoding FROM users").fetchall()
    conn.close()
    return [(r[0], r[1], np.array(json.loads(r[2]))) for r in rows]


def get_all_user_names():
    conn = sqlite3.connect(DB)
    rows = conn.execute("SELECT id, name, rfid FROM users").fetchall()
    conn.close()
    return [{"id": r[0], "name": r[1], "rfid": r[2]} for r in rows]


def delete_user_by_name(name):
    conn = sqlite3.connect(DB)
    cursor = conn.execute("DELETE FROM users WHERE name = ?", (name,))
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    return deleted


def delete_user_by_id(user_id):
    conn = sqlite3.connect(DB)
    cursor = conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    return deleted


def delete_all_users():
    conn = sqlite3.connect(DB)
    conn.execute("DELETE FROM users")
    conn.commit()
    conn.close()


def log_attendance(name, rfid):
    conn = sqlite3.connect(DB)
    conn.execute(
        "INSERT INTO attendance (name, rfid) VALUES (?, ?)",
        (name, rfid)
    )
    conn.commit()
    conn.close()


def get_attendance():
    conn = sqlite3.connect(DB)
    rows = conn.execute(
        "SELECT name, rfid, timestamp FROM attendance ORDER BY timestamp DESC LIMIT 50"
    ).fetchall()
    conn.close()
    return [{"name": r[0], "rfid": r[1], "time": r[2]} for r in rows]


def delete_all_attendance():
    conn = sqlite3.connect(DB)
    conn.execute("DELETE FROM attendance")
    conn.commit()
    conn.close()