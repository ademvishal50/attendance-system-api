FROM python:3.10-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user for Hugging Face
RUN useradd -m -u 1000 user
USER user
ENV PATH="/home/user/.local/bin:${PATH}"

WORKDIR /app

# Upgrade pip and install wheels
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

COPY --chown=user:user requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create /data directory so it exists even if volume isn't mounted
# and ensure the user has write permissions to it
USER root
RUN mkdir -p /data && chown -R user:user /data && chmod -R 777 /data
USER user

COPY --chown=user:user . .

# Ensure a local db exists as fallback
RUN touch attendance.db && chmod 666 attendance.db

EXPOSE 7860

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]
