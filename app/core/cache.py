"""
Cache utilities for signal service

Provides Redis-based caching with TTL support.
"""
import json
import logging
from typing import Any, Optional
from app.core.redis_manager import get_redis_client

logger = logging.getLogger(__name__)


class Cache:
    """Redis-based cache implementation."""
    
    def __init__(self):
        self.redis_client = None
    
    async def initialize(self):
        """Initialize cache with Redis client."""
        self.redis_client = await get_redis_client()
    
    async def set(self, key: str, value: Any, expire: Optional[int] = None) -> bool:
        """
        Set a value in cache with optional expiration.
        
        Args:
            key: Cache key
            value: Value to cache (will be JSON serialized)
            expire: TTL in seconds (None for no expiration)
            
        Returns:
            True if successful
        """
        try:
            serialized = json.dumps(value)
            if expire:
                await self.redis_client.setex(key, expire, serialized)
            else:
                await self.redis_client.set(key, serialized)
            return True
        except Exception as e:
            logger.error(f"Cache set error: {e}")
            return False
    
    async def get(self, key: str) -> Optional[Any]:
        """
        Get a value from cache.
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None if not found
        """
        try:
            value = await self.redis_client.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.error(f"Cache get error: {e}")
            return None
    
    async def delete(self, key: str) -> bool:
        """
        Delete a value from cache.
        
        Args:
            key: Cache key
            
        Returns:
            True if deleted
        """
        try:
            result = await self.redis_client.delete(key)
            return result > 0
        except Exception as e:
            logger.error(f"Cache delete error: {e}")
            return False
    
    async def exists(self, key: str) -> bool:
        """
        Check if key exists in cache.
        
        Args:
            key: Cache key
            
        Returns:
            True if exists
        """
        try:
            return await self.redis_client.exists(key)
        except Exception as e:
            logger.error(f"Cache exists error: {e}")
            return False


# Global cache instance
_cache = None


async def get_cache() -> Cache:
    """Get global cache instance."""
    global _cache
    if _cache is None:
        _cache = Cache()
        await _cache.initialize()
    return _cache