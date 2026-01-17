"""
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
