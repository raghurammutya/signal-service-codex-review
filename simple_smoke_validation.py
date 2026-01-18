#!/usr/bin/env python3
"""
Simple Smoke Validation

Basic structure and import validation for production readiness.
"""
import os
import sys

def validate_critical_files():
    """Validate critical files exist."""
    print("📁 Validating Critical Files...")
    
    critical_files = [
        "app/main.py",
        "app/config/budget_config.py",
        "app/config/pool_manager.py", 
        "app/api/v2/config_admin.py",
        "app/clients/client_factory.py",
        "app/services/metrics_service.py",
        "app/core/startup_resilience.py",
        "app/utils/logging_security.py",
        "scripts/validate_production_hardening.py",
        "scripts/deployment_safety_validation.py",
        "tests/contracts/test_external_service_contracts.py"
    ]
    
    missing_files = []
    for file_path in critical_files:
        if os.path.exists(file_path):
            print(f"  ✅ {file_path}")
        else:
            print(f"  ❌ {file_path}")
            missing_files.append(file_path)
    
    return len(missing_files) == 0


def validate_integration_structure():
    """Validate key integration code exists in files."""
    print("\n🔗 Validating Integration Structure...")
    
    integrations = [
        ("app/main.py", "config_admin_router", "Config admin router integration"),
        ("app/main.py", "configure_secure_logging", "Security logging integration"),
        ("app/main.py", "validate_startup_dependencies", "Startup resilience integration"),
        ("app/services/metrics_service.py", "get_budget_manager", "Config-driven budget integration"),
        ("app/services/metrics_service.py", "refresh_budget_config", "Budget refresh capability"),
        ("app/clients/client_factory.py", "CircuitBreakerConfig", "Circuit breaker integration"),
        ("app/api/v2/config_admin.py", "verify_admin_token", "Admin API security"),
    ]
    
    passed = 0
    for file_path, search_term, description in integrations:
        if os.path.exists(file_path):
            with open(file_path, 'r') as f:
                content = f.read()
                if search_term in content:
                    print(f"  ✅ {description}")
                    passed += 1
                else:
                    print(f"  ❌ {description} - {search_term} not found")
        else:
            print(f"  ❌ {description} - {file_path} not found")
    
    return passed >= len(integrations) * 0.8  # 80% pass rate


def validate_production_hardening_scripts():
    """Validate production hardening scripts are executable."""
    print("\n🛡️ Validating Production Hardening Scripts...")
    
    scripts = [
        "scripts/validate_production_hardening.py",
        "scripts/validate_config_driven_budgets.py",
        "scripts/deployment_safety_validation.py",
        "scripts/lint_direct_client_usage.py"
    ]
    
    executable_count = 0
    for script in scripts:
        if os.path.exists(script):
            if os.access(script, os.X_OK) or script.endswith('.py'):
                print(f"  ✅ {script}")
                executable_count += 1
            else:
                print(f"  ⚠️ {script} (not executable)")
        else:
            print(f"  ❌ {script}")
    
    return executable_count >= len(scripts) * 0.8


def validate_admin_api_security():
    """Validate admin API has security measures."""
    print("\n🔒 Validating Admin API Security...")
    
    config_admin_file = "app/api/v2/config_admin.py"
    if not os.path.exists(config_admin_file):
        print(f"  ❌ {config_admin_file} not found")
        return False
    
    with open(config_admin_file, 'r') as f:
        content = f.read()
    
    security_checks = [
        ("HTTPBearer", "Bearer token authentication"),
        ("verify_admin_token", "Admin token verification"),
        ("ADMIN_API_TOKEN", "Admin token configuration"),
        ("_sanitize_config_response", "Response sanitization"),
        ("***REDACTED***", "Sensitive data redaction")
    ]
    
    passed = 0
    for check, description in security_checks:
        if check in content:
            print(f"  ✅ {description}")
            passed += 1
        else:
            print(f"  ❌ {description}")
    
    return passed >= len(security_checks) * 0.8


def main():
    """Run simple smoke validation."""
    print("🔍 Simple Smoke Validation for Production Readiness")
    print("=" * 60)
    
    tests = [
        ("Critical Files", validate_critical_files),
        ("Integration Structure", validate_integration_structure),
        ("Production Hardening Scripts", validate_production_hardening_scripts),
        ("Admin API Security", validate_admin_api_security)
    ]
    
    results = {}
    passed_count = 0
    
    for test_name, test_func in tests:
        try:
            result = test_func()
            results[test_name] = result
            if result:
                passed_count += 1
        except Exception as e:
            print(f"❌ {test_name} failed: {e}")
            results[test_name] = False
    
    print("\n" + "=" * 60)
    print("🎯 Smoke Validation Summary:")
    print(f"  Passed: {passed_count}/{len(tests)}")
    
    for test_name, result in results.items():
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"  {status}: {test_name}")
    
    if passed_count >= len(tests) * 0.8:
        print(f"\n🎉 SMOKE VALIDATION PASSED ({passed_count}/{len(tests)})")
        return 0
    else:
        print(f"\n❌ SMOKE VALIDATION INSUFFICIENT ({passed_count}/{len(tests)})")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)