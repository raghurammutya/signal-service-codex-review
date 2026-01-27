#!/usr/bin/env python3
"""
Base Broker Client - Phase 1 Migration

CLIENT_002: Broker Integration Wrapper
- Unified interface for all broker integrations
- Internal token resolution via registry
- instrument_key as primary identifier for all operations
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from app.sdk.instrument_client import InstrumentClient, create_instrument_client

logger = logging.getLogger(__name__)

class BrokerType(Enum):
    KITE = "kite"
    ZERODHA = "zerodha"
    IBKR = "ibkr"
    UPSTOX = "upstox"
    MOCK = "mock"  # For testing

@dataclass
class BrokerConfig:
    """Configuration for broker client"""
    broker_type: BrokerType
    api_key: str
    api_secret: str
    access_token: str | None = None
    base_url: str | None = None
    timeout: int = 30
    rate_limit_per_second: int = 10
    enable_token_resolution: bool = True

@dataclass
class BrokerOrder:
    """Unified order representation across brokers"""
    instrument_key: str  # Primary identifier
    symbol: str          # Enriched from registry
    exchange: str        # Enriched from registry
    order_id: str
    broker_order_id: str
    side: str           # BUY/SELL
    order_type: str     # MARKET/LIMIT/STOP
    quantity: int
    price: float | None = None
    status: str = "PENDING"
    created_at: datetime = None
    # Internal broker data - not exposed
    _broker_token: str | None = None
    _raw_broker_response: dict | None = None

@dataclass
class BrokerQuote:
    """Unified quote representation"""
    instrument_key: str
    symbol: str
    exchange: str
    ltp: float
    bid: float | None = None
    ask: float | None = None
    volume: int = 0
    timestamp: datetime = None
    # Registry enriched metadata
    sector: str | None = None
    market_cap: float | None = None
    # Internal fields
    _broker_token: str | None = None

class BaseBrokerClient(ABC):
    """
    Abstract base class for all broker integrations

    CLIENT_002: All broker clients implement instrument_key-first interface
    with internal token resolution via registry integration.
    """

    def __init__(self, config: BrokerConfig, instrument_client: InstrumentClient | None = None):
        self.config = config
        self.broker_type = config.broker_type
        self.instrument_client = instrument_client or create_instrument_client()
        self._session = None
        self._rate_limiter = asyncio.Semaphore(config.rate_limit_per_second)

    # =============================================================================
    # PUBLIC API - instrument_key REQUIRED
    # =============================================================================

    async def place_order(self,
                         instrument_key: str,
                         side: str,
                         quantity: int,
                         order_type: str = "MARKET",
                         price: float | None = None,
                         **kwargs) -> BrokerOrder:
        """
        Place order using instrument_key as primary identifier

        Args:
            instrument_key: Primary identifier (e.g., "AAPL_NASDAQ_EQUITY")
            side: "BUY" or "SELL"
            quantity: Number of shares
            order_type: "MARKET", "LIMIT", etc.
            price: Limit price if applicable
            **kwargs: Additional broker-specific parameters

        Returns:
            BrokerOrder: Unified order with enriched metadata
        """
        # Get instrument metadata for enrichment
        metadata = await self.instrument_client.get_instrument_metadata(instrument_key)

        # Resolve broker token internally
        broker_token = await self.instrument_client.resolve_broker_token(
            instrument_key, self.broker_type.value
        )

        # Rate limiting
        async with self._rate_limiter:
            try:
                # Call broker-specific implementation with resolved token
                raw_response = await self._place_order_impl(
                    broker_token=broker_token,
                    side=side,
                    quantity=quantity,
                    order_type=order_type,
                    price=price,
                    **kwargs
                )

                # Create unified order object
                order = BrokerOrder(
                    instrument_key=instrument_key,
                    symbol=metadata.symbol,
                    exchange=metadata.exchange,
                    order_id=f"{self.broker_type.value}_{raw_response.get('order_id')}",
                    broker_order_id=raw_response.get('order_id', ''),
                    side=side,
                    order_type=order_type,
                    quantity=quantity,
                    price=price,
                    status=raw_response.get('status', 'PENDING'),
                    created_at=datetime.now(),
                    _broker_token=broker_token,
                    _raw_broker_response=raw_response
                )

                logger.info(f"Order placed via {self.broker_type.value}: {instrument_key} ({metadata.symbol})")
                return order

            except Exception as e:
                logger.error(f"Order placement failed for {instrument_key}: {e}")
                raise RuntimeError(f"Broker order failed: {e}")

    async def get_quote(self, instrument_key: str) -> BrokerQuote:
        """
        Get real-time quote using instrument_key

        Args:
            instrument_key: Primary identifier

        Returns:
            BrokerQuote: Unified quote with enriched metadata
        """
        metadata = await self.instrument_client.get_instrument_metadata(instrument_key)
        broker_token = await self.instrument_client.resolve_broker_token(
            instrument_key, self.broker_type.value
        )

        async with self._rate_limiter:
            try:
                raw_quote = await self._get_quote_impl(broker_token)

                quote = BrokerQuote(
                    instrument_key=instrument_key,
                    symbol=metadata.symbol,
                    exchange=metadata.exchange,
                    ltp=raw_quote.get('ltp', 0.0),
                    bid=raw_quote.get('bid'),
                    ask=raw_quote.get('ask'),
                    volume=raw_quote.get('volume', 0),
                    timestamp=datetime.now(),
                    sector=metadata.sector,
                    _broker_token=broker_token
                )

                logger.debug(f"Quote retrieved: {instrument_key} LTP={quote.ltp}")
                return quote

            except Exception as e:
                logger.error(f"Quote retrieval failed for {instrument_key}: {e}")
                raise RuntimeError(f"Quote failed: {e}")

    async def get_order_status(self, order_id: str) -> BrokerOrder | None:
        """
        Get order status by order ID

        Args:
            order_id: Unified order ID

        Returns:
            BrokerOrder: Updated order status
        """
        # Extract broker order ID from unified order ID
        if not order_id.startswith(f"{self.broker_type.value}_"):
            raise ValueError(f"Invalid order ID format: {order_id}")

        broker_order_id = order_id.replace(f"{self.broker_type.value}_", "")

        async with self._rate_limiter:
            try:
                raw_status = await self._get_order_status_impl(broker_order_id)

                # Reconstruct order with updated status
                # Note: In real implementation, we'd need to store/retrieve original order data
                return BrokerOrder(
                    instrument_key=raw_status.get('instrument_key', ''),
                    symbol=raw_status.get('symbol', ''),
                    exchange=raw_status.get('exchange', ''),
                    order_id=order_id,
                    broker_order_id=broker_order_id,
                    side=raw_status.get('side', ''),
                    order_type=raw_status.get('order_type', ''),
                    quantity=raw_status.get('quantity', 0),
                    price=raw_status.get('price'),
                    status=raw_status.get('status', 'UNKNOWN'),
                    created_at=datetime.fromisoformat(raw_status.get('created_at', datetime.now().isoformat()))
                )

            except Exception as e:
                logger.error(f"Order status check failed for {order_id}: {e}")
                return None

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel order by order ID"""
        broker_order_id = order_id.replace(f"{self.broker_type.value}_", "")

        async with self._rate_limiter:
            try:
                result = await self._cancel_order_impl(broker_order_id)
                logger.info(f"Order canceled: {order_id}")
                return result
            except Exception as e:
                logger.error(f"Order cancellation failed for {order_id}: {e}")
                return False

    # =============================================================================
    # BROKER-SPECIFIC IMPLEMENTATIONS (INTERNAL TOKEN-BASED)
    # =============================================================================

    @abstractmethod
    async def _place_order_impl(self,
                               broker_token: str,
                               side: str,
                               quantity: int,
                               order_type: str,
                               price: float | None = None,
                               **kwargs) -> dict[str, Any]:
        """
        Broker-specific order placement implementation

        This method handles the actual broker API calls using resolved tokens.
        Never exposed in public interface.
        """

    @abstractmethod
    async def _get_quote_impl(self, broker_token: str) -> dict[str, Any]:
        """Broker-specific quote implementation"""

    @abstractmethod
    async def _get_order_status_impl(self, broker_order_id: str) -> dict[str, Any]:
        """Broker-specific order status implementation"""

    @abstractmethod
    async def _cancel_order_impl(self, broker_order_id: str) -> bool:
        """Broker-specific order cancellation implementation"""

    # =============================================================================
    # CONNECTION MANAGEMENT
    # =============================================================================

    async def connect(self) -> bool:
        """Establish connection to broker"""
        try:
            await self._connect_impl()
            logger.info(f"Connected to {self.broker_type.value}")
            return True
        except Exception as e:
            logger.error(f"Connection failed to {self.broker_type.value}: {e}")
            return False

    async def disconnect(self):
        """Close connection to broker"""
        await self._disconnect_impl()
        logger.info(f"Disconnected from {self.broker_type.value}")

    @abstractmethod
    async def _connect_impl(self):
        """Broker-specific connection implementation"""

    @abstractmethod
    async def _disconnect_impl(self):
        """Broker-specific disconnection implementation"""

    # =============================================================================
    # HEALTH CHECK
    # =============================================================================

    async def health_check(self) -> dict[str, Any]:
        """Check broker connection health"""
        try:
            # Test with a simple quote request if connected
            health_status = await self._health_check_impl()
            return {
                "broker": self.broker_type.value,
                "healthy": True,
                "status": health_status,
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            return {
                "broker": self.broker_type.value,
                "healthy": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }

    @abstractmethod
    async def _health_check_impl(self) -> dict[str, Any]:
        """Broker-specific health check implementation"""
