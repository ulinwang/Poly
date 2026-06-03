FROM python:3.12-slim

WORKDIR /app

# Install system dependencies (for packages that may need compilation)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files
COPY pyproject.toml requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source code and parent packages it depends on
COPY webapp/backend/ ./webapp/backend/
COPY agent/ ./agent/
COPY environment/ ./environment/
COPY experiments/ ./experiments/
COPY viz/ ./viz/
COPY data/ ./data/

# Ensure SQLite data directory exists and is writable
RUN mkdir -p /app/webapp/backend/data

# Set Python path so webapp.backend resolves correctly
ENV PYTHONPATH=/app

EXPOSE 8000

CMD ["uvicorn", "webapp.backend.server_v2:app", "--host", "0.0.0.0", "--port", "8000"]
