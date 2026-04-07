import os
import io
import json
import numpy as np
import face_recognition
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import database

app = FastAPI(title="Global Attendance API")
database.init_db()

THRESHOLD = 0.4
security = HTTPBearer()

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    expected_token = os.environ.get("ATTENDANCE_TOKEN")
    if not expected_token or credentials.credentials != expected_token:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return credentials.credentials

@app.get("/")
def root():
    return {"status": "online", "database": "Turso Cloud", "engine": "Local face_recognition"}

@app.post("/register")
async def register(name: str = Form(), rfid: str = Form(), image: UploadFile = File(), token: str = Depends(verify_token)):
    img_bytes = await image.read()
    # Load image directly from bytes
    img = face_recognition.load_image_file(io.BytesIO(img_bytes))
    encodings = face_recognition.face_encodings(img)

    if not encodings:
        raise HTTPException(status_code=400, detail="No face detected.")
    if len(encodings) > 1:
        raise HTTPException(status_code=400, detail="Multiple faces detected.")

    database.save_user(name, rfid, encodings[0])
    return {"status": "success", "message": f"{name} registered."}

@app.post("/verify")
async def verify(rfid: str = Form(""), image: UploadFile = File(), token: str = Depends(verify_token)):
    img_bytes = await image.read()
    img = face_recognition.load_image_file(io.BytesIO(img_bytes))
    unknown_enc = face_recognition.face_encodings(img)

    if not unknown_enc:
        raise HTTPException(status_code=400, detail="No face detected.")

    matched_name = None
    best_distance = 1.0

    # Optimization: If RFID is provided, check that specific user first
    if rfid:
        user = database.get_user_by_rfid(rfid)
        if user:
            name, stored_rfid, stored_enc = user
            distance = np.linalg.norm(stored_enc - unknown_enc[0])
            if distance < THRESHOLD:
                matched_name = name
                best_distance = float(distance)
                database.log_attendance(matched_name, rfid)
                return {
                    "status": "success",
                    "name": matched_name,
                    "mode": "verification",
                    "confidence": f"{round((1 - best_distance) * 100, 1)}%"
                }

    # Fallback or Global Scan: Search all users
    users = database.get_all_users()
    if not users:
        return {"status": "error", "message": "No users registered."}

    # Extract stored data
    names = [u[0] for u in users]
    stored_encs = [u[2] for u in users]

    # Manual distance calculation (Euclidean)
    distances = np.linalg.norm(np.array(stored_encs) - unknown_enc[0], axis=1)
    best_idx = int(np.argmin(distances))
    best_distance = float(distances[best_idx])

    if best_distance < THRESHOLD:
        matched_name = names[best_idx]
        # Use the provided RFID if available, otherwise use the one from DB (though database.log_attendance takes rfid)
        # In recognition mode, we might not have the RFID if it wasn't sent
        matched_rfid = rfid if rfid else users[best_idx][1]
        database.log_attendance(matched_name, matched_rfid)
        return {
            "status": "success", 
            "name": matched_name, 
            "mode": "recognition",
            "confidence": f"{round((1 - best_distance) * 100, 1)}%"
        }

    return {"status": "no_match", "distance": round(best_distance, 4)}

@app.get("/students")
def get_students(token: str = Depends(verify_token)):
    return database.get_all_user_names()

@app.get("/attendance")
def get_attendance(token: str = Depends(verify_token)):
    return database.get_attendance()

@app.delete("/delete/id/{user_id}")
def delete_user(user_id: int, token: str = Depends(verify_token)):
    if database.delete_user_by_id(user_id) > 0:
        return {"status": "success"}
    raise HTTPException(status_code=404, detail="User not found")