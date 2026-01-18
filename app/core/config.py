"""
Signal Service configuration loader with sensible defaults for dev/test.

ARCHITECTURE COMPLIANCE:
- Config service is MANDATORY (Principle #1)
- All secrets fetched from config_service (Principle #2)
- No fallbacks to environment variables for secrets (Principle #4)
- Fail-fast if config service unavailable
"""

import os
import logging
import sys
from typing import Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# Service registry integration for standardized service URLs
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

# Config service integration - MANDATORY
_config_client = None
_config_loaded = False


def _get_config_client(environment: str = None):
    """
    Get or create config service client with startup resilience.

    Args:
        environment: Explicit environment override. If None, reads from ENVIRONMENT env var.

    ARCHITECTURE COMPLIANCE:
    - Config service is REQUIRED (no fallbacks)
    - Bounded retry with exponential backoff for transient failures
    - Service exits with sys.exit(1) if config service permanently unavailable
    """
    global _config_client, _config_loaded

    if _config_loaded:
        return _config_client

    _config_loaded = True

    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
        from common.config_service.client import ConfigServiceClient

        # Environment can be explicitly provided or from env var for easier testing
        if environment is None:
            environment = os.getenv("ENVIRONMENT")
            if not environment:
                raise ValueError("ENVIRONMENT must be provided explicitly or via environment variable")
        
        client = ConfigServiceClient(
            service_name="signal_service",
            environment=environment,
            timeout=30
        )

        # Retry health check with backoff (3 attempts)
        for attempt in range(3):
            try:
                if client.health_check():
                    logger.info("✓ Config service connected successfully")
                    _config_client = client
                    return _config_client
                else:
                    logger.warning(f"Config service unhealthy (attempt {attempt+1}/3)")
                    if attempt < 2:
                        import time
                        time.sleep(2 ** attempt)  # Exponential backoff: 1s, 2s
            except Exception as retry_error:
                logger.warning(f"Health check failed (attempt {attempt+1}/3): {retry_error}")
                if attempt < 2:
                    import time
                    time.sleep(2 ** attempt)

        # FAIL-FAST: Config service is MANDATORY
        logger.critical("=" * 80)
        logger.critical("CONFIG SERVICE UNAVAILABLE - REFUSING TO START")
        logger.critical("ARCHITECTURE VIOLATION: Config service is MANDATORY")
        logger.critical("=" * 80)
        sys.exit(1)

    except ImportError as e:
        logger.critical(f"Config service client not available: {e}")
        sys.exit(1)
    except Exception as e:
        logger.critical(f"Config service connection failed: {e}")
        sys.exit(1)


def _get_from_config_service(key: str, required: bool = True, is_secret: bool = False, default: Optional[str] = None, environment: str = None) -> Optional[str]:
    """
    Get value from config service (MANDATORY for secrets - no fallbacks).

    ARCHITECTURE COMPLIANCE:
    - Fetches from config_service ONLY (no env var fallbacks for secrets)
    - Fails if required secret not found
    - Logs secret access for audit trail
    """
    client = _get_config_client(environment)
    if not client:
        if required:
            logger.critical(f"Required config/secret not available: {key}")
            sys.exit(1)
        return default

    try:
        if is_secret:
            value = client.get_secret(key, required=required)
            if value:
                logger.debug(f"✓ Loaded secret: {key}")
        else:
            value = client.get_config(key)
            if value:
                logger.debug(f"✓ Loaded config: {key}")

        return value if value else default

    except Exception as e:
        logger.error(f"Failed to fetch {key} from config service: {e}")
        if required:
            logger.critical(f"Required config/secret not available: {key}")
            sys.exit(1)
        return default


# _get_config_int removed - use explicit config_service calls with required validation


# _get_config_bool removed - use explicit config_service calls with required validation


# _get_config_str removed - use explicit config_service calls with required validation


def _get_service_url(service_name: str, fallback_port: Optional[int] = None, environment: str = None) -> str:
    """
    Get service URL from config_service.

    ARCHITECTURE COMPLIANCE:
    - Uses config_service for service discovery
    - No hardcoded URLs
    """
    client = _get_config_client(environment)
    if client:
        try:
            # Use docker-compose service name for inter-container communication
            # Map service names to docker-compose service names
            service_host_map = {
                "ticker_service": "ticker-service",
                "marketplace_service": "marketplace-service",
                "order_service": "order-service",
                "user_service": "user-service"
            }
            host = service_host_map.get(service_name, service_name)
            url = client.get_service_url(service_name, host=host)
            if url:
                return url
        except Exception as e:
            logger.warning(f"Failed to get service URL for {service_name}: {e}")

    # No fallbacks allowed - config_service is mandatory
    logger.critical(f"Service URL not available for {service_name} - config_service required")
    raise ValueError(f"Service URL for {service_name} not found in config_service")


def _bool(val: Optional[str], default: bool = False) -> bool:
    if val is None:
        return default
    return str(val).lower() in ("true", "1", "yes")


class SignalServiceConfig:
    """Settings for Signal Service."""

    def __init__(self, environment: str = None):
        # Store environment for explicit override during testing
        self._environment = environment
        
        # Load service name from config_service
        service_name_from_config = _get_from_config_service(
            "signal_service.service_name",
            required=True,
            is_secret=False,
            environment=self._environment
        )
        if not service_name_from_config:
            raise ValueError("service_name not found in config_service")
        self.service_name = service_name_from_config
        self.environment = _get_from_config_service("signal_service.environment", required=True, is_secret=False, environment=self._environment)
        if not self.environment:
            raise ValueError("environment not found in config_service")
        self._load_from_config()

    def _load_from_config(self):
        # Service networking configuration - from config_service only
        self.SERVICE_HOST = _get_from_config_service("signal_service.service_host", required=True, is_secret=False, environment=self._environment)
        if not self.SERVICE_HOST:
            raise ValueError("service_host not found in config_service")
        
        self.SERVICE_PORT = _get_from_config_service("signal_service.service_port", required=True, is_secret=False, environment=self._environment)
        if not self.SERVICE_PORT:
            raise ValueError("service_port not found in config_service")
        self.SERVICE_PORT = int(self.SERVICE_PORT)
        
        # PORT - from config_service only (keeping for backwards compatibility)
        self.PORT = self.SERVICE_PORT
        
        # Dashboard integration URL - from config_service only
        self.DASHBOARD_URL = _get_from_config_service("signal_service.dashboard_url", required=True, is_secret=False, environment=self._environment)
        if not self.DASHBOARD_URL:
            raise ValueError("dashboard_url not found in config_service")

        # Required secrets from config_service (MANDATORY - fail-fast)
        self.DATABASE_URL = _get_from_config_service("DATABASE_URL", required=True, is_secret=True, environment=self._environment)
        if not self.DATABASE_URL:
            raise ValueError("DATABASE_URL not found in config_service")

        self.REDIS_URL = _get_from_config_service("REDIS_URL", required=True, is_secret=True, environment=self._environment)
        if not self.REDIS_URL:
            raise ValueError("REDIS_URL not found in config_service")

        # Redis Sentinel - from config_service only
        sentinel_enabled = _get_from_config_service("signal_service.redis_sentinel_enabled", required=True, is_secret=False, environment=self._environment)
        if not sentinel_enabled:
            raise ValueError("redis_sentinel_enabled not found in config_service")
        self.REDIS_SENTINEL_ENABLED = sentinel_enabled.lower() == "true"
        self.REDIS_SENTINEL_HOSTS = _get_from_config_service("signal_service.redis_sentinel_hosts", required=True, is_secret=False, environment=self._environment)
        if not self.REDIS_SENTINEL_HOSTS:
            raise ValueError("redis_sentinel_hosts not found in config_service")
        self.REDIS_SENTINEL_MASTER_NAME = _get_from_config_service("signal_service.redis_sentinel_master_name", required=True, is_secret=False, environment=self._environment)
        if not self.REDIS_SENTINEL_MASTER_NAME:
            raise ValueError("redis_sentinel_master_name not found in config_service")

        # Service URLs from config_service
        self.TICKER_SERVICE_URL = _get_from_config_service("signal_service.ticker_service_url", required=True, is_secret=False, environment=self._environment)
        if not self.TICKER_SERVICE_URL:
            raise ValueError("ticker_service_url not found in config_service")
        self.INSTRUMENT_SERVICE_URL = _get_from_config_service("signal_service.instrument_service_url", required=True, is_secret=False, environment=self._environment)
        if not self.INSTRUMENT_SERVICE_URL:
            raise ValueError("instrument_service_url not found in config_service")
        self.MARKETPLACE_SERVICE_URL = _get_from_config_service("signal_service.marketplace_service_url", required=True, is_secret=False, environment=self._environment)
        if not self.MARKETPLACE_SERVICE_URL:
            raise ValueError("marketplace_service_url not found in config_service")
        self.USER_SERVICE_URL = _get_from_config_service("signal_service.user_service_url", required=True, is_secret=False, environment=self._environment)
        if not self.USER_SERVICE_URL:
            raise ValueError("user_service_url not found in config_service")
        
        # Additional service integration URLs
        self.CALENDAR_SERVICE_URL = _get_from_config_service("signal_service.calendar_service_url", required=True, is_secret=False, environment=self._environment)
        if not self.CALENDAR_SERVICE_URL:
            raise ValueError("calendar_service_url not found in config_service")
        
        self.ALERT_SERVICE_URL = _get_from_config_service("signal_service.alert_service_url", required=True, is_secret=False, environment=self._environment)
        if not self.ALERT_SERVICE_URL:
            raise ValueError("alert_service_url not found in config_service")
        
        self.MESSAGING_SERVICE_URL = _get_from_config_service("signal_service.messaging_service_url", required=True, is_secret=False, environment=self._environment)
        if not self.MESSAGING_SERVICE_URL:
            raise ValueError("messaging_service_url not found in config_service")

        # Gateway authentication secrets
        self.gateway_secret = _get_from_config_service(
            "GATEWAY_SECRET",
            required=True,
            is_secret=True
        , environment=self._environment)
        if not self.gateway_secret:
            raise ValueError("GATEWAY_SECRET not found in config_service")
        
        # Internal API key for service-to-service communication
        self.internal_api_key = _get_from_config_service(
            "INTERNAL_API_KEY",
            required=False,
            is_secret=True
        , environment=self._environment)
        
        # Marketplace webhook secret (optional)
        self.MARKETPLACE_WEBHOOK_SECRET = _get_from_config_service(
            "MARKETPLACE_WEBHOOK_SECRET",
            required=False,
            is_secret=True
        , environment=self._environment)
        
        # Email webhook secret (optional)
        self.EMAIL_WEBHOOK_SECRET = _get_from_config_service(
            "EMAIL_WEBHOOK_SECRET",
            required=False,
            is_secret=True
        , environment=self._environment)
        
        # Watermark configuration secrets
        self.WATERMARK_SECRET = _get_from_config_service(
            "WATERMARK_SECRET",
            required=False,
            is_secret=True
        , environment=self._environment)
        
        self.WATERMARK_ENFORCEMENT_ENABLED = _get_from_config_service(
            "WATERMARK_ENFORCEMENT_ENABLED",
            required=False,
            is_secret=False,
            default="true"
        , environment=self._environment)
        
        self.WATERMARK_ENFORCEMENT_POLICY = _get_from_config_service(
            "WATERMARK_ENFORCEMENT_POLICY",
            required=False,
            is_secret=False,
            default="auto-enforce"
        , environment=self._environment)

        # Cache & Performance Settings - from config_service only
        cache_ttl = _get_from_config_service("signal_service.cache_ttl_seconds", required=True, is_secret=False, environment=self._environment)
        if not cache_ttl:
            raise ValueError("cache_ttl_seconds not found in config_service")
        self.CACHE_TTL_SECONDS = int(cache_ttl)
        max_batch = _get_from_config_service("signal_service.max_batch_size", required=True, is_secret=False, environment=self._environment)
        if not max_batch:
            raise ValueError("max_batch_size not found in config_service")
        self.MAX_BATCH_SIZE = int(max_batch)
        max_cores = _get_from_config_service("signal_service.max_cpu_cores", required=True, is_secret=False, environment=self._environment)
        if not max_cores:
            raise ValueError("max_cpu_cores not found in config_service")
        self.MAX_CPU_CORES = int(max_cores)
        
        # Service integration timeout - from config_service only
        integration_timeout = _get_from_config_service("signal_service.service_integration_timeout", required=True, is_secret=False, environment=self._environment)
        if not integration_timeout:
            raise ValueError("service_integration_timeout not found in config_service")
        self.SERVICE_INTEGRATION_TIMEOUT = float(integration_timeout)

        # Greeks calculation config - from config_service only
        greeks_rate = _get_from_config_service("signal_service.greeks_risk_free_rate", required=True, is_secret=False, environment=self._environment)
        if not greeks_rate:
            raise ValueError("greeks_risk_free_rate not found in config_service")
        self.GREEKS_RISK_FREE_RATE = float(greeks_rate)

        # Redis Stream Config - from config_service only
        self.REDIS_TICK_STREAM_PREFIX = _get_from_config_service("signal_service.redis_tick_stream_prefix", required=True, is_secret=False, environment=self._environment)
        if not self.REDIS_TICK_STREAM_PREFIX:
            raise ValueError("redis_tick_stream_prefix not found in config_service")
        self.CONSUMER_GROUP_NAME = _get_from_config_service("signal_service.consumer_group_name", required=True, is_secret=False, environment=self._environment)
        if not self.CONSUMER_GROUP_NAME:
            raise ValueError("consumer_group_name not found in config_service")
        self.CONSUMER_NAME = _get_from_config_service("signal_service.consumer_name", required=True, is_secret=False, environment=self._environment)
        if not self.CONSUMER_NAME:
            raise ValueError("consumer_name not found in config_service")

        # WebSocket Config - from config_service only
        ws_max_conn = _get_from_config_service("signal_service.websocket_max_connections", required=True, is_secret=False, environment=self._environment)
        if not ws_max_conn:
            raise ValueError("websocket_max_connections not found in config_service")
        self.WEBSOCKET_MAX_CONNECTIONS = int(ws_max_conn)
        ws_heartbeat = _get_from_config_service("signal_service.websocket_heartbeat_interval", required=True, is_secret=False, environment=self._environment)
        if not ws_heartbeat:
            raise ValueError("websocket_heartbeat_interval not found in config_service")
        self.WEBSOCKET_HEARTBEAT_INTERVAL = int(ws_heartbeat)

        # Subscription Config - from config_service only
        lease_seconds = _get_from_config_service("signal_service.default_subscription_lease_seconds", required=True, is_secret=False, environment=self._environment)
        if not lease_seconds:
            raise ValueError("default_subscription_lease_seconds not found in config_service")
        self.DEFAULT_SUBSCRIPTION_LEASE_SECONDS = int(lease_seconds)
        max_indicators = _get_from_config_service("signal_service.max_indicators_per_timeframe", required=True, is_secret=False, environment=self._environment)
        if not max_indicators:
            raise ValueError("max_indicators_per_timeframe not found in config_service")
        self.MAX_INDICATORS_PER_TIMEFRAME = int(max_indicators)

        # ACL Cache - from config_service only
        acl_enabled = _get_from_config_service("signal_service.acl_cache_enabled", required=True, is_secret=False, environment=self._environment)
        if not acl_enabled:
            raise ValueError("acl_cache_enabled not found in config_service")
        self.ACL_CACHE_ENABLED = acl_enabled.lower() == "true"
        acl_ttl = _get_from_config_service("signal_service.acl_cache_ttl_seconds", required=True, is_secret=False, environment=self._environment)
        if not acl_ttl:
            raise ValueError("acl_cache_ttl_seconds not found in config_service")
        self.ACL_CACHE_TTL_SECONDS = int(acl_ttl)

        # Celery - from config_service only
        self.CELERY_BROKER_URL = _get_from_config_service("signal_service.celery_broker_url", required=True, is_secret=True, environment=self._environment)
        if not self.CELERY_BROKER_URL:
            raise ValueError("celery_broker_url not found in config_service")
        self.CELERY_RESULT_BACKEND = _get_from_config_service("signal_service.celery_result_backend", required=True, is_secret=True, environment=self._environment)
        if not self.CELERY_RESULT_BACKEND:
            raise ValueError("celery_result_backend not found in config_service")
        async_enabled = _get_from_config_service("signal_service.async_computation_enabled", required=True, is_secret=False, environment=self._environment)
        if not async_enabled:
            raise ValueError("async_computation_enabled not found in config_service")
        self.ASYNC_COMPUTATION_ENABLED = async_enabled.lower() == "true"

        # Metrics - from config_service only
        metrics_enabled = _get_from_config_service("signal_service.metrics_enabled", required=True, is_secret=False, environment=self._environment)
        if not metrics_enabled:
            raise ValueError("metrics_enabled not found in config_service")
        self.METRICS_ENABLED = metrics_enabled.lower() == "true"
        metrics_port = _get_from_config_service("signal_service.metrics_port", required=True, is_secret=False, environment=self._environment)
        if not metrics_port:
            raise ValueError("metrics_port not found in config_service")
        self.METRICS_PORT = int(metrics_port)
        metrics_interval = _get_from_config_service("signal_service.metrics_update_interval_seconds", required=True, is_secret=False, environment=self._environment)
        if not metrics_interval:
            raise ValueError("metrics_update_interval_seconds not found in config_service")
        self.METRICS_UPDATE_INTERVAL_SECONDS = int(metrics_interval)

        # Usage Tracking - from config_service only
        tracking_enabled = _get_from_config_service("signal_service.usage_tracking_enabled", required=True, is_secret=False, environment=self._environment)
        if not tracking_enabled:
            raise ValueError("usage_tracking_enabled not found in config_service")
        self.USAGE_TRACKING_ENABLED = tracking_enabled.lower() == "true"
        usage_batch = _get_from_config_service("signal_service.usage_batch_size", required=True, is_secret=False, environment=self._environment)
        if not usage_batch:
            raise ValueError("usage_batch_size not found in config_service")
        self.USAGE_BATCH_SIZE = int(usage_batch)

        # Subscription Service URL - from config_service only
        self.SUBSCRIPTION_SERVICE_URL = _get_from_config_service("signal_service.subscription_service_url", required=True, is_secret=False, environment=self._environment)
        if not self.SUBSCRIPTION_SERVICE_URL:
            raise ValueError("subscription_service_url not found in config_service")

        logger.info("✓ Configuration loaded from config_service and environment")

    def get_tick_stream_name(self, instrument_key: str) -> str:
        return f"{self.REDIS_TICK_STREAM_PREFIX}{instrument_key}"
    
    def get_config(self, key: str, default=None):
        """Get configuration value from config service."""
        return _get_from_config_service(key, required=False, is_secret=False, default=default, environment=self._environment)


# Lazy initialization - prevents import-time environment variable dependency
_settings_instance = None

def get_settings(environment: str = None) -> SignalServiceConfig:
    """Get or create settings instance with optional environment override.
    
    Args:
        environment: Explicit environment override for testing.
                    If None, uses environment variable.
    
    Returns:
        SignalServiceConfig instance
    """
    global _settings_instance
    
    # For testing or explicit environment override
    if environment is not None:
        return SignalServiceConfig(environment=environment)
    
    # Lazy initialization for normal usage
    if _settings_instance is None:
        _settings_instance = SignalServiceConfig()
    
    return _settings_instance

# Backward compatibility with lazy loading
class _LazySettings:
    def __getattr__(self, name):
        return getattr(get_settings(), name)
        
    def get_config(self, key: str, default=None):
        return get_settings().get_config(key, default)
        
    def get_tick_stream_name(self, instrument_key: str):
        return get_settings().get_tick_stream_name(instrument_key)

settings = _LazySettings()
