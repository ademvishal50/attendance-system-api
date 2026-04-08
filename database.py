import os
import json
import numpy as np
import libsql

# Using Environment Variables for Security
URL = os.environ.get("TURSO_URL")
TOKEN = os.environ.get("TURSO_TOKEN")

if not URL or not TOKEN:
    print("WARNING: TURSO_URL or TURSO_TOKEN environment variables are not set!")

def get_client():
    return libsql.connect(URL, auth_token=TOKEN)

def init_db():
    try:
        with get_client() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, rfid TEXT UNIQUE, encoding TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS attendance (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, rfid TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
            conn.commit()
    except Exception as e:
        print(f"DATABASE INIT ERROR: {e}")

def save_user(name, rfid, encoding):
    enc_json = json.dumps(encoding.tolist())
    with get_client() as conn:
        conn.execute("INSERT OR REPLACE INTO users (name, rfid, encoding) VALUES (?, ?, ?)", (name, rfid, enc_json))
        conn.commit()

def get_all_users():
    with get_client() as conn:
        res = conn.execute("SELECT name, rfid, encoding FROM users")
        rows = res.fetchall()
        return [(row[0], row[1], np.array(json.loads(row[2]))) for row in rows]

def get_user_by_rfid(rfid):
    with get_client() as conn:
        res = conn.execute("SELECT name, rfid, encoding FROM users WHERE rfid = ?", (rfid,))
        row = res.fetchone()
        if row:
            return (row[0], row[1], np.array(json.loads(row[2])))
        return None

def get_all_user_names():
    with get_client() as conn:
        res = conn.execute("SELECT id, name, rfid FROM users")
        rows = res.fetchall()
        return [{"id": row[0], "name": row[1], "rfid": row[2]} for row in rows]

def log_attendance(name, rfid):
    with get_client() as conn:
        conn.execute("INSERT INTO attendance (name, rfid) VALUES (?, ?)", (name, rfid))
        conn.commit()

def get_attendance():
    with get_client() as conn:
        res = conn.execute("SELECT name, rfid, timestamp FROM attendance ORDER BY timestamp DESC LIMIT 50")
        rows = res.fetchall()
        return [{"name": row[0], "rfid": row[1], "time": row[2]} for row in rows]

def delete_user_by_name(name):
    with get_client() as conn:
        res = conn.execute("DELETE FROM users WHERE name = ?", (name,))
        conn.commit()
        return res.rowcount

def delete_user_by_id(user_id):
    with get_client() as conn:
        res = conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
        return res.rowcount

def delete_all_users():
    with get_client() as conn:
        conn.execute("DELETE FROM users")
        conn.commit()

def delete_all_attendance():
    with get_client() as conn:
        conn.execute("DELETE FROM attendance")
        conn.commit()

def get_debug_users():
    with get_client() as conn:
        res = conn.execute("SELECT id, name, rfid, encoding FROM users")
        rows = res.fetchall()
        return [
            {
                "id": r[0],
                "name": r[1],
                "rfid": r[2],
                "encoding_length": len(json.loads(r[3])),
                "encoding_preview": json.loads(r[3])[:5]
            }
            for r in rows
        ]