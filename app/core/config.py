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


def _get_config_client():
    """
    Get or create config service client (MANDATORY - fail-fast if unavailable).

    ARCHITECTURE COMPLIANCE:
    - Config service is REQUIRED (no fallbacks)
    - Service exits with sys.exit(1) if config service unhealthy
    - Retries with exponential backoff before failing
    """
    global _config_client, _config_loaded

    if _config_loaded:
        return _config_client

    _config_loaded = True

    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
        from common.config_service.client import ConfigServiceClient

        # ARCHITECTURE COMPLIANCE: Environment MUST be provided externally (no defaults)
        environment = os.getenv("ENVIRONMENT")
        if not environment:
            raise ValueError("ENVIRONMENT variable not set. Config service requires explicit environment - no defaults allowed per architecture.")
        
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


def _get_from_config_service(key: str, required: bool = True, is_secret: bool = False, default: Optional[str] = None) -> Optional[str]:
    """
    Get value from config service (MANDATORY for secrets - no fallbacks).

    ARCHITECTURE COMPLIANCE:
    - Fetches from config_service ONLY (no env var fallbacks for secrets)
    - Fails if required secret not found
    - Logs secret access for audit trail
    """
    client = _get_config_client()
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


def _get_config_int(key: str, default: int) -> int:
    val = _get_from_config_service(key, required=False, is_secret=False)
    try:
        return int(val) if val else default
    except ValueError:
        logger.warning("Config %s is not int: %s", key, val)
        return default


def _get_config_bool(key: str, default: bool) -> bool:
    val = _get_from_config_service(key, required=False, is_secret=False)
    if val is None or val == "":
        return default
    return str(val).lower() in ("1", "true", "yes", "on")


def _get_config_str(key: str, default: str = "") -> str:
    val = _get_from_config_service(key, required=False, is_secret=False)
    return val if val else default


# Removed _get_service_url function - replaced with direct config_service calls
# per Architecture Principle #1: Config service exclusivity (no fallbacks)


def _bool(val: Optional[str], default: bool = False) -> bool:
    if val is None:
        return default
    return str(val).lower() in ("true", "1", "yes")


class SignalServiceConfig:
    """Settings for Signal Service."""

    def __init__(self):
        # Load service name from config_service (MANDATORY - no defaults per architecture)
        service_name_from_config = _get_from_config_service(
            "signal_service.service_name",
            required=True,
            is_secret=False
        )
        if not service_name_from_config:
            raise ValueError("signal_service.service_name not found in config_service")
        self.service_name = service_name_from_config
        # ENVIRONMENT from config_service (MANDATORY - no defaults per architecture)
        self.environment = _get_from_config_service("ENVIRONMENT", required=True, is_secret=False)
        if not self.environment:
            raise ValueError("ENVIRONMENT not found in config_service")
        self._load_from_config()

    def _load_from_config(self):
        # PORT - from config_service (MANDATORY - no fallbacks per architecture)
        self.PORT = _get_from_config_service("SIGNAL_SERVICE_PORT", required=True, is_secret=False)
        if not self.PORT:
            raise ValueError("SIGNAL_SERVICE_PORT not found in config_service")
        self.PORT = int(self.PORT)

        # Required secrets from config_service (MANDATORY - fail-fast)
        self.DATABASE_URL = _get_from_config_service("DATABASE_URL", required=True, is_secret=True)
        if not self.DATABASE_URL:
            raise ValueError("DATABASE_URL not found in config_service")

        self.REDIS_URL = _get_from_config_service("REDIS_URL", required=True, is_secret=True)
        if not self.REDIS_URL:
            raise ValueError("REDIS_URL not found in config_service")

        # Redis Sentinel (MANDATORY from config_service - no defaults)
        self.REDIS_SENTINEL_ENABLED = _get_from_config_service("REDIS_SENTINEL_ENABLED", required=True, is_secret=False)
        if self.REDIS_SENTINEL_ENABLED is None:
            raise ValueError("REDIS_SENTINEL_ENABLED not found in config_service")
        self.REDIS_SENTINEL_ENABLED = self.REDIS_SENTINEL_ENABLED.lower() == "true"
        
        self.REDIS_SENTINEL_HOSTS = _get_from_config_service("REDIS_SENTINEL_HOSTS", required=True, is_secret=False)
        if not self.REDIS_SENTINEL_HOSTS:
            raise ValueError("REDIS_SENTINEL_HOSTS not found in config_service")
            
        self.REDIS_SENTINEL_MASTER_NAME = _get_from_config_service("REDIS_SENTINEL_MASTER_NAME", required=True, is_secret=False)
        if not self.REDIS_SENTINEL_MASTER_NAME:
            raise ValueError("REDIS_SENTINEL_MASTER_NAME not found in config_service")

        # Service URLs from config_service (MANDATORY - no fallbacks per architecture)
        self.TICKER_SERVICE_URL = _get_from_config_service("TICKER_SERVICE_URL", required=True, is_secret=False)
        if not self.TICKER_SERVICE_URL:
            raise ValueError("TICKER_SERVICE_URL not found in config_service")
            
        self.INSTRUMENT_SERVICE_URL = _get_from_config_service("INSTRUMENT_SERVICE_URL", required=True, is_secret=False)
        if not self.INSTRUMENT_SERVICE_URL:
            raise ValueError("INSTRUMENT_SERVICE_URL not found in config_service")
            
        self.MARKETPLACE_SERVICE_URL = _get_from_config_service("MARKETPLACE_SERVICE_URL", required=True, is_secret=False)
        if not self.MARKETPLACE_SERVICE_URL:
            raise ValueError("MARKETPLACE_SERVICE_URL not found in config_service")

        # Gateway authentication secrets
        self.gateway_secret = _get_from_config_service(
            "GATEWAY_SECRET",
            required=True,
            is_secret=True
        )
        if not self.gateway_secret:
            raise ValueError("GATEWAY_SECRET not found in config_service")
        
        # Internal API key for service-to-service communication
        self.internal_api_key = _get_from_config_service(
            "INTERNAL_API_KEY",
            required=False,
            is_secret=True
        )
        
        # Marketplace webhook secret (optional)
        self.MARKETPLACE_WEBHOOK_SECRET = _get_from_config_service(
            "MARKETPLACE_WEBHOOK_SECRET",
            required=False,
            is_secret=True
        )

        # Cache & Performance Settings (MANDATORY from config_service - no defaults)
        self.CACHE_TTL_SECONDS = _get_from_config_service("CACHE_TTL_SECONDS", required=True, is_secret=False)
        if not self.CACHE_TTL_SECONDS:
            raise ValueError("CACHE_TTL_SECONDS not found in config_service")
        self.CACHE_TTL_SECONDS = int(self.CACHE_TTL_SECONDS)
        
        self.MAX_BATCH_SIZE = _get_from_config_service("MAX_BATCH_SIZE", required=True, is_secret=False)
        if not self.MAX_BATCH_SIZE:
            raise ValueError("MAX_BATCH_SIZE not found in config_service")
        self.MAX_BATCH_SIZE = int(self.MAX_BATCH_SIZE)
        
        self.MAX_CPU_CORES = _get_from_config_service("MAX_CPU_CORES", required=True, is_secret=False)
        if not self.MAX_CPU_CORES:
            raise ValueError("MAX_CPU_CORES not found in config_service")
        self.MAX_CPU_CORES = int(self.MAX_CPU_CORES)

        # Greeks calculation config (MANDATORY from config_service - no defaults)
        greeks_rate = _get_from_config_service("GREEKS_RISK_FREE_RATE", required=True, is_secret=False)
        if not greeks_rate:
            raise ValueError("GREEKS_RISK_FREE_RATE not found in config_service")
        self.GREEKS_RISK_FREE_RATE = float(greeks_rate)

        # Redis Stream Config (MANDATORY from config_service - no defaults)
        self.REDIS_TICK_STREAM_PREFIX = _get_from_config_service("REDIS_TICK_STREAM_PREFIX", required=True, is_secret=False)
        if not self.REDIS_TICK_STREAM_PREFIX:
            raise ValueError("REDIS_TICK_STREAM_PREFIX not found in config_service")
            
        self.CONSUMER_GROUP_NAME = _get_from_config_service("CONSUMER_GROUP_NAME", required=True, is_secret=False)
        if not self.CONSUMER_GROUP_NAME:
            raise ValueError("CONSUMER_GROUP_NAME not found in config_service")
        # CONSUMER_NAME from config_service (MANDATORY - no defaults per architecture)
        self.CONSUMER_NAME = _get_from_config_service("CONSUMER_NAME", required=True, is_secret=False)
        if not self.CONSUMER_NAME:
            raise ValueError("CONSUMER_NAME not found in config_service")

        # WebSocket Config (MANDATORY from config_service - no defaults)
        ws_max_conn = _get_from_config_service("WEBSOCKET_MAX_CONNECTIONS", required=True, is_secret=False)
        if not ws_max_conn:
            raise ValueError("WEBSOCKET_MAX_CONNECTIONS not found in config_service")
        self.WEBSOCKET_MAX_CONNECTIONS = int(ws_max_conn)
        
        ws_heartbeat = _get_from_config_service("WEBSOCKET_HEARTBEAT_INTERVAL", required=True, is_secret=False)
        if not ws_heartbeat:
            raise ValueError("WEBSOCKET_HEARTBEAT_INTERVAL not found in config_service")
        self.WEBSOCKET_HEARTBEAT_INTERVAL = int(ws_heartbeat)

        # Subscription Config (MANDATORY from config_service - no defaults)
        lease_seconds = _get_from_config_service("DEFAULT_SUBSCRIPTION_LEASE_SECONDS", required=True, is_secret=False)
        if not lease_seconds:
            raise ValueError("DEFAULT_SUBSCRIPTION_LEASE_SECONDS not found in config_service")
        self.DEFAULT_SUBSCRIPTION_LEASE_SECONDS = int(lease_seconds)
        
        max_indicators = _get_from_config_service("MAX_INDICATORS_PER_TIMEFRAME", required=True, is_secret=False)
        if not max_indicators:
            raise ValueError("MAX_INDICATORS_PER_TIMEFRAME not found in config_service")
        self.MAX_INDICATORS_PER_TIMEFRAME = int(max_indicators)

        # ACL Cache (MANDATORY from config_service - no defaults)
        acl_enabled = _get_from_config_service("ACL_CACHE_ENABLED", required=True, is_secret=False)
        if acl_enabled is None:
            raise ValueError("ACL_CACHE_ENABLED not found in config_service")
        self.ACL_CACHE_ENABLED = acl_enabled.lower() == "true"
        
        acl_ttl = _get_from_config_service("ACL_CACHE_TTL_SECONDS", required=True, is_secret=False)
        if not acl_ttl:
            raise ValueError("ACL_CACHE_TTL_SECONDS not found in config_service")
        self.ACL_CACHE_TTL_SECONDS = int(acl_ttl)

        # Celery (MANDATORY from config_service - no defaults)
        celery_broker = _get_from_config_service("CELERY_BROKER_URL", required=True, is_secret=True)
        if not celery_broker:
            raise ValueError("CELERY_BROKER_URL not found in config_service")
        self.CELERY_BROKER_URL = celery_broker

        celery_backend = _get_from_config_service("CELERY_RESULT_BACKEND", required=True, is_secret=True)
        if not celery_backend:
            raise ValueError("CELERY_RESULT_BACKEND not found in config_service")
        self.CELERY_RESULT_BACKEND = celery_backend

        async_enabled = _get_from_config_service("ASYNC_COMPUTATION_ENABLED", required=True, is_secret=False)
        if async_enabled is None:
            raise ValueError("ASYNC_COMPUTATION_ENABLED not found in config_service")
        self.ASYNC_COMPUTATION_ENABLED = async_enabled.lower() == "true"

        # Metrics (MANDATORY from config_service - no defaults)
        metrics_enabled = _get_from_config_service("METRICS_ENABLED", required=True, is_secret=False)
        if metrics_enabled is None:
            raise ValueError("METRICS_ENABLED not found in config_service")
        self.METRICS_ENABLED = metrics_enabled.lower() == "true"
        
        metrics_port = _get_from_config_service("METRICS_PORT", required=True, is_secret=False)
        if not metrics_port:
            raise ValueError("METRICS_PORT not found in config_service")
        self.METRICS_PORT = int(metrics_port)
        
        metrics_interval = _get_from_config_service("METRICS_UPDATE_INTERVAL_SECONDS", required=True, is_secret=False)
        if not metrics_interval:
            raise ValueError("METRICS_UPDATE_INTERVAL_SECONDS not found in config_service")
        self.METRICS_UPDATE_INTERVAL_SECONDS = int(metrics_interval)

        # Usage Tracking (MANDATORY from config_service - no defaults)
        usage_enabled = _get_from_config_service("USAGE_TRACKING_ENABLED", required=True, is_secret=False)
        if usage_enabled is None:
            raise ValueError("USAGE_TRACKING_ENABLED not found in config_service")
        self.USAGE_TRACKING_ENABLED = usage_enabled.lower() == "true"
        
        usage_batch = _get_from_config_service("USAGE_BATCH_SIZE", required=True, is_secret=False)
        if not usage_batch:
            raise ValueError("USAGE_BATCH_SIZE not found in config_service")
        self.USAGE_BATCH_SIZE = int(usage_batch)

        # Subscription Service URL (MANDATORY from config_service - no defaults)
        subscription_url = _get_from_config_service("SUBSCRIPTION_SERVICE_URL", required=True, is_secret=False)
        if not subscription_url:
            raise ValueError("SUBSCRIPTION_SERVICE_URL not found in config_service")
        self.SUBSCRIPTION_SERVICE_URL = subscription_url

        logger.info("✓ Configuration loaded from config_service and environment")

    def get_tick_stream_name(self, instrument_key: str) -> str:
        return f"{self.REDIS_TICK_STREAM_PREFIX}{instrument_key}"
    
    def get_config(self, key: str):
        """Get configuration value from config service (MANDATORY - no defaults per architecture)."""
        value = _get_from_config_service(key, required=True, is_secret=False)
        if value is None:
            raise ValueError(f"Configuration key '{key}' not found in config_service")
        return value


settings = SignalServiceConfig()
