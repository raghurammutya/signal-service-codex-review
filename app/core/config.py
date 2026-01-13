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

        client = ConfigServiceClient(
            service_name="signal_service",
            environment=os.getenv("ENVIRONMENT", "prod"),
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


def _get_service_url(service_name: str, fallback_port: Optional[int] = None) -> str:
    """
    Get service URL from config_service.

    ARCHITECTURE COMPLIANCE:
    - Uses config_service for service discovery
    - No hardcoded URLs
    """
    client = _get_config_client()
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

    # If config_service unavailable and we have a fallback port, use it
    if fallback_port:
        return f"http://localhost:{fallback_port}"

    # Otherwise fail-fast
    logger.critical(f"Service URL not available: {service_name}")
    sys.exit(1)


def _bool(val: Optional[str], default: bool = False) -> bool:
    if val is None:
        return default
    return str(val).lower() in ("true", "1", "yes")


class SignalServiceConfig:
    """Settings for Signal Service."""

    def __init__(self):
        # Load service name from config_service
        service_name_from_config = _get_from_config_service(
            "signal_service.service_name",
            required=False,
            is_secret=False,
            default="signal_service"
        )
        self.service_name = service_name_from_config or "signal_service"
        self.environment = _get_config_str("ENVIRONMENT", "dev")
        self._load_from_config()

    def _load_from_config(self):
        # PORT - from config_service (fallback to env if absent)
        self.PORT = _get_config_int("PORT", int(os.getenv("PORT", "8003")))

        # Required secrets from config_service (MANDATORY - fail-fast)
        self.DATABASE_URL = _get_from_config_service("DATABASE_URL", required=True, is_secret=True)
        if not self.DATABASE_URL:
            raise ValueError("DATABASE_URL not found in config_service")

        self.REDIS_URL = _get_from_config_service("REDIS_URL", required=True, is_secret=True)
        if not self.REDIS_URL:
            raise ValueError("REDIS_URL not found in config_service")

        # Redis Sentinel (optional)
        self.REDIS_SENTINEL_ENABLED = _get_config_bool("REDIS_SENTINEL_ENABLED", False)
        self.REDIS_SENTINEL_HOSTS = _get_config_str("REDIS_SENTINEL_HOSTS", "")
        self.REDIS_SENTINEL_MASTER_NAME = _get_config_str("REDIS_SENTINEL_MASTER_NAME", "signal-master")

        # Service URLs from config_service
        self.TICKER_SERVICE_URL = _get_service_url("ticker_service", fallback_port=8089)
        self.INSTRUMENT_SERVICE_URL = _get_config_str("INSTRUMENT_SERVICE_URL", "http://instrument-service:8008")
        self.MARKETPLACE_SERVICE_URL = _get_service_url("marketplace_service", fallback_port=8090)

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

        # Cache & Performance Settings (optional with defaults)
        self.CACHE_TTL_SECONDS = _get_config_int("CACHE_TTL_SECONDS", 300)
        self.MAX_BATCH_SIZE = _get_config_int("MAX_BATCH_SIZE", 100)
        self.MAX_CPU_CORES = _get_config_int("MAX_CPU_CORES", 4)

        # Greeks calculation config (can come from config_service)
        greeks_rate = _get_from_config_service("GREEKS_RISK_FREE_RATE", required=False, is_secret=False, default="0.06")
        self.GREEKS_RISK_FREE_RATE = float(greeks_rate)

        # Redis Stream Config
        self.REDIS_TICK_STREAM_PREFIX = _get_config_str("REDIS_TICK_STREAM_PREFIX", "tick_stream:")
        self.CONSUMER_GROUP_NAME = _get_config_str("CONSUMER_GROUP_NAME", "signal_processors")
        self.CONSUMER_NAME = os.getenv("HOSTNAME", _get_config_str("CONSUMER_NAME", "signal_processor_1"))

        # WebSocket Config
        self.WEBSOCKET_MAX_CONNECTIONS = _get_config_int("WEBSOCKET_MAX_CONNECTIONS", 10000)
        self.WEBSOCKET_HEARTBEAT_INTERVAL = _get_config_int("WEBSOCKET_HEARTBEAT_INTERVAL", 30)

        # Subscription Config
        self.DEFAULT_SUBSCRIPTION_LEASE_SECONDS = _get_config_int("DEFAULT_SUBSCRIPTION_LEASE_SECONDS", 300)
        self.MAX_INDICATORS_PER_TIMEFRAME = _get_config_int("MAX_INDICATORS_PER_TIMEFRAME", 50)

        # ACL Cache
        self.ACL_CACHE_ENABLED = _get_config_bool("ACL_CACHE_ENABLED", True)
        self.ACL_CACHE_TTL_SECONDS = _get_config_int("ACL_CACHE_TTL_SECONDS", 300)

        # Celery (optional)
        celery_broker = _get_from_config_service("CELERY_BROKER_URL", required=False, is_secret=True)
        self.CELERY_BROKER_URL = celery_broker or _get_config_str("CELERY_BROKER_URL", "")

        celery_backend = _get_from_config_service("CELERY_RESULT_BACKEND", required=False, is_secret=True)
        self.CELERY_RESULT_BACKEND = celery_backend or _get_config_str("CELERY_RESULT_BACKEND", "")

        self.ASYNC_COMPUTATION_ENABLED = _get_config_bool("ASYNC_COMPUTATION_ENABLED", False)

        # Metrics
        self.METRICS_ENABLED = _get_config_bool("METRICS_ENABLED", True)
        self.METRICS_PORT = _get_config_int("METRICS_PORT", self.PORT)
        self.METRICS_UPDATE_INTERVAL_SECONDS = _get_config_int("METRICS_UPDATE_INTERVAL_SECONDS", 60)

        # Usage Tracking
        self.USAGE_TRACKING_ENABLED = _get_config_bool("USAGE_TRACKING_ENABLED", True)
        self.USAGE_BATCH_SIZE = _get_config_int("USAGE_BATCH_SIZE", 100)

        # Subscription Service URL (optional)
        self.SUBSCRIPTION_SERVICE_URL = _get_config_str("SUBSCRIPTION_SERVICE_URL", "")

        logger.info("✓ Configuration loaded from config_service and environment")

    def get_tick_stream_name(self, instrument_key: str) -> str:
        return f"{self.REDIS_TICK_STREAM_PREFIX}{instrument_key}"
    
    def get_config(self, key: str, default=None):
        """Get configuration value from config service."""
        return _get_from_config_service(key, required=False, is_secret=False, default=default)


settings = SignalServiceConfig()
