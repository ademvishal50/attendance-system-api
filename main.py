from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import FileResponse
import requests
import os
import sqlite3
import json
import database
import numpy as np
import cv2

app = FastAPI(title="Attendance API")
database.init_db()

# ─── Configuration ───────────────────────────────────────────
THRESHOLD = 0.4
# External Face Recognition API URL (defaults to a generic placeholder if not set)
RECOGNITION_API_URL = os.environ.get("RECOGNITION_API_URL", "")
# Token for the external API if needed
RECOGNITION_API_TOKEN = os.environ.get("RECOGNITION_API_TOKEN", "")
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

async def get_encoding_from_api(image_bytes: bytes):
    """Sends image to external API to get face encodings."""
    if not RECOGNITION_API_URL:
        raise HTTPException(
            status_code=500,
            detail="RECOGNITION_API_URL is not configured in environment variables."
        )
    
    try:
        # Assuming the API takes an 'image' file field
        files = {"image": ("image.jpg", image_bytes, "image/jpeg")}
        headers = {}
        if RECOGNITION_API_TOKEN:
            headers["Authorization"] = f"Bearer {RECOGNITION_API_TOKEN}"
            
        response = requests.post(RECOGNITION_API_URL, files=files, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # Most APIs return a list of encodings: {"encodings": [[...]]}
        encodings = data.get("encodings", [])
        return [np.array(e) for e in encodings]
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error calling Face Recognition API: {str(e)}"
        )

# ─── Health Check (public - no token needed) ─────────────────
@app.get("/")
def root():
    """Health check endpoint for Hugging Face and users."""
    return {
        "status": "online",
        "message": "Attendance API is ready!",
        "database": {
            "path": database.DB,
            "mode": getattr(database, "STORAGE_MODE", "Unknown"),
            "exists": os.path.exists(database.DB)
        },
        "recognition": {
            "api_url": RECOGNITION_API_URL or "NOT_CONFIGURED",
            "api_configured": bool(RECOGNITION_API_URL)
        },
        "instruction": "Set RECOGNITION_API_URL and ATTENDANCE_TOKEN in your Space's environment variables. "
                       "Enable Persistent Storage in Space settings to use /data."
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
    
    # Get encodings from API instead of local library
    encodings = await get_encoding_from_api(img_bytes)

    if not encodings:
        raise HTTPException(status_code=400, detail="No face detected in the uploaded photo.")

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
    
    # Get encodings from API instead of local library
    encodings = await get_encoding_from_api(img_bytes)

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
