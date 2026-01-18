"""
<<<<<<< HEAD
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
=======
Redis client utilities for Signal Service.
Production-ready Redis connection management.
"""

from typing import Optional
import os
import redis.asyncio as redis
import ssl
from app.core.config import settings


_redis_client: Optional[redis.Redis] = None


async def get_redis_client() -> redis.Redis:
    """Get Redis client connection."""
    global _redis_client
    
    if _redis_client is None:
        from app.core.config import settings
        redis_url = settings.REDIS_URL
        
        # Parse Redis URL for SSL support
        if redis_url.startswith('rediss://'):
            # SSL Redis connection
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            
            _redis_client = redis.from_url(
                redis_url,
                encoding="utf-8",
                decode_responses=True,
                ssl=ssl_context,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
                health_check_interval=30
            )
        else:
            # Standard Redis connection
            _redis_client = redis.from_url(
                redis_url,
                encoding="utf-8", 
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
                health_check_interval=30
            )
    
    return _redis_client


async def close_redis_client():
    """Close Redis client connection."""
    global _redis_client
    if _redis_client:
        await _redis_client.close()
        _redis_client = None
>>>>>>> compliance-violations-fixed
