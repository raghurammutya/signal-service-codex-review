# Config Service Bootstrap Requirements

## Overview

The Signal Service requires proper Config Service integration for production deployment. This document covers the mandatory environment variables and bootstrap validation requirements identified in functionality_issues.txt.

## Mandatory Environment Variables

### Required for Bootstrap

The following environment variables MUST be set before starting the Signal Service:

#### 1. ENVIRONMENT
- **Required**: Yes (mandatory for config service bootstrap)
- **Purpose**: Specifies the deployment environment for config service client
- **Valid Values**: `production`, `staging`, `development`, `test`
- **Location**: `app/core/config.py:48-50`
- **Failure Mode**: Service fails fast with `ValueError` if not set

```bash
export ENVIRONMENT=production
```

#### 2. CONFIG_SERVICE_URL
- **Required**: Yes (mandatory for config service client)
- **Purpose**: Base URL for config service API endpoints
- **Format**: Valid HTTP/HTTPS URL
- **Location**: `common/config_service/client.py:26`
- **Failure Mode**: Service fails fast with `ConfigServiceError` if not set

```bash
export CONFIG_SERVICE_URL=https://config-service.your-domain.com
```

#### 3. CONFIG_SERVICE_API_KEY
- **Required**: Yes (mandatory for config service authentication)
- **Purpose**: API key for authenticating with config service
- **Format**: Secure token/key string
- **Location**: `common/config_service/client.py:27`
- **Failure Mode**: Service fails fast with `ConfigServiceError` if not set

```bash
export CONFIG_SERVICE_API_KEY=your-api-key-here
```

## Deployment Script Requirements

### Kubernetes Deployment

Ensure your Kubernetes deployment sets all required environment variables:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: signal-service
spec:
  template:
    spec:
      containers:
      - name: signal-service
        env:
        - name: ENVIRONMENT
          value: "production"
        - name: CONFIG_SERVICE_URL
          valueFrom:
            secretKeyRef:
              name: config-service-credentials
              key: url
        - name: CONFIG_SERVICE_API_KEY
          valueFrom:
            secretKeyRef:
              name: config-service-credentials
              key: api-key
```

### Docker Compose

```yaml
version: '3.8'
services:
  signal-service:
    environment:
      - ENVIRONMENT=production
      - CONFIG_SERVICE_URL=https://config-service.your-domain.com
      - CONFIG_SERVICE_API_KEY=${CONFIG_SERVICE_API_KEY}
```

### Shell Script Deployment

```bash
#!/bin/bash
# deployment.sh - Signal Service deployment script

# Validate required environment variables
if [[ -z "${ENVIRONMENT}" ]]; then
    echo "ERROR: ENVIRONMENT environment variable is required"
    exit 1
fi

if [[ -z "${CONFIG_SERVICE_URL}" ]]; then
    echo "ERROR: CONFIG_SERVICE_URL environment variable is required"
    exit 1
fi

if [[ -z "${CONFIG_SERVICE_API_KEY}" ]]; then
    echo "ERROR: CONFIG_SERVICE_API_KEY environment variable is required"
    exit 1
fi

echo "✓ All required config service environment variables set"
echo "  ENVIRONMENT: ${ENVIRONMENT}"
echo "  CONFIG_SERVICE_URL: ${CONFIG_SERVICE_URL}"
echo "  CONFIG_SERVICE_API_KEY: [REDACTED]"

# Start the service
python -m app.main
```

## Bootstrap Validation

### Test Coverage Requirements

The config bootstrap validation is tested in `tests/config/test_config_bootstrap.py` with the following coverage requirements:

#### Required Test Scenarios (95% Path Coverage)

1. **Missing ENVIRONMENT variable** - Validates fail-fast behavior
2. **Missing CONFIG_SERVICE_URL** - Validates config client failure
3. **Missing CONFIG_SERVICE_API_KEY** - Validates authentication requirement
4. **Config service unreachable** - Validates network failure handling
5. **Successful bootstrap** - Validates complete configuration loading

#### Running Coverage Tests

```bash
# Run bootstrap tests with coverage measurement
pytest tests/config/test_config_bootstrap.py --cov=app.core.config --cov=common.config_service.client --cov-report=html --cov-fail-under=95

# View coverage report
open htmlcov/index.html
```

#### Expected Coverage Metrics

- **app.core.config.py**: ≥95% line coverage
- **common.config_service.client.py**: ≥95% line coverage
- **Bootstrap paths**: 100% coverage of fail-fast scenarios
- **Config loading**: 100% coverage of successful scenarios

### Continuous Integration

Add coverage verification to CI pipeline:

```yaml
# .github/workflows/config-bootstrap-tests.yml
name: Config Bootstrap Tests
on: [push, pull_request]

jobs:
  test-bootstrap:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v2
    - name: Set up Python
      uses: actions/setup-python@v2
      with:
        python-version: 3.12
    
    - name: Install dependencies
      run: |
        pip install pytest pytest-cov
        pip install -r requirements.txt
    
    - name: Run config bootstrap tests with coverage
      run: |
        pytest tests/config/test_config_bootstrap.py \
               --cov=app.core.config \
               --cov=common.config_service.client \
               --cov-fail-under=95 \
               --cov-report=term-missing
```

## Production Checklist

Before deploying to production, verify:

- [ ] `ENVIRONMENT` is set in deployment scripts
- [ ] `CONFIG_SERVICE_URL` is configured and reachable
- [ ] `CONFIG_SERVICE_API_KEY` is securely managed
- [ ] Config service health check passes
- [ ] Bootstrap tests achieve ≥95% coverage
- [ ] Fail-fast behavior tested and verified
- [ ] No fallback to environment variables for secrets

## Troubleshooting

### Common Bootstrap Failures

1. **ValueError: ENVIRONMENT environment variable is required**
   - **Cause**: Missing ENVIRONMENT variable
   - **Solution**: Set ENVIRONMENT in deployment configuration

2. **ConfigServiceError: Config service URL is required**
   - **Cause**: Missing CONFIG_SERVICE_URL variable
   - **Solution**: Configure CONFIG_SERVICE_URL in secrets

3. **ConfigServiceError: Config service API key is required**
   - **Cause**: Missing CONFIG_SERVICE_API_KEY variable
   - **Solution**: Configure CONFIG_SERVICE_API_KEY in secrets

4. **CONFIG SERVICE UNAVAILABLE - REFUSING TO START**
   - **Cause**: Config service health check failed
   - **Solution**: Verify config service is running and reachable

### Validation Commands

```bash
# Test config service connectivity
curl -H "Authorization: Bearer ${CONFIG_SERVICE_API_KEY}" \
     "${CONFIG_SERVICE_URL}/health"

# Run bootstrap smoke test
python tests/config/test_config_bootstrap.py

# Verify all environment variables
env | grep -E "(ENVIRONMENT|CONFIG_SERVICE_URL|CONFIG_SERVICE_API_KEY)"
```

## Architecture Compliance

This bootstrap configuration ensures compliance with:
- **Principle #1**: Config service is MANDATORY
- **Principle #2**: All secrets fetched from config_service
- **Principle #4**: No fallbacks to environment variables for secrets
- **Fail-fast requirement**: Service exits if config service unavailable