#!/bin/bash
# 3rd Party Package Integration Verification Suite
# 
# This script runs the complete verification suite for PyVolLib, scikit-learn,
# and pandas_ta integrations. Use this before any release to ensure all
# integrations are properly wired end-to-end.

set -e

echo "=========================================="
echo "3RD PARTY PACKAGE VERIFICATION SUITE"
echo "=========================================="
echo "Timestamp: $(date)"
echo

# Configuration
API_BASE_URL="${API_BASE_URL:-http://localhost:8003}"
VERBOSE="${VERBOSE:-false}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    local color=$1
    local message=$2
    echo -e "${color}${message}${NC}"
}

# Function to check if service is running
check_service() {
    print_status $YELLOW "Checking if signal service is running..."
    
    if curl -s --connect-timeout 5 "${API_BASE_URL}/health" > /dev/null 2>&1; then
        print_status $GREEN "✓ Service is running at ${API_BASE_URL}"
        return 0
    else
        print_status $RED "✗ Service is not running at ${API_BASE_URL}"
        print_status $YELLOW "Please start the service first:"
        print_status $YELLOW "  python -m app.main"
        print_status $YELLOW "  # or"
        print_status $YELLOW "  uvicorn app.main:app --host 0.0.0.0 --port 8003"
        return 1
    fi
}

# Function to run the main verification script
run_verification() {
    local verbose_flag=""
    if [ "$VERBOSE" = "true" ]; then
        verbose_flag="--verbose"
    fi
    
    print_status $BLUE "Running comprehensive verification script..."
    echo
    
    if python verify_3rd_party_integrations.py --api-base-url "$API_BASE_URL" $verbose_flag; then
        print_status $GREEN "✓ All verifications passed - READY FOR RELEASE"
        return 0
    else
        print_status $RED "✗ One or more verifications failed - DO NOT RELEASE"
        return 1
    fi
}

# Function to run quick smoke tests
run_smoke_tests() {
    print_status $BLUE "Running quick smoke tests..."
    
    echo "Checking indicator registration..."
    if python -c "
from app.services.register_indicators import register_all_indicators
from app.services.indicator_registry import IndicatorRegistry
register_all_indicators()
counts = IndicatorRegistry.count_by_category()
total = IndicatorRegistry.count()
print(f'Total indicators: {total}')
for cat, count in sorted(counts.items()):
    print(f'  {cat}: {count}')

# Verify critical integrations
expected = {'greeks': 7, 'clustering': 3}
for cat, exp_count in expected.items():
    actual = counts.get(cat, 0)
    if actual >= exp_count:
        print(f'✓ {cat}: {actual} >= {exp_count}')
    else:
        print(f'✗ {cat}: {actual} < {exp_count}')
        exit(1)
print('✓ All critical integrations registered')
"; then
        print_status $GREEN "✓ Smoke tests passed"
        return 0
    else
        print_status $RED "✗ Smoke tests failed"
        return 1
    fi
}

# Function to generate verification report
generate_report() {
    local timestamp=$(date +"%Y%m%d_%H%M%S")
    local report_file="verification_report_${timestamp}.md"
    
    print_status $BLUE "Generating verification report: ${report_file}"
    
    cat > "$report_file" << EOF
# 3rd Party Package Integration Verification Report

**Timestamp:** $(date)
**API Base URL:** ${API_BASE_URL}
**Environment:** ${ENVIRONMENT:-development}

## Verification Summary

This report documents the verification of PyVolLib, scikit-learn, and pandas_ta integrations.

### Critical Integration Points Verified

1. **PyVolLib (Options Greeks)**
   - Vectorized engine functionality
   - API accessibility via /api/v2/indicators/calculate
   - Real calculations (not placeholders)
   - Complete integration test coverage

2. **Scikit-learn (Clustering)**
   - DBSCAN, KMeans, IsolationForest indicators
   - Registry integration and API exposure
   - Dependency verification

3. **Pandas_ta (Technical Analysis)**
   - 244+ indicator support
   - Executor functionality with fallback
   - Strategy-based execution
   - API integration

4. **Universal Computation API**
   - All libraries accessible via unified endpoint
   - Library enumeration working
   - Cross-library compatibility

5. **QA Pipeline Integration**
   - Coverage reports reference integrations
   - Test artifacts properly archived
   - Documentation includes verification steps

### Commands Run

\`\`\`bash
# Service health check
curl ${API_BASE_URL}/health

# Comprehensive verification
python verify_3rd_party_integrations.py --api-base-url ${API_BASE_URL}

# Smoke tests
python -c "from app.services.register_indicators import register_all_indicators; ..."
\`\`\`

### Release Readiness

EOF

    if check_service && run_verification && run_smoke_tests; then
        echo "**Status:** ✅ **APPROVED FOR RELEASE**" >> "$report_file"
        echo "" >> "$report_file"
        echo "All 3rd party package integrations are properly wired and functional." >> "$report_file"
    else
        echo "**Status:** ❌ **NOT READY FOR RELEASE**" >> "$report_file"
        echo "" >> "$report_file"
        echo "One or more integration issues detected. Do not proceed with release." >> "$report_file"
    fi
    
    echo "" >> "$report_file"
    echo "---" >> "$report_file"
    echo "*Report generated by run_verification_suite.sh*" >> "$report_file"
    
    print_status $GREEN "Report generated: ${report_file}"
}

# Main execution
main() {
    local exit_code=0
    
    # Check prerequisites
    if ! command -v python &> /dev/null; then
        print_status $RED "Python is not installed or not in PATH"
        exit 1
    fi
    
    if ! command -v curl &> /dev/null; then
        print_status $RED "curl is not installed"
        exit 1
    fi
    
    # Run verification suite
    if ! check_service; then
        exit_code=1
    elif ! run_verification; then
        exit_code=1
    elif ! run_smoke_tests; then
        exit_code=1
    fi
    
    # Generate report regardless of outcome
    generate_report
    
    # Final status
    echo
    print_status $YELLOW "=========================================="
    if [ $exit_code -eq 0 ]; then
        print_status $GREEN "VERIFICATION SUITE COMPLETED SUCCESSFULLY"
        print_status $GREEN "All 3rd party integrations verified ✓"
    else
        print_status $RED "VERIFICATION SUITE FAILED"
        print_status $RED "Integration issues detected ✗"
    fi
    print_status $YELLOW "=========================================="
    
    exit $exit_code
}

# Handle command line arguments
case "${1:-}" in
    --help|-h)
        echo "Usage: $0 [OPTIONS]"
        echo ""
        echo "Options:"
        echo "  --help, -h          Show this help message"
        echo "  --verbose, -v       Enable verbose output"
        echo ""
        echo "Environment Variables:"
        echo "  API_BASE_URL        Base URL for API (default: http://localhost:8003)"
        echo "  VERBOSE            Enable verbose output (default: false)"
        echo "  ENVIRONMENT        Environment name for reporting"
        echo ""
        echo "Examples:"
        echo "  $0                           # Run with defaults"
        echo "  VERBOSE=true $0              # Run with verbose output"
        echo "  API_BASE_URL=http://prod:8003 $0  # Run against different service"
        exit 0
        ;;
    --verbose|-v)
        VERBOSE=true
        ;;
esac

# Run main function
main