FROM python:3.10-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 1. Install system dependencies needed for OpenCV, dlib, and general image processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    libopenblas-dev \
    liblapack-dev \
    libx11-dev \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    && rm -rf /var/lib/apt/lists/*

# 2. Create a non-root user for security and cloud compatibility (UID 1000)
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH
WORKDIR $HOME/app

# 3. Skip 20-minute compilation by using dlib-bin and manual dependency management
RUN pip install --no-cache-dir --user dlib-bin
RUN pip install --no-cache-dir --user face-recognition --no-deps
RUN pip install --no-cache-dir --user face-recognition-models Click Pillow requests

# 4. Install the rest of your project requirements
COPY --chown=user requirements.txt .
RUN sed -i '/face-recognition/d' requirements.txt && \
    pip install --no-cache-dir --user -r requirements.txt

# 5. Copy your main.py and database.py with correct ownership
COPY --chown=user . .

# Cloud service port (Hugging Face / Render / Railway default)
EXPOSE 7860

# Regular start command
CMD ["python3", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]