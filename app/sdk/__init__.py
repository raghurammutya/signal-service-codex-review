#!/usr/bin/env python3
"""
PythonSDK - Phase 1 Migration Package

SDK_001-003: instrument_key-first SDK with registry integration
- All public APIs require instrument_key as primary identifier
- Internal token resolution via Phase 3 registry
- Zero direct token inputs in public APIs
- Comprehensive backward compatibility with migration guidance
"""

from .instrument_client import InstrumentClient, InstrumentMetadata, create_instrument_client
from .order_client import OrderClient, Order, OrderType, OrderSide, OrderStatus, create_order_client
from .data_client import DataClient, MarketData, TimeFrame, DataType, create_data_client
from .http_client import InstrumentHTTPClient, HTTPClientConfig, create_http_client

__version__ = "1.0.0-phase1"
__all__ = [
    # Instrument management
    "InstrumentClient", 
    "InstrumentMetadata",
    "create_instrument_client",
    
    # Order management
    "OrderClient",
    "Order",
    "OrderType", 
    "OrderSide",
    "OrderStatus",
    "create_order_client",
    
    # Market data
    "DataClient",
    "MarketData",
    "TimeFrame",
    "DataType", 
    "create_data_client",
    
    # HTTP client
    "InstrumentHTTPClient",
    "HTTPClientConfig",
    "create_http_client",
]

# SDK-wide configuration
SDK_CONFIG = {
    "requires_instrument_key": True,
    "supports_legacy_tokens": False,  # Fully removed in Phase 1
    "registry_integration": True,
    "token_resolution": "internal_only",
    "metadata_enrichment": True,
    "phase": "1.0-sdk-strategy-migration"
}

# Contract validation
def validate_no_token_parameters(func_kwargs: dict) -> None:
    """
    Validate that no legacy token parameters are passed to SDK methods
    
    Args:
        func_kwargs: Function keyword arguments to validate
        
    Raises:
        ValueError: If legacy token parameters detected
    """
    forbidden_params = [
        'instrument_token', 'token', 'broker_token', 
        'ticker_token', 'token_id', 'legacy_token'
    ]
    
    for param in forbidden_params:
        if param in func_kwargs:
            raise ValueError(
                f"Parameter '{param}' not supported in Phase 1 SDK. "
                f"Use 'instrument_key' parameter instead. "
                f"Migration guide: docs.company.com/sdk-migration"
            )

# Migration helper
class SDKMigrationHelper:
    """Helper class for SDK migration guidance"""
    
    @staticmethod
    def get_migration_guide() -> str:
        """Return migration guide for token -> instrument_key conversion"""
        return """
        Phase 1 SDK Migration Guide
        ==========================
        
        OLD (deprecated):
            client.create_order(instrument_token="256265", ...)
            client.get_data(token="12345", ...)
        
        NEW (Phase 1):
            client.create_order(instrument_key="AAPL_NASDAQ_EQUITY", ...)
            client.get_data(instrument_key="AAPL_NASDAQ_EQUITY", ...)
        
        Key Changes:
        - All methods require instrument_key parameter
        - No token parameters accepted in public APIs
        - Automatic metadata enrichment from registry
        - Internal token resolution for broker operations
        
        Need help? Contact: sdk-migration@company.com
        """
    
    @staticmethod  
    def convert_symbol_to_key(symbol: str, exchange: str = "NSE") -> str:
        """
        Helper to convert symbol to instrument_key format
        
        Args:
            symbol: Trading symbol (e.g., "AAPL", "RELIANCE")
            exchange: Exchange name (e.g., "NASDAQ", "NSE")
            
        Returns:
            str: Formatted instrument_key
        """
        return f"{symbol}_{exchange}_EQUITY"