"""
Production config service client - requires actual config service integration.
Mock implementations removed to enforce proper production deployment.
"""
import asyncio
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class ConfigServiceUnavailableError(Exception):
    """Exception raised when config service is unavailable"""
    pass


class ConfigServiceClient:
    """Production config service client requiring actual service integration."""
    
    def __init__(self, base_url: str = None, api_key: str = None, 
                 service_name: str = "signal_service", timeout: int = 30, 
                 environment: str = None, **kwargs):
        if not base_url:
            raise ConfigServiceUnavailableError("Config service URL required - cannot operate without config service")
        if not api_key:
            raise ConfigServiceUnavailableError("Config service API key required - cannot operate without authentication")
        if not environment:
            raise ConfigServiceUnavailableError("Environment required for config service client")
            
        self.base_url = base_url
        self.api_key = api_key
        self.service_name = service_name
        self.timeout = timeout
        self.environment = environment
        
        # Production config service integration required
        raise ConfigServiceUnavailableError(
            f"Production config service integration required - cannot use mock client for {service_name} in {environment}"
        )
        
    def get_secret(self, key: str, required: bool = True, environment: str = None) -> str:
        """Get secret from config service - requires real implementation."""
        raise ConfigServiceUnavailableError(
            f"Config service integration required to fetch secret: {key}"
        )
        
    def get_config(self, key: str, required: bool = True) -> str:
        """Get configuration from config service - requires real implementation."""
        raise ConfigServiceUnavailableError(
            f"Config service integration required to fetch config: {key}"
        )
        
    def get_service_url(self, service_name: str, host: str = None) -> str:
        """Get service URL from config service - requires real implementation."""
        raise ConfigServiceUnavailableError(
            f"Config service integration required to get service URL for: {service_name}"
        )
        
    def health_check(self) -> bool:
        """Health check requires actual config service connection."""
        raise ConfigServiceUnavailableError(
            "Config service health check requires actual service integration"
        )
        
    async def async_get_secret(self, key: str, required: bool = True) -> str:
        """Async get secret - requires real implementation."""
        raise ConfigServiceUnavailableError(
            f"Config service integration required to fetch secret: {key}"
        )
        
    async def async_get_config(self, key: str, required: bool = True) -> str:
        """Async get configuration - requires real implementation."""
        raise ConfigServiceUnavailableError(
            f"Config service integration required to fetch config: {key}"
        )


# For backwards compatibility - all methods require proper implementation
def get_config_client(**kwargs):
    """Get config client - requires proper config service integration."""
    return ConfigServiceClient(**kwargs)