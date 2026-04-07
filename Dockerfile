# This base image comes with dlib, face_recognition, and OpenCV pre-installed
FROM datamachines/face_recognition-cpu:python3.10-slim

WORKDIR /app

# Install only the extra packages you need (like Turso/libsql)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Hugging Face Spaces default port
EXPOSE 7860

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]