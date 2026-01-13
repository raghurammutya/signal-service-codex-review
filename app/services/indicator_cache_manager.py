"""
Redis Cluster Cache Manager for Technical Indicator Calculations
Provides caching layer to avoid redundant calculations
"""

import json
import asyncio
from typing import Dict, Optional, Any, List
from datetime import datetime, timedelta
import hashlib
from dataclasses import dataclass, asdict

from app.utils.logging_utils import log_info, log_error, log_warning
from app.services.signal_redis_manager import signal_redis_manager


@dataclass
class CachedIndicatorResult:
    """Cached indicator calculation result"""
    symbol: str
    indicator: str
    period: int
    timeframe: str
    value: float
    timestamp: datetime
    calculation_time: datetime
    cache_key: str
    metadata: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage"""
        result = asdict(self)
        result['timestamp'] = self.timestamp.isoformat()
        result['calculation_time'] = self.calculation_time.isoformat()
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CachedIndicatorResult':
        """Create from dictionary"""
        data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        data['calculation_time'] = datetime.fromisoformat(data['calculation_time'])
        return cls(**data)


class IndicatorCacheManager:
    """
    Manages Redis cluster caching for indicator calculations
    Uses hash tags to ensure cache entries are co-located with data
    """
    
    def __init__(self):
        self.redis_manager = signal_redis_manager
        self.default_ttl = 300  # 5 minutes default cache TTL
        self.cache_stats = {
            "hits": 0,
            "misses": 0,
            "writes": 0,
            "evictions": 0
        }
        
    def _generate_cache_key(self, symbol: str, indicator: str, period: int, 
                           timeframe: str, end_date: Optional[datetime] = None) -> str:
        """
        Generate cache key for indicator calculation
        Uses hash tag {symbol} to ensure co-location with symbol data
        """
        # Create deterministic key including all parameters
        key_parts = [
            symbol,
            indicator.upper(),
            str(period),
            timeframe,
            end_date.isoformat() if end_date else "latest"
        ]
        
        # Create hash for uniqueness
        key_hash = hashlib.md5(":".join(key_parts).encode()).hexdigest()[:8]
        
        # Return key with hash tag for Redis cluster
        return f"signal:cache:{{{symbol}}}:indicator:{indicator}:{key_hash}"
    
    async def get_cached_indicator(self, symbol: str, indicator: str, period: int,
                                  timeframe: str, end_date: Optional[datetime] = None) -> Optional[CachedIndicatorResult]:
        """
        Retrieve cached indicator value if available and not expired
        """
        try:
            cache_key = self._generate_cache_key(symbol, indicator, period, timeframe, end_date)
            
            # Get from Redis
            cached_data = await self.redis_manager.get(cache_key)
            
            if cached_data:
                # Parse cached result
                result = CachedIndicatorResult.from_dict(json.loads(cached_data))
                
                # Check if cache is still valid (not implementing expiry check here as TTL handles it)
                self.cache_stats["hits"] += 1
                log_info(f"Cache HIT for {symbol} {indicator}({period}) - Key: {cache_key}")
                
                return result
            else:
                self.cache_stats["misses"] += 1
                log_info(f"Cache MISS for {symbol} {indicator}({period}) - Key: {cache_key}")
                return None
                
        except Exception as e:
            log_error(f"Error retrieving from cache: {str(e)}")
            # For cache failures, distinguish between connection vs. data issues
            if "connection" in str(e).lower():
                from app.errors import CacheConnectionError
                raise CacheConnectionError(f"Cache connection failed: {str(e)}") from e
            else:
                # Data corruption/serialization errors can be handled gracefully
                return None
    
    async def cache_indicator_result(self, symbol: str, indicator: str, period: int,
                                    timeframe: str, value: float, timestamp: datetime,
                                    end_date: Optional[datetime] = None,
                                    metadata: Optional[Dict[str, Any]] = None,
                                    ttl: Optional[int] = None) -> bool:
        """
        Cache indicator calculation result
        """
        try:
            cache_key = self._generate_cache_key(symbol, indicator, period, timeframe, end_date)
            
            # Create cached result
            cached_result = CachedIndicatorResult(
                symbol=symbol,
                indicator=indicator,
                period=period,
                timeframe=timeframe,
                value=value,
                timestamp=timestamp,
                calculation_time=datetime.utcnow(),
                cache_key=cache_key,
                metadata=metadata
            )
            
            # Store in Redis with TTL
            cache_ttl = ttl or self.default_ttl
            success = await self.redis_manager.setex(
                cache_key,
                cache_ttl,
                json.dumps(cached_result.to_dict())
            )
            
            if success:
                self.cache_stats["writes"] += 1
                log_info(f"Cached {symbol} {indicator}({period}) for {cache_ttl}s - Key: {cache_key}")
            
            return success
            
        except Exception as e:
            log_error(f"Error caching result: {str(e)}")
            return False
    
    async def cache_batch_indicators(self, results: List[Dict[str, Any]], ttl: Optional[int] = None) -> int:
        """
        Cache multiple indicator results in batch
        Returns number of successfully cached items
        """
        cached_count = 0
        
        for result in results:
            try:
                success = await self.cache_indicator_result(
                    symbol=result['symbol'],
                    indicator=result['indicator'],
                    period=result.get('period', 20),
                    timeframe=result.get('timeframe', 'daily'),
                    value=result['value'],
                    timestamp=result.get('timestamp', datetime.utcnow()),
                    end_date=result.get('end_date'),
                    metadata=result.get('metadata'),
                    ttl=ttl
                )
                
                if success:
                    cached_count += 1
                    
            except Exception as e:
                log_error(f"Error caching batch result: {str(e)}")
        
        return cached_count
    
    async def invalidate_symbol_cache(self, symbol: str) -> int:
        """
        Invalidate all cached indicators for a symbol
        Returns number of keys deleted
        """
        try:
            # Pattern to match all indicators for this symbol
            pattern = f"signal:cache:{{{symbol}}}:indicator:*"
            
            # Get all matching keys
            keys = []
            async for key in self.redis_manager.scan_iter(match=pattern):
                keys.append(key)
            
            # Delete all keys
            if keys:
                deleted = await self.redis_manager.delete(*keys)
                self.cache_stats["evictions"] += deleted
                log_info(f"Invalidated {deleted} cache entries for {symbol}")
                return deleted
            
            return 0
            
        except Exception as e:
            log_error(f"Error invalidating cache: {str(e)}")
            return 0
    
    async def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics
        """
        total_requests = self.cache_stats["hits"] + self.cache_stats["misses"]
        hit_rate = (self.cache_stats["hits"] / total_requests * 100) if total_requests > 0 else 0
        
        return {
            "hits": self.cache_stats["hits"],
            "misses": self.cache_stats["misses"],
            "writes": self.cache_stats["writes"],
            "evictions": self.cache_stats["evictions"],
            "total_requests": total_requests,
            "hit_rate": round(hit_rate, 2),
            "status": "healthy" if hit_rate > 50 else "warming_up"
        }
    
    async def warm_cache(self, symbols: List[str], indicators: List[str]) -> int:
        """
        Pre-warm cache for common symbol/indicator combinations
        Returns number of entries warmed
        """
        warmed = 0
        
        try:
            for symbol in symbols:
                for indicator in indicators:
                    # Check if already cached
                    cache_key = self._generate_cache_key(symbol, indicator, 20, "daily")
                    exists = await self.redis_manager.exists(cache_key)
                    
                    if not exists:
                        # Would trigger calculation here in real implementation
                        log_info(f"Would warm cache for {symbol} {indicator}")
                        warmed += 1
            
            return warmed
            
        except Exception as e:
            log_error(f"Error warming cache: {str(e)}")
            return 0
    
    def get_ttl_for_indicator(self, indicator: str, timeframe: str) -> int:
        """
        Get appropriate TTL based on indicator and timeframe
        """
        # Normalize timeframe names
        timeframe_map = {
            "1day": "daily",
            "daily": "daily",
            "1hour": "hourly", 
            "hourly": "hourly",
            "30min": "minute",
            "15min": "minute",
            "5min": "minute",
            "1min": "minute",
            "minute": "minute"
        }
        
        normalized_timeframe = timeframe_map.get(timeframe, "daily")
        
        # Longer TTL for slower-changing indicators and longer timeframes
        ttl_matrix = {
            "daily": {
                "sma": 600,      # 10 minutes
                "ema": 600,
                "rsi": 300,      # 5 minutes  
                "macd": 300,
                "bollinger": 300,
                "bbands": 300,
                "stoch": 300,
                "adx": 600,      # Slower changing
                "atr": 300,
                "vwap": 180,     # Volume-based, changes more
                "default": 300   # Default for unknown indicators
            },
            "hourly": {
                "sma": 300,      # 5 minutes
                "ema": 300,
                "rsi": 180,      # 3 minutes
                "macd": 180,
                "bollinger": 180,
                "bbands": 180,
                "stoch": 180,
                "adx": 300,
                "atr": 180,
                "vwap": 120,
                "default": 180
            },
            "minute": {
                "sma": 60,       # 1 minute
                "ema": 60,
                "rsi": 60,
                "macd": 60,
                "bollinger": 60,
                "bbands": 60,
                "stoch": 60,
                "adx": 120,      # Still slower changing
                "atr": 60,
                "vwap": 30,      # Very dynamic for minute
                "default": 60
            }
        }
        
        ttl = ttl_matrix.get(normalized_timeframe, {}).get(indicator.lower())
        if ttl is None:
            ttl = ttl_matrix.get(normalized_timeframe, {}).get("default", self.default_ttl)
        
        return ttl


# Global instance
indicator_cache_manager = IndicatorCacheManager()


async def cached_indicator_calculation(symbol: str, indicator: str, period: int,
                                     timeframe: str, calculation_func, 
                                     end_date: Optional[datetime] = None) -> Dict[str, Any]:
    """
    Decorator-like function for cached indicator calculations
    
    Usage:
        result = await cached_indicator_calculation(
            symbol="RELIANCE",
            indicator="sma", 
            period=20,
            timeframe="daily",
            calculation_func=lambda: calculate_sma(symbol, period, timeframe)
        )
    """
    # Check cache first
    cached_result = await indicator_cache_manager.get_cached_indicator(
        symbol, indicator, period, timeframe, end_date
    )
    
    if cached_result:
        return {
            "value": cached_result.value,
            "timestamp": cached_result.timestamp,
            "cached": True,
            "cache_time": cached_result.calculation_time
        }
    
    # Calculate if not cached
    log_info(f"Calculating {indicator} for {symbol} (not in cache)")
    result = await calculation_func()
    
    if result and "value" in result:
        # Cache the result
        ttl = indicator_cache_manager.get_ttl_for_indicator(indicator, timeframe)
        await indicator_cache_manager.cache_indicator_result(
            symbol=symbol,
            indicator=indicator,
            period=period,
            timeframe=timeframe,
            value=result["value"],
            timestamp=result.get("timestamp", datetime.utcnow()),
            end_date=end_date,
            metadata=result.get("metadata"),
            ttl=ttl
        )
        
        result["cached"] = False
    
    return result