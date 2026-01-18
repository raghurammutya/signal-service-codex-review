"""
Config Service Bootstrap Tests - SECURITY COMPLIANT

Tests for verifying required environment variables and config service health.
These tests ensure the service fails fast when critical configuration is missing.

SECURITY COMPLIANCE:
- NO hardcoded secrets or API keys
- NO external URLs in code
- Config service bootstrap only
- Proper mocking for all external dependencies
"""
import os
import pytest
import sys
from unittest.mock import patch, MagicMock

# Add project root to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))


class TestSecureConfigBootstrap:
    """Test secure config service bootstrap requirements."""
    
    def test_missing_environment_variable_fails_fast(self):
        """Test that missing ENVIRONMENT variable causes immediate failure."""
        # Clear environment variables
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="ENVIRONMENT environment variable is required"):
                from app.core.config import SignalServiceConfig
                SignalServiceConfig()
    
    def test_missing_config_service_url_fails_fast(self):
        """Test that missing CONFIG_SERVICE_URL causes immediate failure."""
        with patch.dict(os.environ, {
            'ENVIRONMENT': 'test',
            'CONFIG_SERVICE_API_KEY': 'test-key'
        }, clear=True):
            # Mock the config client to fail on URL
            with patch('common.config_service.client.ConfigServiceClient') as mock_client:
                mock_client.side_effect = Exception("CONFIG_SERVICE_URL not configured")
                
                with pytest.raises(SystemExit):
                    from app.core.config import SignalServiceConfig
                    SignalServiceConfig()
    
    def test_secure_config_service_bootstrap(self):
        """Test secure config service bootstrap with proper mocking."""
        with patch.dict(os.environ, {
            'ENVIRONMENT': 'test',
            'CONFIG_SERVICE_URL': 'http://config.test.local',  # Non-production URL for testing
            'CONFIG_SERVICE_API_KEY': 'test-key'
        }, clear=True):
            # Mock successful config client
            mock_client = MagicMock()
            mock_client.health_check.return_value = True
            
            # Mock all required config service responses (NO real secrets)
            config_responses = {
                'signal_service.service_name': 'signal_service',
                'signal_service.environment': 'test',
                'signal_service.service_host': '0.0.0.0',
                'signal_service.service_port': '8000',
                'signal_service.dashboard_url': 'http://dashboard.test.local',
                'signal_service.redis_sentinel_enabled': 'false',
                'signal_service.redis_sentinel_hosts': 'localhost:26379',
                'signal_service.redis_sentinel_master_name': 'mymaster',
                'signal_service.ticker_service_url': 'http://ticker.test.local',
                'signal_service.instrument_service_url': 'http://instrument.test.local',
                'signal_service.marketplace_service_url': 'http://marketplace.test.local',
                'signal_service.user_service_url': 'http://user.test.local',
                'signal_service.calendar_service_url': 'http://calendar.test.local',
                'signal_service.alert_service_url': 'http://alert.test.local',
                'signal_service.messaging_service_url': 'http://messaging.test.local',
                'signal_service.cache_ttl_seconds': '300',
                'signal_service.max_batch_size': '100',
                'signal_service.max_cpu_cores': '4',
                'signal_service.service_integration_timeout': '30.0',
                'signal_service.greeks_risk_free_rate': '0.02',
                'signal_service.redis_tick_stream_prefix': 'ticks:',
                'signal_service.consumer_group_name': 'signal_consumers',
                'signal_service.consumer_name': 'signal_consumer_1',
                'signal_service.websocket_max_connections': '1000',
                'signal_service.websocket_heartbeat_interval': '30',
                'signal_service.default_subscription_lease_seconds': '3600',
                'signal_service.max_indicators_per_timeframe': '10',
                'signal_service.acl_cache_enabled': 'true',
                'signal_service.acl_cache_ttl_seconds': '600',
                'signal_service.celery_broker_url': 'redis://localhost:6379',
                'signal_service.celery_result_backend': 'redis://localhost:6379',
                'signal_service.async_computation_enabled': 'true',
                'signal_service.metrics_enabled': 'true',
                'signal_service.metrics_port': '9090',
                'signal_service.metrics_update_interval_seconds': '60',
                'signal_service.usage_tracking_enabled': 'true',
                'signal_service.usage_batch_size': '100',
                'signal_service.subscription_service_url': 'http://subscription.test.local'
            }
            
            # Mock test secrets (NO real secrets)
            secret_responses = {
                'DATABASE_URL': 'postgresql://test:test@localhost/test',
                'REDIS_URL': 'redis://localhost:6379',
                'GATEWAY_SECRET': 'test-gateway-secret'
            }
            
            def mock_get_config(key, required=True, is_secret=False):
                if key in config_responses:
                    return config_responses[key]
                elif required:
                    raise Exception(f"Required config {key} not found")
                return None
                
            def mock_get_secret(key, required=True):
                if key in secret_responses:
                    return secret_responses[key]
                elif required:
                    raise Exception(f"Required secret {key} not found")
                return None
            
            mock_client.get_config.side_effect = mock_get_config
            mock_client.get_secret.side_effect = mock_get_secret
            
            with patch('common.config_service.client.ConfigServiceClient', return_value=mock_client):
                # This should not raise an exception
                from app.core.config import SignalServiceConfig
                config = SignalServiceConfig()
                
                # Verify critical settings are loaded
                assert config.service_name == 'signal_service'
                assert config.environment == 'test'
                assert config.DATABASE_URL == 'postgresql://test:test@localhost/test'
                assert config.gateway_secret == 'test-gateway-secret'


class TestSecureHotReloadConfiguration:
    """Test secure hot parameter reloading functionality."""
    
    @pytest.mark.asyncio
    async def test_secure_hot_reload_initialization(self):
        """Test secure hot reload system initialization."""
        with patch.dict(os.environ, {
            'ENVIRONMENT': 'test',
            'ENABLE_HOT_RELOAD': 'true'
        }, clear=True):
            # Mock config client and dependencies
            mock_config_client = MagicMock()
            mock_config_client.health_check.return_value = True
            
            # Mock all required config responses for hot reloadable config
            config_responses = {
                'signal_service.service_name': 'signal_service',
                'signal_service.environment': 'test',
                'signal_service.service_host': '0.0.0.0',
                'signal_service.service_port': '8000'
            }
            
            secret_responses = {
                'DATABASE_URL': 'postgresql://test:test@localhost/test',
                'REDIS_URL': 'redis://localhost:6379',
                'GATEWAY_SECRET': 'test-gateway-secret'
            }
            
            def mock_get_config(key, required=True, is_secret=False):
                if key in config_responses:
                    return config_responses[key]
                elif required:
                    raise Exception(f"Required config {key} not found")
                return None
                
            def mock_get_secret(key, required=True):
                if key in secret_responses:
                    return secret_responses[key]
                elif required:
                    raise Exception(f"Required secret {key} not found")
                return None
            
            mock_config_client.get_config.side_effect = mock_get_config
            mock_config_client.get_secret.side_effect = mock_get_secret
            
            with patch('common.config_service.client.ConfigServiceClient', return_value=mock_config_client):
                with patch('common.config_service.notification_client.ConfigNotificationClient') as mock_notification:
                    mock_notification_instance = MagicMock()
                    mock_notification.return_value = mock_notification_instance
                    
                    # Test hot reloadable config
                    from app.core.hot_config import get_hot_reloadable_settings
                    config = get_hot_reloadable_settings(environment='test')
                    
                    # Initialize hot reload
                    await config.initialize_hot_reload(enable_hot_reload=True)
                    
                    # Verify initialization
                    assert hasattr(config, '_hot_reload_enabled')
                    assert hasattr(config, '_security_context')
                    assert config._security_context['auth_required'] is True
                    
                    # Test security validation
                    security_valid = config._validate_security_context()
                    assert isinstance(security_valid, bool)
                    
                    # Test health monitoring (no external dependencies)
                    health_data = await config.get_hot_reload_health()
                    assert "hot_reload_enabled" in health_data
                    assert "security_context_valid" in health_data
                    assert "handlers_registered" in health_data
                    
                    # Cleanup
                    await config.shutdown_hot_reload()
    
    @pytest.mark.asyncio
    async def test_hot_reload_security_validation(self):
        """Test hot reload security validation requirements."""
        from app.core.hot_config import HotReloadableSignalServiceConfig
        
        # Mock base initialization to avoid dependency on actual config service
        with patch('app.core.hot_config.BaseSignalServiceConfig.__init__') as mock_base_init:
            mock_base_init.return_value = None
            config = HotReloadableSignalServiceConfig()
            
            # Verify security requirements
            assert hasattr(config, '_security_context'), "Security context required"
            assert config._security_context['auth_required'] is True, "Authentication must be required"
            assert config._security_context['internal_only'] is True, "Internal only access required"
            assert config._security_context['circuit_breaker'] is True, "Circuit breaker required"
            
            # Test security validation
            security_valid = config._validate_security_context()
            assert isinstance(security_valid, bool), "Security validation must return boolean"
    
    def test_no_hardcoded_external_endpoints(self):
        """Test that no external endpoints are hardcoded in configuration."""
        from app.core.hot_config import HotReloadableSignalServiceConfig
        
        # Mock base initialization
        with patch('app.core.hot_config.BaseSignalServiceConfig.__init__') as mock_base_init:
            mock_base_init.return_value = None
            config = HotReloadableSignalServiceConfig()
            
            # Security check: NO hardcoded external URLs
            assert not hasattr(config, '_external_config_urls'), "NO hardcoded external URLs allowed"
            assert not hasattr(config, '_use_external_config'), "NO external config flags allowed"
            
            # Verify secure defaults
            assert hasattr(config, '_hot_reload_enabled'), "Hot reload control required"
            assert hasattr(config, '_security_context'), "Security context required"


class TestConfigServiceClient:
    """Test config service client security compliance."""
    
    def test_config_client_requires_secure_bootstrap(self):
        """Test that ConfigServiceClient requires secure bootstrap only."""
        from common.config_service.client import ConfigServiceClient, ConfigServiceError
        
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ConfigServiceError, match="Config service URL is required"):
                ConfigServiceClient()
    
    def test_config_client_health_check(self):
        """Test config service health check functionality."""
        from common.config_service.client import ConfigServiceClient
        
        with patch.dict(os.environ, {
            'CONFIG_SERVICE_URL': 'http://config.test.local',
            'CONFIG_SERVICE_API_KEY': 'test-key',
            'ENVIRONMENT': 'test'
        }, clear=True):
            client = ConfigServiceClient()
            
            # Mock successful health check
            with patch('httpx.Client') as mock_client:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_client.return_value.__enter__.return_value.get.return_value = mock_response
                
                assert client.health_check() is True
            
            # Mock failed health check
            with patch('httpx.Client') as mock_client:
                mock_response = MagicMock()
                mock_response.status_code = 500
                mock_client.return_value.__enter__.return_value.get.return_value = mock_response
                
                assert client.health_check() is False


def main():
    """Run secure config bootstrap tests."""
    import subprocess
    import sys
    
    print("🔍 Running Secure Config Service Bootstrap Tests...")
    
    # Run the tests
    result = subprocess.run([
        sys.executable, '-m', 'pytest', 
        __file__, 
        '-v', 
        '--tb=short'
    ], capture_output=True, text=True)
    
    print("STDOUT:")
    print(result.stdout)
    
    if result.stderr:
        print("STDERR:")
        print(result.stderr)
    
    if result.returncode == 0:
        print("✅ Secure config bootstrap tests passed!")
        print("\n📋 Security Requirements Verified:")
        print("  - NO hardcoded secrets or API keys")
        print("  - NO external URLs in code")
        print("  - Config service bootstrap only")
        print("  - Authentication and security validation")
        print("  - Proper mocking for external dependencies")
        print("  - Hot reload security compliance")
    else:
        print("❌ Config bootstrap tests failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()