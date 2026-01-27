#!/usr/bin/env python3
"""
PythonSDK Instrument Client - Phase 1 Migration

SDK_001: Update PythonSDK instrument_key Requirements
- All public methods require instrument_key parameter
- Internal token resolution via Phase 3 registry
- Backward compatibility with deprecation warnings
"""

import logging
import warnings
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from app.clients.instrument_registry_client import InstrumentRegistryClient, create_registry_client

logger = logging.getLogger(__name__)

@dataclass
class InstrumentMetadata:
    """Enriched instrument metadata from registry"""
    instrument_key: str
    symbol: str
    exchange: str
    sector: str | None = None
    instrument_type: str = "EQUITY"
    lot_size: int = 1
    tick_size: float = 0.01
    # Internal broker tokens - not exposed in public API
    _broker_tokens: dict[str, str] | None = None

class InstrumentClient:
    """
    Phase 1: instrument_key-first Instrument Client

    All public methods require instrument_key as primary identifier.
    Internal token resolution via Phase 3 registry integration.
    """

    def __init__(self, registry_client: InstrumentRegistryClient | None = None):
        """Initialize with registry client for token resolution"""
        self.registry_client = registry_client or create_registry_client()
        self._cache = {}
        self._cache_ttl = 300  # 5 minute cache

    async def get_instrument_metadata(self, instrument_key: str) -> InstrumentMetadata:
        """
        Get enriched instrument metadata by instrument_key

        Args:
            instrument_key: Primary identifier (e.g., "AAPL_NASDAQ_EQUITY")

        Returns:
            InstrumentMetadata: Complete instrument information
        """
        # Check cache
        cache_key = f"metadata:{instrument_key}"
        cached = self._get_from_cache(cache_key)
        if cached:
            return cached

        # Fetch from registry
        try:
            result = await self.registry_client.get_instrument_metadata([instrument_key])
            instruments = result.get('instruments', [])

            if not instruments:
                raise ValueError(f"Instrument not found: {instrument_key}")

            instrument_data = instruments[0]

            metadata = InstrumentMetadata(
                instrument_key=instrument_key,
                symbol=instrument_data.get('symbol', ''),
                exchange=instrument_data.get('exchange', ''),
                sector=instrument_data.get('sector'),
                instrument_type=instrument_data.get('instrument_type', 'EQUITY'),
                lot_size=instrument_data.get('lot_size', 1),
                tick_size=instrument_data.get('tick_size', 0.01),
                _broker_tokens=instrument_data.get('broker_tokens', {})
            )

            # Cache the result
            self._set_cache(cache_key, metadata)

            logger.debug(f"Retrieved metadata for {instrument_key}: {metadata.symbol}")
            return metadata

        except Exception as e:
            logger.error(f"Failed to get metadata for {instrument_key}: {e}")
            raise RuntimeError(f"Metadata retrieval failed: {e}")

    async def search_instruments(self, query: str, limit: int = 50) -> list[InstrumentMetadata]:
        """
        Search instruments by symbol, name, or other attributes

        Args:
            query: Search term (symbol, company name, etc.)
            limit: Maximum results to return

        Returns:
            List[InstrumentMetadata]: Matching instruments
        """
        try:
            result = await self.registry_client.search_instruments(query, limit)
            instruments = result.get('instruments', [])

            metadata_list = []
            for instrument_data in instruments:
                metadata = InstrumentMetadata(
                    instrument_key=instrument_data.get('instrument_key', ''),
                    symbol=instrument_data.get('symbol', ''),
                    exchange=instrument_data.get('exchange', ''),
                    sector=instrument_data.get('sector'),
                    instrument_type=instrument_data.get('instrument_type', 'EQUITY'),
                    lot_size=instrument_data.get('lot_size', 1),
                    tick_size=instrument_data.get('tick_size', 0.01),
                    _broker_tokens=instrument_data.get('broker_tokens', {})
                )
                metadata_list.append(metadata)

            logger.debug(f"Search '{query}' returned {len(metadata_list)} results")
            return metadata_list

        except Exception as e:
            logger.error(f"Search failed for '{query}': {e}")
            raise RuntimeError(f"Search failed: {e}")

    async def resolve_broker_token(self, instrument_key: str, broker_id: str) -> str:
        """
        Internal method: Resolve broker-specific token from instrument_key

        This method is used internally by other SDK components.
        Public API consumers should not call this directly.

        Args:
            instrument_key: Primary identifier
            broker_id: Target broker (kite, zerodha, ibkr, etc.)

        Returns:
            str: Broker-specific instrument token
        """
        metadata = await self.get_instrument_metadata(instrument_key)

        if not metadata._broker_tokens or broker_id not in metadata._broker_tokens:
            raise ValueError(f"Broker token not available for {instrument_key} on {broker_id}")

        token = metadata._broker_tokens[broker_id]
        logger.debug(f"Resolved {instrument_key} -> {broker_id} token: {token[:8]}***")
        return token

    # =============================================================================
    # DEPRECATED METHODS - Backward Compatibility with Warnings
    # =============================================================================

    @staticmethod
    def accept_legacy_token(instrument_token: str) -> str:
        """
        DEPRECATED: Convert legacy token to instrument_key

        Args:
            instrument_token: Legacy broker token

        Returns:
            str: instrument_key if mapping exists

        Raises:
            DeprecationWarning: Method is deprecated
            ValueError: If token cannot be mapped
        """
        warnings.warn(
            "accept_legacy_token() is deprecated. Use instrument_key parameter directly. "
            "This method will be removed in SDK v2.0",
            DeprecationWarning,
            stacklevel=2
        )

        # TODO: Implement reverse token lookup via registry
        # For now, return a placeholder to maintain compatibility
        logger.warning(f"Legacy token conversion requested: {instrument_token[:8]}***")
        raise ValueError(
            "Legacy token conversion not supported in Phase 1. "
            "Please use instrument_key parameter. "
            "Contact support for migration assistance."
        )

    def get_metadata_by_token(self, instrument_token: str) -> dict[str, Any]:
        """
        DEPRECATED: Get metadata by legacy token

        Args:
            instrument_token: Legacy broker token

        Returns:
            Dict: Instrument metadata

        Raises:
            DeprecationWarning: Method is deprecated
        """
        warnings.warn(
            "get_metadata_by_token() is deprecated. Use get_instrument_metadata() with instrument_key. "
            "This method will be removed in SDK v2.0",
            DeprecationWarning,
            stacklevel=2
        )

        logger.warning(f"Deprecated token-based metadata access: {instrument_token[:8]}***")
        raise ValueError(
            "Token-based metadata access is deprecated. "
            "Use get_instrument_metadata(instrument_key) instead."
        )

    # =============================================================================
    # PRIVATE HELPERS
    # =============================================================================

    def _get_from_cache(self, key: str) -> Any | None:
        """Get value from internal cache if not expired"""
        if key in self._cache:
            entry = self._cache[key]
            if datetime.now() < entry["expires_at"]:
                return entry["value"]
            del self._cache[key]
        return None

    def _set_cache(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Set value in internal cache with TTL"""
        ttl = ttl or self._cache_ttl
        self._cache[key] = {
            "value": value,
            "expires_at": datetime.now() + timedelta(seconds=ttl)
        }

# Factory function for SDK users
def create_instrument_client() -> InstrumentClient:
    """
    Create instrument client with registry integration

    Returns:
        InstrumentClient: Ready-to-use client with registry connection
    """
    return InstrumentClient()
