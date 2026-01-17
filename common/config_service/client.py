"""
Production-ready config service client that enforces proper integration.
Requires actual config service endpoint and credentials but provides graceful degradation.
"""
import logging
import os
import httpx
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class ConfigServiceError(Exception):
    """Exception raised when config service operations fail"""
    pass


class ConfigServiceClient:
    """Production config service client with proper error handling."""
    
    def __init__(self, base_url: str = None, api_key: str = None, 
                 service_name: str = "signal_service", timeout: int = 30, 
                 environment: str = None, **kwargs):
        
        # Production requires these parameters to be explicitly provided
        self.base_url = base_url or os.getenv("CONFIG_SERVICE_URL")
        self.api_key = api_key or os.getenv("CONFIG_SERVICE_API_KEY")
        self.service_name = service_name
        self.timeout = timeout
        self.environment = environment or os.getenv("ENVIRONMENT", "production")
        
        if not self.base_url:
            logger.critical("CONFIG_SERVICE_URL not configured - config service integration required")
            raise ConfigServiceError("Config service URL is required for production deployment")
            
        if not self.api_key:
            logger.critical("CONFIG_SERVICE_API_KEY not configured - config service authentication required")
            raise ConfigServiceError("Config service API key is required for production deployment")
            
        logger.info(f"ConfigServiceClient initialized for {self.service_name} in {self.environment}")
        
    def get_secret(self, key: str, required: bool = True, environment: str = None) -> Optional[str]:
        """Get secret from config service with proper error handling."""
        try:
            # Real config service integration
            env = environment or self.environment
            url = f"{self.base_url}/api/v1/secrets/{key}"
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "X-Service-Name": self.service_name,
                "X-Environment": env
            }
            
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(url, headers=headers)
                
                if response.status_code == 200:
                    data = response.json()
                    secret_value = data.get("value")
                    logger.debug(f"Retrieved secret: {key}")
                    return secret_value
                elif response.status_code == 404:
                    if required:
                        logger.error(f"Required secret {key} not found in config service")
                        raise ConfigServiceError(f"Required secret {key} not available")
                    return None
                else:
                    error_msg = f"Config service error {response.status_code}: {response.text}"
                    logger.error(error_msg)
                    raise ConfigServiceError(error_msg)
            
        except httpx.RequestError as e:
            logger.error(f"Config service request failed for secret {key}: {e}")
            if required:
                raise ConfigServiceError(f"Config service unreachable for secret {key}: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to retrieve secret {key}: {e}")
            if required:
                raise ConfigServiceError(f"Config service error retrieving {key}: {e}")
            return None
        
    def get_config(self, key: str, required: bool = True) -> Optional[str]:
        """Get configuration value from config service."""
        try:
            # Real config service integration
            url = f"{self.base_url}/api/v1/config/{key}"
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "X-Service-Name": self.service_name,
                "X-Environment": self.environment
            }
            
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(url, headers=headers)
                
                if response.status_code == 200:
                    data = response.json()
                    config_value = data.get("value")
                    logger.debug(f"Retrieved config: {key}")
                    return config_value
                elif response.status_code == 404:
                    if required:
                        logger.error(f"Required config {key} not found in config service")
                        raise ConfigServiceError(f"Required config {key} not available")
                    return None
                else:
                    error_msg = f"Config service error {response.status_code}: {response.text}"
                    logger.error(error_msg)
                    raise ConfigServiceError(error_msg)
            
        except httpx.RequestError as e:
            logger.error(f"Config service request failed for config {key}: {e}")
            if required:
                raise ConfigServiceError(f"Config service unreachable for config {key}: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to retrieve config {key}: {e}")
            if required:
                raise ConfigServiceError(f"Config service error retrieving {key}: {e}")
            return None
        
    def get_service_url(self, service_name: str, host: str = None) -> Optional[str]:
        """Get service URL from config service with proper service discovery."""
        try:
            # Real service discovery through config service
            url = f"{self.base_url}/api/v1/services/{service_name}/url"
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "X-Service-Name": self.service_name,
                "X-Environment": self.environment
            }
            
            params = {}
            if host:
                params["host"] = host
                
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(url, headers=headers, params=params)
                
                if response.status_code == 200:
                    data = response.json()
                    service_url = data.get("url")
                    logger.debug(f"Resolved service URL for {service_name}: {service_url}")
                    return service_url
                else:
                    error_msg = f"Service discovery failed for {service_name}: {response.status_code} - {response.text}"
                    logger.error(error_msg)
                    raise ConfigServiceError(error_msg)
                    
        except httpx.RequestError as e:
            logger.error(f"Config service unreachable for service discovery {service_name}: {e}")
            raise ConfigServiceError(f"Service discovery failed for {service_name}: {e}")
        except Exception as e:
            logger.error(f"Failed to resolve service URL for {service_name}: {e}")
            raise ConfigServiceError(f"Service discovery failed for {service_name}: {e}")
        
    def health_check(self) -> bool:
        """Check config service health with timeout."""
        try:
            # Real config service health check
            url = f"{self.base_url}/api/v1/health"
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "X-Service-Name": self.service_name
            }
            
            with httpx.Client(timeout=10) as client:  # Shorter timeout for health checks
                response = client.get(url, headers=headers)
                
                if response.status_code == 200:
                    logger.debug("Config service health check passed")
                    return True
                else:
                    logger.warning(f"Config service health check failed: {response.status_code}")
                    return False
                    
        except httpx.RequestError as e:
            logger.error(f"Config service health check failed - service unreachable: {e}")
            return False
        except Exception as e:
            logger.error(f"Config service health check failed: {e}")
            return False


# Factory function for backward compatibility
def get_config_client(**kwargs) -> ConfigServiceClient:
    """Create config service client with production requirements."""
    return ConfigServiceClient(**kwargs)