FROM python:3.10-slim

# 1. Install system tools
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

# 2. Install dlib FIRST (The 20-minute part)
# This layer will be cached and won't run again if you edit main.py
RUN pip install --no-cache-dir dlib==19.24.1

# 3. Install remaining smaller packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. Copy your code LAST
COPY . .

EXPOSE 7860
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]