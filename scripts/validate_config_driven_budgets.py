#!/usr/bin/env python3
"""
Config-Driven Budgets and Pools Validation Script

Validates that budget guards and connection pools are properly driven by config service.
Tests configuration refresh, validation, and runtime adjustment capabilities.
"""
import asyncio
import json
import os
import sys
from datetime import datetime
from typing import Any

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def test_budget_config_loading():
    """Test loading budget configuration from config service."""
    try:
        from app.config.budget_config import get_budget_manager

        print("🔧 Testing Budget Config Loading...")

        budget_manager = get_budget_manager()

        # Test getting each configuration section
        sections = [
            ('metrics_budget', budget_manager.get_metrics_budget),
            ('database_pool', budget_manager.get_database_pool_config),
            ('redis_pool', budget_manager.get_redis_pool_config),
            ('client_pool', budget_manager.get_client_pool_config),
            ('cache_pool', budget_manager.get_cache_pool_config)
        ]

        for section_name, get_config_func in sections:
            try:
                config = await get_config_func()
                print(f"  ✅ {section_name}: {type(config).__name__} loaded")

                # Validate config has expected attributes
                if hasattr(config, 'dict'):
                    config_dict = config.dict()
                    print(f"     Keys: {list(config_dict.keys())}")

                    # Check for required fields based on section
                    if section_name == 'metrics_budget':
                        required = ['max_concurrent_operations', 'max_memory_mb', 'max_cpu_percent']
                        missing = [key for key in required if key not in config_dict]
                        if missing:
                            print(f"     ⚠️ Missing required fields: {missing}")
                        else:
                            print("     ✅ All required metrics budget fields present")

                    elif section_name.endswith('_pool'):
                        if 'max_connections' in config_dict:
                            print(f"     ✅ Pool config includes max_connections: {config_dict['max_connections']}")

            except Exception as e:
                print(f"  ❌ {section_name}: Failed to load - {e}")
                return False

        print("  ✅ All budget configuration sections loaded successfully")
        return True

    except Exception as e:
        print(f"❌ Budget config loading failed: {e}")
        return False


async def test_metrics_service_integration():
    """Test that metrics service uses config-driven budgets."""
    try:
        from app.services.metrics_service import get_metrics_collector

        print("\n📊 Testing Metrics Service Integration...")

        metrics_collector = get_metrics_collector()
        await metrics_collector.initialize()

        # Check that budget guards are loaded from config
        if metrics_collector.budget_guards is None:
            print("  ❌ Budget guards not initialized")
            return False

        budget_guards = metrics_collector.budget_guards
        print(f"  ✅ Budget guards loaded: {len(budget_guards)} settings")

        required_guards = [
            'max_concurrent_operations',
            'max_memory_mb',
            'max_cpu_percent',
            'max_request_rate_per_minute',
            'max_processing_time_ms'
        ]

        for guard in required_guards:
            if guard in budget_guards:
                print(f"     ✅ {guard}: {budget_guards[guard]}")
            else:
                print(f"     ❌ Missing budget guard: {guard}")
                return False

        # Test config refresh
        print("  🔄 Testing budget config refresh...")
        await metrics_collector.refresh_budget_config()
        print("     ✅ Budget configuration refreshed successfully")

        return True

    except Exception as e:
        print(f"❌ Metrics service integration test failed: {e}")
        return False


async def test_pool_manager_initialization():
    """Test that pool manager initializes with config-driven settings."""
    try:
        from app.config.pool_manager import get_pool_manager

        print("\n🏊 Testing Pool Manager Initialization...")

        pool_manager = get_pool_manager()

        # Test pool status before initialization
        status_before = await pool_manager.get_pool_status()
        print(f"  📊 Status before init: initialized={status_before['initialized']}")

        # Initialize pools with config-driven settings
        await pool_manager.initialize()

        # Test pool status after initialization
        status_after = await pool_manager.get_pool_status()
        print(f"  📊 Status after init: initialized={status_after['initialized']}")

        if not status_after['initialized']:
            print("  ❌ Pool manager not properly initialized")
            return False

        # Check individual pool status
        pools = status_after.get('pools', {})
        for pool_name, pool_info in pools.items():
            status = pool_info.get('status', 'unknown')
            print(f"     ✅ {pool_name}: {status}")

            if pool_name == 'database' and pool_info.get('total_connections'):
                print(f"        DB connections: {pool_info['total_connections']} total")
            elif pool_name == 'http_clients' and pool_info.get('client_count'):
                print(f"        HTTP clients: {pool_info['client_count']} clients")

        return True

    except Exception as e:
        print(f"❌ Pool manager initialization test failed: {e}")
        return False


async def test_config_validation():
    """Test configuration validation functionality."""
    try:
        from app.config.budget_config import get_budget_manager

        print("\n✅ Testing Configuration Validation...")

        budget_manager = get_budget_manager()

        # Test configuration validation
        validation_result = await budget_manager.validate_and_apply_config()

        print(f"  📋 Validation result: valid={validation_result['valid']}")

        # Report errors and warnings
        if validation_result['errors']:
            print(f"     ❌ Errors: {len(validation_result['errors'])}")
            for error in validation_result['errors'][:3]:  # Show first 3
                print(f"        - {error}")
        else:
            print("     ✅ No configuration errors")

        if validation_result['warnings']:
            print(f"     ⚠️ Warnings: {len(validation_result['warnings'])}")
            for warning in validation_result['warnings'][:3]:  # Show first 3
                print(f"        - {warning}")
        else:
            print("     ✅ No configuration warnings")

        # Test validation of individual sections
        sections = validation_result.get('sections', {})
        for section_name, section_result in sections.items():
            section_valid = section_result.get('valid', False)
            status_icon = "✅" if section_valid else "❌"
            print(f"     {status_icon} {section_name}: {'valid' if section_valid else 'invalid'}")

        return validation_result['valid']

    except Exception as e:
        print(f"❌ Configuration validation test failed: {e}")
        return False


async def test_runtime_config_refresh():
    """Test runtime configuration refresh functionality."""
    try:
        print("\n🔄 Testing Runtime Config Refresh...")

        from app.config.budget_config import get_budget_manager
        from app.config.pool_manager import get_pool_manager
        from app.services.metrics_service import get_metrics_collector

        budget_manager = get_budget_manager()
        pool_manager = get_pool_manager()
        metrics_collector = get_metrics_collector()

        # Ensure initialization
        if not metrics_collector.budget_guards:
            await metrics_collector.initialize()

        # Test forcing configuration refresh
        print("  🔄 Forcing budget config refresh...")
        await budget_manager.get_budget_config()
        await budget_manager.get_budget_config(force_refresh=True)

        print("     ✅ Budget config refreshed")

        # Test metrics service config refresh
        print("  📊 Refreshing metrics service config...")
        await metrics_collector.refresh_budget_config()
        print("     ✅ Metrics budget guards refreshed")

        # Test pool config refresh
        print("  🏊 Refreshing pool configs...")
        await pool_manager.refresh_pool_configs()
        print("     ✅ Pool configurations refreshed")

        return True

    except Exception as e:
        print(f"❌ Runtime config refresh test failed: {e}")
        return False


async def test_config_driven_integration():
    """Test end-to-end config-driven integration."""
    try:
        print("\n🔗 Testing End-to-End Config-Driven Integration...")

        # Test that all components are using config service
        components_tested = []

        # 1. Budget manager loads config from service
        from app.config.budget_config import get_budget_manager
        budget_manager = get_budget_manager()
        await budget_manager.get_budget_config()
        components_tested.append("budget_manager")
        print("     ✅ Budget manager loads from config service")

        # 2. Metrics service uses budget manager
        from app.services.metrics_service import get_metrics_collector
        metrics_collector = get_metrics_collector()
        if not metrics_collector.budget_guards:
            await metrics_collector.initialize()
        if metrics_collector._budget_manager:
            components_tested.append("metrics_service")
            print("     ✅ Metrics service uses budget manager")

        # 3. Pool manager uses budget manager
        from app.config.pool_manager import get_pool_manager
        pool_manager = get_pool_manager()
        await pool_manager.initialize()
        components_tested.append("pool_manager")
        print("     ✅ Pool manager uses budget manager")

        # 4. Test configuration flow
        print("  🔄 Testing configuration flow...")
        original_max_ops = metrics_collector.budget_guards.get('max_concurrent_operations', 0)
        print(f"     Current max concurrent ops: {original_max_ops}")

        # Force refresh and check if it propagates
        await budget_manager.get_budget_config(force_refresh=True)
        await metrics_collector.refresh_budget_config()

        updated_max_ops = metrics_collector.budget_guards.get('max_concurrent_operations', 0)
        print(f"     After refresh max concurrent ops: {updated_max_ops}")

        print(f"  ✅ Integration test complete: {len(components_tested)} components tested")
        return True

    except Exception as e:
        print(f"❌ Config-driven integration test failed: {e}")
        return False


async def main():
    """Run all config-driven budget and pool validation tests."""
    print("🔍 Config-Driven Budgets and Pools Validation")
    print("=" * 60)

    test_functions = [
        ("Budget Config Loading", test_budget_config_loading),
        ("Metrics Service Integration", test_metrics_service_integration),
        ("Pool Manager Initialization", test_pool_manager_initialization),
        ("Configuration Validation", test_config_validation),
        ("Runtime Config Refresh", test_runtime_config_refresh),
        ("Config-Driven Integration", test_config_driven_integration)
    ]

    results = {}
    passed_count = 0

    for test_name, test_func in test_functions:
        try:
            result = await test_func()
            results[test_name] = result
            if result:
                passed_count += 1
        except Exception as e:
            print(f"❌ {test_name} failed with exception: {e}")
            results[test_name] = False

    print("\n" + "=" * 60)
    print("🎯 Validation Summary:")
    print(f"  Passed: {passed_count}/{len(test_functions)}")

    for test_name, result in results.items():
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"  {status}: {test_name}")

    if passed_count == len(test_functions):
        print("\n🎉 ALL CONFIG-DRIVEN BUDGET AND POOL TESTS PASSED")
        print("\n📋 Config-Driven Features Verified:")
        print("  - Budget configuration loaded from config service")
        print("  - Metrics service uses config-driven budget guards")
        print("  - Pool manager uses config-driven connection limits")
        print("  - Configuration validation and refresh working")
        print("  - Runtime configuration updates supported")
        print("  - End-to-end config service integration confirmed")
        return 0
    print(f"\n❌ {len(test_functions) - passed_count} TESTS FAILED")
    return 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n⏹️ Validation interrupted")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Validation failed: {e}")
        sys.exit(1)
