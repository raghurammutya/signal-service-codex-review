"""
Broker Symbol Converter for Signal Service
Handles conversion between ExchangeCode (standard) and broker-specific symbols
"""
import logging
from typing import Dict, Optional, List, Any
from datetime import datetime
import aiohttp

from app.utils.logging_utils import log_info, log_error, log_exception
from app.core.config import settings


class BrokerSymbolConverter:
    """
    Converts between standardized ExchangeCode symbols and broker-specific symbols
    Works with instrument_service for broker mappings
    """
    
    def __init__(self, instrument_service_url: str = None):
        self.instrument_service_url = instrument_service_url or settings.INSTRUMENT_SERVICE_URL or "http://instrument-service:8008"
        self.cache = {}  # Simple in-memory cache
        self.cache_ttl = 3600  # 1 hour cache
        self.session: Optional[aiohttp.ClientSession] = None
        
        log_info("BrokerSymbolConverter initialized")
    
    async def ensure_session(self):
        """Ensure aiohttp session is created"""
        if not self.session:
            self.session = aiohttp.ClientSession()
    
    async def convert_to_broker_symbol(
        self,
        exchange_code: str,
        broker_name: str,
        instrument_key: str
    ) -> Optional[str]:
        """
        Convert standardized ExchangeCode to broker-specific symbol
        
        Args:
            exchange_code: Standard exchange code (e.g., "RELIANCE")
            broker_name: Broker name (e.g., "breeze", "autotrader")
            instrument_key: Full instrument key
            
        Returns:
            Broker-specific symbol or None if not found
        """
        cache_key = f"{exchange_code}:{broker_name}"
        
        # Check cache
        if cache_key in self.cache:
            cached_data, timestamp = self.cache[cache_key]
            if (datetime.utcnow() - timestamp).seconds < self.cache_ttl:
                return cached_data
        
        await self.ensure_session()
        
        try:
            # Query instrument service for broker mapping
            url = f"{self.instrument_service_url}/api/v1/broker-integration/convert-symbol"
            payload = {
                "symbol": exchange_code,
                "from_format": "internal",
                "to_format": f"{broker_name}_native",
                "instrument_key": instrument_key
            }
            
            async with self.session.post(url, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    broker_symbol = data.get("converted_symbol")
                    
                    # Cache the result
                    self.cache[cache_key] = (broker_symbol, datetime.utcnow())
                    
                    return broker_symbol
                else:
                    log_error(f"Failed to convert symbol: {response.status}")
                    return None
                    
        except Exception as e:
            log_exception(f"Error converting to broker symbol: {e}")
            return None
    
    async def convert_from_broker_symbol(
        self,
        broker_symbol: str,
        broker_name: str
    ) -> Optional[str]:
        """
        Convert broker-specific symbol to standardized ExchangeCode
        
        Args:
            broker_symbol: Broker-specific symbol
            broker_name: Broker name
            
        Returns:
            Standard exchange code or None if not found
        """
        cache_key = f"{broker_name}:{broker_symbol}"
        
        # Check cache
        if cache_key in self.cache:
            cached_data, timestamp = self.cache[cache_key]
            if (datetime.utcnow() - timestamp).seconds < self.cache_ttl:
                return cached_data
        
        await self.ensure_session()
        
        try:
            # Query instrument service
            url = f"{self.instrument_service_url}/api/v1/broker-integration/convert-symbol"
            payload = {
                "symbol": broker_symbol,
                "from_format": f"{broker_name}_native",
                "to_format": "internal"
            }
            
            async with self.session.post(url, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    exchange_code = data.get("converted_symbol")
                    
                    # Cache the result
                    self.cache[cache_key] = (exchange_code, datetime.utcnow())
                    
                    return exchange_code
                else:
                    log_error(f"Failed to convert broker symbol: {response.status}")
                    return None
                    
        except Exception as e:
            log_exception(f"Error converting from broker symbol: {e}")
            return None
    
    async def get_broker_mappings(self, exchange_code: str) -> Dict[str, str]:
        """
        Get all broker mappings for a given ExchangeCode
        
        Args:
            exchange_code: Standard exchange code
            
        Returns:
            Dictionary of broker_name -> broker_specific_symbol
        """
        await self.ensure_session()
        
        try:
            url = f"{self.instrument_service_url}/api/v1/broker-integration/broker-mappings/{exchange_code}"
            
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("mappings", {})
                else:
                    log_error(f"Failed to get broker mappings: {response.status}")
                    return {}
                    
        except Exception as e:
            log_exception(f"Error getting broker mappings: {e}")
            return {}
    
    async def validate_instrument_key(self, instrument_key: str) -> bool:
        """
        Validate that instrument key uses standard ExchangeCode format
        
        Args:
            instrument_key: Instrument key to validate
            
        Returns:
            True if valid, False otherwise
        """
        try:
            # Instrument key format: exchange@symbol@product_type[@expiry][@option_type][@strike]
            parts = instrument_key.split('@')
            
            if len(parts) < 3:
                return False
            
            exchange = parts[0]
            symbol = parts[1]
            product_type = parts[2]
            
            # Validate exchange
            valid_exchanges = ['NSE', 'BSE', 'NFO', 'MCX', 'CDS', 'NYSE', 'NASDAQ', 'BINANCE']
            if exchange not in valid_exchanges:
                return False
            
            # Additional validation can be added here
            return True
            
        except Exception as e:
            log_error(f"Error validating instrument key: {e}")
            return False
    
    async def enrich_with_broker_info(
        self,
        signal_data: Dict[str, Any],
        broker_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Enrich signal data with broker-specific information
        
        Args:
            signal_data: Signal data with ExchangeCode
            broker_name: Optional specific broker to include
            
        Returns:
            Enriched signal data
        """
        instrument_key = signal_data.get("instrument_key")
        
        if not instrument_key:
            return signal_data
        
        # Extract symbol from instrument key
        parts = instrument_key.split('@')
        if len(parts) >= 2:
            exchange_code = parts[1]
            
            # Get broker mappings
            if broker_name:
                # Get specific broker mapping
                broker_symbol = await self.convert_to_broker_symbol(
                    exchange_code, broker_name, instrument_key
                )
                if broker_symbol:
                    signal_data["broker_symbols"] = {
                        broker_name: broker_symbol
                    }
            else:
                # Get all broker mappings
                mappings = await self.get_broker_mappings(exchange_code)
                if mappings:
                    signal_data["broker_symbols"] = mappings
        
        return signal_data
    
    async def close(self):
        """Close the HTTP session"""
        if self.session:
            await self.session.close()
            self.session = None