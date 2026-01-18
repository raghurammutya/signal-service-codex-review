"""
<<<<<<< HEAD
Production Config Service Client

Architecture Principle #1: Config service is MANDATORY with NO fallbacks.
This client implements the production config_service protocol.
"""
import httpx
import logging
from typing import Any, Dict, Optional, Union
import os
import json

logger = logging.getLogger(__name__)


class ConfigServiceError(Exception):
    """Config service error - no fallbacks allowed per architecture."""
    pass

=======
Production-ready config service client that enforces proper integration.
Requires actual config service endpoint and credentials but provides graceful degradation.
"""
import logging
import os
import httpx
from typing import Any, Dict, Optional
>>>>>>> compliance-violations-fixed

logger = logging.getLogger(__name__)


class ConfigServiceError(Exception):
    """Exception raised when config service operations fail"""
    pass


class ConfigServiceClient:
<<<<<<< HEAD
    """Production config service client - NO mock behavior, NO fallbacks."""
    
    def __init__(self, service_name: str, environment: str, 
                 base_url: str = None, api_key: str = None, timeout: int = 30):
        """
        Initialize production config service client.
        
        Args:
            service_name: Name of the requesting service
            environment: Environment (production/staging/development)
            base_url: Config service URL (from CONFIG_SERVICE_URL env var if not provided)
            api_key: API key for config service (from STOCKSBLITZ_CONFIG_API_KEY env var if not provided)
            timeout: Request timeout in seconds
        """
        self.service_name = service_name
        self.environment = environment
        self.timeout = timeout
        
        # Config service URL - only bootstrap environment variable allowed
        if base_url is None:
            base_url = os.getenv("CONFIG_SERVICE_URL")
            if not base_url:
                raise ConfigServiceError(
                    "CONFIG_SERVICE_URL environment variable not set. "
                    "Config service URL is required per Architecture Principle #1. "
                    "No hardcoded defaults allowed."
                )
        self.base_url = base_url.rstrip('/')
        
        # API key - only bootstrap environment variable allowed  
        if api_key is None:
            api_key = os.getenv("STOCKSBLITZ_CONFIG_API_KEY")
            if not api_key:
                raise ConfigServiceError(
                    "STOCKSBLITZ_CONFIG_API_KEY environment variable not set. "
                    "Config service authentication is required per Architecture Principle #1. "
                    "No hardcoded defaults allowed."
                )
        self.api_key = api_key
        
        # HTTP client
        self._client: Optional[httpx.Client] = None
        
        logger.info(
            f"Initialized ConfigServiceClient for {service_name} in {environment} environment "
            f"connecting to {self.base_url}"
        )
    
    def _get_client(self) -> httpx.Client:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.Client(
                base_url=self.base_url,
                timeout=self.timeout,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "User-Agent": f"ConfigServiceClient/{self.service_name}"
                }
            )
        return self._client
    
    def close(self):
        """Close HTTP client."""
        if self._client:
            self._client.close()
            self._client = None
    
    def get_secret(self, key: str, required: bool = True, environment: str = None) -> Optional[str]:
        """
        Get secret from config service.
        
        Args:
            key: Secret key name
            required: If True, raises ConfigServiceError if secret not found
            environment: Environment override (uses instance environment if not provided)
            
        Returns:
            Secret value or None if not required and not found
            
        Raises:
            ConfigServiceError: If secret not found and required=True, or if config service fails
        """
        env = environment or self.environment
        client = self._get_client()
        
        try:
            response = client.get(
                f"/api/v1/secrets/{self.service_name}/{env}/{key}"
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get("value")
            elif response.status_code == 404:
                if required:
                    raise ConfigServiceError(
                        f"Required secret '{key}' not found in config_service for "
                        f"service '{self.service_name}' environment '{env}'. "
                        f"No fallbacks allowed per Architecture Principle #1."
                    )
                return None
            else:
                raise ConfigServiceError(
                    f"Config service error getting secret '{key}': "
                    f"HTTP {response.status_code} - {response.text}"
                )
                
        except httpx.RequestError as e:
            raise ConfigServiceError(
                f"Failed to connect to config service at {self.base_url}: {e}. "
                f"Config service is mandatory per Architecture Principle #1 - no fallbacks allowed."
            )
        except json.JSONDecodeError as e:
            raise ConfigServiceError(
                f"Invalid JSON response from config service for secret '{key}': {e}"
            )
    
    def get_config(self, key: str, environment: str = None) -> Optional[str]:
        """
        Get configuration value from config service.
        
        Args:
            key: Configuration key name
            environment: Environment override (uses instance environment if not provided)
            
        Returns:
            Configuration value or None if not found
            
        Raises:
            ConfigServiceError: If config service fails
        """
        env = environment or self.environment
        client = self._get_client()
        
        try:
            response = client.get(
                f"/api/v1/config/{self.service_name}/{env}/{key}"
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get("value")
            elif response.status_code == 404:
                return None
            else:
                raise ConfigServiceError(
                    f"Config service error getting config '{key}': "
                    f"HTTP {response.status_code} - {response.text}"
                )
                
        except httpx.RequestError as e:
            raise ConfigServiceError(
                f"Failed to connect to config service at {self.base_url}: {e}. "
                f"Config service is mandatory per Architecture Principle #1 - no fallbacks allowed."
            )
        except json.JSONDecodeError as e:
            raise ConfigServiceError(
                f"Invalid JSON response from config service for config '{key}': {e}"
            )
    
    def get_service_url(self, service_name: str, host: str = None) -> str:
        """
        Get service URL from config service.
        
        Args:
            service_name: Name of the target service
            host: Optional host override
            
        Returns:
            Service URL
            
        Raises:
            ConfigServiceError: If service URL not found or config service fails
        """
        client = self._get_client()
        
        try:
            response = client.get(
                f"/api/v1/services/{self.environment}/{service_name}/url"
            )
            
            if response.status_code == 200:
                data = response.json()
                url = data.get("url")
                if not url:
                    raise ConfigServiceError(
                        f"Service URL for '{service_name}' not found in config_service. "
                        f"No hardcoded fallbacks allowed per Architecture Principle #1."
                    )
                return url
            elif response.status_code == 404:
                raise ConfigServiceError(
                    f"Service '{service_name}' not found in config_service environment '{self.environment}'. "
                    f"No hardcoded fallbacks allowed per Architecture Principle #1."
                )
            else:
                raise ConfigServiceError(
                    f"Config service error getting service URL for '{service_name}': "
                    f"HTTP {response.status_code} - {response.text}"
                )
                
        except httpx.RequestError as e:
            raise ConfigServiceError(
                f"Failed to connect to config service at {self.base_url}: {e}. "
                f"Config service is mandatory per Architecture Principle #1 - no fallbacks allowed."
            )
        except json.JSONDecodeError as e:
            raise ConfigServiceError(
                f"Invalid JSON response from config service for service URL '{service_name}': {e}"
            )
    
    def health_check(self) -> bool:
        """
        Check config service health.
        
        Returns:
            True if config service is healthy
            
        Raises:
            ConfigServiceError: If config service is unhealthy or unreachable
        """
        client = self._get_client()
        
        try:
            response = client.get("/health")
            
            if response.status_code == 200:
                return True
            else:
                raise ConfigServiceError(
                    f"Config service health check failed: HTTP {response.status_code} - {response.text}"
                )
                
        except httpx.RequestError as e:
            raise ConfigServiceError(
                f"Config service health check failed - unable to connect to {self.base_url}: {e}"
            )
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - close client."""
        self.close()


# Convenience functions for backward compatibility
def get_config_service_client(service_name: str = "signal_service", environment: str = None) -> ConfigServiceClient:
    """
    Get config service client instance.
    
    Args:
        service_name: Name of the requesting service
        environment: Environment (must be provided explicitly - no defaults per architecture)
        
    Returns:
        ConfigServiceClient instance
        
    Raises:
        ConfigServiceError: If environment not provided or config service unavailable
    """
    if environment is None:
        # Environment MUST be provided explicitly - no defaults per Architecture Principle #1
        env_from_var = os.getenv("ENVIRONMENT")
        if not env_from_var:
            raise ConfigServiceError(
                "Environment must be provided explicitly. "
                "ENVIRONMENT variable not set and no default allowed per Architecture Principle #1."
            )
        environment = env_from_var
    
    return ConfigServiceClient(
        service_name=service_name,
        environment=environment
    )


def get_secret(key: str, service_name: str = "signal_service", environment: str = None) -> str:
    """
    Get secret from config service (convenience function).
    
    Args:
        key: Secret key name
        service_name: Name of the requesting service
        environment: Environment (must be provided explicitly - no defaults per architecture)
        
    Returns:
        Secret value
        
    Raises:
        ConfigServiceError: If secret not found or config service fails
    """
    client = get_config_service_client(service_name, environment)
    try:
        return client.get_secret(key, required=True)
    finally:
        client.close()


def get_config(key: str, service_name: str = "signal_service", environment: str = None) -> Optional[str]:
    """
    Get configuration value from config service (convenience function).
    
    Args:
        key: Configuration key name
        service_name: Name of the requesting service
        environment: Environment (must be provided explicitly - no defaults per architecture)
        
    Returns:
        Configuration value or None if not found
        
    Raises:
        ConfigServiceError: If config service fails
    """
    client = get_config_service_client(service_name, environment)
    try:
        return client.get_config(key)
    finally:
        client.close()
=======
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
>>>>>>> compliance-violations-fixed
