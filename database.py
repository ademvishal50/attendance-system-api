import os, sqlite3, json, numpy as np, time

# Try to import libsql for Turso support
try:
    import libsql
    HAS_LIBSQL = True
except ImportError:
    HAS_LIBSQL = False

# ─── Turso Configuration ───────────────────────────────────
TURSO_URL = os.environ.get("TURSO_URL")
TURSO_TOKEN = os.environ.get("TURSO_TOKEN")
USE_TURSO = bool(TURSO_URL and TURSO_TOKEN and HAS_LIBSQL)

# ─── Local Database Path (Fallback/Ephemeral) ──────────────
DATA_DIR = "/data"
if os.path.exists(DATA_DIR) and os.access(DATA_DIR, os.W_OK):
    DB = os.path.join(DATA_DIR, "attendance.db")
    STORAGE_MODE = "Persistent (Hugging Face /data)"
else:
    DB = "attendance.db"
    STORAGE_MODE = "Ephemeral (Local/Container)"

if USE_TURSO:
    STORAGE_MODE = "Turso Remote (Distributed)"
    DB_DISPLAY = TURSO_URL
else:
    DB_DISPLAY = DB

print(f"[DB] Initial Storage Mode: {STORAGE_MODE}")
print(f"[DB] Database Target: {DB_DISPLAY}")
# ──────────────────────────────────────────────────────────────

def get_db_conn():
    """Helper to get either a Turso or SQLite connection."""
    if USE_TURSO:
        return libsql.connect(TURSO_URL, auth_token=TURSO_TOKEN)
    return sqlite3.connect(DB)


def init_db():
    global DB, STORAGE_MODE
    # Sometimes it takes a moment for the HF volume to be fully ready
    if DB.startswith("/data"):
        time.sleep(2) 
        
    try:
        # Create directory for local DB if it doesn't exist
        if not USE_TURSO:
            dir_name = os.path.dirname(DB)
            if dir_name and not os.path.exists(dir_name):
                os.makedirs(dir_name, exist_ok=True)
            
        print(f"[DB] Attempting to initialize at: {DB_DISPLAY}...")
        conn = get_db_conn()
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
                status    TEXT DEFAULT 'present',
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Migration: add status column if it doesn't exist yet (for older DBs)
        try:
            conn.execute("ALTER TABLE attendance ADD COLUMN status TEXT DEFAULT 'present'")
        except Exception:
            pass  # Column already exists, ignore
        conn.commit()
        conn.close()
        print(f"[DB] Successfully initialized database.")
    except Exception as e:
        print(f"[ERROR] Could not initialize database at {DB_DISPLAY}: {e}")
        if not USE_TURSO and DB.startswith("/data"):
            print(f"[FALLBACK] Switching to ephemeral storage in the local folder.")
            DB = "attendance.db"
            STORAGE_MODE = "Ephemeral (Fallback due to error)"
            init_db() # Recursively initialize locally
        else:
            print("[FATAL] Local database initialization also failed.")
            raise e



def save_user(name, rfid, encoding):
    conn = get_db_conn()
    conn.execute(
        "INSERT INTO users (name, rfid, encoding) VALUES (?, ?, ?)",
        (name, rfid, json.dumps(encoding.tolist()))
    )
    conn.commit()
    conn.close()


def get_all_users():
    conn = get_db_conn()
    rows = conn.execute("SELECT name, rfid, encoding FROM users").fetchall()
    conn.close()
    return [(r[0], r[1], np.array(json.loads(r[2]))) for r in rows]


def get_all_user_names():
    conn = get_db_conn()
    rows = conn.execute("SELECT id, name, rfid FROM users").fetchall()
    conn.close()
    return [{"id": r[0], "name": r[1], "rfid": r[2]} for r in rows]


def delete_user_by_name(name):
    conn = get_db_conn()
    cursor = conn.execute("DELETE FROM users WHERE name = ?", (name,))
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    return deleted


def delete_user_by_id(user_id):
    conn = get_db_conn()
    cursor = conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    return deleted


def delete_all_users():
    conn = get_db_conn()
    conn.execute("DELETE FROM users")
    conn.commit()
    conn.close()


def log_attendance(name, rfid):
    conn = get_db_conn()
    conn.execute(
        "INSERT INTO attendance (name, rfid, status) VALUES (?, ?, 'present')",
        (name, rfid)
    )
    conn.commit()
    conn.close()


def log_absent_bulk(absent_list: list):
    """
    Insert absent records for a list of students.
    Allows overwriting an existing status (e.g., changing 'present' to 'absent').
    """
    conn = get_db_conn()
    cursor = conn.cursor()
    count = 0
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    
    for student in absent_list:
        name = student.get("name", "").strip()
        rfid = student.get("rfid", "") or ""
        if not name:
            continue
            
        # Use INSERT OR REPLACE to update status to 'absent' if a record already exists
        # We also try to keep the original timestamp if possible
        cursor.execute("""
            INSERT OR REPLACE INTO attendance (id, name, rfid, status, timestamp)
            VALUES (
                (SELECT id FROM attendance WHERE name = ? AND DATE(timestamp) = ?),
                ?, ?, 'absent', 
                (SELECT timestamp FROM attendance WHERE name = ? AND DATE(timestamp) = ? OR CURRENT_TIMESTAMP)
            )
        """, (name, today, name, rfid, name, today))
        
        count += 1
            
    conn.commit()
    conn.close()
    return count


def get_attendance():
    conn = get_db_conn()
    rows = conn.execute(
        "SELECT name, rfid, status, timestamp FROM attendance ORDER BY timestamp DESC LIMIT 50"
    ).fetchall()
    conn.close()
    return [{"name": r[0], "rfid": r[1], "status": r[2] or "present", "time": r[3]} for r in rows]


def delete_all_attendance():
    conn = get_db_conn()
    conn.execute("DELETE FROM attendance")
    conn.commit()
    conn.close()

def log_present_bulk(present_list: list):
    """
    Mark a list of students as present. 
    If they were previously marked absent today, this will update their record to 'present'.
    """
    conn = get_db_conn()
    cursor = conn.cursor()
    count = 0
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    
    print(f"[DB] Bulk Present: Processing {len(present_list)} students")

    for student in present_list:
        name = student.get("name", "").strip()
        rfid = student.get("rfid", "") or ""
        if not name: continue
        
        # Check if a record already exists for today
        existing = cursor.execute(
            "SELECT id FROM attendance WHERE name = ? AND DATE(timestamp) = ?",
            (name, today)
        ).fetchone()
        
        if existing:
            # Update existing record (e.g. from 'absent' to 'present')
            cursor.execute(
                "UPDATE attendance SET status = 'present', rfid = ? WHERE id = ?",
                (rfid, existing[0])
            )
            print(f"[DB]   - Updated to PRESENT: {name}")
        else:
            # Create new record
            cursor.execute(
                "INSERT INTO attendance (name, rfid, status) VALUES (?, ?, 'present')",
                (name, rfid)
            )
            print(f"[DB]   - Marked PRESENT (new): {name}")
        count += 1
        
    conn.commit()
    conn.close()
    return count
