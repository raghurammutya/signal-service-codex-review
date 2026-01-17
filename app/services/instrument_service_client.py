"""
Production Client for integrating with Instrument Service.
"""

import logging
import asyncio
import httpx
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Dict, List, Optional
from datetime import datetime
import json

from app.core.config import settings


class ServiceUnavailableError(Exception):
    """Exception raised when external service is unavailable"""
    pass


logger = logging.getLogger(__name__)


@dataclass
class InstrumentKey:
    """Minimal instrument key representation used for parsing in tests."""

    raw: str
    exchange: Optional[str] = None
    symbol: Optional[str] = None
    asset_class: Optional[str] = None

    @classmethod
    def parse(cls, instrument_key: str) -> "InstrumentKey":
        parts = instrument_key.replace(":", "@").split("@")
        exchange = parts[0] if parts else None
        symbol = parts[1] if len(parts) > 1 else None
        asset_class = parts[2] if len(parts) > 2 else None
        return cls(raw=instrument_key, exchange=exchange, symbol=symbol, asset_class=asset_class)


class InstrumentServiceClient:
    """
    Production client for communicating with the Instrument Service.
    
    Features:
    - HTTP client with connection pooling
    - Internal API key authentication
    - Response caching with TTL
    - Graceful fallback to stub data when service unavailable
    """

    def __init__(self):
        self.base_url = settings.INSTRUMENT_SERVICE_URL
        self.internal_api_key = getattr(settings, 'internal_api_key', None)
        self._cache: Dict[str, Any] = {}
        self._cache_ttl = 300  # seconds
        self._http_client: Optional[httpx.AsyncClient] = None
        self._service_available = True  # Optimistically assume service is available
    
    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client for instrument service requests"""
        if self._http_client is None:
            headers = {"Content-Type": "application/json"}
            if self.internal_api_key:
                headers["X-Internal-API-Key"] = self.internal_api_key
                
            self._http_client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=headers,
                timeout=10.0
            )
        return self._http_client
    
    async def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make HTTP request to instrument service with error handling"""
        if not self._service_available:
            raise ServiceUnavailableError(f"Instrument service marked as unavailable ({method} {endpoint})")
            
        try:
            client = await self._get_http_client()
            response = await client.request(method, endpoint, **kwargs)
            response.raise_for_status()
            return response.json()
            
        except Exception as e:
            logger.exception(f"Instrument service request failed ({method} {endpoint}): {e}")
            self._service_available = False
            raise ServiceUnavailableError(f"Instrument service unavailable ({method} {endpoint}): {e}") from e
    
    async def get_instrument(self, instrument_key: str) -> Dict[str, Any]:
        """Get instrument details from service (no fallbacks)"""
        try:
            service_response = await self._make_request("GET", f"/api/v1/instruments/{instrument_key}")
            if service_response:
                return service_response
            else:
                raise ServiceUnavailableError(f"Instrument service returned no data for {instrument_key}")
        except Exception as e:
            logger.exception(f"Failed to get instrument {instrument_key}: {e}")
            raise

    async def get_instrument_metadata(self, instrument_key: str) -> Dict[str, Any]:
        return await self.get_instrument(instrument_key)

    async def calculate_moneyness(self, option_key: str, spot_price: float, method: str = "simple") -> Optional[Dict[str, Any]]:
        """Calculate moneyness using service or return fallback calculation"""
        # Try real service calculation
        payload = {
            "option_key": option_key,
            "spot_price": spot_price,
            "method": method
        }
        service_response = await self._make_request("POST", "/api/v1/moneyness/calculate", json=payload)
        if service_response:
            return service_response
            
        # No fallback calculation in production - service must provide data
        raise RuntimeError(f"Instrument service failed to calculate moneyness for {option_key} - no fallback data in production")

    async def get_strikes_by_moneyness(self, underlying_symbol, moneyness_level, expiry_date=None) -> List[Dict[str, Any]]:
        """Get option strikes by moneyness level from service or return fallback data"""
        # Try real service first
        params = {
            "underlying_symbol": underlying_symbol,
            "moneyness_level": moneyness_level,
            "expiry_date": expiry_date
        }
        service_response = await self._make_request("GET", f"/api/v1/options/strikes/moneyness", params=params)
        if service_response and service_response.get("strikes"):
            return service_response["strikes"]
            
        # No fallback data in production - fail fast if service unavailable
        raise RuntimeError(f"Strike data not available from instrument service for {underlying_symbol}")

    async def get_moneyness_history(self, symbol: str, start_time: datetime, end_time: datetime, interval: str = "5m") -> List[Dict[str, Any]]:
        """Get moneyness history from instrument service."""
        # Production implementation requires instrument service integration
        raise RuntimeError(f"Moneyness history service integration not available for {symbol} - production system requires complete implementation")

    async def enrich_instrument(self, instrument_data: Dict[str, Any]) -> Dict[str, Any]:
        """Echo back instrument data with a timestamp."""
        instrument_data = dict(instrument_data)
        instrument_data["enriched_at"] = datetime.utcnow().isoformat()
        return instrument_data

    @lru_cache(maxsize=1000)
    def parse_instrument_key(self, instrument_key: str) -> Optional[InstrumentKey]:
        """Parse and validate instrument key."""
        try:
            return InstrumentKey.parse(instrument_key)
        except Exception as exc:
            logger.error("Failed to parse instrument key %s: %s", instrument_key, exc)
            return None

    async def get_atm_iv(self, underlying_symbol: str, expiry_date: str, spot_price: float) -> Optional[float]:
        """Get ATM implied volatility from instrument service - no fallback data."""
        raise RuntimeError(f"ATM IV calculation requires instrument service integration - stub data removed")

    async def get_otm_delta_strikes(self, underlying_symbol: str, delta_target: float, option_type: str, expiry_date: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get OTM delta strikes from instrument service - no fallback data."""
        raise RuntimeError(f"Delta-based strike calculation requires instrument service integration - stub data removed")

    async def get_moneyness_configuration(self) -> Dict[str, Any]:
        """Get moneyness configuration from instrument service - no default fallback."""
        raise RuntimeError(f"Moneyness configuration requires instrument service integration - default config removed")

    # Note: _get_default_moneyness_config removed - production must use instrument service
    # for moneyness configuration instead of hardcoded defaults

    async def close(self):
        """Close HTTP client and cleanup resources"""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
        self._cache.clear()
        logger.info("InstrumentServiceClient closed and cleaned up")
