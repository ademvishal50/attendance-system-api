import os
import json
import numpy as np
import libsql_client

# Get these from Hugging Face Secrets (Settings tab)
URL = os.environ.get("TURSO_URL")
TOKEN = os.environ.get("TURSO_TOKEN")

if not URL or not TOKEN:
    print("WARNING: TURSO_URL or TURSO_TOKEN environment variables are not set.")

def get_client():
    return libsql_client.create_client_sync(url=URL, auth_token=TOKEN)

def init_db():
    print("Initializing Database...")
    if not URL or not TOKEN:
        print("ERROR: Database credentials missing! URL and TOKEN must be set.")
        return
    
    try:
        with get_client() as client:
            client.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, rfid TEXT UNIQUE, encoding TEXT)")
            client.execute("CREATE TABLE IF NOT EXISTS attendance (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, rfid TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
            print("Database initialized successfully.")
    except Exception as e:
        print(f"DATABASE INITIALIZATION ERROR: {e}")


def save_user(name, rfid, encoding):
    # Convert numpy array to list then to JSON string for storage
    enc_json = json.dumps(encoding.tolist())
    with get_client() as client:
        client.execute("INSERT OR REPLACE INTO users (name, rfid, encoding) VALUES (?, ?, ?)", (name, rfid, enc_json))

def get_all_users():
    with get_client() as client:
        result = client.execute("SELECT name, rfid, encoding FROM users")
        # Convert JSON strings back to numpy arrays
        return [(r[0], r[1], np.array(json.loads(r[2]))) for r in result.rows]

def get_user_by_rfid(rfid):
    with get_client() as client:
        result = client.execute("SELECT name, rfid, encoding FROM users WHERE rfid = ?", (rfid,))
        if result.rows:
            r = result.rows[0]
            return (r[0], r[1], np.array(json.loads(r[2])))
        return None

def get_all_user_names():
    with get_client() as client:
        result = client.execute("SELECT id, name, rfid FROM users")
        return [{"id": r[0], "name": r[1], "rfid": r[2]} for r in result.rows]

def log_attendance(name, rfid):
    with get_client() as client:
        client.execute("INSERT INTO attendance (name, rfid) VALUES (?, ?)", (name, rfid))

def get_attendance():
    with get_client() as client:
        result = client.execute("SELECT name, rfid, timestamp FROM attendance ORDER BY timestamp DESC LIMIT 50")
        return [{"name": r[0], "rfid": r[1], "time": r[2]} for r in result.rows]

def delete_user_by_id(user_id):
    with get_client() as client:
        res = client.execute("DELETE FROM users WHERE id = ?", (user_id,))
        return res.rows_affected

def delete_all_users():
    with get_client() as client:
        client.execute("DELETE FROM users")

def delete_all_attendance():
    with get_client() as client:
        client.execute("DELETE FROM attendance")