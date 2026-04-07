from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import FileResponse
import face_recognition
import numpy as np
import cv2
import os
import sqlite3
import json
import database

app = FastAPI(title="Attendance API")
database.init_db()

THRESHOLD = 0.4

# ─── Bearer Token Security ────────────────────────────────────
security = HTTPBearer()

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    expected_token = os.environ.get("ATTENDANCE_TOKEN", "")
    if not expected_token:
        raise HTTPException(
            status_code=500,
            detail="Server token not configured"
        )
    if credentials.credentials != expected_token:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing token"
        )
    return credentials.credentials

# ─── Health Check (public - no token needed) ─────────────────
@app.get("/")
def root():
    return {
        "status": "running",
        "message": "Attendance API is live!",
        "db_path": database.DB          # ← helpful to confirm /data is being used
    }

# ─── Register ────────────────────────────────────────────────
@app.post("/register")
async def register(
    name: str = Form(),
    rfid: str = Form(),
    image: UploadFile = File(),
    token: str = Depends(verify_token)
):
    img_bytes = await image.read()
    img = cv2.imdecode(np.frombuffer(img_bytes, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(status_code=400, detail="Invalid image file")

    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    encodings = face_recognition.face_encodings(rgb)

    if not encodings:
        raise HTTPException(status_code=400, detail="No face detected. Use a clear front-facing photo.")

    if len(encodings) > 1:
        raise HTTPException(status_code=400, detail="Multiple faces detected. Upload a photo with only one face.")

    database.save_user(name, rfid, encodings[0])
    return {"status": "success", "message": f"{name} registered successfully"}

# ─── Verify ──────────────────────────────────────────────────
@app.post("/verify")
async def verify(
    rfid: str = Form(""),
    image: UploadFile = File(),
    token: str = Depends(verify_token)
):
    img_bytes = await image.read()
    img = cv2.imdecode(np.frombuffer(img_bytes, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(status_code=400, detail="Invalid image file")

    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    encodings = face_recognition.face_encodings(rgb)

    if not encodings:
        raise HTTPException(status_code=400, detail="No face detected in image")

    unknown_enc = encodings[0]
    users = database.get_all_users()

    if not users:
        return {"status": "error", "message": "No users registered yet"}

    names = [u[0] for u in users]
    stored_encs = [u[2] for u in users]

    distances = face_recognition.face_distance(stored_encs, unknown_enc)
    best_idx = int(np.argmin(distances))
    best_distance = float(distances[best_idx])

    if best_distance < THRESHOLD:
        matched_name = names[best_idx]
        database.log_attendance(matched_name, rfid)
        return {
            "status": "success",
            "name": matched_name,
            "distance": round(best_distance, 4),
            "confidence": f"{round((1 - best_distance) * 100, 1)}%"
        }

    return {
        "status": "no_match",
        "message": "Face did not match any registered user",
        "closest_distance": round(best_distance, 4),
        "threshold": THRESHOLD
    }

# ─── List all registered students ────────────────────────────
@app.get("/students")
def get_students(token: str = Depends(verify_token)):
    users = database.get_all_user_names()
    return {"total": len(users), "students": users}

# ─── Get attendance records ──────────────────────────────────
@app.get("/attendance")
def get_attendance(token: str = Depends(verify_token)):
    records = database.get_attendance()
    return {"total": len(records), "records": records}

# ─── Delete by name ──────────────────────────────────────────
@app.delete("/delete/name/{name}")
def delete_user_by_name(name: str, token: str = Depends(verify_token)):
    deleted = database.delete_user_by_name(name)
    if deleted == 0:
        raise HTTPException(status_code=404, detail=f"No user found with name '{name}'")
    return {"status": "success", "message": f"Deleted user '{name}'"}

# ─── Delete by ID ────────────────────────────────────────────
@app.delete("/delete/id/{user_id}")
def delete_user_by_id(user_id: int, token: str = Depends(verify_token)):
    deleted = database.delete_user_by_id(user_id)
    if deleted == 0:
        raise HTTPException(status_code=404, detail=f"No user found with id '{user_id}'")
    return {"status": "success", "message": f"Deleted user with id {user_id}"}

# ─── List users ──────────────────────────────────────────────
@app.get("/delete/list")
def list_users(token: str = Depends(verify_token)):
    users = database.get_all_user_names()
    return {"total": len(users), "users": users}

# ─── Delete all faces ────────────────────────────────────────
@app.delete("/delete/all-faces")
def delete_all_users(token: str = Depends(verify_token)):
    database.delete_all_users()
    return {"status": "success", "message": "All registered faces deleted"}

# ─── Delete all attendance ───────────────────────────────────
@app.delete("/delete/all-attendance")
def delete_all_attendance(token: str = Depends(verify_token)):
    database.delete_all_attendance()
    return {"status": "success", "message": "All attendance records deleted"}

# ─── Debug: view users ───────────────────────────────────────
@app.get("/debug/users")
def debug_users(token: str = Depends(verify_token)):
    conn = sqlite3.connect(database.DB)     # ← uses persistent DB path
    rows = conn.execute("SELECT id, name, rfid, encoding FROM users").fetchall()
    conn.close()
    return {
        "total": len(rows),
        "users": [
            {
                "id": r[0],
                "name": r[1],
                "rfid": r[2],
                "encoding_length": len(json.loads(r[3])),
                "encoding_preview": json.loads(r[3])[:5]
            }
            for r in rows
        ]
    }

# ─── Debug: download database ────────────────────────────────
@app.get("/debug/download-db")
def download_db(token: str = Depends(verify_token)):
    if not os.path.exists(database.DB):     # ← uses persistent DB path
        raise HTTPException(status_code=404, detail="Database not found")
    return FileResponse(
        database.DB,                        # ← uses persistent DB path
        media_type="application/octet-stream",
        filename="attendance.db"
    )
