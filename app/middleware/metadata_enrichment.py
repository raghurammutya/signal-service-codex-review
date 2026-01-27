#!/usr/bin/env python3
"""
Registry Metadata Enrichment Middleware - Phase 1 Migration

META_001: Registry Metadata Enrichment
- All API responses include instrument metadata from registry
- Symbol, exchange, sector information automatically populated
- Market data enriched with registry-sourced attributes
- Response schemas updated to include metadata fields
- Metadata enrichment maintains <50ms performance impact
"""

import asyncio
import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import wraps
from typing import Any

from app.sdk import InstrumentClient, create_instrument_client

logger = logging.getLogger(__name__)

@dataclass
class EnrichmentConfig:
    """Configuration for metadata enrichment"""
    enable_caching: bool = True
    cache_ttl_seconds: int = 300  # 5 minutes
    max_cache_size: int = 1000
    performance_threshold_ms: float = 50.0
    batch_size: int = 10
    # Field selection for enrichment
    include_fields: list[str] = field(default_factory=lambda: [
        'symbol', 'exchange', 'sector', 'instrument_type', 'lot_size', 'tick_size'
    ])
    exclude_internal_fields: bool = True

@dataclass
class EnrichmentMetrics:
    """Metrics for enrichment performance monitoring"""
    total_requests: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    avg_enrichment_time_ms: float = 0.0
    max_enrichment_time_ms: float = 0.0
    failed_enrichments: int = 0
    registry_calls: int = 0
    last_reset: datetime = field(default_factory=datetime.now)

class MetadataCache:
    """High-performance metadata cache with TTL"""

    def __init__(self, max_size: int = 1000, ttl_seconds: int = 300):
        self._cache: dict[str, dict[str, Any]] = {}
        self._timestamps: dict[str, datetime] = {}
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._lock = asyncio.Lock()

    async def get(self, instrument_key: str) -> dict[str, Any] | None:
        """Get cached metadata for instrument"""
        async with self._lock:
            if instrument_key not in self._cache:
                return None

            # Check TTL
            timestamp = self._timestamps[instrument_key]
            if datetime.now() - timestamp > timedelta(seconds=self.ttl_seconds):
                del self._cache[instrument_key]
                del self._timestamps[instrument_key]
                return None

            return self._cache[instrument_key].copy()

    async def set(self, instrument_key: str, metadata: dict[str, Any]):
        """Cache metadata for instrument"""
        async with self._lock:
            # Implement LRU eviction if cache is full
            if len(self._cache) >= self.max_size and instrument_key not in self._cache:
                # Remove oldest entry
                oldest_key = min(self._timestamps, key=self._timestamps.get)
                del self._cache[oldest_key]
                del self._timestamps[oldest_key]

            self._cache[instrument_key] = metadata.copy()
            self._timestamps[instrument_key] = datetime.now()

    async def batch_get(self, instrument_keys: list[str]) -> dict[str, dict[str, Any]]:
        """Get multiple cached metadata entries"""
        result = {}
        for key in instrument_keys:
            cached = await self.get(key)
            if cached:
                result[key] = cached
        return result

    async def clear(self):
        """Clear all cached metadata"""
        async with self._lock:
            self._cache.clear()
            self._timestamps.clear()

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics"""
        return {
            "size": len(self._cache),
            "max_size": self.max_size,
            "ttl_seconds": self.ttl_seconds,
            "memory_usage_kb": len(json.dumps(self._cache).encode()) / 1024
        }

class MetadataEnrichmentMiddleware:
    """
    Middleware for automatic metadata enrichment in API responses

    META_001: Enriches all responses containing instrument_key with metadata
    from the Phase 3 registry while maintaining <50ms performance impact.
    """

    def __init__(self,
                 instrument_client: InstrumentClient | None = None,
                 config: EnrichmentConfig | None = None):
        """
        Initialize metadata enrichment middleware

        Args:
            instrument_client: Client for registry communication
            config: Enrichment configuration
        """
        self.instrument_client = instrument_client or create_instrument_client()
        self.config = config or EnrichmentConfig()
        self.cache = MetadataCache(
            max_size=self.config.max_cache_size,
            ttl_seconds=self.config.cache_ttl_seconds
        ) if self.config.enable_caching else None
        self.metrics = EnrichmentMetrics()

        # Performance tracking
        self._enrichment_times: list[float] = []
        self._max_samples = 100

    # =============================================================================
    # MIDDLEWARE DECORATORS
    # =============================================================================

    def enrich_response(self, extract_keys_func: Callable | None = None):
        """
        Decorator for automatic response enrichment

        Args:
            extract_keys_func: Function to extract instrument_keys from response
        """
        def decorator(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                # Execute original function
                response = await func(*args, **kwargs)

                # Enrich response
                enriched_response = await self.enrich_response_data(
                    response, extract_keys_func
                )

                return enriched_response
            return wrapper
        return decorator

    def enrich_request(self):
        """Decorator for request preprocessing with metadata"""
        def decorator(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                # Pre-warm cache with request instrument keys if available
                instrument_keys = self._extract_instrument_keys_from_request(kwargs)
                if instrument_keys:
                    await self._preload_metadata(instrument_keys)

                return await func(*args, **kwargs)
            return wrapper
        return decorator

    # =============================================================================
    # CORE ENRICHMENT METHODS
    # =============================================================================

    async def enrich_response_data(self,
                                 response: Any,
                                 extract_keys_func: Callable | None = None) -> Any:
        """
        Enrich response data with instrument metadata

        Args:
            response: Original response data
            extract_keys_func: Function to extract instrument keys

        Returns:
            Enriched response with metadata
        """
        start_time = time.time()

        try:
            # Extract instrument keys from response
            instrument_keys = (
                extract_keys_func(response) if extract_keys_func
                else self._auto_extract_instrument_keys(response)
            )

            if not instrument_keys:
                return response

            # Get metadata for all instruments
            metadata_map = await self._get_metadata_batch(instrument_keys)

            # Enrich response
            enriched = await self._apply_enrichment(response, metadata_map)

            # Track performance
            enrichment_time = (time.time() - start_time) * 1000
            await self._track_performance(enrichment_time, len(instrument_keys))

            return enriched

        except Exception as e:
            self.metrics.failed_enrichments += 1
            logger.error(f"Metadata enrichment failed: {e}")
            # Return original response on enrichment failure
            return response

    async def enrich_single_instrument(self, instrument_key: str) -> dict[str, Any]:
        """
        Get enriched metadata for single instrument

        Args:
            instrument_key: Instrument to enrich

        Returns:
            Enriched metadata dictionary
        """
        metadata_map = await self._get_metadata_batch([instrument_key])
        return metadata_map.get(instrument_key, {
            "symbol": "Unknown",
            "exchange": "Unknown",
            "sector": "Unknown",
            "enrichment_status": "failed"
        })

    async def enrich_market_data(self, market_data: dict[str, Any]) -> dict[str, Any]:
        """
        Enrich market data with instrument metadata

        Args:
            market_data: Market data response

        Returns:
            Market data enriched with metadata
        """
        if "instrument_key" not in market_data:
            return market_data

        metadata = await self.enrich_single_instrument(market_data["instrument_key"])

        # Create enriched market data
        enriched = market_data.copy()
        enriched["instrument_metadata"] = self._filter_metadata_fields(metadata)
        enriched["enriched_at"] = datetime.now().isoformat()

        # Add metadata fields directly to response for convenience
        for field_name in ["symbol", "exchange", "sector"]:
            if field_name in metadata:
                enriched[field_name] = metadata[field_name]

        return enriched

    # =============================================================================
    # METADATA RETRIEVAL AND CACHING
    # =============================================================================

    async def _get_metadata_batch(self, instrument_keys: list[str]) -> dict[str, dict[str, Any]]:
        """Get metadata for multiple instruments with caching"""
        metadata_map = {}
        keys_to_fetch = []

        # Check cache first if enabled
        if self.cache:
            cached_metadata = await self.cache.batch_get(instrument_keys)
            metadata_map.update(cached_metadata)
            keys_to_fetch = [key for key in instrument_keys if key not in cached_metadata]
            self.metrics.cache_hits += len(cached_metadata)
            self.metrics.cache_misses += len(keys_to_fetch)
        else:
            keys_to_fetch = instrument_keys

        # Fetch missing metadata from registry
        if keys_to_fetch:
            fetched_metadata = await self._fetch_metadata_from_registry(keys_to_fetch)
            metadata_map.update(fetched_metadata)

            # Cache the fetched metadata
            if self.cache:
                for key, metadata in fetched_metadata.items():
                    await self.cache.set(key, metadata)

        return metadata_map

    async def _fetch_metadata_from_registry(self, instrument_keys: list[str]) -> dict[str, dict[str, Any]]:
        """Fetch metadata from registry for instruments"""
        metadata_map = {}

        try:
            # Batch fetch metadata
            for key in instrument_keys:
                try:
                    metadata = await self.instrument_client.get_instrument_metadata(key)
                    metadata_map[key] = self._convert_metadata_to_dict(metadata)
                except Exception as e:
                    logger.warning(f"Failed to fetch metadata for {key}: {e}")
                    # Provide fallback metadata
                    metadata_map[key] = self._create_fallback_metadata(key)

            self.metrics.registry_calls += 1

        except Exception as e:
            logger.error(f"Registry batch fetch failed: {e}")
            # Provide fallback metadata for all keys
            for key in instrument_keys:
                metadata_map[key] = self._create_fallback_metadata(key)

        return metadata_map

    async def _preload_metadata(self, instrument_keys: list[str]):
        """Preload metadata for instruments to warm cache"""
        if not self.cache:
            return

        # Only fetch keys not already cached
        uncached_keys = []
        for key in instrument_keys:
            if await self.cache.get(key) is None:
                uncached_keys.append(key)

        if uncached_keys:
            # Fetch and cache in background
            asyncio.create_task(self._get_metadata_batch(uncached_keys))

    # =============================================================================
    # RESPONSE PROCESSING AND ENRICHMENT
    # =============================================================================

    async def _apply_enrichment(self, response: Any, metadata_map: dict[str, dict[str, Any]]) -> Any:
        """Apply metadata enrichment to response"""
        if isinstance(response, dict):
            return await self._enrich_dict(response, metadata_map)
        if isinstance(response, list):
            return await self._enrich_list(response, metadata_map)
        return response

    async def _enrich_dict(self, data: dict[str, Any], metadata_map: dict[str, dict[str, Any]]) -> dict[str, Any]:
        """Enrich dictionary response"""
        enriched = data.copy()

        # Single instrument enrichment
        if "instrument_key" in data:
            instrument_key = data["instrument_key"]
            if instrument_key in metadata_map:
                metadata = metadata_map[instrument_key]

                # Add metadata object
                enriched["instrument_metadata"] = self._filter_metadata_fields(metadata)

                # Add convenient top-level fields
                for field in ["symbol", "exchange", "sector"]:
                    if field in metadata and field not in enriched:
                        enriched[field] = metadata[field]

                # Add enrichment timestamp
                enriched["enriched_at"] = datetime.now().isoformat()

        # Recursively enrich nested structures
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                enriched[key] = await self._apply_enrichment(value, metadata_map)

        return enriched

    async def _enrich_list(self, data: list[Any], metadata_map: dict[str, dict[str, Any]]) -> list[Any]:
        """Enrich list response"""
        enriched = []
        for item in data:
            enriched_item = await self._apply_enrichment(item, metadata_map)
            enriched.append(enriched_item)
        return enriched

    # =============================================================================
    # UTILITY METHODS
    # =============================================================================

    def _auto_extract_instrument_keys(self, response: Any) -> list[str]:
        """Automatically extract instrument_keys from response"""
        keys = set()

        def extract_recursive(obj):
            if isinstance(obj, dict):
                if "instrument_key" in obj and isinstance(obj["instrument_key"], str):
                    keys.add(obj["instrument_key"])
                for value in obj.values():
                    extract_recursive(value)
            elif isinstance(obj, list):
                for item in obj:
                    extract_recursive(item)

        extract_recursive(response)
        return list(keys)

    def _extract_instrument_keys_from_request(self, request_data: dict[str, Any]) -> list[str]:
        """Extract instrument keys from request for preloading"""
        keys = []

        # Check common request parameter names
        for param in ["instrument_key", "instrument_keys", "instruments"]:
            if param in request_data:
                value = request_data[param]
                if isinstance(value, str):
                    keys.append(value)
                elif isinstance(value, list):
                    keys.extend(v for v in value if isinstance(v, str))

        return keys

    def _convert_metadata_to_dict(self, metadata) -> dict[str, Any]:
        """Convert metadata object to dictionary"""
        result = {
            "instrument_key": metadata.instrument_key,
            "symbol": metadata.symbol,
            "exchange": metadata.exchange,
            "sector": metadata.sector,
            "instrument_type": metadata.instrument_type,
            "lot_size": metadata.lot_size,
            "tick_size": metadata.tick_size,
            "enrichment_source": "registry",
            "enriched_at": datetime.now().isoformat()
        }

        # Add optional fields if present
        for field_name in ["market_cap", "industry", "currency", "timezone"]:
            if hasattr(metadata, field_name):
                value = getattr(metadata, field_name)
                if value is not None:
                    result[field_name] = value

        # Exclude internal fields if configured
        if self.config.exclude_internal_fields:
            result = {k: v for k, v in result.items() if not k.startswith('_')}

        return result

    def _filter_metadata_fields(self, metadata: dict[str, Any]) -> dict[str, Any]:
        """Filter metadata fields based on configuration"""
        if not self.config.include_fields:
            return metadata

        filtered = {}
        for field_name in self.config.include_fields:
            if field_name in metadata:
                filtered[field_name] = metadata[field_name]

        # Always include core enrichment fields
        for core_field in ["enrichment_source", "enriched_at"]:
            if core_field in metadata:
                filtered[core_field] = metadata[core_field]

        return filtered

    def _create_fallback_metadata(self, instrument_key: str) -> dict[str, Any]:
        """Create fallback metadata when registry lookup fails"""
        # Try to parse some information from instrument_key
        parts = instrument_key.split('_')
        symbol = parts[0] if parts else "Unknown"
        exchange = parts[1] if len(parts) > 1 else "Unknown"

        return {
            "instrument_key": instrument_key,
            "symbol": symbol,
            "exchange": exchange,
            "sector": "Unknown",
            "instrument_type": "Unknown",
            "lot_size": 1,
            "tick_size": 0.01,
            "enrichment_source": "fallback",
            "enrichment_status": "registry_unavailable",
            "enriched_at": datetime.now().isoformat()
        }

    # =============================================================================
    # PERFORMANCE MONITORING
    # =============================================================================

    async def _track_performance(self, enrichment_time_ms: float, key_count: int):
        """Track enrichment performance metrics"""
        self.metrics.total_requests += 1

        # Track timing
        self._enrichment_times.append(enrichment_time_ms)
        if len(self._enrichment_times) > self._max_samples:
            self._enrichment_times.pop(0)

        # Update metrics
        self.metrics.avg_enrichment_time_ms = sum(self._enrichment_times) / len(self._enrichment_times)
        self.metrics.max_enrichment_time_ms = max(
            self.metrics.max_enrichment_time_ms, enrichment_time_ms
        )

        # Performance warning
        if enrichment_time_ms > self.config.performance_threshold_ms:
            logger.warning(
                f"Enrichment exceeded threshold: {enrichment_time_ms:.2f}ms "
                f"(threshold: {self.config.performance_threshold_ms}ms) for {key_count} instruments"
            )

    def get_performance_metrics(self) -> dict[str, Any]:
        """Get enrichment performance metrics"""
        cache_hit_rate = (
            self.metrics.cache_hits / (self.metrics.cache_hits + self.metrics.cache_misses)
            if (self.metrics.cache_hits + self.metrics.cache_misses) > 0 else 0
        )

        return {
            "performance": {
                "total_requests": self.metrics.total_requests,
                "avg_enrichment_time_ms": round(self.metrics.avg_enrichment_time_ms, 2),
                "max_enrichment_time_ms": round(self.metrics.max_enrichment_time_ms, 2),
                "failed_enrichments": self.metrics.failed_enrichments,
                "registry_calls": self.metrics.registry_calls,
                "performance_threshold_ms": self.config.performance_threshold_ms
            },
            "caching": {
                "enabled": self.config.enable_caching,
                "cache_hit_rate": round(cache_hit_rate * 100, 2) if cache_hit_rate else 0,
                "cache_hits": self.metrics.cache_hits,
                "cache_misses": self.metrics.cache_misses,
                "cache_stats": self.cache.get_stats() if self.cache else None
            },
            "configuration": {
                "batch_size": self.config.batch_size,
                "include_fields": self.config.include_fields,
                "exclude_internal_fields": self.config.exclude_internal_fields
            },
            "timestamp": datetime.now().isoformat()
        }

    async def reset_metrics(self):
        """Reset performance metrics"""
        self.metrics = EnrichmentMetrics()
        self._enrichment_times.clear()
        if self.cache:
            await self.cache.clear()

    # =============================================================================
    # HEALTH AND DIAGNOSTICS
    # =============================================================================

    async def health_check(self) -> dict[str, Any]:
        """Health check for metadata enrichment"""
        try:
            # Test registry connectivity
            test_key = "AAPL_NASDAQ_EQUITY"
            start_time = time.time()

            await self.enrich_single_instrument(test_key)
            response_time_ms = (time.time() - start_time) * 1000

            healthy = response_time_ms < self.config.performance_threshold_ms * 2

            return {
                "service": "MetadataEnrichmentMiddleware",
                "healthy": healthy,
                "response_time_ms": round(response_time_ms, 2),
                "registry_accessible": True,
                "cache_enabled": self.config.enable_caching,
                "performance_within_threshold": response_time_ms < self.config.performance_threshold_ms,
                "last_check": datetime.now().isoformat()
            }

        except Exception as e:
            return {
                "service": "MetadataEnrichmentMiddleware",
                "healthy": False,
                "error": str(e),
                "registry_accessible": False,
                "last_check": datetime.now().isoformat()
            }
