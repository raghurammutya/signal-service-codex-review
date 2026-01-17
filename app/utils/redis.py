"""
Production Redis helper utilities.

This module provides Redis client initialization for production use.
Development fake implementations have been moved to test/stubs/fake_redis.py.
"""

import logging
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


async def get_redis_client(redis_url: Optional[str] = None):
    """
    Get async Redis client for production use.
    
    Returns:
        Redis client instance
        
    Raises:
        RuntimeError: If Redis configuration is missing or connection fails
    """
    from app.core.redis_manager import get_redis_client as get_core_client
    return await get_core_client(redis_url)


def get_redis_client_sync(redis_url: Optional[str] = None):
    """
    Get synchronous Redis client for production use.
    
    Returns:
        Redis client instance
        
    Raises:
        RuntimeError: If Redis configuration is missing or connection fails
    """
    try:
        import redis
        url = redis_url or getattr(settings, "REDIS_URL", None)
        if not url:
            raise RuntimeError("REDIS_URL not configured in config_service")
        
        client = redis.from_url(
            url,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
            health_check_interval=30
        )
        
        client.ping()
        logger.info("Synchronous Redis client initialized successfully")
        return client
        
    except ImportError:
        raise RuntimeError("redis package not installed. Install with: pip install redis[hiredis]")
    except Exception as e:
        logger.error(f"Failed to initialize synchronous Redis client: {e}")
        raise RuntimeError(f"Redis connection failed: {e}")
