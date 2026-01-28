"""
Redis Manager for Signal Service

Provides production Redis connections with proper configuration and fallback handling.
"""

import asyncio
import logging
from typing import Any

import redis.asyncio as aioredis

from app.core.config import settings

logger = logging.getLogger(__name__)

_redis_client: aioredis.Redis | None = None
_redis_lock = asyncio.Lock()


class RedisConnectionError(Exception):
    """Redis connection error."""


async def get_redis_client(redis_url: str | None = None) -> aioredis.Redis:
    """
    Get Redis client instance with proper error handling.

    Args:
        redis_url: Optional Redis URL override

    Returns:
        Configured Redis client

    Raises:
        RedisConnectionError: If Redis connection fails
    """
    global _redis_client

    # Use lock to prevent race conditions during initialization
    async with _redis_lock:
        if _redis_client is not None:
            # Test existing connection
            try:
                await _redis_client.ping()
                return _redis_client
            except Exception:
                # Connection is stale, recreate
                _redis_client = None

        # Get Redis URL from config_service (Architecture Principle #1: Config service exclusivity)
        url = redis_url or getattr(settings, 'REDIS_URL', None)
        if not url:
            raise RedisConnectionError("Redis URL must be provided via config_service (no environment fallbacks)")

        if not url:
            raise RedisConnectionError(
                "Redis URL not configured in config_service. "
                    "set REDIS_URL environment variable or configure in settings."
                )

            # Development fallback - use fake Redis
            logger.warning(
                "No Redis URL configured, using fake Redis for development. "
                "This should NOT happen in production!"
            )
            from app.utils.redis import get_redis_client as get_fake_client
            return await get_fake_client()

        try:
            # Create production Redis client
            _redis_client = await aioredis.from_url(
                url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
                health_check_interval=30,
                max_connections=20,
                socket_keepalive=True,
                socket_keepalive_options={}
            )

            # Test connection
            await _redis_client.ping()
            logger.info(f"Redis connected successfully to {url}")

            return _redis_client

        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")

            # No silent fallbacks allowed per architecture - fail fast in all environments
            raise RedisConnectionError(f"Redis connection failed and no fallbacks allowed per architecture: {e}") from e


async def close_redis_client():
    """Close Redis client connection."""
    global _redis_client

    async with _redis_lock:
        if _redis_client is not None:
            try:
                await _redis_client.close()
                logger.info("Redis connection closed")
            except Exception as e:
                logger.warning(f"Error closing Redis connection: {e}")
            finally:
                _redis_client = None


class RedisHealthChecker:
    """Redis health checker for monitoring."""

    @staticmethod
    async def check_health() -> dict[str, Any]:
        """
        Check Redis health status.

        Returns:
            Health status dict
        """
        try:
            client = await get_redis_client()

            # Test ping
            start_time = asyncio.get_event_loop().time()
            await client.ping()
            ping_time = (asyncio.get_event_loop().time() - start_time) * 1000

            # Get info
            info = await client.info()

            return {
                "status": "up",
                "ping_time_ms": round(ping_time, 2),
                "used_memory": info.get('used_memory', 0),
                "connected_clients": info.get('connected_clients', 0),
                "uptime_seconds": info.get('uptime_in_seconds', 0),
                "version": info.get('redis_version', 'unknown'),
                "role": info.get('role', 'unknown')
            }

        except Exception as e:
            return {
                "status": "down",
                "error": str(e),
                "ping_time_ms": None
            }


# Backwards compatibility alias
get_redis = get_redis_client
