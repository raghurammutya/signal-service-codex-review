FROM ghcr.io/raghurammutya/stocksblitz-base:latest

WORKDIR /app

# Copy service-specific requirements
COPY docker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app ./app

# The service relies on local helpers instead of any external shared module.

# Set environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV SERVICE_NAME=signal_service
ENV SERVICE_PORT=8003

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python /usr/local/bin/healthcheck.py --port=8003 --endpoint=/health || exit 1

# Run as non-root user (inherited from base image)
USER appuseruser

EXPOSE 8003

CMD ["python", "-m", "app.main"]
