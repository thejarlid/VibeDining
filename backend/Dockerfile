# Use Python slim image for smaller size
FROM python:3.11-slim

# Install system dependencies needed for ML packages
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    git \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for better Docker layer caching
COPY requirements.txt .

# Upgrade pip and install packages with optimizations
RUN pip install --upgrade pip && \
    pip install --no-cache-dir \
    --prefer-binary \
    --index-url https://download.pytorch.org/whl/cpu \
    torch torchvision torchaudio && \
    pip install --no-cache-dir --prefer-binary -r requirements.txt

# Copy application code
COPY . .

# DEBUG: List files to see what got copied
RUN ls -la
RUN find . -name "*.db" -o -name "*chroma*" | head -20

# Expose port (Railway will override with $PORT)
EXPOSE 8000

# Start command
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}