"""Timeframe cache manager for efficient data access"""
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Any
import json
import logging

from app.utils.redis import get_redis_client

logger = logging.getLogger(__name__)


class TimeframeCache:
    """Cache for a specific instrument and timeframe"""
    
    def __init__(self, instrument_key: str, timeframe: str):
        self.instrument_key = instrument_key
        self.timeframe = timeframe
        self.last_access = datetime.now()
        self.subscriber_count = 0
        self.local_cache = {}  # In-memory cache
        self.cache_size = 0
        self.hit_count = 0
        self.miss_count = 0
        
    async def get(self, key: str) -> Optional[Any]:
        """Get from cache"""
        self.last_access = datetime.now()
        
        if key in self.local_cache:
            self.hit_count += 1
            return self.local_cache[key]
        
        self.miss_count += 1
        return None
    
    async def set(self, key: str, value: Any, ttl: int = 300):
        """Set in cache"""
        self.local_cache[key] = {
            'value': value,
            'expires': datetime.now() + timedelta(seconds=ttl)
        }
        self.cache_size = len(self.local_cache)
    
    async def clear_expired(self):
        """Clear expired entries"""
        now = datetime.now()
        expired_keys = [
            k for k, v in self.local_cache.items()
            if v['expires'] < now
        ]
        
        for key in expired_keys:
            del self.local_cache[key]
            
        self.cache_size = len(self.local_cache)
        
        if expired_keys:
            log_info(f"Cleared {len(expired_keys)} expired entries from {self.instrument_key}:{self.timeframe}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        total_requests = self.hit_count + self.miss_count
        hit_rate = self.hit_count / total_requests if total_requests > 0 else 0
        
        return {
            'instrument_key': self.instrument_key,
            'timeframe': self.timeframe,
            'size': self.cache_size,
            'hit_rate': hit_rate,
            'hit_count': self.hit_count,
            'miss_count': self.miss_count,
            'last_access': self.last_access.isoformat(),
            'subscriber_count': self.subscriber_count
        }


class TimeframeCacheManager:
    """Manages timeframe data caches with lifecycle"""
    
    def __init__(self):
        self.cache_registry: Dict[str, TimeframeCache] = {}
        self.subscriber_count: Dict[str, int] = {}
        self.cluster_manager = None
        self.running = False
        self.cleanup_interval = 300  # 5 minutes
        self.max_cache_age = 3600  # 1 hour
        
    async def initialize(self):
        """Initialize the cache manager"""
        redis_client = await get_redis_client()
        self.cluster_manager = type("Cluster", (), {"client": redis_client})
        logger.info("Timeframe cache manager initialized")
        
    async def get_or_create_cache(self, instrument_key: str, 
                                 timeframe: str) -> TimeframeCache:
        """Get existing cache or create new one"""
        
        cache_key = f"{instrument_key}:{timeframe}"
        
        if cache_key not in self.cache_registry:
            # Create new cache
            cache = TimeframeCache(instrument_key, timeframe)
            self.cache_registry[cache_key] = cache
            logger.info("Created new timeframe cache for %s", cache_key)
            
        # Update access time
        cache = self.cache_registry[cache_key]
        cache.last_access = datetime.now()
        
        return cache
    
    async def subscribe(self, instrument_key: str, timeframe: str):
        """Subscribe to a timeframe cache"""
        cache_key = f"{instrument_key}:{timeframe}"
        
        # Get or create cache
        cache = await self.get_or_create_cache(instrument_key, timeframe)
        
        # Increment subscriber count
        cache.subscriber_count += 1
        self.subscriber_count[cache_key] = cache.subscriber_count
        
        logger.info("Subscribed to %s, subscribers: %s", cache_key, cache.subscriber_count)
        
    async def unsubscribe(self, instrument_key: str, timeframe: str):
        """Unsubscribe from a timeframe cache"""
        cache_key = f"{instrument_key}:{timeframe}"
        
        if cache_key in self.cache_registry:
            cache = self.cache_registry[cache_key]
            cache.subscriber_count = max(0, cache.subscriber_count - 1)
            self.subscriber_count[cache_key] = cache.subscriber_count
            
            logger.info("Unsubscribed from %s, subscribers: %s", cache_key, cache.subscriber_count)
    
    async def get_cached_data(self, instrument_key: str, timeframe: str, 
                            data_type: str = 'ohlcv') -> Optional[List[Dict]]:
        """Get cached timeframe data"""
        
        cache = await self.get_or_create_cache(instrument_key, timeframe)
        
        # Try local cache first
        cache_key = f"{data_type}:latest"
        cached_data = await cache.get(cache_key)
        
        if cached_data:
            return cached_data['value']
        
        # Try Redis cache
        redis_key = f"signal:timeframe_cache:{data_type}:{instrument_key}:{timeframe}"
        
        try:
            redis_data = await self.cluster_manager.client.get(redis_key)
            if redis_data:
                data = json.loads(redis_data)
                
                # Cache locally
                await cache.set(cache_key, data, ttl=60)  # 1 minute local cache
                
                return data
                
        except Exception as e:
            logger.warning("Failed to get cached data from Redis: %s", e)
            
        return None
    
    async def set_cached_data(self, instrument_key: str, timeframe: str,
                            data: List[Dict], data_type: str = 'ohlcv'):
        """Set cached timeframe data"""
        
        cache = await self.get_or_create_cache(instrument_key, timeframe)
        
        # Cache locally
        cache_key = f"{data_type}:latest"
        await cache.set(cache_key, data, ttl=60)
        
        # Cache in Redis
        redis_key = f"signal:timeframe_cache:{data_type}:{instrument_key}:{timeframe}"
        
        try:
            # Determine TTL based on timeframe
            ttl_map = {
                '1minute': 300,     # 5 minutes
                '5minute': 600,     # 10 minutes
                '15minute': 1800,   # 30 minutes
                '30minute': 3600,   # 1 hour
                '1hour': 7200,      # 2 hours
                '4hour': 14400,     # 4 hours
                '1day': 86400       # 24 hours
            }
            
            ttl = ttl_map.get(timeframe, 3600)
            
            await self.cluster_manager.client.setex(
                redis_key,
                ttl,
                json.dumps(data)
            )
            
        except Exception as e:
            logger.exception("Failed to cache data in Redis: %s", e)
    
    async def cleanup_unused_caches(self):
        """Remove caches not accessed for > max_cache_age"""
        cutoff = datetime.now() - timedelta(seconds=self.max_cache_age)
        
        caches_to_remove = []
        
        for cache_key, cache in self.cache_registry.items():
            # Clear expired entries first
            await cache.clear_expired()
            
            # Check if cache should be removed
            if (cache.last_access < cutoff and 
                cache.subscriber_count == 0):
                caches_to_remove.append(cache_key)
        
        # Remove unused caches
        for cache_key in caches_to_remove:
            del self.cache_registry[cache_key]
            if cache_key in self.subscriber_count:
                del self.subscriber_count[cache_key]
                
        if caches_to_remove:
            logger.info("Removed %s unused caches", len(caches_to_remove))
    
    async def cleanup_task(self):
        """Background task to cleanup unused caches"""
        self.running = True
        
        while self.running:
            try:
                await asyncio.sleep(self.cleanup_interval)
                await self.cleanup_unused_caches()
                
                # Log statistics
                stats = self.get_statistics()
                logger.info("Cache manager stats: %s", stats)
                
            except Exception as e:
                logger.exception("Error in cache cleanup task: %s", e)
                await asyncio.sleep(60)
    
    async def stop(self):
        """Stop the cache manager"""
        self.running = False
        logger.info("Timeframe cache manager stopped")
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get cache manager statistics"""
        
        cache_stats = []
        total_size = 0
        total_hits = 0
        total_misses = 0
        
        for cache in self.cache_registry.values():
            stats = cache.get_stats()
            cache_stats.append(stats)
            total_size += stats['size']
            total_hits += stats['hit_count']
            total_misses += stats['miss_count']
        
        total_requests = total_hits + total_misses
        overall_hit_rate = total_hits / total_requests if total_requests > 0 else 0
        
        return {
            'cache_count': len(self.cache_registry),
            'total_size': total_size,
            'overall_hit_rate': overall_hit_rate,
            'total_hits': total_hits,
            'total_misses': total_misses,
            'active_subscribers': sum(self.subscriber_count.values()),
            'caches': cache_stats
        }
    
    async def warm_cache(self, instrument_key: str, timeframes: List[str]):
        """Pre-warm cache for specific instrument and timeframes"""
        
        for timeframe in timeframes:
            try:
                cache = await self.get_or_create_cache(instrument_key, timeframe)
                
                # Trigger data load (implementation depends on data source)
                # Cache warming implementation would trigger data load here
                logger.info("Warming cache for %s:%s", instrument_key, timeframe)
                
            except Exception as e:
                logger.exception("Failed to warm cache for %s:%s: %s", instrument_key, timeframe, e)
