"""
Config Service Bootstrap Tests

Tests for verifying required environment variables and config service health.
These tests ensure the service fails fast when critical configuration is missing.
"""
import os
import pytest
import sys
from unittest.mock import patch, MagicMock

# Add project root to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))


class TestConfigBootstrap:
    """Test config service bootstrap requirements."""
    
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
    
    def test_missing_config_service_api_key_fails_fast(self):
        """Test that missing CONFIG_SERVICE_API_KEY causes immediate failure."""
        with patch.dict(os.environ, {
            'ENVIRONMENT': 'test',
            'CONFIG_SERVICE_URL': 'http://config.test.com'
        }, clear=True):
            # Mock the config client to fail on API key
            with patch('common.config_service.client.ConfigServiceClient') as mock_client:
                mock_client.side_effect = Exception("CONFIG_SERVICE_API_KEY not configured")
                
                with pytest.raises(SystemExit):
                    from app.core.config import SignalServiceConfig
                    SignalServiceConfig()
    
    def test_config_service_unreachable_fails_fast(self):
        """Test that unreachable config service causes immediate failure."""
        with patch.dict(os.environ, {
            'ENVIRONMENT': 'test',
            'CONFIG_SERVICE_URL': 'http://config.test.com',
            'CONFIG_SERVICE_API_KEY': 'test-key'
        }, clear=True):
            # Mock config client that fails health check
            mock_client = MagicMock()
            mock_client.health_check.return_value = False
            
            with patch('common.config_service.client.ConfigServiceClient', return_value=mock_client):
                with pytest.raises(SystemExit):
                    from app.core.config import SignalServiceConfig
                    SignalServiceConfig()
    
    def test_config_service_health_check_success(self):
        """Test successful config service bootstrap."""
        with patch.dict(os.environ, {
            'ENVIRONMENT': 'test',
            'CONFIG_SERVICE_URL': 'http://config.test.com',
            'CONFIG_SERVICE_API_KEY': 'test-key'
        }, clear=True):
            # Mock successful config client
            mock_client = MagicMock()
            mock_client.health_check.return_value = True
            
            # Mock all required config service responses
            config_responses = {
                'signal_service.service_name': 'signal_service',
                'signal_service.environment': 'test',
                'signal_service.service_host': '0.0.0.0',
                'signal_service.service_port': '8000',
                'signal_service.dashboard_url': 'http://dashboard.test.com',
                'signal_service.redis_sentinel_enabled': 'false',
                'signal_service.redis_sentinel_hosts': 'localhost:26379',
                'signal_service.redis_sentinel_master_name': 'mymaster',
                'signal_service.ticker_service_url': 'http://ticker.test.com',
                'signal_service.instrument_service_url': 'http://instrument.test.com',
                'signal_service.marketplace_service_url': 'http://marketplace.test.com',
                'signal_service.user_service_url': 'http://user.test.com',
                'signal_service.calendar_service_url': 'http://calendar.test.com',
                'signal_service.alert_service_url': 'http://alert.test.com',
                'signal_service.messaging_service_url': 'http://messaging.test.com',
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
                'signal_service.subscription_service_url': 'http://subscription.test.com'
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


class TestConfigServiceClient:
    """Test config service client directly."""
    
    def test_config_client_requires_url(self):
        """Test that ConfigServiceClient requires URL."""
        from common.config_service.client import ConfigServiceClient, ConfigServiceError
        
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ConfigServiceError, match="Config service URL is required"):
                ConfigServiceClient()
    
    def test_config_client_requires_api_key(self):
        """Test that ConfigServiceClient requires API key."""
        from common.config_service.client import ConfigServiceClient, ConfigServiceError
        
        with patch.dict(os.environ, {
            'CONFIG_SERVICE_URL': 'http://config.test.com'
        }, clear=True):
            with pytest.raises(ConfigServiceError, match="Config service API key is required"):
                ConfigServiceClient()
    
    def test_config_client_health_check(self):
        """Test config service health check functionality."""
        from common.config_service.client import ConfigServiceClient
        
        with patch.dict(os.environ, {
            'CONFIG_SERVICE_URL': 'http://config.test.com',
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
    """Run config bootstrap tests as a smoke test."""
    import subprocess
    import sys
    
    print("🔍 Running Config Service Bootstrap Tests...")
    
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
        print("✅ Config bootstrap tests passed!")
        print("\n📋 Bootstrap Requirements Verified:")
        print("  - ENVIRONMENT variable validation")
        print("  - CONFIG_SERVICE_URL validation") 
        print("  - CONFIG_SERVICE_API_KEY validation")
        print("  - Config service health check integration")
        print("  - Fail-fast behavior on missing configuration")
    else:
        print("❌ Config bootstrap tests failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()