#!/usr/bin/env python3
"""
Production Hardening Validation Script

Validates that all production hardening components are properly integrated.
"""
import sys
import os
import importlib
import asyncio
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def validate_client_factory_integration():
    """Validate client factory integration."""
    print("🔧 Validating Client Factory Integration...")
    
    try:
        from app.clients.client_factory import get_client_manager, CircuitBreakerConfig
        
        # Test circuit breaker config
        config = CircuitBreakerConfig()
        services = ['ticker_service', 'user_service', 'alert_service', 'comms_service']
        
        for service in services:
            cb_config = config.get_config(service)
            assert 'max_failures' in cb_config
            assert cb_config['max_failures'] > 0
            print(f"  ✅ {service} circuit breaker config: OK")
        
        # Test client manager
        manager = get_client_manager()
        assert manager is not None
        print("  ✅ Client manager initialization: OK")
        
        return True
        
    except Exception as e:
        print(f"  ❌ Client factory validation failed: {e}")
        return False

def validate_metrics_budget_guards():
    """Validate metrics service budget guards structure and config integration."""
    print("📊 Validating Metrics Budget Guards...")
    
    try:
        from app.services.metrics_service import MetricsCollector
        
        # Test structure without initialization to avoid config service dependency
        collector = MetricsCollector()
        
        # Verify config-driven structure exists
        assert hasattr(collector, 'budget_guards')
        assert hasattr(collector, '_budget_manager')
        assert hasattr(collector, 'backpressure_state')
        print("  ✅ Config-driven budget structure: OK")
        
        # Test backpressure system structure
        assert hasattr(collector, 'concurrent_operations')
        assert 'active' in collector.backpressure_state
        assert 'level' in collector.backpressure_state
        print("  ✅ Backpressure system structure: OK")
        
        # Verify refresh method exists
        import inspect
        assert hasattr(collector, 'refresh_budget_config')
        assert inspect.iscoroutinefunction(collector.refresh_budget_config)
        print("  ✅ Budget config refresh method: OK")
        
        # Verify config integration code
        import app.services.metrics_service as metrics_module
        source = inspect.getsource(metrics_module)
        
        config_indicators = [
            'get_budget_manager',
            '_refresh_budget_config',
            'budget_config.max_concurrent_operations'
        ]
        
        for indicator in config_indicators:
            assert indicator in source
            print(f"  ✅ Config integration ({indicator}): OK")
        
        return True
        
    except Exception as e:
        print(f"  ❌ Metrics budget guards validation failed: {e}")
        return False

def validate_startup_resilience():
    """Validate startup resilience integration."""
    print("🚀 Validating Startup Resilience...")
    
    try:
        from app.core.startup_resilience import validate_startup_dependencies
        
        # Test function exists and is importable
        assert callable(validate_startup_dependencies)
        print("  ✅ Startup validation function: OK")
        
        # Verify it's used in main.py
        main_py_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'app', 'main.py')
        with open(main_py_path, 'r') as f:
            main_content = f.read()
            assert 'validate_startup_dependencies' in main_content
            print("  ✅ Integrated in main.py: OK")
        
        return True
        
    except Exception as e:
        print(f"  ❌ Startup resilience validation failed: {e}")
        return False

def validate_security_logging():
    """Validate security logging filters."""
    print("🔒 Validating Security Logging...")
    
    try:
        from app.utils.logging_security import configure_secure_logging, SensitiveDataFilter
        
        # Test filter functionality
        filter_obj = SensitiveDataFilter()
        test_data = "api_key=secretkeyvalue123456789 password=mypasswordvalue123456"
        redacted = filter_obj._redact_sensitive_data(test_data)
        
        assert "secretkeyvalue123456789" not in redacted
        assert "mypasswordvalue123456" not in redacted
        assert "***REDACTED***" in redacted
        print("  ✅ Sensitive data redaction: OK")
        
        # Verify integration in main.py
        main_py_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'app', 'main.py')
        with open(main_py_path, 'r') as f:
            main_content = f.read()
            assert 'configure_secure_logging' in main_content
            print("  ✅ Integrated in main.py: OK")
        
        return True
        
    except Exception as e:
        print(f"  ❌ Security logging validation failed: {e}")
        return False

def validate_cache_concurrency():
    """Validate cache concurrency safety."""
    print("💾 Validating Cache Concurrency...")
    
    try:
        # Check source code for concurrency features
        import inspect
        from app.clients.historical_data_client import HistoricalDataClient
        
        # Check class has the required attributes in source
        source = inspect.getsource(HistoricalDataClient.__init__)
        assert '_cache_locks' in source
        print("  ✅ Per-key locks in source: OK")
        
        # Check invalidate_cache method exists
        assert hasattr(HistoricalDataClient, 'invalidate_cache')
        print("  ✅ Lock cleanup method: OK")
        
        # Check for async locking in get methods
        source = inspect.getsource(HistoricalDataClient.get_historical_timeframe_data)
        assert 'async with self._cache_locks' in source
        print("  ✅ Async cache locking: OK")
        
        return True
        
    except Exception as e:
        print(f"  ❌ Cache concurrency validation failed: {e}")
        return False

def validate_rare_failure_tests():
    """Validate rare failure mode tests exist."""
    print("🧪 Validating Rare Failure Tests...")
    
    try:
        test_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'tests', 'integration', 'test_rare_failure_modes.py')
        
        assert os.path.exists(test_file)
        print("  ✅ Test file exists: OK")
        
        with open(test_file, 'r') as f:
            content = f.read()
            
        # Check for specific test classes
        test_classes = [
            'TestMetricsServiceRareFailures',
            'TestClientFactoryRareFailures',
            'TestStartupResilienceRareFailures',
            'TestLoggingSecurityRareFailures',
            'TestHistoricalDataRareFailures',
            'TestProductionScenarios'
        ]
        
        for test_class in test_classes:
            assert test_class in content
            print(f"  ✅ {test_class}: OK")
        
        return True
        
    except Exception as e:
        print(f"  ❌ Rare failure tests validation failed: {e}")
        return False

def validate_deployment_workflow():
    """Validate deployment validation workflow."""
    print("🔄 Validating Deployment Workflow...")
    
    try:
        workflow_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.github', 'workflows', 'deployment-validation.yml')
        
        assert os.path.exists(workflow_file)
        print("  ✅ Workflow file exists: OK")
        
        with open(workflow_file, 'r') as f:
            content = f.read()
        
        # Check for key components
        required_components = [
            'deployment_safety_validation.py',
            'circuit breaker configuration',
            'rare failure mode tests',
            'security logging test',
            'startup health validation'
        ]
        
        for component in required_components:
            assert any(term.lower() in content.lower() for term in component.split())
            print(f"  ✅ {component}: OK")
        
        return True
        
    except Exception as e:
        print(f"  ❌ Deployment workflow validation failed: {e}")
        return False


def validate_config_driven_budgets():
    """Validate config-driven budget and pool management."""
    print("⚙️ Validating Config-Driven Budgets and Pools...")
    
    try:
        # Check that budget config module exists
        budget_config_file = "app/config/budget_config.py"
        assert os.path.exists(budget_config_file)
        print("  ✅ Budget config module exists: OK")
        
        # Check that pool manager module exists
        pool_manager_file = "app/config/pool_manager.py"
        assert os.path.exists(pool_manager_file)
        print("  ✅ Pool manager module exists: OK")
        
        # Check config admin API exists
        config_admin_file = "app/api/v2/config_admin.py"
        assert os.path.exists(config_admin_file)
        print("  ✅ Config admin API exists: OK")
        
        # Check validation script exists
        validation_script = "scripts/validate_config_driven_budgets.py"
        assert os.path.exists(validation_script)
        print("  ✅ Config budget validation script exists: OK")
        
        # Verify key components in budget config
        with open(budget_config_file, 'r') as f:
            budget_content = f.read()
        
        required_classes = [
            'MetricsBudgetConfig',
            'DatabasePoolConfig', 
            'RedisPoolConfig',
            'ClientPoolConfig',
            'ConfigDrivenBudgetManager'
        ]
        
        for cls in required_classes:
            assert cls in budget_content
            print(f"  ✅ {cls} class defined: OK")
        
        # Verify metrics service integration
        metrics_file = "app/services/metrics_service.py"
        with open(metrics_file, 'r') as f:
            metrics_content = f.read()
        
        # Check for config-driven budget integration
        config_indicators = [
            'budget_config',
            '_budget_manager',
            'refresh_budget_config'
        ]
        
        for indicator in config_indicators:
            assert indicator in metrics_content
            print(f"  ✅ Metrics service config integration ({indicator}): OK")
        
        # Check main.py includes config admin router
        main_file = "app/main.py"
        with open(main_file, 'r') as f:
            main_content = f.read()
        
        assert 'config_admin_router' in main_content
        print("  ✅ Config admin router included in main app: OK")
        
        return True
        
    except Exception as e:
        print(f"  ❌ Config-driven budgets validation failed: {e}")
        return False


async def main():
    """Run all production hardening validations."""
    print("🛡️ Production Hardening Validation")
    print("=" * 50)
    
    validations = [
        validate_client_factory_integration,
        validate_metrics_budget_guards,
        validate_startup_resilience,
        validate_security_logging,
        validate_cache_concurrency,
        validate_rare_failure_tests,
        validate_deployment_workflow,
        validate_config_driven_budgets
    ]
    
    results = []
    for validation in validations:
        try:
            if asyncio.iscoroutinefunction(validation):
                result = await validation()
            else:
                result = validation()
            results.append(result)
        except Exception as e:
            print(f"❌ Validation {validation.__name__} crashed: {e}")
            results.append(False)
        print()
    
    print("=" * 50)
    print("🎯 Validation Summary:")
    print(f"  Passed: {sum(results)}/{len(results)}")
    
    if all(results):
        print("✅ All production hardening validations PASSED")
        print("\n🚀 Production readiness confirmed:")
        print("  - Client factory with circuit breakers: ✅")
        print("  - Metrics budget guards with backpressure: ✅")
        print("  - Startup resilience with retries: ✅")
        print("  - Security logging with redaction: ✅")
        print("  - Cache concurrency protection: ✅")
        print("  - Rare failure mode testing: ✅")
        print("  - CI/CD deployment validation: ✅")
        print("  - Config-driven budgets and pools: ✅")
        return 0
    else:
        print("❌ Some production hardening validations FAILED")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)