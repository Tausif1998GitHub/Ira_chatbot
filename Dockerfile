# ---------- Dockerfile ----------
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Copy dependency list first (better caching)
COPY requirements.txt .

# Install system + python deps
RUN apt-get update && apt-get install -y build-essential && \
    pip install --no-cache-dir -r requirements.txt && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Copy rest of the code
COPY . .

# Expose FastAPI port
EXPOSE 8000

# Run app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]