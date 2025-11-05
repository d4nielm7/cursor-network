FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy both files - api_server.py for Railway backend, server.py for MCP client
COPY api_server.py .
COPY server.py .

# Run the API server for Railway deployment
# Railway sets PORT env var automatically, uvicorn will read it
CMD uvicorn api_server:app --host 0.0.0.0 --port ${PORT:-8000}

