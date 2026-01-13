# Signal Service Comprehensive QA Testing Guide

## Overview

This document provides comprehensive guidance for testing the Signal Service using the implemented containerized testing framework. The testing strategy follows "Option C" as requested - all test cases are baked into Docker containers and executed from there.

## Quick Start

```bash
# Run all tests with 95%+ coverage requirement
./run_all_tests.sh

# Run only unit tests with coverage
./run_all_tests.sh unit --coverage-only

# Run performance tests in parallel
./run_all_tests.sh performance --parallel

# Validate test environment setup
./run_all_tests.sh validate

# Run full test suite with cleanup
./run_all_tests.sh all --cleanup
```

## Testing Strategy Implementation

### 1. Unit Testing (95%+ Coverage Required)
- **Location**: `test/unit/`
- **Coverage Threshold**: 95% (enforced)
- **Framework**: pytest with coverage.py
- **Execution**: Containerized with mocked dependencies

```bash
# Run unit tests
./run_all_tests.sh unit

# Coverage report location
./test-reports/coverage/html/index.html
```

**Key Features:**
- Comprehensive unit tests for all core components
- 95%+ code coverage requirement (build fails if not met)
- Critical architectural fixes validation
- Performance-focused unit tests
- Mock external services (config_service, ticker_service)

### 2. Integration Testing
- **Location**: `test/integration/`
- **Containers**: Real PostgreSQL (TimescaleDB), Redis, Kafka
- **Services**: WireMock for external service simulation
- **Execution**: TestContainers with real infrastructure

```bash
# Run integration tests
./run_all_tests.sh integration
```

**Key Features:**
- Real database connections with TimescaleDB
- Redis integration for caching and streams  
- Service-to-service communication testing
- Error propagation validation
- Concurrent operation testing

### 3. System Testing (End-to-End)
- **Location**: `test/system/`
- **Scope**: Complete workflows from API to database
- **Approach**: Full application stack testing
- **Validation**: End-to-end data flow verification

```bash
# Run system tests
./run_all_tests.sh system
```

**Key Features:**
- Complete Greeks calculation workflows
- Smart Money indicators processing
- Custom script execution validation
- API error handling workflows
- Data consistency verification

### 4. Performance Testing
- **Location**: `test/performance/`
- **Tools**: Locust (load testing) + pytest-benchmark
- **Metrics**: Response time, throughput, resource usage
- **Scenarios**: Multiple load patterns

```bash
# Run performance tests
./run_all_tests.sh performance
```

**Performance Test Types:**
- **Benchmark Tests**: Individual component performance
- **Load Tests**: Multiple user simulation with Locust
- **Stress Tests**: High-load scenarios
- **Memory Tests**: Large dataset processing

## Test Environment Architecture

### Docker Compose Test Stack
The testing environment includes:

```yaml
services:
  # Core Infrastructure
  test-timescaledb          # PostgreSQL with TimescaleDB
  test-redis               # Redis for caching/streams
  test-kafka              # Event streaming (with Zookeeper)
  
  # Mock Services  
  mock-config-service     # WireMock for config service
  mock-ticker-service     # WireMock for ticker service
  
  # Test Execution
  signal-service-test     # Main test runner container
  
  # Load Testing
  locust-master           # Locust master for load tests
  locust-worker           # Locust workers (scalable)
  
  # Monitoring
  prometheus-test         # Test metrics collection
  elasticsearch-test      # Test log aggregation
```

### Service Health Validation
All services include health checks and the test framework waits for full readiness before proceeding:

```bash
# Health check validation
curl -f http://localhost:8101/__admin/health  # Config service mock
curl -f http://localhost:8090/__admin/health  # Ticker service mock
```

## Test Data and Fixtures

### Database Schema
- **Location**: `test/fixtures/sql/init_test_schema.sql`
- **Features**: TimescaleDB hypertables, test data, validation functions
- **Tables**: signal_greeks, signal_indicators, market_data, computation_metrics

### Mock Service Data
- **Config Service**: `test/mocks/config-service/mappings/`
- **Ticker Service**: `test/mocks/ticker-service/mappings/`
- **Format**: WireMock JSON mappings

### Test Data Factories
- **Location**: `test/conftest.py`
- **Features**: Sample Greeks data, market data, performance test datasets
- **Fixtures**: Database containers, Redis connections, mock services

## Critical Fixes Validation

The testing framework validates all critical architectural fixes:

### 1. ticker_service_v2 Elimination
- **Test**: `test/unit/core/test_critical_fixes.py::test_no_ticker_service_v2_references`
- **Validation**: Scans entire codebase for eliminated references

### 2. NIFTY Reference Removal  
- **Test**: `test/unit/core/test_critical_fixes.py::test_no_nifty_references`
- **Validation**: Ensures all NIFTY hardcoded references are removed

### 3. Silent Fallback Fixes
- **Test**: Multiple tests across repositories and services
- **Validation**: Ensures errors are raised, not silently handled

### 4. Error Handling Validation
- **Test**: Repository and service layer error propagation
- **Validation**: DatabaseError exceptions are properly raised

## Performance Testing Details

### Benchmark Tests
```python
# Example benchmark test
@pytest.mark.benchmark(group="greeks")  
def test_greeks_calculation_benchmark(self, benchmark):
    result = benchmark(calculate_greeks)
    assert stats.mean < 0.01  # Must be under 10ms
```

### Load Test Scenarios
| Scenario | Users | Spawn Rate | Duration | Purpose |
|----------|-------|------------|----------|---------|
| Standard Load | 50 | 5/sec | 5min | Normal operation |
| Stress Test | 200 | 20/sec | 2min | High load |  
| Memory Test | 10 | 1/sec | 5min | Large datasets |

### Performance Assertions
- Greeks calculation: < 10ms average
- API responses: < 500ms average  
- Memory usage: < 500MB peak
- Concurrent operations: > 1.5x threading speedup

## Test Reporting

### HTML Report Generation
```bash
# Generate comprehensive HTML report
python generate_test_report.py \
    --reports-dir test-reports \
    --performance-dir performance-reports \
    --output signal_service_test_report.html
```

### Report Contents
- **Test Summary**: Overall pass/fail status, coverage metrics
- **Coverage Analysis**: Line and branch coverage with threshold validation  
- **Performance Results**: Benchmark data, load test metrics
- **Critical Fixes**: Architectural validation status
- **QA Compliance**: Requirements checklist verification

### CI/CD Integration
- **GitHub Actions**: `.github/workflows/qa-testing.yml`
- **Triggers**: Push, PR, scheduled runs, manual dispatch
- **Artifacts**: Test reports, coverage data, performance metrics
- **Notifications**: PR comments with test results

## Test Execution Examples

### Development Testing
```bash
# Quick unit test run during development
./run_all_tests.sh unit --fail-fast

# Integration tests with verbose output  
./run_all_tests.sh integration --verbose

# Performance validation
./run_all_tests.sh performance --parallel
```

### Pre-Release Testing
```bash
# Full QA validation before release
./run_all_tests.sh all --cleanup

# Generate release test report
python generate_test_report.py --output release_test_report.html
```

### Continuous Integration
```bash
# CI-optimized execution
./run_all_tests.sh all --parallel --coverage-only
```

## Troubleshooting

### Common Issues

**1. Service Health Check Failures**
```bash
# Check service logs
docker-compose -f docker-compose.test.yml logs test-timescaledb
docker-compose -f docker-compose.test.yml logs mock-config-service
```

**2. Coverage Threshold Not Met**
```bash
# Run coverage report to identify missing coverage
./run_all_tests.sh coverage
open test-reports/coverage/html/index.html
```

**3. Performance Test Failures**
```bash
# Check performance reports for bottlenecks
ls -la performance-reports/
cat performance-reports/standard-load-requests.csv
```

### Debug Mode
```bash
# Run with verbose output and no cleanup
./run_all_tests.sh all --verbose --skip-build
```

## QA Requirements Compliance

✅ **Completed Requirements:**

1. **Unit Testing with 95%+ Coverage** - Implemented with enforced threshold
2. **Integration Testing** - Real containers with TestContainers framework  
3. **Performance Testing** - Locust + pytest-benchmark integration
4. **System Testing** - End-to-end workflow validation
5. **Containerized Environment** - Option C fully implemented
6. **Mock External Services** - WireMock for config/ticker services
7. **Test Reporting** - Comprehensive HTML reports with metrics
8. **Critical Fixes Validation** - Architectural compliance testing

## Maintenance

### Adding New Tests
1. **Unit Tests**: Add to appropriate `test/unit/` subdirectory
2. **Integration Tests**: Use TestContainers patterns from existing tests
3. **System Tests**: Follow workflow patterns in `test/system/`
4. **Performance Tests**: Add benchmarks or Locust scenarios

### Updating Test Data
1. **Database Schema**: Modify `test/fixtures/sql/init_test_schema.sql`
2. **Mock Responses**: Update WireMock mappings in `test/mocks/`
3. **Test Fixtures**: Update `test/conftest.py` factories

### Infrastructure Updates
1. **Docker Services**: Modify `docker-compose.test.yml`
2. **CI/CD Pipeline**: Update `.github/workflows/qa-testing.yml`  
3. **Test Scripts**: Enhance `run_all_tests.sh` as needed

This comprehensive testing framework ensures Signal Service meets all QA requirements before production deployment, with containerized execution, comprehensive coverage, and thorough validation of all critical architectural fixes.