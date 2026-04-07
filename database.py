import os
import json
import numpy as np
import libsql

# Direct connection for stability
URL = "https://attendance-db-ademvishal50.aws-ap-south-1.turso.io"
TOKEN = "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3NzU1NzQ1NDIsImlkIjoiMDE5ZDY4N2MtY2UwMS03YjFmLTg3NzgtNDMzZDQ2MzhlYzhmIiwicmlkIjoiYzEyNTM5MDgtOGJiYS00YTk2LWI4N2MtNDZlZTFiMzk0NzQ4In0.HRQ6V4vp2GwL5bFd3WgVD8NFotsvTpi2aqMWBNX9GCRhnfMccKkizgOOFtLSmIw5IxXOny28MyqkJggwi9sXBg"

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

def delete_user_by_id(user_id):
    with get_client() as conn:
        res = conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
        # In libsql, we can get affected rows from the cursor
        return res.rowcount

def delete_all_users():
    with get_client() as conn:
        conn.execute("DELETE FROM users")
        conn.commit()

def delete_all_attendance():
    with get_client() as conn:
        conn.execute("DELETE FROM attendance")
        conn.commit()