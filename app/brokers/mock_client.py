#!/usr/bin/env python3
"""
Mock Broker Client - Phase 1 Migration

CLIENT_002: Mock broker for testing and development
- Implements unified broker interface
- Simulates real broker behavior with instrument_key resolution
"""

import asyncio
import logging
import random
from datetime import datetime
from typing import Any

from app.brokers.base_broker_client import BaseBrokerClient, BrokerConfig, BrokerType

logger = logging.getLogger(__name__)

class MockBrokerClient(BaseBrokerClient):
    """
    Mock broker client for testing and development

    CLIENT_002: Implements full broker interface with simulated
    behavior for testing instrument_key-first operations.
    """

    def __init__(self, config: BrokerConfig):
        # Override broker type to MOCK
        config.broker_type = BrokerType.MOCK
        super().__init__(config)

        # Mock data storage
        self._orders: dict[str, dict[str, Any]] = {}
        self._positions: dict[str, dict[str, Any]] = {}
        self._mock_prices: dict[str, float] = {}
        self._order_counter = 1000

        # Initialize some mock price data
        self._initialize_mock_data()

    def _initialize_mock_data(self):
        """Initialize mock price data for common instruments"""

        # Generate realistic mock prices
        base_prices = {
            "AAPL_NASDAQ_EQUITY": 150.0,
            "GOOGL_NASDAQ_EQUITY": 2800.0,
            "MSFT_NASDAQ_EQUITY": 330.0,
            "RELIANCE_NSE_EQUITY": 2400.0,
            "INFY_NSE_EQUITY": 1450.0,
            "TCS_NSE_EQUITY": 3200.0,
            "NIFTY50_NSE_INDEX": 18500.0,
            "BANKNIFTY_NSE_INDEX": 42000.0
        }

        for instrument, base_price in base_prices.items():
            # Add some random variation
            variation = random.uniform(-0.02, 0.02)  # ±2%
            self._mock_prices[instrument] = base_price * (1 + variation)

    # =============================================================================
    # MOCK IMPLEMENTATIONS
    # =============================================================================

    async def _place_order_impl(self,
                               broker_token: str,
                               side: str,
                               quantity: int,
                               order_type: str,
                               price: float | None = None,
                               **kwargs) -> dict[str, Any]:
        """Mock order placement"""

        # Simulate some processing time
        await asyncio.sleep(random.uniform(0.1, 0.5))

        # Generate mock order ID
        order_id = f"MOCK_{self._order_counter}"
        self._order_counter += 1

        # Mock order status (90% success rate)
        if random.random() < 0.9:
            status = "OPEN" if order_type != "MARKET" else "FILLED"
        else:
            status = "REJECTED"

        # Store order for status tracking
        self._orders[order_id] = {
            "order_id": order_id,
            "broker_token": broker_token,
            "side": side,
            "quantity": quantity,
            "order_type": order_type,
            "price": price,
            "status": status,
            "created_at": datetime.now().isoformat(),
            "filled_quantity": quantity if status == "FILLED" else 0
        }

        logger.debug(f"Mock order placed: {order_id} - {status}")

        return {
            "order_id": order_id,
            "status": status,
            "message": "Mock order placed successfully" if status != "REJECTED" else "Mock rejection"
        }

    async def _get_quote_impl(self, broker_token: str) -> dict[str, Any]:
        """Mock quote generation"""

        # Simulate network latency
        await asyncio.sleep(random.uniform(0.05, 0.15))

        # Try to find matching instrument in mock prices
        # In real implementation, broker_token would be used to identify instrument
        matching_instrument = None
        for instrument_key, price in self._mock_prices.items():
            # Simple heuristic: if token matches part of instrument key
            if broker_token in instrument_key or broker_token.isdigit():
                matching_instrument = instrument_key
                break

        if matching_instrument:
            base_price = self._mock_prices[matching_instrument]

            # Add some random price movement
            price_change = random.uniform(-0.005, 0.005)  # ±0.5%
            current_price = base_price * (1 + price_change)
            self._mock_prices[matching_instrument] = current_price

        else:
            # Generate random price for unknown instrument
            current_price = random.uniform(100, 5000)

        # Generate realistic bid-ask spread
        spread_pct = random.uniform(0.001, 0.003)  # 0.1% to 0.3%
        bid = current_price * (1 - spread_pct/2)
        ask = current_price * (1 + spread_pct/2)

        return {
            "ltp": round(current_price, 2),
            "bid": round(bid, 2),
            "ask": round(ask, 2),
            "volume": random.randint(1000, 100000),
            "timestamp": datetime.now().isoformat()
        }

    async def _get_order_status_impl(self, broker_order_id: str) -> dict[str, Any]:
        """Mock order status check"""

        await asyncio.sleep(random.uniform(0.05, 0.1))

        if broker_order_id not in self._orders:
            raise Exception(f"Order not found: {broker_order_id}")

        order = self._orders[broker_order_id]

        # Simulate order progression
        current_status = order["status"]
        if current_status == "OPEN" and random.random() < 0.3:  # 30% chance to fill
            order["status"] = "FILLED"
            order["filled_quantity"] = order["quantity"]

        return {
            "order_id": broker_order_id,
            "status": order["status"],
            "quantity": order["quantity"],
            "filled_quantity": order.get("filled_quantity", 0),
            "price": order["price"],
            "side": order["side"],
            "order_type": order["order_type"],
            "created_at": order["created_at"]
        }

    async def _cancel_order_impl(self, broker_order_id: str) -> bool:
        """Mock order cancellation"""

        await asyncio.sleep(random.uniform(0.05, 0.1))

        if broker_order_id not in self._orders:
            return False

        order = self._orders[broker_order_id]
        if order["status"] in ["OPEN", "PENDING"]:
            order["status"] = "CANCELLED"
            return True

        return False

    # =============================================================================
    # CONNECTION MANAGEMENT
    # =============================================================================

    async def _connect_impl(self):
        """Mock connection establishment"""
        await asyncio.sleep(0.1)  # Simulate connection time
        logger.info("Mock broker connection established")

    async def _disconnect_impl(self):
        """Mock disconnection"""
        await asyncio.sleep(0.05)
        logger.info("Mock broker disconnected")

    async def _health_check_impl(self) -> dict[str, Any]:
        """Mock health check"""
        await asyncio.sleep(0.05)

        # Simulate occasional health issues
        healthy = random.random() > 0.05  # 95% uptime

        if healthy:
            return {
                "api_status": "connected",
                "orders_today": len(self._orders),
                "mock_price_count": len(self._mock_prices),
                "last_check": datetime.now().isoformat()
            }
        raise Exception("Mock broker temporary unavailability")

    # =============================================================================
    # MOCK-SPECIFIC FEATURES
    # =============================================================================

    def set_mock_price(self, instrument_key: str, price: float):
        """Set mock price for testing"""
        self._mock_prices[instrument_key] = price
        logger.debug(f"Mock price set: {instrument_key} = {price}")

    def get_mock_orders(self) -> dict[str, dict[str, Any]]:
        """Get all mock orders for testing"""
        return self._orders.copy()

    def simulate_order_fill(self, order_id: str) -> bool:
        """Manually simulate order fill for testing"""
        if order_id in self._orders and self._orders[order_id]["status"] == "OPEN":
            self._orders[order_id]["status"] = "FILLED"
            self._orders[order_id]["filled_quantity"] = self._orders[order_id]["quantity"]
            logger.debug(f"Mock order filled: {order_id}")
            return True
        return False

    def simulate_market_movement(self, instrument_key: str, movement_pct: float):
        """Simulate market movement for testing"""
        if instrument_key in self._mock_prices:
            old_price = self._mock_prices[instrument_key]
            new_price = old_price * (1 + movement_pct)
            self._mock_prices[instrument_key] = new_price
            logger.debug(f"Mock price movement: {instrument_key} {old_price:.2f} -> {new_price:.2f}")

    def reset_mock_data(self):
        """Reset all mock data for clean testing"""
        self._orders.clear()
        self._positions.clear()
        self._order_counter = 1000
        self._initialize_mock_data()
        logger.info("Mock broker data reset")
