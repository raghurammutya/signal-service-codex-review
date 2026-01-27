#!/usr/bin/env python3
"""
Trailing Stop Service - Phase 1 Migration

TRAILING_001: Trailing Stop Service Migration
- Trailing stops created with instrument_key reference
- Price monitoring uses registry-enriched metadata
- Stop execution derives broker tokens internally
- Order state tracking by instrument_key with metadata
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from app.sdk import (
    DataClient,
    InstrumentClient,
    OrderClient,
    OrderSide,
    OrderType,
    create_data_client,
    create_instrument_client,
    create_order_client,
)

logger = logging.getLogger(__name__)

class TrailingStopStatus(Enum):
    ACTIVE = "active"
    TRIGGERED = "triggered"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    ERROR = "error"

class TrailingStopType(Enum):
    PERCENTAGE = "percentage"    # Trail by percentage
    ABSOLUTE = "absolute"       # Trail by absolute amount
    ATR = "atr"                # Trail by ATR multiple
    VOLATILITY = "volatility"   # Trail by volatility measure

@dataclass
class TrailingStopConfig:
    """Trailing stop configuration with instrument_key"""
    stop_id: str
    instrument_key: str          # Primary identifier - NO tokens
    side: str                   # SELL (for long position) or BUY (for short position)
    original_quantity: int
    current_quantity: int
    trail_type: TrailingStopType
    trail_value: float          # Percentage, absolute amount, or multiplier
    initial_stop_price: float   # Initial stop price
    current_stop_price: float   # Current trailing stop price
    peak_price: float           # Best price seen since creation
    created_at: datetime = field(default_factory=datetime.now)
    last_updated: datetime = field(default_factory=datetime.now)
    expires_at: datetime | None = None

@dataclass
class TrailingStopExecution:
    """Execution record with enriched metadata"""
    execution_id: str
    stop_id: str
    instrument_key: str
    symbol: str                 # Enriched from registry
    exchange: str              # Enriched from registry
    sector: str                # Enriched from registry
    quantity_executed: int
    execution_price: float
    trigger_price: float
    execution_timestamp: datetime
    broker_order_id: str
    realized_pnl: float | None = None
    # Internal tracking - not exposed
    _broker_token: str | None = None

class TrailingStopService:
    """
    Trailing Stop Service - Phase 1 Migration

    TRAILING_001: All trailing stop operations use instrument_key as primary
    identifier with automatic metadata enrichment and internal token resolution.
    """

    def __init__(self,
                 instrument_client: InstrumentClient | None = None,
                 order_client: OrderClient | None = None,
                 data_client: DataClient | None = None):
        """
        Initialize trailing stop service with Phase 1 SDK integration

        Args:
            instrument_client: Client for metadata and token resolution
            order_client: Client for order execution
            data_client: Client for price monitoring
        """
        self.instrument_client = instrument_client or create_instrument_client()
        self.order_client = order_client or create_order_client()
        self.data_client = data_client or create_data_client()

        # Trailing stop state
        self._active_stops: dict[str, TrailingStopConfig] = {}
        self._stop_executions: dict[str, list[TrailingStopExecution]] = {}
        self._stop_status: dict[str, TrailingStopStatus] = {}

        # Price monitoring
        self._price_subscriptions: dict[str, dict[str, Any]] = {}
        self._monitoring_task: asyncio.Task | None = None

        # Configuration
        self.price_check_interval = 5.0  # seconds
        self.max_price_deviation = 0.1   # 10% max price movement filter

    # =============================================================================
    # TRAILING STOP CREATION (instrument_key-based)
    # =============================================================================

    async def create_trailing_stop(self,
                                 instrument_key: str,
                                 side: str,
                                 quantity: int,
                                 trail_type: TrailingStopType,
                                 trail_value: float,
                                 initial_stop_price: float | None = None,
                                 expires_in_hours: int | None = 24) -> dict[str, Any]:
        """
        Create trailing stop using instrument_key

        Args:
            instrument_key: Primary identifier (e.g., "AAPL_NASDAQ_EQUITY")
            side: "SELL" for long position, "BUY" for short position
            quantity: Number of shares/contracts
            trail_type: Type of trailing (percentage, absolute, ATR, volatility)
            trail_value: Trail amount/percentage/multiplier
            initial_stop_price: Initial stop price (current market if None)
            expires_in_hours: Expiration time in hours

        Returns:
            Dict: Trailing stop creation result with metadata
        """
        # Get instrument metadata for enrichment
        try:
            metadata = await self.instrument_client.get_instrument_metadata(instrument_key)
        except Exception as e:
            logger.error(f"Failed to get metadata for {instrument_key}: {e}")
            raise ValueError(f"Invalid instrument: {instrument_key}")

        # Get current market price if initial stop price not provided
        if initial_stop_price is None:
            try:
                quote = await self.data_client.get_real_time_quote(instrument_key)
                current_price = quote.data.get('ltp', 0)

                if side.upper() == "SELL":
                    # For long position, stop below current price
                    if trail_type == TrailingStopType.PERCENTAGE:
                        initial_stop_price = current_price * (1 - trail_value / 100)
                    else:
                        initial_stop_price = current_price - trail_value
                else:
                    # For short position, stop above current price
                    if trail_type == TrailingStopType.PERCENTAGE:
                        initial_stop_price = current_price * (1 + trail_value / 100)
                    else:
                        initial_stop_price = current_price + trail_value

            except Exception as e:
                logger.error(f"Failed to get current price for {instrument_key}: {e}")
                raise RuntimeError(f"Unable to determine initial stop price: {e}")

        # Generate stop ID
        stop_id = f"trail_{instrument_key}_{int(datetime.now().timestamp())}"

        # Set expiration
        expires_at = datetime.now() + timedelta(hours=expires_in_hours) if expires_in_hours else None

        # Create trailing stop configuration
        stop_config = TrailingStopConfig(
            stop_id=stop_id,
            instrument_key=instrument_key,
            side=side.upper(),
            original_quantity=quantity,
            current_quantity=quantity,
            trail_type=trail_type,
            trail_value=trail_value,
            initial_stop_price=initial_stop_price,
            current_stop_price=initial_stop_price,
            peak_price=initial_stop_price,  # Will be updated on first price check
            expires_at=expires_at
        )

        # Store configuration
        self._active_stops[stop_id] = stop_config
        self._stop_status[stop_id] = TrailingStopStatus.ACTIVE
        self._stop_executions[stop_id] = []

        # Start price monitoring for this instrument
        await self._add_price_subscription(instrument_key)

        logger.info(f"Trailing stop created: {stop_id} for {instrument_key} ({metadata.symbol}) - {trail_type.value} {trail_value}")

        return {
            "stop_id": stop_id,
            "instrument_key": instrument_key,
            "instrument_metadata": {
                "symbol": metadata.symbol,
                "exchange": metadata.exchange,
                "sector": metadata.sector,
                "instrument_type": metadata.instrument_type
            },
            "configuration": {
                "side": side.upper(),
                "quantity": quantity,
                "trail_type": trail_type.value,
                "trail_value": trail_value,
                "initial_stop_price": initial_stop_price,
                "expires_at": expires_at.isoformat() if expires_at else None
            },
            "status": TrailingStopStatus.ACTIVE.value,
            "created_at": datetime.now().isoformat()
        }

    # =============================================================================
    # PRICE MONITORING AND STOP ADJUSTMENT
    # =============================================================================

    async def _add_price_subscription(self, instrument_key: str):
        """Add price subscription for instrument monitoring"""
        if instrument_key not in self._price_subscriptions:
            self._price_subscriptions[instrument_key] = {
                "last_price": 0.0,
                "last_update": datetime.now(),
                "stop_ids": []
            }

        # Start monitoring task if not already running
        if self._monitoring_task is None or self._monitoring_task.done():
            self._monitoring_task = asyncio.create_task(self._price_monitoring_loop())

    async def _price_monitoring_loop(self):
        """Main price monitoring loop for all subscribed instruments"""
        logger.info("Starting trailing stop price monitoring loop")

        try:
            while True:
                if not self._price_subscriptions:
                    await asyncio.sleep(self.price_check_interval)
                    continue

                # Get prices for all subscribed instruments
                tasks = []
                for instrument_key in list(self._price_subscriptions.keys()):
                    tasks.append(self._update_instrument_price(instrument_key))

                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)

                # Clean up inactive subscriptions
                await self._cleanup_subscriptions()

                await asyncio.sleep(self.price_check_interval)

        except asyncio.CancelledError:
            logger.info("Price monitoring loop cancelled")
            raise
        except Exception as e:
            logger.error(f"Error in price monitoring loop: {e}")
            # Restart after delay
            await asyncio.sleep(5)
            self._monitoring_task = asyncio.create_task(self._price_monitoring_loop())

    async def _update_instrument_price(self, instrument_key: str):
        """Update price for specific instrument and check trailing stops"""
        try:
            # Get current quote
            quote = await self.data_client.get_real_time_quote(instrument_key)
            current_price = quote.data.get('ltp', 0)

            if current_price <= 0:
                logger.warning(f"Invalid price for {instrument_key}: {current_price}")
                return

            # Update subscription
            subscription = self._price_subscriptions[instrument_key]
            last_price = subscription["last_price"]

            # Validate price movement (filter out obvious errors)
            if last_price > 0:
                price_change = abs(current_price - last_price) / last_price
                if price_change > self.max_price_deviation:
                    logger.warning(f"Suspicious price movement for {instrument_key}: {price_change:.2%}")
                    return

            subscription["last_price"] = current_price
            subscription["last_update"] = datetime.now()

            # Check all trailing stops for this instrument
            await self._check_trailing_stops(instrument_key, current_price, quote)

        except Exception as e:
            logger.error(f"Failed to update price for {instrument_key}: {e}")

    async def _check_trailing_stops(self, instrument_key: str, current_price: float, quote_data):
        """Check and update trailing stops for instrument"""
        stops_to_check = [
            (stop_id, config) for stop_id, config in self._active_stops.items()
            if config.instrument_key == instrument_key and
            self._stop_status.get(stop_id) == TrailingStopStatus.ACTIVE
        ]

        for stop_id, config in stops_to_check:
            try:
                await self._update_trailing_stop(stop_id, config, current_price, quote_data)
            except Exception as e:
                logger.error(f"Failed to update trailing stop {stop_id}: {e}")
                self._stop_status[stop_id] = TrailingStopStatus.ERROR

    async def _update_trailing_stop(self,
                                   stop_id: str,
                                   config: TrailingStopConfig,
                                   current_price: float,
                                   quote_data):
        """Update individual trailing stop based on current price"""
        # Check expiration
        if config.expires_at and datetime.now() > config.expires_at:
            self._stop_status[stop_id] = TrailingStopStatus.EXPIRED
            logger.info(f"Trailing stop expired: {stop_id}")
            return

        # Update peak price and adjust stop
        price_improved = False

        if config.side == "SELL":  # Long position
            if current_price > config.peak_price:
                config.peak_price = current_price
                price_improved = True

            # Check if stop should trigger
            if current_price <= config.current_stop_price:
                await self._trigger_stop(stop_id, config, current_price, quote_data)
                return

        else:  # Short position (side == "BUY")
            if current_price < config.peak_price:
                config.peak_price = current_price
                price_improved = True

            # Check if stop should trigger
            if current_price >= config.current_stop_price:
                await self._trigger_stop(stop_id, config, current_price, quote_data)
                return

        # Adjust trailing stop if price improved
        if price_improved:
            new_stop_price = self._calculate_new_stop_price(config)

            if config.side == "SELL":
                # Only move stop up for long position
                if new_stop_price > config.current_stop_price:
                    old_stop = config.current_stop_price
                    config.current_stop_price = new_stop_price
                    config.last_updated = datetime.now()

                    logger.debug(f"Stop adjusted up: {stop_id} {old_stop:.2f} -> {new_stop_price:.2f}")
            else:
                # Only move stop down for short position
                if new_stop_price < config.current_stop_price:
                    old_stop = config.current_stop_price
                    config.current_stop_price = new_stop_price
                    config.last_updated = datetime.now()

                    logger.debug(f"Stop adjusted down: {stop_id} {old_stop:.2f} -> {new_stop_price:.2f}")

    def _calculate_new_stop_price(self, config: TrailingStopConfig) -> float:
        """Calculate new stop price based on trail configuration"""
        peak_price = config.peak_price

        if config.trail_type == TrailingStopType.PERCENTAGE:
            if config.side == "SELL":  # Long position
                return peak_price * (1 - config.trail_value / 100)
            # Short position
            return peak_price * (1 + config.trail_value / 100)

        if config.trail_type == TrailingStopType.ABSOLUTE:
            if config.side == "SELL":  # Long position
                return peak_price - config.trail_value
            # Short position
            return peak_price + config.trail_value

        if config.trail_type == TrailingStopType.ATR:
            # For ATR, would need to calculate ATR from historical data
            # Simplified implementation using fixed multiplier
            atr_estimate = peak_price * 0.02  # 2% as ATR estimate
            if config.side == "SELL":
                return peak_price - (atr_estimate * config.trail_value)
            return peak_price + (atr_estimate * config.trail_value)

        # VOLATILITY
        # For volatility, would calculate based on recent price volatility
        vol_estimate = peak_price * 0.015  # 1.5% as volatility estimate
        if config.side == "SELL":
            return peak_price - (vol_estimate * config.trail_value)
        return peak_price + (vol_estimate * config.trail_value)

    # =============================================================================
    # STOP EXECUTION (token resolution via SDK)
    # =============================================================================

    async def _trigger_stop(self,
                           stop_id: str,
                           config: TrailingStopConfig,
                           trigger_price: float,
                           quote_data):
        """Trigger trailing stop execution"""
        logger.info(f"Triggering trailing stop: {stop_id} at price {trigger_price:.2f}")

        # Get instrument metadata for execution record
        try:
            metadata = await self.instrument_client.get_instrument_metadata(config.instrument_key)
        except Exception as e:
            logger.error(f"Failed to get metadata for execution: {e}")
            metadata = type('obj', (object,), {
                'symbol': 'Unknown', 'exchange': 'Unknown', 'sector': 'Unknown'
            })()

        # Place market order using Phase 1 SDK (internal token resolution)
        try:
            order = await self.order_client.create_order(
                instrument_key=config.instrument_key,
                side=OrderSide.SELL if config.side == "SELL" else OrderSide.BUY,
                quantity=config.current_quantity,
                order_type=OrderType.MARKET
            )

            # Create execution record
            execution = TrailingStopExecution(
                execution_id=f"exec_{stop_id}_{int(datetime.now().timestamp())}",
                stop_id=stop_id,
                instrument_key=config.instrument_key,
                symbol=metadata.symbol,
                exchange=metadata.exchange,
                sector=metadata.sector or "Unknown",
                quantity_executed=config.current_quantity,
                execution_price=order.price or trigger_price,
                trigger_price=trigger_price,
                execution_timestamp=datetime.now(),
                broker_order_id=order.order_id
            )

            # Store execution
            self._stop_executions[stop_id].append(execution)
            self._stop_status[stop_id] = TrailingStopStatus.TRIGGERED

            # Remove from active stops
            config.current_quantity = 0

            logger.info(f"Trailing stop executed: {stop_id} - {metadata.symbol} {config.current_quantity} @ {execution.execution_price:.2f}")

        except Exception as e:
            logger.error(f"Failed to execute trailing stop {stop_id}: {e}")
            self._stop_status[stop_id] = TrailingStopStatus.ERROR

    # =============================================================================
    # STOP MANAGEMENT
    # =============================================================================

    async def cancel_trailing_stop(self, stop_id: str) -> dict[str, Any]:
        """Cancel active trailing stop"""
        if stop_id not in self._active_stops:
            raise ValueError(f"Trailing stop not found: {stop_id}")

        config = self._active_stops[stop_id]
        current_status = self._stop_status.get(stop_id, TrailingStopStatus.ACTIVE)

        if current_status not in [TrailingStopStatus.ACTIVE]:
            raise ValueError(f"Cannot cancel stop in {current_status.value} status")

        # Update status
        self._stop_status[stop_id] = TrailingStopStatus.CANCELLED

        # Get metadata for response
        try:
            metadata = await self.instrument_client.get_instrument_metadata(config.instrument_key)
        except:
            metadata = type('obj', (object,), {'symbol': 'Unknown', 'exchange': 'Unknown'})()

        logger.info(f"Trailing stop cancelled: {stop_id}")

        return {
            "stop_id": stop_id,
            "instrument_key": config.instrument_key,
            "symbol": metadata.symbol,
            "exchange": metadata.exchange,
            "status": TrailingStopStatus.CANCELLED.value,
            "cancelled_at": datetime.now().isoformat()
        }

    async def get_trailing_stop_status(self, stop_id: str) -> dict[str, Any]:
        """Get detailed trailing stop status"""
        if stop_id not in self._active_stops:
            raise ValueError(f"Trailing stop not found: {stop_id}")

        config = self._active_stops[stop_id]
        status = self._stop_status.get(stop_id, TrailingStopStatus.ACTIVE)
        executions = self._stop_executions.get(stop_id, [])

        # Get enriched instrument metadata
        try:
            metadata = await self.instrument_client.get_instrument_metadata(config.instrument_key)
        except:
            metadata = type('obj', (object,), {
                'symbol': 'Unknown', 'exchange': 'Unknown', 'sector': 'Unknown'
            })()

        return {
            "stop_id": stop_id,
            "status": status.value,
            "instrument_key": config.instrument_key,
            "instrument_metadata": {
                "symbol": metadata.symbol,
                "exchange": metadata.exchange,
                "sector": metadata.sector
            },
            "configuration": {
                "side": config.side,
                "original_quantity": config.original_quantity,
                "current_quantity": config.current_quantity,
                "trail_type": config.trail_type.value,
                "trail_value": config.trail_value,
                "initial_stop_price": config.initial_stop_price,
                "current_stop_price": config.current_stop_price,
                "peak_price": config.peak_price
            },
            "timing": {
                "created_at": config.created_at.isoformat(),
                "last_updated": config.last_updated.isoformat(),
                "expires_at": config.expires_at.isoformat() if config.expires_at else None
            },
            "executions": [
                {
                    "execution_id": exec.execution_id,
                    "quantity_executed": exec.quantity_executed,
                    "execution_price": exec.execution_price,
                    "trigger_price": exec.trigger_price,
                    "timestamp": exec.execution_timestamp.isoformat(),
                    "broker_order_id": exec.broker_order_id
                }
                for exec in executions
            ]
        }

    async def get_active_trailing_stops(self, instrument_key: str | None = None) -> dict[str, Any]:
        """Get all active trailing stops, optionally filtered by instrument"""
        active_stops = []

        for stop_id, config in self._active_stops.items():
            status = self._stop_status.get(stop_id, TrailingStopStatus.ACTIVE)

            # Filter by instrument if specified
            if instrument_key and config.instrument_key != instrument_key:
                continue

            # Get metadata
            try:
                metadata = await self.instrument_client.get_instrument_metadata(config.instrument_key)
            except:
                metadata = type('obj', (object,), {'symbol': 'Unknown', 'exchange': 'Unknown'})()

            active_stops.append({
                "stop_id": stop_id,
                "status": status.value,
                "instrument_key": config.instrument_key,
                "symbol": metadata.symbol,
                "exchange": metadata.exchange,
                "side": config.side,
                "current_quantity": config.current_quantity,
                "current_stop_price": config.current_stop_price,
                "trail_type": config.trail_type.value,
                "trail_value": config.trail_value,
                "created_at": config.created_at.isoformat()
            })

        return {
            "active_stops": active_stops,
            "total_stops": len(active_stops),
            "filter": {"instrument_key": instrument_key} if instrument_key else None,
            "timestamp": datetime.now().isoformat()
        }

    # =============================================================================
    # CLEANUP
    # =============================================================================

    async def _cleanup_subscriptions(self):
        """Clean up inactive price subscriptions"""
        instruments_to_remove = []

        for instrument_key, subscription in self._price_subscriptions.items():
            # Check if any active stops exist for this instrument
            has_active_stops = any(
                config.instrument_key == instrument_key and
                self._stop_status.get(stop_id) == TrailingStopStatus.ACTIVE
                for stop_id, config in self._active_stops.items()
            )

            if not has_active_stops:
                instruments_to_remove.append(instrument_key)

        for instrument_key in instruments_to_remove:
            del self._price_subscriptions[instrument_key]
            logger.debug(f"Removed price subscription for {instrument_key}")

    async def shutdown(self):
        """Shutdown trailing stop service"""
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass

        logger.info("Trailing stop service shutdown complete")
