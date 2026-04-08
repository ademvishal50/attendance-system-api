from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List
import requests
import os
import sqlite3
import json
import database
import numpy as np
import cv2
import io
try:
    import face_recognition
    HAS_FACE_REC = True
except ImportError:
    HAS_FACE_REC = False


app = FastAPI(title="Attendance API")
database.init_db()

THRESHOLD = 0.4

# ──────────────────────────────────────────────────────────────

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

# ──────────────────────────────────────────────────────────────

# ─── Health Check (public - no token needed) ─────────────────
@app.get("/")
def root():
    """Health check endpoint for Hugging Face and users."""
    is_turso = getattr(database, "USE_TURSO", False)
    db_mode = getattr(database, "STORAGE_MODE", "Unknown")
    
    return {
        "status": "online",
        "message": "Attendance API is ready!",
        "database": {
            "type": "Turso (Remote)" if is_turso else "SQLite (Local)",
            "mode": db_mode,
            "target": getattr(database, "DB_DISPLAY", "Unknown")
        },
        "recognition": "Local (processing on Render server)",
        "environment": "Production (Render)" if is_turso else "Local/Development"
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
    
    if not HAS_FACE_REC:
        raise HTTPException(status_code=500, detail="face_recognition library not installed.")

    # Local processing
    img = face_recognition.load_image_file(io.BytesIO(img_bytes))
    encodings = face_recognition.face_encodings(img)

    if not encodings:
        raise HTTPException(status_code=400, detail="No face detected in the uploaded photo.")

    if len(encodings) > 1:
        raise HTTPException(status_code=400, detail="Multiple faces detected. Upload a photo with only one face.")

    # Check if RFID already exists to provide a better error message
    existing_user = database.get_user_by_rfid(rfid)
    if existing_user:
        existing_name = existing_user[0]
        if existing_name != name:
             raise HTTPException(
                status_code=400, 
                detail=f"RFID {rfid} is already assigned to {existing_name}. Please use a different RFID."
            )
        # If it's the same name, we treat it as an update (re-enrolling)
        print(f"[REGISTER] Updating existing user: {name}")

    try:
        database.save_user(name, rfid, encodings[0])
    except Exception as e:
        print(f"[ERROR] Database error during registration: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

    return {"status": "success", "message": f"{name} registered successfully"}

# ─── Verify ──────────────────────────────────────────────────
@app.post("/verify")
async def verify(
    rfid: str = Form(""),
    image: UploadFile = File(),
    token: str = Depends(verify_token)
):
    img_bytes = await image.read()
    
    if not HAS_FACE_REC:
        raise HTTPException(status_code=500, detail="face_recognition library not installed.")

    # Local processing
    img = face_recognition.load_image_file(io.BytesIO(img_bytes))
    encodings = face_recognition.face_encodings(img)

    if not encodings:
        raise HTTPException(status_code=400, detail="No face detected in image")

    unknown_enc = encodings[0]
    users = database.get_all_users()

    if not users:
        return {"status": "error", "message": "No users registered yet"}

    names = [u[0] for u in users]
    stored_encs = [u[2] for u in users]

    # Calculate distances manually using numpy (Euclidean distance)
    # Equivalent to face_recognition.face_distance
    distances = np.linalg.norm(np.array(stored_encs) - unknown_enc, axis=1)
    
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


# ─── Bulk-mark students as absent ────────────────────────────
class AbsentStudent(BaseModel):
    name: str
    rfid: str = ""

@app.post("/attendance/bulk-absent")
def bulk_absent(
    students: List[AbsentStudent],
    token: str = Depends(verify_token)
):
    """
    Accepts a JSON array of students to be marked absent.
    Example body: [{"name": "John", "rfid": "ABC123"}, ...]
    Students who already have any attendance record for today are skipped.
    """
    if not students:
        raise HTTPException(status_code=400, detail="No students provided")

    absent_list = [{"name": s.name, "rfid": s.rfid} for s in students]
    inserted = database.log_absent_bulk(absent_list)

    return {
        "status": "success",
        "total_received": len(students),
        "newly_marked_absent": inserted,
        "skipped": len(students) - inserted,
        "message": f"{inserted} student(s) marked absent, {len(students) - inserted} already had a record for today."
    }
@app.post("/attendance/bulk-present")
def bulk_present(
    students: List[AbsentStudent],
    token: str = Depends(verify_token)
):
    """
    Accepts a JSON array of students to be marked present manually.
    """
    if not students:
        raise HTTPException(status_code=400, detail="No students provided")

    present_list = [{"name": s.name, "rfid": s.rfid} for s in students]
    inserted = database.log_present_bulk(present_list)

    return {
        "status": "success",
        "total_received": len(students),
        "newly_marked_present": inserted
    }

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
    conn = database.get_db_conn()
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
