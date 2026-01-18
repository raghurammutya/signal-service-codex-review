# Production Deployment Guide - Signal Service
Generated: 2026-01-18T08:00:46.588948

## 🚀 Quick Start

### Required Environment Variables
```bash
export ENVIRONMENT=production
export CONFIG_SERVICE_URL=http://config-service:8100
export INTERNAL_API_KEY=<secure_internal_key>
export SERVICE_NAME=signal-service
```

### Required Config Service Keys
- `database_pool_config`: Database connection pool settings
- `budget_guards_config`: Memory and CPU budget configurations
- `circuit_breaker_config`: Circuit breaker settings for all external services
- `metrics_export_config`: Metrics collection and export settings

### Pre-Deployment Validation
```bash
# Run production hardening validation
python3 scripts/validate_production_hardening.py

# Run deployment safety validation  
python3 scripts/deployment_safety_validation.py

# Run smoke tests
python3 simple_smoke_validation.py
```

### Service Startup
```bash
# Start the service
uvicorn app.main:app --host 0.0.0.0 --port 8000

# Verify health
curl http://localhost:8000/health

# Check metrics
curl http://localhost:8000/metrics
```

### Critical Dependencies
1. **TimescaleDB**: Time-series database for signal storage
2. **Config Service**: Centralized configuration management
3. **Redis**: Caching and rate limiting
4. **External Services**: 
   - Ticker Service
   - User Service  
   - Alert Service
   - Communications Service

### Health Checks
- `/health`: Basic health check
- `/health/live`: Liveness probe
- `/health/ready`: Readiness probe
- `/metrics`: Prometheus metrics

### Monitoring & Observability
- Metrics exported to Prometheus format
- Structured logging with sensitive data redaction
- Circuit breaker status monitoring
- Budget guard and backpressure monitoring

### Security Notes
- All API endpoints require proper authentication
- Admin endpoints require special admin tokens
- Sensitive data is automatically redacted from logs
- CORS configured for production (no wildcards)

### Troubleshooting
1. **Config Service Connection Issues**: Verify CONFIG_SERVICE_URL and network connectivity
2. **Database Connection Issues**: Check TimescaleDB availability and credentials  
3. **Circuit Breaker Trips**: Monitor external service health
4. **Budget Guard Triggers**: Check memory/CPU usage and adjust budget configs

For detailed validation results, see the production readiness bundle artifacts.
