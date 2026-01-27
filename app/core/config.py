"""
Signal Service configuration loader with sensible defaults for dev/test.

ARCHITECTURE COMPLIANCE:
- Config service is MANDATORY (Principle #1)
- All secrets fetched from config_service (Principle #2)
- No fallbacks to environment variables for secrets (Principle #4)
- Fail-fast if config service unavailable
"""

import logging
import os
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Service registry integration for standardized service URLs
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

# Config service integration - MANDATORY
_config_client = None
_config_loaded = False

# Define ConfigServiceError for fallback handling
class ConfigServiceError(Exception):
    """Exception raised when config service operations fail"""


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
        from common.config_service.client import ConfigServiceClient, ConfigServiceError

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


def _get_from_config_service(key: str, required: bool = True, is_secret: bool = False, default: str | None = None) -> str | None:
    """
    Get value from config service ONLY - no environment variable fallbacks.

    ARCHITECTURE COMPLIANCE:
    - Fetches from config_service ONLY
    - Fails gracefully with clear message if config service lacks required parameters
    - No fallbacks to environment variables (config_service is the single source of truth)
    """
    client = _get_config_client()
    if not client:
        if required:
            logger.critical(f"CONFIG SERVICE UNAVAILABLE: Cannot retrieve required {key}")
            logger.critical("Add this parameter to config service or mark as optional")
            sys.exit(1)
        return default

    try:
        if is_secret:
            value = client.get_secret(key, required=False)  # Don't let client exit, handle here
            if value:
                logger.debug(f"✓ Loaded secret: {key}")
            elif required:
                logger.critical(f"MISSING SECRET IN CONFIG SERVICE: {key}")
                logger.critical(f"Add secret '{key}' to config service for signal_service")
                sys.exit(1)
        else:
            value = client.get_config(key, required=False)  # Don't let client exit, handle here
            if value:
                logger.debug(f"✓ Loaded config: {key}")
            elif required:
                logger.critical(f"MISSING CONFIG IN CONFIG SERVICE: {key}")
                logger.critical(f"Add config '{key}' to config service for signal_service")
                sys.exit(1)

        return value if value else default

    except Exception as e:
        logger.error(f"Config service error for {key}: {e}")
        if required:
            logger.critical(f"CONFIG SERVICE ERROR: Cannot retrieve required {key}")
            logger.critical("Fix config service connectivity or add missing parameter")
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


def _get_service_url(service_name: str) -> str:
    """
    Get service URL from config_service exclusively.

    ARCHITECTURE COMPLIANCE:
    - Uses config_service for service discovery only
    - No hardcoded URLs or fallback ports
    - Raises exceptions for Docker network alias fallback handling
    """
    client = _get_config_client()
    if not client:
        logger.warning(f"Config service unavailable - cannot get URL for {service_name}")
        raise ConfigServiceError(f"Config service unavailable for {service_name}")

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

        # No URL found in config_service - raise exception for fallback handling
        logger.warning(f"Service URL not found in config_service: {service_name}")
        raise ConfigServiceError(f"Service URL not found in config_service: {service_name}")

    except Exception as e:
        logger.warning(f"Failed to get service URL for {service_name}: {e}")
        raise ConfigServiceError(f"Failed to get service URL for {service_name}: {e}") from e


def _bool(val: str | None, default: bool = False) -> bool:
    if val is None:
        return default
    return str(val).lower() in ("true", "1", "yes")


class SignalServiceConfig:
    """Settings for Signal Service - startup via docker-compose.production.yml only."""

    def __init__(self):
        # REQUIRED: These must be provided by docker-compose.production.yml
        self.service_name = os.getenv("SERVICE_NAME")
        if not self.service_name:
            logger.critical("SERVICE_NAME must be provided in docker-compose.production.yml")
            sys.exit(1)

        self.environment = os.getenv("ENVIRONMENT")
        if not self.environment:
            logger.critical("ENVIRONMENT must be provided in docker-compose.production.yml")
            sys.exit(1)

        if self.environment != "production":
            logger.critical(f"ENVIRONMENT must be 'production', got: {self.environment}")
            sys.exit(1)

        self.PORT = os.getenv("PORT")
        if not self.PORT:
            logger.critical("PORT must be provided in docker-compose.production.yml")
            sys.exit(1)
        self.PORT = int(self.PORT)

        self.DATABASE_URL = os.getenv("DATABASE_URL")
        if not self.DATABASE_URL:
            logger.critical("DATABASE_URL must be provided in docker-compose.production.yml")
            sys.exit(1)

        self.REDIS_URL = os.getenv("REDIS_URL")
        if not self.REDIS_URL:
            logger.critical("REDIS_URL must be provided in docker-compose.production.yml")
            sys.exit(1)

        logger.info(f"✓ Basic configuration loaded from docker-compose for {self.service_name} in {self.environment}")

        # Load remaining configuration from config_service
        self._load_from_config_service()

    def _load_from_config_service(self):
        # Load additional configuration from config_service
        # Basic parameters already loaded from docker-compose environment variables
        logger.info("Loading additional configuration from config_service...")

        # DATABASE_URL and REDIS_URL already loaded from docker-compose environment

        # Redis Sentinel (optional)
        self.REDIS_SENTINEL_ENABLED = _get_config_bool("REDIS_SENTINEL_ENABLED", False)
        self.REDIS_SENTINEL_HOSTS = _get_config_str("REDIS_SENTINEL_HOSTS", "")
        self.REDIS_SENTINEL_MASTER_NAME = _get_config_str("REDIS_SENTINEL_MASTER_NAME", "signal-master")

        # Service URLs - use Docker network aliases as fallback
        try:
            self.TICKER_SERVICE_URL = _get_service_url("ticker_service")
        except Exception:
            # Fallback to Docker network alias (works with --network-alias ticker-service)
            self.TICKER_SERVICE_URL = "http://ticker-service:8089"
            logger.info("✓ Using Docker network alias for ticker_service: http://ticker-service:8089")
        # INSTRUMENT_SERVICE_URL → Use TICKER_SERVICE_URL (ticker service handles instruments)
        self.INSTRUMENT_SERVICE_URL = self.TICKER_SERVICE_URL

        try:
            self.MARKETPLACE_SERVICE_URL = _get_service_url("marketplace_service")
        except Exception:
            # Fallback to Docker network alias (works with --network-alias marketplace-service)
            self.MARKETPLACE_SERVICE_URL = "http://marketplace-service:8091"
            logger.info("✓ Using Docker network alias for marketplace_service: http://marketplace-service:8091")

        # Gateway authentication secrets (use fallback to INTERNAL_API_KEY if not found)
        self.gateway_secret = _get_from_config_service(
            "GATEWAY_SECRET",
            required=False,
            is_secret=True
        ) or _get_from_config_service(
            "INTERNAL_API_KEY",
            required=True,
            is_secret=True
        )
        if not self.gateway_secret:
            raise ValueError("GATEWAY_SECRET or INTERNAL_API_KEY not found in config_service")

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
        # HOSTNAME from config_service only (architecture compliance)
        self.CONSUMER_NAME = _get_config_str("CONSUMER_NAME", "signal_processor_1")

        # WebSocket Config
        self.WEBSOCKET_MAX_CONNECTIONS = _get_config_int("WEBSOCKET_MAX_CONNECTIONS", 10000)
        self.WEBSOCKET_HEARTBEAT_INTERVAL = _get_config_int("WEBSOCKET_HEARTBEAT_INTERVAL", 30)

        # Subscription Config
        self.DEFAULT_SUBSCRIPTION_LEASE_SECONDS = _get_config_int("DEFAULT_SUBSCRIPTION_LEASE_SECONDS", 300)
        self.MAX_INDICATORS_PER_TIMEFRAME = _get_config_int("MAX_INDICATORS_PER_TIMEFRAME", 50)

        # ACL Cache
        self.ACL_CACHE_ENABLED = _get_config_bool("ACL_CACHE_ENABLED", True)
        self.ACL_CACHE_TTL_SECONDS = _get_config_int("ACL_CACHE_TTL_SECONDS", 300)

        # Celery (use existing Redis from config service)
        celery_broker = _get_from_config_service("CELERY_BROKER_URL", required=False, is_secret=True)
        self.CELERY_BROKER_URL = celery_broker or self.REDIS_URL  # Use existing Redis from config service

        celery_backend = _get_from_config_service("CELERY_RESULT_BACKEND", required=False, is_secret=True)
        self.CELERY_RESULT_BACKEND = celery_backend or self.REDIS_URL  # Use existing Redis from config service

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
