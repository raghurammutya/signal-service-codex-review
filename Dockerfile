# Use Python 3.12 for pandas-ta compatibility
FROM python:3.12-slim

# Install minimal build dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r signalservice && \
    useradd -r -g signalservice -u 1001 -s /bin/bash -m signalservice

# Set working directory
WORKDIR /app

# Copy service-specific requirements (context is project root)
COPY signal_service/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code (context is project root)
COPY signal_service/app/ ./app/

# Copy tests for in-container execution
COPY signal_service/tests/ ./signal_service/tests/
COPY signal_service/conftest.py ./signal_service/conftest.py

# Copy config service client (if using common directory)
COPY common/ ./common/

# Create necessary directories and set permissions
RUN mkdir -p /app/logs && \
    chmod 755 /app/logs && \
    chown -R signalservice:signalservice /app /app/logs

# Service-specific configuration
ENV SERVICE_NAME=signal_service
ENV SERVICE_PORT=8003
ENV PYTHONPATH=/app

# Health endpoints from shared architecture
EXPOSE 8003

# Switch to non-root user
USER signalservice

# Run the service
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8003"]