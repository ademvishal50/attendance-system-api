import os
import io
import json
import numpy as np
import face_recognition
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import database

app = FastAPI(title="Attendance API")

# Initialize database on startup
@app.on_event("startup")
async def startup_event():
    database.init_db()

# ─── Configuration ───────────────────────────────────────────
THRESHOLD = 0.4

# ─── Bearer Token Security ────────────────────────────────────
security = HTTPBearer()

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    expected_token = os.environ.get("ATTENDANCE_TOKEN")
    if not expected_token:
        raise HTTPException(status_code=500, detail="Server token (ATTENDANCE_TOKEN) not configured")
    if credentials.credentials != expected_token:
        raise HTTPException(status_code=401, detail="Invalid or missing token")
    return credentials.credentials

# ─── Health Check (public - no token needed) ─────────────────
@app.get("/")
def root():
    return {
        "status": "online",
        "message": "Attendance API is ready!",
        "database": "Turso Cloud",
        "engine": "Local face_recognition"
    }

# ─── Register ────────────────────────────────────────────────
@app.post("/register")
async def register(name: str = Form(), rfid: str = Form(), image: UploadFile = File(), token: str = Depends(verify_token)):
    try:
        img_bytes = await image.read()
        img = face_recognition.load_image_file(io.BytesIO(img_bytes))
        encodings = face_recognition.face_encodings(img)

        if not encodings:
            raise HTTPException(status_code=400, detail="No face detected.")
        if len(encodings) > 1:
            raise HTTPException(status_code=400, detail="Multiple faces detected.")

        database.save_user(name, rfid, encodings[0])
        return {"status": "success", "message": f"{name} registered successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ─── Verify ──────────────────────────────────────────────────
@app.post("/verify")
async def verify(rfid: str = Form(""), image: UploadFile = File(), token: str = Depends(verify_token)):
    try:
        img_bytes = await image.read()
        img = face_recognition.load_image_file(io.BytesIO(img_bytes))
        unknown_enc = face_recognition.face_encodings(img)

        if not unknown_enc:
            raise HTTPException(status_code=400, detail="No face detected in image")

        # 1. Try direct RFID match first (Optimized)
        if rfid:
            user = database.get_user_by_rfid(rfid)
            if user:
                name, _, stored_enc = user
                distance = np.linalg.norm(stored_enc - unknown_enc[0])
                if distance < THRESHOLD:
                    database.log_attendance(name, rfid)
                    return {
                        "status": "success",
                        "name": name,
                        "mode": "verification",
                        "confidence": f"{round((1 - distance) * 100, 1)}%"
                    }

        # 2. Fallback to global scan
        users = database.get_all_users()
        if not users:
            return {"status": "error", "message": "No users registered yet"}

        names = [u[0] for u in users]
        stored_encs = [u[2] for u in users]

        distances = np.linalg.norm(np.array(stored_encs) - unknown_enc[0], axis=1)
        best_idx = int(np.argmin(distances))
        best_distance = float(distances[best_idx])

        if best_distance < THRESHOLD:
            matched_name = names[best_idx]
            matched_rfid = rfid if rfid else users[best_idx][1]
            database.log_attendance(matched_name, matched_rfid)
            return {
                "status": "success",
                "name": matched_name,
                "mode": "recognition",
                "confidence": f"{round((1 - best_distance) * 100, 1)}%"
            }

        return {"status": "no_match", "closest_distance": round(best_distance, 4)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ─── Management Endpoints ─────────────────────────────────────

@app.get("/students")
def get_students(token: str = Depends(verify_token)):
    users = database.get_all_user_names()
    return {"total": len(users), "students": users}

@app.get("/attendance")
def get_attendance(token: str = Depends(verify_token)):
    records = database.get_attendance()
    return {"total": len(records), "records": records}

@app.delete("/delete/name/{name}")
def delete_user_by_name(name: str, token: str = Depends(verify_token)):
    deleted = database.delete_user_by_name(name)
    if deleted == 0:
        raise HTTPException(status_code=404, detail=f"No user found with name '{name}'")
    return {"status": "success", "message": f"Deleted user '{name}'"}

@app.delete("/delete/id/{user_id}")
def delete_user_by_id(user_id: int, token: str = Depends(verify_token)):
    deleted = database.delete_user_by_id(user_id)
    if deleted == 0:
        raise HTTPException(status_code=404, detail=f"No user found with id {user_id}")
    return {"status": "success", "message": f"Deleted user with id {user_id}"}

@app.delete("/delete/all-faces")
def delete_all_users(token: str = Depends(verify_token)):
    database.delete_all_users()
    return {"status": "success", "message": "All registered faces deleted"}

@app.delete("/delete/all-attendance")
def delete_all_attendance(token: str = Depends(verify_token)):
    database.delete_all_attendance()
    return {"status": "success", "message": "All attendance records deleted"}

# ─── Debug: view users ───────────────────────────────────────
@app.get("/debug/users")
def debug_users(token: str = Depends(verify_token)):
    try:
        users = database.get_debug_users()
        return {"total": len(users), "users": users}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))