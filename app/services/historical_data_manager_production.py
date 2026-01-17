"""
Production Historical Data Manager - API Delegation Implementation

Replaces the placeholder historical data manager with real ticker_service integration.
Follows Architecture v3.0 - API Delegation Era patterns from CLAUDE.md
"""
import asyncio
import logging
from typing import Dict, Any, List, Optional, Union
from datetime import datetime, timedelta
from dataclasses import dataclass
import pandas as pd
import numpy as np
import aiohttp
import json

from app.core.config import settings
from app.utils.redis import get_redis_client

logger = logging.getLogger(__name__)


@dataclass
class HistoricalDataRequest:
    """Request parameters for historical data"""
    symbol: str
    timeframe: str
    periods_required: int
    indicator_name: Optional[str] = None
    end_date: Optional[str] = None
    include_volume: bool = True
    data_quality_check: bool = True


@dataclass
class HistoricalDataResponse:
    """Response structure for historical data"""
    success: bool
    data: List[Dict[str, Any]]
    metadata: Dict[str, Any]
    error: Optional[str] = None


class ProductionHistoricalDataManager:
    """
    Production Historical Data Manager using ticker_service API delegation.
    
    Follows Architecture v3.0 principles:
    - No direct database access
    - All data via ticker_service APIs
    - Proper error handling and caching
    - Internal API key authentication
    """
    
    def __init__(self):
        self.ticker_service_url = self._get_ticker_service_url()
        self.internal_api_key = self._get_internal_api_key()
        self.redis_client = None
        self.session: Optional[aiohttp.ClientSession] = None
        
        # Cache configuration
        self.cache_ttl = 300  # 5 minutes cache for historical data
        self.cache_prefix = "historical_data:"
        
        logger.info("ProductionHistoricalDataManager initialized with ticker_service integration")
    
    def _get_ticker_service_url(self) -> str:
        """Get ticker service URL from config"""
        if hasattr(settings, 'TICKER_SERVICE_URL'):
            return settings.TICKER_SERVICE_URL
        raise RuntimeError("TICKER_SERVICE_URL not configured in config_service - cannot access ticker service")
    
    def _get_internal_api_key(self) -> str:
        """Get internal API key for service-to-service authentication"""
        api_key = getattr(settings, 'internal_api_key', None)
        if not api_key:
            raise ValueError("INTERNAL_API_KEY not configured - required for ticker_service authentication")
        return api_key
    
    async def initialize(self):
        """Initialize the historical data manager"""
        self.redis_client = await get_redis_client()
        
        # Create HTTP session with proper authentication
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            headers={'X-Internal-API-Key': self.internal_api_key}
        )
        
        logger.info("ProductionHistoricalDataManager initialized with ticker_service connection")
    
    async def get_historical_data_for_indicator(
        self,
        symbol: str,
        timeframe: str,
        periods_required: int,
        indicator_name: str = None
    ) -> Dict[str, Any]:
        """
        Get historical data for indicator calculations via ticker_service API.
        
        This is the main interface that replaces the placeholder implementation.
        """
        request = HistoricalDataRequest(
            symbol=symbol,
            timeframe=timeframe,
            periods_required=periods_required,
            indicator_name=indicator_name
        )
        
        try:
            # Check cache first
            cached_data = await self._get_cached_data(request)
            if cached_data:
                logger.debug(f"Cache hit for historical data: {symbol} {timeframe}")
                return cached_data
            
            # Fetch from ticker_service
            response = await self._fetch_from_ticker_service(request)
            
            if response.success:
                # Cache the successful response
                await self._cache_data(request, response)
                
                return {
                    "success": True,
                    "data": response.data,
                    "source": "ticker_service",
                    "quality": response.metadata.get("quality", "good"),
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "periods": len(response.data),
                    "periods_requested": periods_required,
                    "indicator": indicator_name,
                    "cached": False,
                    "metadata": response.metadata
                }
            else:
                logger.error(f"Failed to fetch historical data: {response.error}")
                return self._error_response(symbol, timeframe, periods_required, indicator_name, response.error)
                
        except Exception as e:
            logger.error(f"Error getting historical data for {symbol}: {e}")
            return self._error_response(symbol, timeframe, periods_required, indicator_name, str(e))
    
    async def _fetch_from_ticker_service(self, request: HistoricalDataRequest) -> HistoricalDataResponse:
        """Fetch historical data from ticker_service using internal APIs"""
        
        if not self.session:
            raise ValueError("Historical data manager not initialized")
        
        # Calculate date range
        end_date = request.end_date or datetime.now().strftime("%Y-%m-%d")
        
        # Map timeframe to ticker_service parameters
        timeframe_mapping = {
            "1m": "1minute",
            "1minute": "1minute", 
            "5m": "5minute",
            "5minute": "5minute",
            "15m": "15minute", 
            "15minute": "15minute",
            "1h": "1hour",
            "1hour": "1hour",
            "1d": "1day",
            "1day": "1day"
        }
        
        api_timeframe = timeframe_mapping.get(request.timeframe, request.timeframe)
        
        # Calculate start date based on periods required
        start_date = self._calculate_start_date(end_date, api_timeframe, request.periods_required)
        
        # Use ticker_service internal API for signal_service context
        # Following CLAUDE.md pattern: signal_service → ticker_service/api/v1/internal/context/*
        url = f"{self.ticker_service_url}/api/v1/internal/context/historical"
        
        params = {
            "symbol": request.symbol,
            "start_date": start_date,
            "end_date": end_date,
            "timeframe": api_timeframe,
            "limit": request.periods_required + 50,  # Get extra data to ensure we have enough
            "include_volume": request.include_volume,
            "format": "signal_context"  # Optimized format for signal calculations
        }
        
        try:
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    if data.get("success", False):
                        historical_data = data.get("historical_data", [])
                        
                        # Ensure we have enough data points
                        if len(historical_data) >= request.periods_required:
                            # Take the most recent periods_required data points
                            limited_data = historical_data[-request.periods_required:]
                            
                            return HistoricalDataResponse(
                                success=True,
                                data=limited_data,
                                metadata={
                                    "source": "ticker_service_internal",
                                    "quality": data.get("data_quality", "good"),
                                    "timeframe": api_timeframe,
                                    "total_available": len(historical_data),
                                    "returned": len(limited_data),
                                    "api_response_time_ms": data.get("response_time_ms"),
                                    "cached_at_source": data.get("cached", False)
                                }
                            )
                        else:
                            return HistoricalDataResponse(
                                success=False,
                                data=[],
                                metadata={},
                                error=f"Insufficient data: got {len(historical_data)}, needed {request.periods_required}"
                            )
                    else:
                        return HistoricalDataResponse(
                            success=False,
                            data=[],
                            metadata={},
                            error=data.get("error", "Unknown ticker_service error")
                        )
                else:
                    error_text = await response.text()
                    return HistoricalDataResponse(
                        success=False,
                        data=[],
                        metadata={},
                        error=f"HTTP {response.status}: {error_text}"
                    )
                    
        except asyncio.TimeoutError:
            return HistoricalDataResponse(
                success=False,
                data=[],
                metadata={},
                error="Timeout connecting to ticker_service"
            )
        except Exception as e:
            return HistoricalDataResponse(
                success=False,
                data=[],
                metadata={},
                error=f"Connection error: {str(e)}"
            )
    
    def _calculate_start_date(self, end_date: str, timeframe: str, periods_required: int) -> str:
        """Calculate start date based on timeframe and required periods"""
        try:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
            
            # Timeframe to timedelta mapping
            timeframe_deltas = {
                "1minute": timedelta(minutes=periods_required + 100),  # Extra buffer
                "5minute": timedelta(minutes=(periods_required + 50) * 5),
                "15minute": timedelta(minutes=(periods_required + 30) * 15),
                "1hour": timedelta(hours=periods_required + 24),
                "1day": timedelta(days=periods_required + 30)
            }
            
            delta = timeframe_deltas.get(timeframe, timedelta(days=periods_required + 30))
            start_dt = end_dt - delta
            
            return start_dt.strftime("%Y-%m-%d")
            
        except Exception as e:
            logger.warning(f"Error calculating start date: {e}")
            # Fallback to 90 days ago
            fallback_start = datetime.now() - timedelta(days=90)
            return fallback_start.strftime("%Y-%m-%d")
    
    async def _get_cached_data(self, request: HistoricalDataRequest) -> Optional[Dict[str, Any]]:
        """Get cached historical data if available"""
        if not self.redis_client:
            return None
        
        try:
            cache_key = self._build_cache_key(request)
            cached_json = await self.redis_client.get(cache_key)
            
            if cached_json:
                cached_data = json.loads(cached_json)
                cached_data["cached"] = True
                return cached_data
                
        except Exception as e:
            logger.warning(f"Cache retrieval error: {e}")
        
        return None
    
    async def _cache_data(self, request: HistoricalDataRequest, response: HistoricalDataResponse):
        """Cache successful historical data response"""
        if not self.redis_client or not response.success:
            return
        
        try:
            cache_key = self._build_cache_key(request)
            cache_data = {
                "success": True,
                "data": response.data,
                "source": "ticker_service",
                "quality": response.metadata.get("quality", "good"),
                "symbol": request.symbol,
                "timeframe": request.timeframe,
                "periods": len(response.data),
                "periods_requested": request.periods_required,
                "indicator": request.indicator_name,
                "metadata": response.metadata,
                "cached_at": datetime.utcnow().isoformat()
            }
            
            await self.redis_client.setex(
                cache_key,
                self.cache_ttl,
                json.dumps(cache_data)
            )
            
        except Exception as e:
            logger.warning(f"Cache storage error: {e}")
    
    def _build_cache_key(self, request: HistoricalDataRequest) -> str:
        """Build cache key for historical data request"""
        return f"{self.cache_prefix}{request.symbol}:{request.timeframe}:{request.periods_required}:{request.indicator_name or 'general'}"
    
    def _error_response(
        self,
        symbol: str,
        timeframe: str,
        periods_required: int,
        indicator_name: str,
        error: str
    ) -> Dict[str, Any]:
        """Generate standardized error response"""
        return {
            "success": False,
            "data": [],
            "source": "error",
            "quality": "error",
            "symbol": symbol,
            "timeframe": timeframe,
            "periods": 0,
            "periods_requested": periods_required,
            "indicator": indicator_name,
            "error": error,
            "cached": False,
            "metadata": {"error_timestamp": datetime.utcnow().isoformat()}
        }
    
    async def get_multiple_symbols_data(
        self,
        symbols: List[str],
        timeframe: str,
        periods_required: int,
        indicator_name: str = None
    ) -> Dict[str, Dict[str, Any]]:
        """Get historical data for multiple symbols efficiently"""
        tasks = []
        for symbol in symbols:
            task = self.get_historical_data_for_indicator(
                symbol, timeframe, periods_required, indicator_name
            )
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        symbol_data = {}
        for i, symbol in enumerate(symbols):
            if isinstance(results[i], Exception):
                symbol_data[symbol] = self._error_response(
                    symbol, timeframe, periods_required, indicator_name, str(results[i])
                )
            else:
                symbol_data[symbol] = results[i]
        
        return symbol_data
    
    async def health_check(self) -> Dict[str, Any]:
        """Check health of historical data manager and ticker_service connection"""
        try:
            # Test connection to ticker_service
            if not self.session:
                return {"status": "unhealthy", "error": "Not initialized"}
            
            url = f"{self.ticker_service_url}/health"
            async with self.session.get(url) as response:
                ticker_healthy = response.status == 200
            
            # Test cache connection
            cache_healthy = False
            if self.redis_client:
                try:
                    await self.redis_client.ping()
                    cache_healthy = True
                except:
                    pass
            
            status = "healthy" if ticker_healthy and cache_healthy else "degraded"
            
            return {
                "status": status,
                "ticker_service": "healthy" if ticker_healthy else "unhealthy",
                "cache": "healthy" if cache_healthy else "unhealthy",
                "api_delegation": "enabled"
            }
            
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}
    
    async def close(self):
        """Close HTTP session and cleanup resources"""
        if self.session:
            await self.session.close()
            self.session = None


# Global instance for singleton pattern
_historical_data_manager = None

async def get_production_historical_data_manager() -> ProductionHistoricalDataManager:
    """Get singleton production historical data manager instance"""
    global _historical_data_manager
    if _historical_data_manager is None:
        _historical_data_manager = ProductionHistoricalDataManager()
        await _historical_data_manager.initialize()
    return _historical_data_manager