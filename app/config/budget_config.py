"""
Config-driven Budget and Pool Management

Centralizes all resource limits and pool configurations through config service,
enabling runtime adjustments without code deployment.
"""
import asyncio
import logging
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, validator

logger = logging.getLogger(__name__)


class MetricsBudgetConfig(BaseModel):
    """Metrics service budget configuration."""
    max_concurrent_operations: int = Field(default=50, ge=1, le=500)
    max_memory_mb: int = Field(default=512, ge=64, le=2048)
    max_cpu_percent: float = Field(default=85.0, ge=10.0, le=100.0)
    max_request_rate_per_minute: int = Field(default=300, ge=10, le=10000)
    max_processing_time_ms: int = Field(default=5000, ge=100, le=30000)

    # Backpressure thresholds
    light_pressure_threshold: float = Field(default=0.7, ge=0.1, le=1.0)
    moderate_pressure_threshold: float = Field(default=0.85, ge=0.1, le=1.0)
    heavy_pressure_threshold: float = Field(default=0.95, ge=0.1, le=1.0)

    @validator('moderate_pressure_threshold')
    def moderate_must_be_greater_than_light(cls, v, values):
        if 'light_pressure_threshold' in values and v <= values['light_pressure_threshold']:
            raise ValueError('moderate_pressure_threshold must be greater than light_pressure_threshold')
        return v

    @validator('heavy_pressure_threshold')
    def heavy_must_be_greater_than_moderate(cls, v, values):
        if 'moderate_pressure_threshold' in values and v <= values['moderate_pressure_threshold']:
            raise ValueError('heavy_pressure_threshold must be greater than moderate_pressure_threshold')
        return v


class DatabasePoolConfig(BaseModel):
    """Database connection pool configuration."""
    min_connections: int = Field(default=5, ge=1, le=50)
    max_connections: int = Field(default=20, ge=5, le=100)
    connection_timeout: float = Field(default=30.0, ge=1.0, le=300.0)
    idle_timeout: float = Field(default=600.0, ge=60.0, le=3600.0)
    max_lifetime: float = Field(default=3600.0, ge=300.0, le=86400.0)
    retry_attempts: int = Field(default=3, ge=1, le=10)

    @validator('max_connections')
    def max_must_be_greater_than_min(cls, v, values):
        if 'min_connections' in values and v <= values['min_connections']:
            raise ValueError('max_connections must be greater than min_connections')
        return v


class RedisPoolConfig(BaseModel):
    """Redis connection pool configuration."""
    min_connections: int = Field(default=5, ge=1, le=50)
    max_connections: int = Field(default=50, ge=5, le=200)
    connection_timeout: float = Field(default=10.0, ge=1.0, le=60.0)
    socket_timeout: float = Field(default=5.0, ge=1.0, le=30.0)
    retry_attempts: int = Field(default=3, ge=1, le=10)
    retry_delay: float = Field(default=1.0, ge=0.1, le=10.0)


class ClientPoolConfig(BaseModel):
    """HTTP client pool configuration for external services."""
    max_connections: int = Field(default=100, ge=10, le=1000)
    max_keepalive_connections: int = Field(default=20, ge=5, le=100)
    keepalive_expiry: float = Field(default=5.0, ge=1.0, le=60.0)
    timeout: float = Field(default=30.0, ge=1.0, le=300.0)
    max_retries: int = Field(default=3, ge=0, le=10)

    @validator('max_keepalive_connections')
    def keepalive_must_be_less_than_max(cls, v, values):
        if 'max_connections' in values and v > values['max_connections']:
            raise ValueError('max_keepalive_connections must be <= max_connections')
        return v


class CachePoolConfig(BaseModel):
    """Cache pool configuration."""
    max_size: int = Field(default=1000, ge=100, le=100000)
    ttl_seconds: int = Field(default=300, ge=10, le=3600)
    eviction_policy: str = Field(default="lru", regex="^(lru|lfu|fifo)$")
    max_memory_mb: int = Field(default=128, ge=16, le=1024)


class BudgetConfig(BaseModel):
    """Complete budget and pool configuration."""
    metrics_budget: MetricsBudgetConfig = Field(default_factory=MetricsBudgetConfig)
    database_pool: DatabasePoolConfig = Field(default_factory=DatabasePoolConfig)
    redis_pool: RedisPoolConfig = Field(default_factory=RedisPoolConfig)
    client_pool: ClientPoolConfig = Field(default_factory=ClientPoolConfig)
    cache_pool: CachePoolConfig = Field(default_factory=CachePoolConfig)


class ConfigDrivenBudgetManager:
    """Manages config-driven budget and pool settings with hot reload capability."""

    def __init__(self):
        self._budget_config: BudgetConfig | None = None
        self._config_cache_ttl = 60  # Cache config for 60 seconds
        self._last_config_fetch = 0
        self._lock = asyncio.Lock()

    async def get_budget_config(self, force_refresh: bool = False) -> BudgetConfig:
        """Get current budget configuration from config service."""
        import time
        current_time = time.time()

        async with self._lock:
            # Check if we need to refresh config
            if (force_refresh or
                not self._budget_config or
                (current_time - self._last_config_fetch) > self._config_cache_ttl):

                try:
                    config_dict = await self._fetch_config_from_service()
                    self._budget_config = BudgetConfig(**config_dict)
                    self._last_config_fetch = current_time
                    logger.info("Budget configuration refreshed from config service")
                except Exception as e:
                    logger.warning(f"Failed to refresh budget config from service: {e}")
                    if not self._budget_config:
                        # Fallback to defaults if no config available
                        self._budget_config = BudgetConfig()
                        logger.info("Using default budget configuration")

            return self._budget_config

    async def _fetch_config_from_service(self) -> dict[str, Any]:
        """Fetch budget configuration from config service."""
        try:
            # Import config service client
            from common.config_service.client import ConfigServiceClient

            config_client = ConfigServiceClient()

            # Fetch each configuration section
            config_sections = {
                'metrics_budget': 'METRICS_BUDGET_CONFIG',
                'database_pool': 'DATABASE_POOL_CONFIG',
                'redis_pool': 'REDIS_POOL_CONFIG',
                'client_pool': 'CLIENT_POOL_CONFIG',
                'cache_pool': 'CACHE_POOL_CONFIG'
            }

            config_dict = {}

            for section, config_key in config_sections.items():
                try:
                    config_value = config_client.get_config(config_key)
                    if config_value:
                        import json
                        config_dict[section] = json.loads(config_value)
                    else:
                        logger.debug(f"No config found for {config_key}, using defaults")
                except Exception as e:
                    logger.warning(f"Error fetching {config_key}: {e}")
                    # Continue with defaults for missing sections

            return config_dict

        except Exception as e:
            logger.error(f"Failed to connect to config service: {e}")
            return {}

    async def get_metrics_budget(self) -> MetricsBudgetConfig:
        """Get metrics budget configuration."""
        config = await self.get_budget_config()
        return config.metrics_budget

    async def get_database_pool_config(self) -> DatabasePoolConfig:
        """Get database pool configuration."""
        config = await self.get_budget_config()
        return config.database_pool

    async def get_redis_pool_config(self) -> RedisPoolConfig:
        """Get Redis pool configuration."""
        config = await self.get_budget_config()
        return config.redis_pool

    async def get_client_pool_config(self) -> ClientPoolConfig:
        """Get HTTP client pool configuration."""
        config = await self.get_budget_config()
        return config.client_pool

    async def get_cache_pool_config(self) -> CachePoolConfig:
        """Get cache pool configuration."""
        config = await self.get_budget_config()
        return config.cache_pool

    async def validate_and_apply_config(self) -> dict[str, Any]:
        """Validate current configuration and return status."""
        try:
            config = await self.get_budget_config()

            # Validate configuration
            validation_status = {
                'valid': True,
                'errors': [],
                'warnings': [],
                'sections': {
                    'metrics_budget': self._validate_metrics_budget(config.metrics_budget),
                    'database_pool': self._validate_database_pool(config.database_pool),
                    'redis_pool': self._validate_redis_pool(config.redis_pool),
                    'client_pool': self._validate_client_pool(config.client_pool),
                    'cache_pool': self._validate_cache_pool(config.cache_pool)
                }
            }

            # Aggregate validation results
            for section, result in validation_status['sections'].items():
                if not result['valid']:
                    validation_status['valid'] = False
                    validation_status['errors'].extend(result['errors'])
                validation_status['warnings'].extend(result['warnings'])

            return validation_status

        except Exception as e:
            logger.error(f"Configuration validation failed: {e}")
            return {
                'valid': False,
                'errors': [f"Configuration validation error: {e}"],
                'warnings': [],
                'sections': {}
            }

    def _validate_metrics_budget(self, config: MetricsBudgetConfig) -> dict[str, Any]:
        """Validate metrics budget configuration."""
        errors = []
        warnings = []

        # Check for reasonable resource limits
        if config.max_memory_mb > 1024:
            warnings.append("High memory limit may impact system stability")

        if config.max_concurrent_operations > 200:
            warnings.append("High concurrent operations limit may cause resource contention")

        if config.max_request_rate_per_minute > 5000:
            warnings.append("Very high request rate may overwhelm external services")

        return {
            'valid': len(errors) == 0,
            'errors': errors,
            'warnings': warnings
        }

    def _validate_database_pool(self, config: DatabasePoolConfig) -> dict[str, Any]:
        """Validate database pool configuration."""
        errors = []
        warnings = []

        if config.max_connections > 50:
            warnings.append("High database connection count may impact database performance")

        if config.connection_timeout < 5.0:
            warnings.append("Very short connection timeout may cause frequent failures")

        return {
            'valid': len(errors) == 0,
            'errors': errors,
            'warnings': warnings
        }

    def _validate_redis_pool(self, config: RedisPoolConfig) -> dict[str, Any]:
        """Validate Redis pool configuration."""
        errors = []
        warnings = []

        if config.max_connections > 100:
            warnings.append("High Redis connection count may impact Redis performance")

        return {
            'valid': len(errors) == 0,
            'errors': errors,
            'warnings': warnings
        }

    def _validate_client_pool(self, config: ClientPoolConfig) -> dict[str, Any]:
        """Validate HTTP client pool configuration."""
        errors = []
        warnings = []

        if config.timeout > 120.0:
            warnings.append("Very long timeout may cause request queuing")

        if config.max_connections > 500:
            warnings.append("High HTTP connection count may impact system resources")

        return {
            'valid': len(errors) == 0,
            'errors': errors,
            'warnings': warnings
        }

    def _validate_cache_pool(self, config: CachePoolConfig) -> dict[str, Any]:
        """Validate cache pool configuration."""
        errors = []
        warnings = []

        if config.max_memory_mb > 512:
            warnings.append("High cache memory usage may impact system performance")

        if config.ttl_seconds < 30:
            warnings.append("Very short TTL may reduce cache effectiveness")

        return {
            'valid': len(errors) == 0,
            'errors': errors,
            'warnings': warnings
        }


# Global budget manager instance
_budget_manager: ConfigDrivenBudgetManager | None = None


def get_budget_manager() -> ConfigDrivenBudgetManager:
    """Get or create global budget manager instance."""
    global _budget_manager
    if _budget_manager is None:
        _budget_manager = ConfigDrivenBudgetManager()
    return _budget_manager
