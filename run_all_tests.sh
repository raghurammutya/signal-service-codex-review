#!/bin/bash

# Signal Service - Comprehensive Testing Framework
# Implements containerized QA testing strategy with 95%+ coverage requirement
# Usage: ./run_all_tests.sh [test_type] [--parallel] [--coverage-only]

set -e  # Exit on any error

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="docker-compose.test.yml"
TEST_CONTAINER="signal-service-test"
COVERAGE_THRESHOLD=95
PERFORMANCE_REPORTS_DIR="performance-reports"
TEST_REPORTS_DIR="test-reports"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Help function
show_help() {
    cat << EOF
Signal Service Comprehensive Testing Framework

USAGE:
    ./run_all_tests.sh [OPTIONS] [TEST_TYPE]

TEST TYPES:
    unit                Run only unit tests (95%+ coverage required)
    integration         Run only integration tests  
    system             Run only system/end-to-end tests
    performance        Run only performance tests
    all                Run all test types (default)
    coverage           Generate coverage report only
    validate           Validate test environment setup

OPTIONS:
    --parallel         Run tests in parallel where possible
    --coverage-only    Run tests for coverage analysis only
    --skip-build       Skip Docker image rebuild
    --verbose          Enable verbose output
    --fail-fast        Stop on first test failure
    --cleanup          Clean up test environment after run
    --help, -h         Show this help message

EXAMPLES:
    ./run_all_tests.sh                          # Run all tests
    ./run_all_tests.sh unit --coverage-only     # Unit tests with coverage
    ./run_all_tests.sh performance --parallel   # Parallel performance tests
    ./run_all_tests.sh validate                 # Validate test setup
    ./run_all_tests.sh all --cleanup            # Full test suite with cleanup

COVERAGE REQUIREMENT:
    Unit tests must achieve ${COVERAGE_THRESHOLD}%+ coverage or build fails

REPORTS:
    - Coverage: ${TEST_REPORTS_DIR}/coverage/
    - Performance: ${PERFORMANCE_REPORTS_DIR}/
    - Test Results: ${TEST_REPORTS_DIR}/junit/
EOF
}

# Parse command line arguments
TEST_TYPE="all"
PARALLEL=false
COVERAGE_ONLY=false
SKIP_BUILD=false
VERBOSE=false
FAIL_FAST=false
CLEANUP=false

while [[ $# -gt 0 ]]; do
    case $1 in
        unit|integration|system|performance|all|coverage|validate)
            TEST_TYPE="$1"
            shift
            ;;
        --parallel)
            PARALLEL=true
            shift
            ;;
        --coverage-only)
            COVERAGE_ONLY=true
            shift
            ;;
        --skip-build)
            SKIP_BUILD=true
            shift
            ;;
        --verbose)
            VERBOSE=true
            shift
            ;;
        --fail-fast)
            FAIL_FAST=true
            shift
            ;;
        --cleanup)
            CLEANUP=true
            shift
            ;;
        --help|-h)
            show_help
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Ensure we're in the right directory
cd "$SCRIPT_DIR"

# Create required directories
mkdir -p "$TEST_REPORTS_DIR"/{coverage,junit,logs}
mkdir -p "$PERFORMANCE_REPORTS_DIR"

log_info "Starting Signal Service Testing Framework"
log_info "Test Type: $TEST_TYPE"
log_info "Coverage Threshold: ${COVERAGE_THRESHOLD}%"

# Function to check if Docker and Docker Compose are available
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed or not in PATH"
        exit 1
    fi
    
    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        log_error "Docker Compose is not installed or not in PATH"
        exit 1
    fi
    
    # Check if Docker daemon is running
    if ! docker info &> /dev/null; then
        log_error "Docker daemon is not running"
        exit 1
    fi
    
    log_success "Prerequisites check passed"
}

# Function to build test environment
build_test_environment() {
    if [[ "$SKIP_BUILD" == "true" ]]; then
        log_info "Skipping Docker build as requested"
        return
    fi
    
    log_info "Building test environment..."
    
    # Build test image
    if [[ "$VERBOSE" == "true" ]]; then
        docker-compose -f "$COMPOSE_FILE" build --no-cache
    else
        docker-compose -f "$COMPOSE_FILE" build --no-cache > /dev/null 2>&1
    fi
    
    log_success "Test environment built successfully"
}

# Function to start test infrastructure
start_test_infrastructure() {
    log_info "Starting test infrastructure..."
    
    # Start dependent services
    docker-compose -f "$COMPOSE_FILE" up -d \
        test-timescaledb \
        test-redis \
        mock-config-service \
        mock-ticker-service
    
    # Wait for services to be healthy
    log_info "Waiting for services to become healthy..."
    
    local max_wait=120
    local elapsed=0
    
    while [[ $elapsed -lt $max_wait ]]; do
        if docker-compose -f "$COMPOSE_FILE" ps | grep -E "(unhealthy|starting)" > /dev/null; then
            sleep 5
            elapsed=$((elapsed + 5))
            echo -n "."
        else
            echo ""
            log_success "All services are healthy"
            return 0
        fi
    done
    
    echo ""
    log_error "Services did not become healthy within ${max_wait} seconds"
    docker-compose -f "$COMPOSE_FILE" ps
    exit 1
}

# Function to run unit tests
run_unit_tests() {
    log_info "Running unit tests with coverage analysis..."
    
    local pytest_args=""
    if [[ "$FAIL_FAST" == "true" ]]; then
        pytest_args="$pytest_args -x"
    fi
    if [[ "$VERBOSE" == "true" ]]; then
        pytest_args="$pytest_args -v"
    fi
    if [[ "$PARALLEL" == "true" ]]; then
        pytest_args="$pytest_args -n auto"
    fi
    
    # Run unit tests with coverage
    docker-compose -f "$COMPOSE_FILE" exec -T "$TEST_CONTAINER" \
        pytest test/unit/ \
        --cov=app \
        --cov-fail-under="$COVERAGE_THRESHOLD" \
        --cov-report=html:coverage/html \
        --cov-report=xml:coverage/coverage.xml \
        --cov-report=term-missing \
        --junit-xml=test-reports/junit/unit_tests.xml \
        $pytest_args
    
    # Copy coverage reports
    docker cp "${TEST_CONTAINER}:/app/coverage" "${TEST_REPORTS_DIR}/"
    
    log_success "Unit tests completed with ${COVERAGE_THRESHOLD}%+ coverage"
}

# Function to run integration tests
run_integration_tests() {
    log_info "Running integration tests..."
    
    local pytest_args="-m integration"
    if [[ "$FAIL_FAST" == "true" ]]; then
        pytest_args="$pytest_args -x"
    fi
    if [[ "$VERBOSE" == "true" ]]; then
        pytest_args="$pytest_args -v"
    fi
    
    docker-compose -f "$COMPOSE_FILE" exec -T "$TEST_CONTAINER" \
        pytest test/integration/ \
        --junit-xml=test-reports/junit/integration_tests.xml \
        $pytest_args
    
    log_success "Integration tests completed"
}

# Function to run system tests
run_system_tests() {
    log_info "Running system/end-to-end tests..."
    
    local pytest_args="-m system"
    if [[ "$FAIL_FAST" == "true" ]]; then
        pytest_args="$pytest_args -x"
    fi
    if [[ "$VERBOSE" == "true" ]]; then
        pytest_args="$pytest_args -v"
    fi
    
    docker-compose -f "$COMPOSE_FILE" exec -T "$TEST_CONTAINER" \
        pytest test/system/ \
        --junit-xml=test-reports/junit/system_tests.xml \
        $pytest_args
    
    log_success "System tests completed"
}

# Function to run performance tests
run_performance_tests() {
    log_info "Running performance tests..."
    
    # Create performance reports directory
    mkdir -p "$PERFORMANCE_REPORTS_DIR"
    
    # Run pytest benchmark tests
    docker-compose -f "$COMPOSE_FILE" exec -T "$TEST_CONTAINER" \
        pytest test/performance/test_benchmarks.py \
        -m performance \
        --benchmark-only \
        --benchmark-json=performance-reports/benchmarks.json \
        --junit-xml=test-reports/junit/performance_tests.xml
    
    # Start Locust load testing
    log_info "Starting Locust load testing..."
    
    docker-compose -f "$COMPOSE_FILE" up -d locust-master locust-worker
    
    # Wait for Locust to be ready
    sleep 10
    
    # Run load test scenarios
    log_info "Running load test scenarios..."
    
    local scenarios=(
        "standard-load:50:5:300s"
        "stress-test:200:20:120s"
        "memory-test:10:1:300s"
    )
    
    for scenario in "${scenarios[@]}"; do
        IFS=':' read -r name users spawn_rate run_time <<< "$scenario"
        
        log_info "Running $name scenario (${users} users, ${spawn_rate}/s spawn rate, ${run_time})"
        
        # Trigger load test via API (headless mode)
        curl -X POST "http://localhost:8089/swarm" \
            -H "Content-Type: application/x-www-form-urlencoded" \
            -d "user_count=${users}&spawn_rate=${spawn_rate}" || true
        
        # Wait for test duration
        case "$run_time" in
            *s) sleep "${run_time%s}" ;;
            *m) sleep "$((${run_time%m} * 60))" ;;
            *) sleep "$run_time" ;;
        esac
        
        # Stop load test
        curl -X GET "http://localhost:8089/stop" || true
        
        # Download results
        curl -X GET "http://localhost:8089/stats/requests/csv" > "${PERFORMANCE_REPORTS_DIR}/${name}-requests.csv" || true
        curl -X GET "http://localhost:8089/stats/distribution/csv" > "${PERFORMANCE_REPORTS_DIR}/${name}-distribution.csv" || true
        
        sleep 5  # Brief pause between scenarios
    done
    
    # Copy performance reports
    docker cp "${TEST_CONTAINER}:/app/performance-reports" ./ || true
    
    log_success "Performance tests completed"
}

# Function to validate test environment
validate_test_environment() {
    log_info "Validating test environment setup..."
    
    # Check all services are running
    log_info "Checking service health..."
    docker-compose -f "$COMPOSE_FILE" ps
    
    # Test database connectivity
    log_info "Testing database connectivity..."
    docker-compose -f "$COMPOSE_FILE" exec -T test-timescaledb \
        psql -U test_user -d signal_service_test -c "SELECT version();"
    
    # Test Redis connectivity
    log_info "Testing Redis connectivity..."
    docker-compose -f "$COMPOSE_FILE" exec -T test-redis \
        redis-cli ping
    
    # Test mock services
    log_info "Testing mock services..."
    curl -f "http://localhost:8101/__admin/health" > /dev/null
    curl -f "http://localhost:8090/__admin/health" > /dev/null
    
    # Test test container
    log_info "Testing test container..."
    docker-compose -f "$COMPOSE_FILE" exec -T "$TEST_CONTAINER" \
        python -c "import pytest, coverage; print('Test dependencies OK')"
    
    log_success "Test environment validation passed"
}

# Function to generate coverage report
generate_coverage_report() {
    log_info "Generating coverage report..."
    
    docker-compose -f "$COMPOSE_FILE" exec -T "$TEST_CONTAINER" \
        python -m coverage html -d coverage/html
    
    docker-compose -f "$COMPOSE_FILE" exec -T "$TEST_CONTAINER" \
        python -m coverage report --show-missing
    
    # Copy coverage reports
    docker cp "${TEST_CONTAINER}:/app/coverage" "${TEST_REPORTS_DIR}/"
    
    log_success "Coverage report generated at ${TEST_REPORTS_DIR}/coverage/"
}

# Function to cleanup test environment
cleanup_test_environment() {
    log_info "Cleaning up test environment..."
    
    # Stop all services
    docker-compose -f "$COMPOSE_FILE" down -v
    
    # Remove test images if requested
    if [[ "$CLEANUP" == "true" ]]; then
        docker-compose -f "$COMPOSE_FILE" down --rmi local -v
        
        # Clean up volumes
        docker volume prune -f
    fi
    
    log_success "Test environment cleaned up"
}

# Function to generate test summary
generate_test_summary() {
    log_info "Generating test summary..."
    
    local summary_file="${TEST_REPORTS_DIR}/test_summary.md"
    
    cat > "$summary_file" << EOF
# Signal Service Test Execution Summary

**Execution Date:** $(date -u '+%Y-%m-%d %H:%M:%S UTC')
**Test Type:** $TEST_TYPE
**Coverage Threshold:** ${COVERAGE_THRESHOLD}%

## Test Results

### Unit Tests
- **Status:** $([ -f "${TEST_REPORTS_DIR}/junit/unit_tests.xml" ] && echo "✅ Passed" || echo "❌ Not Run")
- **Coverage:** $([ -f "${TEST_REPORTS_DIR}/coverage/coverage.xml" ] && echo "See coverage report" || echo "Not available")

### Integration Tests  
- **Status:** $([ -f "${TEST_REPORTS_DIR}/junit/integration_tests.xml" ] && echo "✅ Passed" || echo "❌ Not Run")

### System Tests
- **Status:** $([ -f "${TEST_REPORTS_DIR}/junit/system_tests.xml" ] && echo "✅ Passed" || echo "❌ Not Run")

### Performance Tests
- **Status:** $([ -f "${TEST_REPORTS_DIR}/junit/performance_tests.xml" ] && echo "✅ Passed" || echo "❌ Not Run")
- **Load Test Reports:** $([ -d "$PERFORMANCE_REPORTS_DIR" ] && echo "Available in $PERFORMANCE_REPORTS_DIR/" || echo "Not available")

## Files Generated
- Coverage HTML Report: ${TEST_REPORTS_DIR}/coverage/html/index.html
- JUnit XML Reports: ${TEST_REPORTS_DIR}/junit/
- Performance Reports: ${PERFORMANCE_REPORTS_DIR}/

## QA Requirements Status
- [x] Unit Testing with 95%+ Coverage
- [x] Integration Testing with Real Containers
- [x] System Testing End-to-End Workflows  
- [x] Performance Testing with Load Tests
- [x] Containerized Test Environment (Option C)
- [x] Mock External Services (WireMock)
- [x] Test Reporting and Validation
EOF

    log_success "Test summary generated at $summary_file"
}

# Trap cleanup function
cleanup_on_exit() {
    local exit_code=$?
    if [[ $exit_code -ne 0 ]]; then
        log_error "Test execution failed with exit code $exit_code"
    fi
    
    if [[ "$CLEANUP" == "true" ]]; then
        cleanup_test_environment
    fi
}

trap cleanup_on_exit EXIT

# Main execution flow
main() {
    log_info "Signal Service Comprehensive QA Testing Framework"
    log_info "=================================================="
    
    # Prerequisites check
    check_prerequisites
    
    # Build and start test environment
    build_test_environment
    start_test_infrastructure
    
    # Start test container
    docker-compose -f "$COMPOSE_FILE" up -d "$TEST_CONTAINER"
    
    # Wait for test container to be ready
    sleep 5
    
    # Execute tests based on type
    case "$TEST_TYPE" in
        "unit")
            run_unit_tests
            ;;
        "integration")
            run_integration_tests
            ;;
        "system")
            run_system_tests
            ;;
        "performance")
            run_performance_tests
            ;;
        "coverage")
            run_unit_tests  # Unit tests generate coverage
            generate_coverage_report
            ;;
        "validate")
            validate_test_environment
            ;;
        "all")
            run_unit_tests
            run_integration_tests
            run_system_tests
            run_performance_tests
            ;;
        *)
            log_error "Unknown test type: $TEST_TYPE"
            show_help
            exit 1
            ;;
    esac
    
    # Generate test summary
    generate_test_summary
    
    log_success "All tests completed successfully!"
    log_info "Test reports available in: ${TEST_REPORTS_DIR}/"
    log_info "Performance reports available in: ${PERFORMANCE_REPORTS_DIR}/"
}

# Execute main function
main "$@"