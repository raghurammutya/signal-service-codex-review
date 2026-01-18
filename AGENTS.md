# Codex Review Guidelines

## Overview
This is an enterprise-grade financial signal processing service built with FastAPI, designed for high-frequency trading environments with comprehensive security, scalability, and reliability features.

## Review Priorities

### 🛡️ Security Focus (High Priority)
- **Malicious Code Detection**: Review `app/security/malicious_code_detector.py` - validate AST analysis patterns, behavioral monitoring, and threat detection accuracy
- **Access Control Lists (ACL)**: Examine `app/services/external_function_executor.py` - verify user isolation, role-based permissions, and audit logging
- **Authentication & Authorization**: Check `app/core/auth/` and `app/middleware/entitlement_middleware.py` - validate gateway trust, JWT handling, and F&O access controls
- **Secure Defaults**: Verify configuration in `app/core/config.py` - ensure secrets are properly handled and defaults are secure
- **PII/Logging Safety**: Review logging throughout codebase - ensure no sensitive financial data or credentials are logged

### 📈 Horizontal Scaling & Performance (High Priority)
- **Scaling Architecture**: Review `app/scaling/` directory - validate consistent hashing, work stealing, and backpressure monitoring
- **Idempotency**: Check signal processing workflows for idempotent operations
- **Queue Semantics**: Examine `app/scaling/work_stealing_queue.py` and Redis stream processing
- **Failure Recovery**: Validate circuit breakers, retry logic, and graceful degradation
- **Resource Management**: Check memory limits, CPU usage, and resource exhaustion protection

### 🧪 Test Quality & Coverage (Medium Priority)
- **Security Test Coverage**: Examine `test/security/` - validate malicious code scenarios and ACL enforcement tests
- **Edge Cases**: Review test assertions in `test/` directories for realistic scenarios
- **Integration Tests**: Check `test/integration/` for external service mocking and failure simulation
- **Performance Tests**: Validate `test/performance/` for load testing and concurrency scenarios

### 🚀 Production Readiness (Medium Priority)
- **Docker/Kubernetes**: Review `Dockerfile`, `docker-compose.*.yml`, and `k8s/` manifests
- **Configuration Management**: Check environment variable handling and secret management
- **Observability**: Validate monitoring setup in `monitoring/` and metrics collection
- **Deployment Safety**: Review startup scripts, health checks, and graceful shutdown procedures

## Specific Areas of Concern

### Critical Security Files
- `app/security/malicious_code_detector.py` - Multi-layer threat detection engine
- `app/security/crash_prevention.py` - System protection and resource monitoring
- `app/services/external_function_executor.py` - Secure script execution with ACL
- `app/core/auth/gateway_trust.py` - Network-level security validation

### Scaling & Performance Files
- `app/scaling/scalable_signal_processor.py` - Main scaling orchestrator
- `app/scaling/consistent_hash_manager.py` - Distributed load balancing
- `app/scaling/backpressure_monitor.py` - Auto-scaling recommendations
- `app/scaling/adaptive_load_shedder.py` - Priority-based request handling

### Core Business Logic
- `app/services/pandas_ta_executor.py` - Technical indicator computation (244+ indicators)
- `app/services/greeks_calculator.py` - Options pricing and Greeks calculations
- `app/api/v2/` - All API endpoints with authentication and validation

## Review Requirements

### Must Include in Findings
- **Specific file paths and function names** for each issue identified
- **Security impact assessment** for any vulnerabilities found
- **Performance implications** of identified bottlenecks
- **Concrete remediation steps** with code examples where applicable

### Focus Questions
1. **Security**: Can malicious external scripts bypass the sandbox? Are there ACL bypass paths?
2. **Scale**: Will the horizontal scaling work under 10x load? Are there race conditions?
3. **Reliability**: What happens when external services fail? Are failure modes handled gracefully?
4. **Maintainability**: Is the codebase structured for long-term maintenance and feature additions?

## Test Execution
- Primary test command: `pytest` (runs comprehensive test suite)
- Security tests: `pytest test/security/ -v`
- Performance tests: `pytest test/performance/ -v` 
- Integration tests: `pytest test/integration/ -v`

## Architecture Context
This service processes real-time financial data streams, executes custom trading algorithms, and provides WebSocket subscriptions for live market data. It must handle high throughput (1000s of requests/second), maintain sub-millisecond latencies for critical operations, and provide bank-grade security for financial computations.

Key external dependencies: PostgreSQL + TimescaleDB, Redis, MinIO object storage, and various microservices for alerts, communications, and subscriptions.