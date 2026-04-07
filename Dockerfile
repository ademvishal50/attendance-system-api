FROM animcogn/face_recognition:cpu

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Create /data directory and set permissions BEFORE switching to non-root user
USER root
RUN mkdir -p /data && chmod -R 777 /data

# Note: The base image may already have a 'user' or may require specific handling.
# To be safe and compatible with Hugging Face, we'll ensure /app belongs to the user.
WORKDIR /app

# Upgrade pip as root if needed, then switch user
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Now handle the rest of the application files
COPY . .

# Ensure the app directories are writable
RUN chmod -R 777 /app

# Ensure a local db exists as fallback
RUN touch attendance.db && chmod 666 attendance.db

# Hugging Face runs as user 1000 by default, but we should make sure 
# everything is accessible to it.
EXPOSE 7860

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]
