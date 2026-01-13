#!/bin/bash
# Ensure log directory exists with proper permissions
mkdir -p /app/logs
chmod 777 /app/logs
# Start the service
exec python -m uvicorn app.main:app --host 0.0.0.0 --port ${SERVICE_PORT:-8003}
