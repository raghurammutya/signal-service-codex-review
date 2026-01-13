#!/usr/bin/env python3
"""
Comprehensive test runner for Signal Service
"""
import os
import sys
import subprocess
import argparse
import time
from datetime import datetime

def run_command(command, capture_output=True):
    """Run shell command and return result"""
    print(f"Running: {command}")
    result = subprocess.run(
        command, 
        shell=True, 
        capture_output=capture_output, 
        text=True
    )
    return result

def setup_test_environment():
    """Setup test environment"""
    print("🔧 Setting up test environment...")
    
    # Start test infrastructure
    result = run_command("docker-compose -f docker-compose.test.yml up -d --build")
    if result.returncode != 0:
        print("❌ Failed to start test infrastructure")
        return False
    
    # Wait for services to be ready
    print("⏳ Waiting for services to be ready...")
    time.sleep(30)
    
    # Check service health
    health_checks = [
        "docker-compose -f docker-compose.test.yml exec -T postgres-test pg_isready -U signal_test_user",
        "docker-compose -f docker-compose.test.yml exec -T redis-test redis-cli -a test_password ping"
    ]
    
    for check in health_checks:
        result = run_command(check)
        if result.returncode != 0:
            print(f"❌ Health check failed: {check}")
            return False
    
    print("✅ Test environment ready")
    return True

def run_unit_tests():
    """Run unit tests"""
    print("\n🧪 Running unit tests...")
    
    command = """
    docker-compose -f docker-compose.test.yml exec -T signal-service-test \
    python -m pytest tests/unit/ -v --tb=short --cov=app --cov-report=term-missing
    """
    
    result = run_command(command, capture_output=False)
    return result.returncode == 0

def run_integration_tests():
    """Run integration tests"""
    print("\n🔗 Running integration tests...")
    
    command = """
    docker-compose -f docker-compose.test.yml exec -T signal-service-test \
    python -m pytest tests/integration/ -v --tb=short -m "integration"
    """
    
    result = run_command(command, capture_output=False)
    return result.returncode == 0

def run_performance_tests():
    """Run performance tests"""
    print("\n⚡ Running performance tests...")
    
    command = """
    docker-compose -f docker-compose.test.yml exec -T signal-service-test \
    python -m pytest tests/performance/ -v --tb=short -m "performance" --durations=10
    """
    
    result = run_command(command, capture_output=False)
    return result.returncode == 0

def run_e2e_tests():
    """Run end-to-end tests"""
    print("\n🎯 Running end-to-end tests...")
    
    command = """
    docker-compose -f docker-compose.test.yml exec -T signal-service-test \
    python -m pytest tests/e2e/ -v --tb=short -m "e2e"
    """
    
    result = run_command(command, capture_output=False)
    return result.returncode == 0

def run_specific_tests(test_pattern):
    """Run specific tests matching pattern"""
    print(f"\n🎯 Running tests matching: {test_pattern}")
    
    command = f"""
    docker-compose -f docker-compose.test.yml exec -T signal-service-test \
    python -m pytest {test_pattern} -v --tb=short
    """
    
    result = run_command(command, capture_output=False)
    return result.returncode == 0

def run_coverage_report():
    """Generate coverage report"""
    print("\n📊 Generating coverage report...")
    
    command = """
    docker-compose -f docker-compose.test.yml exec -T signal-service-test \
    python -m pytest tests/ --cov=app --cov-report=html:coverage_html --cov-report=xml:coverage.xml --cov-fail-under=85
    """
    
    result = run_command(command, capture_output=False)
    
    if result.returncode == 0:
        print("✅ Coverage report generated in coverage_html/")
    
    return result.returncode == 0

def run_linting():
    """Run code linting"""
    print("\n🔍 Running linting...")
    
    commands = [
        "docker-compose -f docker-compose.test.yml exec -T signal-service-test python -m flake8 app/ --max-line-length=100",
        "docker-compose -f docker-compose.test.yml exec -T signal-service-test python -m black --check app/",
        "docker-compose -f docker-compose.test.yml exec -T signal-service-test python -m isort --check-only app/"
    ]
    
    all_passed = True
    for command in commands:
        result = run_command(command)
        if result.returncode != 0:
            all_passed = False
            print(f"❌ Linting failed: {command}")
    
    if all_passed:
        print("✅ All linting checks passed")
    
    return all_passed

def cleanup_test_environment():
    """Cleanup test environment"""
    print("\n🧹 Cleaning up test environment...")
    
    result = run_command("docker-compose -f docker-compose.test.yml down -v")
    if result.returncode == 0:
        print("✅ Test environment cleaned up")
    else:
        print("❌ Failed to cleanup test environment")

def main():
    """Main test runner"""
    parser = argparse.ArgumentParser(description="Signal Service Test Runner")
    parser.add_argument(
        "--suite", 
        choices=["unit", "integration", "performance", "e2e", "all"], 
        default="all",
        help="Test suite to run"
    )
    parser.add_argument(
        "--pattern", 
        help="Specific test pattern to run"
    )
    parser.add_argument(
        "--no-setup", 
        action="store_true",
        help="Skip test environment setup"
    )
    parser.add_argument(
        "--no-cleanup", 
        action="store_true",
        help="Skip test environment cleanup"
    )
    parser.add_argument(
        "--coverage", 
        action="store_true",
        help="Generate coverage report"
    )
    parser.add_argument(
        "--lint", 
        action="store_true",
        help="Run linting checks"
    )
    
    args = parser.parse_args()
    
    start_time = datetime.now()
    print(f"🚀 Starting Signal Service test suite at {start_time}")
    
    success = True
    
    # Setup test environment
    if not args.no_setup:
        if not setup_test_environment():
            print("❌ Failed to setup test environment")
            sys.exit(1)
    
    try:
        # Run linting if requested
        if args.lint:
            if not run_linting():
                success = False
        
        # Run specific pattern if provided
        if args.pattern:
            if not run_specific_tests(args.pattern):
                success = False
        else:
            # Run test suites
            if args.suite in ["unit", "all"]:
                if not run_unit_tests():
                    success = False
            
            if args.suite in ["integration", "all"]:
                if not run_integration_tests():
                    success = False
            
            if args.suite in ["performance", "all"]:
                if not run_performance_tests():
                    success = False
            
            if args.suite in ["e2e", "all"]:
                if not run_e2e_tests():
                    success = False
        
        # Generate coverage report if requested
        if args.coverage:
            if not run_coverage_report():
                success = False
    
    finally:
        # Cleanup test environment
        if not args.no_cleanup:
            cleanup_test_environment()
    
    end_time = datetime.now()
    duration = end_time - start_time
    
    if success:
        print(f"\n✅ All tests completed successfully in {duration}")
        print("\n📊 Test Summary:")
        print("   ✓ Unit tests")
        print("   ✓ Integration tests") 
        print("   ✓ Performance tests")
        print("   ✓ End-to-end tests")
    else:
        print(f"\n❌ Some tests failed (completed in {duration})")
        sys.exit(1)

if __name__ == "__main__":
    main()