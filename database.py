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
    Each item in absent_list should be a dict with 'name' and optionally 'rfid'.
    Skips students who already have an attendance record for today.
    Returns the count of newly inserted absent records.
    """
    conn = get_db_conn()
    count = 0
    today = __import__('datetime').date.today().isoformat()  # YYYY-MM-DD
    for student in absent_list:
        name = student.get("name", "").strip()
        rfid = student.get("rfid", "") or ""
        if not name:
            continue
        # Only insert if no record already exists for today
        existing = conn.execute(
            "SELECT id FROM attendance WHERE name = ? AND DATE(timestamp) = ?",
            (name, today)
        ).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO attendance (name, rfid, status) VALUES (?, ?, 'absent')",
                (name, rfid)
            )
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
    Uses INSERT OR REPLACE to update status if they were previously marked absent.
    """
    conn = get_db_conn()
    count = 0
    today = __import__('datetime').date.today().isoformat()
    for student in present_list:
        name = student.get("name", "").strip()
        rfid = student.get("rfid", "") or ""
        if not name: continue
        
        # Use REPLACE to overwrite 'absent' status if it exists
        conn.execute(
            "INSERT OR REPLACE INTO attendance (name, rfid, status, timestamp) "
            "VALUES (?, ?, 'present', COALESCE((SELECT timestamp FROM attendance WHERE name = ? AND DATE(timestamp) = ?), CURRENT_TIMESTAMP))",
            (name, rfid, name, today)
        )
        count += 1
    conn.commit()
    conn.close()
    return count
