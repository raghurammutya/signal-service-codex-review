#!/usr/bin/env python3
"""
PythonSDK Order Client - Phase 1 Migration

SDK_001 & SDK_002: Update Order APIs to require instrument_key
- All order methods require instrument_key parameter
- Internal token resolution for broker calls
- Backward compatibility with deprecation warnings
"""

import asyncio
import logging
import warnings
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from app.sdk.instrument_client import InstrumentClient, create_instrument_client

logger = logging.getLogger(__name__)

class OrderType(Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"

class OrderSide(Enum):
    BUY = "BUY"
    SELL = "SELL"

class OrderStatus(Enum):
    PENDING = "PENDING"
    OPEN = "OPEN"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"

@dataclass
class Order:
    """Order representation with instrument_key as primary identifier"""
    order_id: str
    instrument_key: str  # Primary identifier - NO instrument_token
    symbol: str  # Enriched from registry metadata
    exchange: str  # Enriched from registry metadata
    side: OrderSide
    order_type: OrderType
    quantity: int
    price: float | None = None
    stop_price: float | None = None
    status: OrderStatus = OrderStatus.PENDING
    created_at: datetime = None
    updated_at: datetime = None
    # Broker information for internal use only
    _broker_order_id: str | None = None
    _broker_id: str | None = None

class OrderClient:
    """
    Phase 1: instrument_key-first Order Client

    All public methods require instrument_key as primary identifier.
    Broker tokens are resolved internally and never exposed.
    """

    def __init__(self,
                 instrument_client: InstrumentClient | None = None,
                 broker_id: str = "default"):
        """
        Initialize Order Client with instrument resolution capability

        Args:
            instrument_client: Client for instrument metadata and token resolution
            broker_id: Default broker for order routing
        """
        self.instrument_client = instrument_client or create_instrument_client()
        self.broker_id = broker_id
        self._active_orders: dict[str, Order] = {}

    async def create_order(self,
                         instrument_key: str,
                         side: OrderSide,
                         quantity: int,
                         order_type: OrderType = OrderType.MARKET,
                         price: float | None = None,
                         stop_price: float | None = None,
                         broker_id: str | None = None) -> Order:
        """
        Create order using instrument_key as primary identifier

        Args:
            instrument_key: Primary identifier (e.g., "AAPL_NASDAQ_EQUITY")
            side: BUY or SELL
            quantity: Number of shares/contracts
            order_type: Market, limit, stop, etc.
            price: Limit price (required for limit orders)
            stop_price: Stop price (required for stop orders)
            broker_id: Override default broker

        Returns:
            Order: Created order with enriched metadata
        """
        # Get instrument metadata for enrichment
        metadata = await self.instrument_client.get_instrument_metadata(instrument_key)

        # Resolve broker token internally
        target_broker = broker_id or self.broker_id
        broker_token = await self.instrument_client.resolve_broker_token(
            instrument_key, target_broker
        )

        # Generate order ID
        order_id = f"ord_{int(datetime.now().timestamp() * 1000)}"

        # Create order object with enriched metadata
        order = Order(
            order_id=order_id,
            instrument_key=instrument_key,
            symbol=metadata.symbol,
            exchange=metadata.exchange,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            stop_price=stop_price,
            status=OrderStatus.PENDING,
            created_at=datetime.now(),
            _broker_id=target_broker
        )

        try:
            # Place order with broker using resolved token
            broker_order_id = await self._place_broker_order(
                broker_token=broker_token,
                order=order,
                broker_id=target_broker
            )

            # Update order with broker information
            order._broker_order_id = broker_order_id
            order.status = OrderStatus.OPEN
            order.updated_at = datetime.now()

            # Track active order
            self._active_orders[order_id] = order

            logger.info(f"Order created: {order_id} for {instrument_key} ({metadata.symbol})")
            return order

        except Exception as e:
            order.status = OrderStatus.REJECTED
            order.updated_at = datetime.now()
            logger.error(f"Order creation failed for {instrument_key}: {e}")
            raise RuntimeError(f"Order creation failed: {e}") from e

    async def get_order_status(self, order_id: str) -> Order | None:
        """
        Get current order status

        Args:
            order_id: Order identifier

        Returns:
            Order: Current order state with metadata
        """
        if order_id not in self._active_orders:
            logger.warning(f"Order not found: {order_id}")
            return None

        order = self._active_orders[order_id]

        # Update status from broker if needed
        if order.status in [OrderStatus.OPEN, OrderStatus.PENDING]:
            try:
                updated_status = await self._get_broker_order_status(
                    order._broker_order_id,
                    order._broker_id
                )
                if updated_status != order.status:
                    order.status = updated_status
                    order.updated_at = datetime.now()
                    logger.debug(f"Updated order {order_id} status: {updated_status}")
            except Exception as e:
                logger.error(f"Failed to update order status for {order_id}: {e}")

        return order

    async def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an active order

        Args:
            order_id: Order to cancel

        Returns:
            bool: True if cancellation successful
        """
        order = await self.get_order_status(order_id)
        if not order:
            raise ValueError(f"Order not found: {order_id}")

        if order.status not in [OrderStatus.OPEN, OrderStatus.PENDING]:
            raise ValueError(f"Cannot cancel order in {order.status} status")

        try:
            success = await self._cancel_broker_order(
                order._broker_order_id,
                order._broker_id
            )

            if success:
                order.status = OrderStatus.CANCELED
                order.updated_at = datetime.now()
                logger.info(f"Order canceled: {order_id}")
                return True
            logger.warning(f"Broker cancellation failed for order: {order_id}")
            return False

        except Exception as e:
            logger.error(f"Order cancellation error for {order_id}: {e}")
            raise RuntimeError(f"Cancellation failed: {e}") from e

    async def get_orders_for_instrument(self, instrument_key: str) -> list[Order]:
        """
        Get all orders for a specific instrument

        Args:
            instrument_key: Primary identifier

        Returns:
            list[Order]: All orders for instrument
        """
        orders = [
            order for order in self._active_orders.values()
            if order.instrument_key == instrument_key
        ]

        # Update all order statuses
        for order in orders:
            await self.get_order_status(order.order_id)

        logger.debug(f"Found {len(orders)} orders for {instrument_key}")
        return orders

    # =============================================================================
    # DEPRECATED METHODS - Backward Compatibility
    # =============================================================================

    def create_order_by_token(self, instrument_token: str, **kwargs) -> None:
        """
        DEPRECATED: Create order using legacy token

        Args:
            instrument_token: Legacy broker token
            **kwargs: Order parameters

        Raises:
            DeprecationWarning: Method is deprecated
        """
        warnings.warn(
            "create_order_by_token() is deprecated. Use create_order() with instrument_key. "
            "This method will be removed in SDK v2.0",
            DeprecationWarning,
            stacklevel=2
        )

        logger.warning(f"Deprecated token-based order creation: {instrument_token[:8]}***")
        raise ValueError(
            "Token-based order creation is deprecated. "
            "Use create_order(instrument_key, ...) instead."
        )

    # =============================================================================
    # INTERNAL BROKER INTEGRATION (TOKEN-BASED)
    # =============================================================================

    async def _place_broker_order(self, broker_token: str, order: Order, broker_id: str) -> str:
        """
        Internal: Place order with broker using resolved token

        This method handles the actual broker integration using tokens
        resolved from instrument_key. Never exposed in public API.
        """
        logger.debug(f"Placing broker order: {broker_id} token={broker_token[:8]}***")

        # Simulate broker order placement
        # In real implementation, this would call broker APIs
        broker_order_id = f"brk_{broker_id}_{int(datetime.now().timestamp())}"

        # Simulate some processing time
        await asyncio.sleep(0.1)

        logger.debug(f"Broker order placed: {broker_order_id}")
        return broker_order_id

    async def _get_broker_order_status(self, broker_order_id: str, broker_id: str) -> OrderStatus:
        """Internal: Get order status from broker"""
        # Simulate broker status check
        await asyncio.sleep(0.05)

        # For demo, randomly simulate some orders being filled
        import random
        if random.random() > 0.7:  # 30% chance of being filled
            return OrderStatus.FILLED

        return OrderStatus.OPEN

    async def _cancel_broker_order(self, broker_order_id: str, broker_id: str) -> bool:
        """Internal: Cancel order at broker"""
        logger.debug(f"Canceling broker order: {broker_order_id}")
        await asyncio.sleep(0.1)
        return True

# Factory function for SDK users
def create_order_client(broker_id: str = "default") -> OrderClient:
    """
    Create order client with instrument resolution capability

    Args:
        broker_id: Default broker for order routing

    Returns:
        OrderClient: Ready-to-use client
    """
    return OrderClient(broker_id=broker_id)
