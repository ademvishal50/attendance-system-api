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
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 2. Install dlib using a verified pre-compiled wheel for Python 3.10 (Linux x86_64)
# This prevents the 20-minute compilation and avoids "Building wheel for dlib" hangs.
RUN pip install --no-cache-dir https://github.com/vladmandic/dlib-wheels/releases/download/v19.24.1/dlib-19.24.1-cp310-cp310-manylinux_2_17_x86_64.manylinux2014_x86_64.whl



# 3. Install the rest of your project requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. Copy your main.py and database.py
COPY . .

# Hugging Face Spaces port
EXPOSE 7860

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]