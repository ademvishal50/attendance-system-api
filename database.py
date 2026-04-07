import os
import json
import numpy as np
import libsql_client

# Get these from Hugging Face Secrets (Settings tab)
URL = os.environ.get("TURSO_URL")
TOKEN = os.environ.get("TURSO_TOKEN")

def get_client():
    return libsql_client.create_client_sync(url=URL, auth_token=TOKEN)

def init_db():
    client = get_client()
    client.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, rfid TEXT, encoding TEXT)")
    client.execute("CREATE TABLE IF NOT EXISTS attendance (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, rfid TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")

def save_user(name, rfid, encoding):
    client = get_client()
    # Convert numpy array to list then to JSON string for storage
    enc_json = json.dumps(encoding.tolist())
    client.execute("INSERT INTO users (name, rfid, encoding) VALUES (?, ?, ?)", (name, rfid, enc_json))

def get_all_users():
    client = get_client()
    result = client.execute("SELECT name, rfid, encoding FROM users")
    # Convert JSON strings back to numpy arrays
    return [(r[0], r[1], np.array(json.loads(r[2]))) for r in result.rows]

def get_all_user_names():
    client = get_client()
    result = client.execute("SELECT id, name, rfid FROM users")
    return [{"id": r[0], "name": r[1], "rfid": r[2]} for r in result.rows]

def log_attendance(name, rfid):
    client = get_client()
    client.execute("INSERT INTO attendance (name, rfid) VALUES (?, ?)", (name, rfid))

def get_attendance():
    client = get_client()
    result = client.execute("SELECT name, rfid, timestamp FROM attendance ORDER BY timestamp DESC LIMIT 50")
    return [{"name": r[0], "rfid": r[1], "time": r[2]} for r in result.rows]

def delete_user_by_id(user_id):
    client = get_client()
    res = client.execute("DELETE FROM users WHERE id = ?", (user_id,))
    return res.rows_affected

def delete_all_users():
    get_client().execute("DELETE FROM users")

def delete_all_attendance():
    get_client().execute("DELETE FROM attendance")