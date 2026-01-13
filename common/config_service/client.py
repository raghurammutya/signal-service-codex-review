"""
Mock config service client for testing
"""
import asyncio
from typing import Any, Dict, Optional

class ConfigServiceClient:
    """Mock config service client for testing."""
    
    def __init__(self, base_url: str = "http://localhost:8101", api_key: str = "test_key", 
                 service_name: str = "signal_service", timeout: int = 30, 
                 environment: str = "test", **kwargs):
        self.base_url = base_url
        self.api_key = api_key
        self.service_name = service_name
        self.timeout = timeout
        self.environment = environment
        
    def get_secret(self, key: str, required: bool = True, environment: str = None) -> str:
        """Mock get secret - returns test values (synchronous)."""
        # Return mock values for common secrets
        mock_secrets = {
            "DATABASE_URL": "postgresql://test_user:test_password@test-timescaledb:5432/signal_service_test",
            "REDIS_URL": "redis://test-redis:6379/0",
            "API_KEY": "test_api_key",
            "SECRET_KEY": "test_secret_key",
            "GATEWAY_SECRET": "test_gateway_secret",
            "INTERNAL_API_KEY": "test_internal_api_key",
            "MARKETPLACE_WEBHOOK_SECRET": "test_marketplace_webhook_secret",
            "CELERY_BROKER_URL": "redis://test-redis:6379/1",
            "CELERY_RESULT_BACKEND": "redis://test-redis:6379/2"
        }
        result = mock_secrets.get(key, f"mock_value_for_{key}" if not required else None)
        if required and result is None:
            raise ValueError(f"Required secret {key} not found")
        return result
    
    def get_config(self, key: str, environment: str = None) -> str:
        """Mock get config - returns test values (synchronous)."""
        mock_configs = {
            "PORT": "8003",
            "ENVIRONMENT": "test",
            "CACHE_TTL_SECONDS": "300",
            "MAX_BATCH_SIZE": "100",
            "MAX_CPU_CORES": "4",
            "GREEKS_RISK_FREE_RATE": "0.06",
            "REDIS_TICK_STREAM_PREFIX": "tick_stream:",
            "CONSUMER_GROUP_NAME": "signal_processors",
            "CONSUMER_NAME": "signal_processor_1",
            "WEBSOCKET_MAX_CONNECTIONS": "10000",
            "WEBSOCKET_HEARTBEAT_INTERVAL": "30",
            "DEFAULT_SUBSCRIPTION_LEASE_SECONDS": "300",
            "MAX_INDICATORS_PER_TIMEFRAME": "50",
            "ACL_CACHE_ENABLED": "true",
            "ACL_CACHE_TTL_SECONDS": "300",
            "CELERY_BROKER_URL": "",
            "CELERY_RESULT_BACKEND": "",
            "ASYNC_COMPUTATION_ENABLED": "false",
            "METRICS_ENABLED": "true",
            "METRICS_PORT": "8003",
            "METRICS_UPDATE_INTERVAL_SECONDS": "60",
            "USAGE_TRACKING_ENABLED": "true",
            "USAGE_BATCH_SIZE": "100",
            "SUBSCRIPTION_SERVICE_URL": "",
            "INSTRUMENT_SERVICE_URL": "http://localhost:8008",
            "REDIS_SENTINEL_ENABLED": "false",
            "REDIS_SENTINEL_HOSTS": "",
            "REDIS_SENTINEL_MASTER_NAME": "signal-master",
            "signal_service.service_name": "signal_service",
            "signal_service.options_pricing_model": "black_scholes",
            "signal_service.model_params.risk_free_rate": "0.06",
            "signal_service.model_params.dividend_yield": "0.0",
            "signal_service.model_params.volatility_surface_enabled": "false",
            "signal_service.model_params.default_volatility": "0.25",
            "signal_service.model_params.volatility_min": "0.05",
            "signal_service.model_params.volatility_max": "2.0"
        }
        return mock_configs.get(key, f"test_config_for_{key}")
    
    def get_service_url(self, service_name: str, host: str = None) -> str:
        """Mock get service URL - returns test URLs."""
        service_urls = {
            "ticker_service": "http://mock-ticker-service:8089",
            "marketplace_service": "http://mock-marketplace-service:8090",
            "order_service": "http://mock-order-service:8087",
            "user_service": "http://mock-user-service:8001"
        }
        return service_urls.get(service_name, f"http://mock-{service_name}:8080")
    
    def health_check(self) -> bool:
        """Mock health check - always returns True (synchronous)."""
        return True


def get_config_service_client():
    """Get mock config service client for testing."""
    return ConfigServiceClient()


def get_secret(key: str, environment: str = "test") -> str:
    """Get secret from mock config service."""
    client = get_config_service_client()
    return client.get_secret(key, required=True, environment=environment)


def get_config(key: str, environment: str = "test") -> str:
    """Get config from mock config service."""
    client = get_config_service_client()
    return client.get_config(key, environment=environment)