#!/usr/bin/env python3
"""
Alert Service - Phase 1 Migration

TRAILING_002: Alert Service Integration
- Price alerts reference instrument_key
- Alert notifications include instrument symbols from registry
- Alert history keyed by instrument metadata
- User preferences stored by instrument_key
- Alert rules support metadata-based conditions
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from app.sdk import InstrumentClient, create_instrument_client

logger = logging.getLogger(__name__)

class AlertType(Enum):
    PRICE_ABOVE = "price_above"
    PRICE_BELOW = "price_below"
    PRICE_CHANGE = "price_change"
    VOLUME_SURGE = "volume_surge"
    VOLATILITY_SPIKE = "volatility_spike"
    SECTOR_MOVEMENT = "sector_movement"
    TRAILING_STOP_TRIGGERED = "trailing_stop_triggered"

class AlertStatus(Enum):
    ACTIVE = "active"
    TRIGGERED = "triggered"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    ERROR = "error"

class AlertPriority(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class NotificationChannel(Enum):
    EMAIL = "email"
    SMS = "sms"
    PUSH = "push"
    WEBHOOK = "webhook"
    IN_APP = "in_app"

@dataclass
class AlertCondition:
    """Alert condition with metadata-based rules"""
    condition_type: AlertType
    value: float                              # Threshold value
    comparison: str                          # ">=", "<=", ">", "<", "==", "%change"
    timeframe_minutes: int | None = None  # Timeframe for condition evaluation
    # Metadata-based filters
    applies_to_sectors: list[str] | None = None
    applies_to_exchanges: list[str] | None = None
    market_cap_min: float | None = None
    market_cap_max: float | None = None

@dataclass
class PriceAlert:
    """Price alert with instrument_key as primary identifier"""
    alert_id: str
    user_id: str
    instrument_key: str                    # Primary identifier - NO tokens
    symbol: str                           # Enriched from registry
    exchange: str                         # Enriched from registry
    sector: str                           # Enriched from registry
    condition: AlertCondition
    priority: AlertPriority
    notification_channels: list[NotificationChannel]
    message_template: str
    created_at: datetime = field(default_factory=datetime.now)
    expires_at: datetime | None = None
    status: AlertStatus = AlertStatus.ACTIVE
    triggered_at: datetime | None = None
    triggered_value: float | None = None
    trigger_count: int = 0
    # Internal tracking - not exposed
    _last_check: datetime | None = None
    _check_failures: int = 0

@dataclass
class AlertNotification:
    """Alert notification with enriched metadata"""
    notification_id: str
    alert_id: str
    user_id: str
    instrument_key: str
    symbol: str                           # Enriched from registry
    exchange: str                         # Enriched from registry
    sector: str                           # Enriched from registry
    alert_type: AlertType
    trigger_value: float
    current_price: float
    message: str
    channels_sent: list[NotificationChannel]
    sent_at: datetime = field(default_factory=datetime.now)
    delivery_status: dict[str, str] = field(default_factory=dict)

@dataclass
class UserAlertPreferences:
    """User alert preferences by instrument_key"""
    user_id: str
    # Global preferences
    default_channels: list[NotificationChannel] = field(default_factory=lambda: [NotificationChannel.IN_APP])
    max_alerts_per_hour: int = 10
    quiet_hours_start: str | None = None  # "22:00"
    quiet_hours_end: str | None = None    # "08:00"
    # Instrument-specific preferences
    instrument_preferences: dict[str, dict[str, Any]] = field(default_factory=dict)
    # Metadata-based preferences
    sector_preferences: dict[str, dict[str, Any]] = field(default_factory=dict)
    exchange_preferences: dict[str, dict[str, Any]] = field(default_factory=dict)

class AlertService:
    """
    Alert Service - Phase 1 Migration

    TRAILING_002: All alert operations use instrument_key as primary identifier
    with automatic metadata enrichment and metadata-based alert conditions.
    """

    def __init__(self, instrument_client: InstrumentClient | None = None):
        """
        Initialize alert service with Phase 1 SDK integration

        Args:
            instrument_client: Client for metadata enrichment
        """
        self.instrument_client = instrument_client or create_instrument_client()

        # Alert management
        self._active_alerts: dict[str, PriceAlert] = {}
        self._alert_history: dict[str, list[PriceAlert]] = {}
        self._user_preferences: dict[str, UserAlertPreferences] = {}
        self._notifications: dict[str, AlertNotification] = {}

        # Monitoring and processing
        self._price_subscriptions: dict[str, dict[str, Any]] = {}
        self._monitoring_task: asyncio.Task | None = None

        # Configuration
        self.check_interval = 10.0  # seconds
        self.max_check_failures = 3
        self.notification_retry_attempts = 3

    # =============================================================================
    # ALERT CREATION AND MANAGEMENT (instrument_key-based)
    # =============================================================================

    async def create_price_alert(self,
                               user_id: str,
                               instrument_key: str,
                               condition: AlertCondition,
                               priority: AlertPriority = AlertPriority.MEDIUM,
                               channels: list[NotificationChannel] | None = None,
                               custom_message: str | None = None,
                               expires_in_hours: int | None = 24) -> dict[str, Any]:
        """
        Create price alert using instrument_key

        Args:
            user_id: User identifier
            instrument_key: Primary identifier (e.g., "AAPL_NASDAQ_EQUITY")
            condition: Alert condition with threshold
            priority: Alert priority level
            channels: Notification channels (uses user preferences if None)
            custom_message: Custom alert message template
            expires_in_hours: Alert expiration time

        Returns:
            Dict: Alert creation result with metadata
        """
        # Get instrument metadata for enrichment
        try:
            metadata = await self.instrument_client.get_instrument_metadata(instrument_key)
        except Exception as e:
            logger.error(f"Failed to get metadata for {instrument_key}: {e}")
            raise ValueError(f"Invalid instrument: {instrument_key}")

        # Check metadata-based filters
        if condition.applies_to_sectors and metadata.sector not in condition.applies_to_sectors:
            raise ValueError(f"Alert condition does not apply to sector: {metadata.sector}")

        if condition.applies_to_exchanges and metadata.exchange not in condition.applies_to_exchanges:
            raise ValueError(f"Alert condition does not apply to exchange: {metadata.exchange}")

        # Get user preferences for notification channels
        user_prefs = self._user_preferences.get(user_id, UserAlertPreferences(user_id=user_id))
        if channels is None:
            # Use instrument-specific preferences if available
            instrument_prefs = user_prefs.instrument_preferences.get(instrument_key, {})
            channels = instrument_prefs.get('channels', user_prefs.default_channels)

        # Generate alert ID and expiration
        alert_id = f"alert_{instrument_key}_{user_id}_{uuid.uuid4().hex[:8]}"
        expires_at = datetime.now() + timedelta(hours=expires_in_hours) if expires_in_hours else None

        # Create default message template if not provided
        if custom_message is None:
            if condition.condition_type == AlertType.PRICE_ABOVE:
                custom_message = f"{metadata.symbol} price above {condition.value} (Current: {{current_price}})"
            elif condition.condition_type == AlertType.PRICE_BELOW:
                custom_message = f"{metadata.symbol} price below {condition.value} (Current: {{current_price}})"
            else:
                custom_message = f"{metadata.symbol} {condition.condition_type.value} alert triggered"

        # Create alert
        alert = PriceAlert(
            alert_id=alert_id,
            user_id=user_id,
            instrument_key=instrument_key,
            symbol=metadata.symbol,
            exchange=metadata.exchange,
            sector=metadata.sector or "Unknown",
            condition=condition,
            priority=priority,
            notification_channels=channels,
            message_template=custom_message,
            expires_at=expires_at
        )

        # Store alert
        self._active_alerts[alert_id] = alert

        # Initialize user alert history if needed
        if user_id not in self._alert_history:
            self._alert_history[user_id] = []

        # Start price monitoring for this instrument
        await self._add_price_monitoring(instrument_key)

        logger.info(f"Alert created: {alert_id} for {instrument_key} ({metadata.symbol}) - {condition.condition_type.value} {condition.value}")

        return {
            "alert_id": alert_id,
            "instrument_key": instrument_key,
            "instrument_metadata": {
                "symbol": metadata.symbol,
                "exchange": metadata.exchange,
                "sector": metadata.sector,
                "instrument_type": metadata.instrument_type
            },
            "condition": {
                "type": condition.condition_type.value,
                "value": condition.value,
                "comparison": condition.comparison
            },
            "priority": priority.value,
            "notification_channels": [ch.value for ch in channels],
            "expires_at": expires_at.isoformat() if expires_at else None,
            "status": AlertStatus.ACTIVE.value,
            "created_at": datetime.now().isoformat()
        }

    async def create_sector_alert(self,
                                user_id: str,
                                sector: str,
                                condition: AlertCondition,
                                max_instruments: int = 5) -> dict[str, Any]:
        """
        Create alert for all instruments in a sector

        Args:
            user_id: User identifier
            sector: Sector name (e.g., "Technology")
            condition: Alert condition
            max_instruments: Maximum instruments to monitor

        Returns:
            Dict: Sector alert creation result
        """
        # This would typically query the registry for instruments in the sector
        # For now, simulate with a few example instruments
        sector_instruments = [
            "AAPL_NASDAQ_EQUITY",
            "GOOGL_NASDAQ_EQUITY",
            "MSFT_NASDAQ_EQUITY"
        ][:max_instruments]

        created_alerts = []
        for instrument_key in sector_instruments:
            try:
                alert_result = await self.create_price_alert(
                    user_id=user_id,
                    instrument_key=instrument_key,
                    condition=condition,
                    priority=AlertPriority.LOW  # Sector alerts typically lower priority
                )
                created_alerts.append(alert_result)
            except Exception as e:
                logger.error(f"Failed to create sector alert for {instrument_key}: {e}")

        return {
            "sector": sector,
            "alerts_created": len(created_alerts),
            "alert_ids": [alert["alert_id"] for alert in created_alerts],
            "created_at": datetime.now().isoformat()
        }

    # =============================================================================
    # PRICE MONITORING AND ALERT CHECKING
    # =============================================================================

    async def _add_price_monitoring(self, instrument_key: str):
        """Add price monitoring for instrument alerts"""
        if instrument_key not in self._price_subscriptions:
            self._price_subscriptions[instrument_key] = {
                "last_price": 0.0,
                "last_update": datetime.now(),
                "alert_count": 0
            }

        self._price_subscriptions[instrument_key]["alert_count"] += 1

        # Start monitoring task if not already running
        if self._monitoring_task is None or self._monitoring_task.done():
            self._monitoring_task = asyncio.create_task(self._price_monitoring_loop())

    async def _price_monitoring_loop(self):
        """Main price monitoring loop for all subscribed instruments"""
        logger.info("Starting alert service price monitoring loop")

        try:
            while True:
                if not self._price_subscriptions:
                    await asyncio.sleep(self.check_interval)
                    continue

                # Check prices for all monitored instruments
                tasks = []
                for instrument_key in list(self._price_subscriptions.keys()):
                    tasks.append(self._check_instrument_alerts(instrument_key))

                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)

                # Clean up inactive subscriptions
                await self._cleanup_price_subscriptions()

                await asyncio.sleep(self.check_interval)

        except asyncio.CancelledError:
            logger.info("Alert price monitoring loop cancelled")
            raise
        except Exception as e:
            logger.error(f"Error in alert monitoring loop: {e}")
            # Restart after delay
            await asyncio.sleep(5)
            self._monitoring_task = asyncio.create_task(self._price_monitoring_loop())

    async def _check_instrument_alerts(self, instrument_key: str):
        """Check all alerts for a specific instrument"""
        try:
            # Get current price (simplified - would use real market data)
            import random
            base_price = 150.0  # Mock base price
            current_price = base_price * (1 + random.uniform(-0.05, 0.05))

            # Update subscription
            subscription = self._price_subscriptions[instrument_key]
            subscription["last_price"] = current_price
            subscription["last_update"] = datetime.now()

            # Find alerts for this instrument
            instrument_alerts = [
                alert for alert in self._active_alerts.values()
                if alert.instrument_key == instrument_key and alert.status == AlertStatus.ACTIVE
            ]

            for alert in instrument_alerts:
                try:
                    await self._evaluate_alert(alert, current_price)
                except Exception as e:
                    logger.error(f"Failed to evaluate alert {alert.alert_id}: {e}")
                    alert._check_failures += 1

                    if alert._check_failures >= self.max_check_failures:
                        alert.status = AlertStatus.ERROR
                        logger.error(f"Alert {alert.alert_id} marked as error after {self.max_check_failures} failures")

        except Exception as e:
            logger.error(f"Failed to check alerts for {instrument_key}: {e}")

    async def _evaluate_alert(self, alert: PriceAlert, current_price: float):
        """Evaluate individual alert condition"""
        alert._last_check = datetime.now()

        # Check expiration
        if alert.expires_at and datetime.now() > alert.expires_at:
            alert.status = AlertStatus.EXPIRED
            logger.info(f"Alert expired: {alert.alert_id}")
            return

        condition = alert.condition
        triggered = False

        # Evaluate condition based on type
        if condition.condition_type == AlertType.PRICE_ABOVE:
            triggered = current_price >= condition.value
        elif condition.condition_type == AlertType.PRICE_BELOW:
            triggered = current_price <= condition.value
        elif condition.condition_type == AlertType.PRICE_CHANGE:
            # For price change, would need to track previous price
            # Simplified implementation
            price_change_pct = abs(current_price - 150.0) / 150.0 * 100  # Mock calculation
            triggered = price_change_pct >= condition.value

        if triggered:
            await self._trigger_alert(alert, current_price)

    async def _trigger_alert(self, alert: PriceAlert, trigger_price: float):
        """Trigger alert and send notifications"""
        logger.info(f"Triggering alert: {alert.alert_id} at price {trigger_price:.2f}")

        # Update alert status
        alert.status = AlertStatus.TRIGGERED
        alert.triggered_at = datetime.now()
        alert.triggered_value = trigger_price
        alert.trigger_count += 1

        # Create notification
        notification = AlertNotification(
            notification_id=f"notif_{alert.alert_id}_{int(datetime.now().timestamp())}",
            alert_id=alert.alert_id,
            user_id=alert.user_id,
            instrument_key=alert.instrument_key,
            symbol=alert.symbol,
            exchange=alert.exchange,
            sector=alert.sector,
            alert_type=alert.condition.condition_type,
            trigger_value=trigger_price,
            current_price=trigger_price,
            message=alert.message_template.format(current_price=trigger_price),
            channels_sent=[]
        )

        # Send notification through configured channels
        for channel in alert.notification_channels:
            try:
                await self._send_notification(notification, channel)
                notification.channels_sent.append(channel)
                notification.delivery_status[channel.value] = "sent"
            except Exception as e:
                logger.error(f"Failed to send notification via {channel.value}: {e}")
                notification.delivery_status[channel.value] = f"failed: {str(e)}"

        # Store notification
        self._notifications[notification.notification_id] = notification

        # Add to user history
        self._alert_history[alert.user_id].append(alert)

        # Remove from active alerts (one-time trigger)
        if alert.alert_id in self._active_alerts:
            del self._active_alerts[alert.alert_id]

    async def _send_notification(self, notification: AlertNotification, channel: NotificationChannel):
        """Send notification through specific channel"""
        # Mock implementation - in real system would integrate with actual notification services
        if channel == NotificationChannel.EMAIL:
            logger.info(f"EMAIL: {notification.message} for {notification.symbol}")
        elif channel == NotificationChannel.SMS:
            logger.info(f"SMS: {notification.message} for {notification.symbol}")
        elif channel == NotificationChannel.PUSH:
            logger.info(f"PUSH: {notification.message} for {notification.symbol}")
        elif channel == NotificationChannel.IN_APP:
            logger.info(f"IN_APP: {notification.message} for {notification.symbol}")
        elif channel == NotificationChannel.WEBHOOK:
            # Would make HTTP POST to user's webhook URL
            webhook_payload = {
                "alert_id": notification.alert_id,
                "instrument_key": notification.instrument_key,
                "symbol": notification.symbol,
                "exchange": notification.exchange,
                "sector": notification.sector,
                "trigger_value": notification.trigger_value,
                "message": notification.message,
                "timestamp": notification.sent_at.isoformat()
            }
            logger.info(f"WEBHOOK: {webhook_payload}")

    # =============================================================================
    # ALERT MANAGEMENT AND QUERIES
    # =============================================================================

    async def cancel_alert(self, alert_id: str, user_id: str) -> dict[str, Any]:
        """Cancel active alert"""
        alert = self._active_alerts.get(alert_id)
        if not alert:
            raise ValueError(f"Alert not found: {alert_id}")

        if alert.user_id != user_id:
            raise ValueError("Unauthorized: User cannot cancel this alert")

        alert.status = AlertStatus.CANCELLED

        # Get metadata for response
        try:
            metadata = await self.instrument_client.get_instrument_metadata(alert.instrument_key)
        except:
            metadata = type('obj', (object,), {'symbol': 'Unknown', 'exchange': 'Unknown'})(...)

        # Remove from active alerts
        del self._active_alerts[alert_id]

        logger.info(f"Alert cancelled: {alert_id}")

        return {
            "alert_id": alert_id,
            "instrument_key": alert.instrument_key,
            "symbol": metadata.symbol,
            "exchange": metadata.exchange,
            "status": AlertStatus.CANCELLED.value,
            "cancelled_at": datetime.now().isoformat()
        }

    async def get_user_alerts(self, user_id: str, include_history: bool = True) -> dict[str, Any]:
        """Get all alerts for a user"""
        # Active alerts
        active_alerts = [
            {
                "alert_id": alert.alert_id,
                "instrument_key": alert.instrument_key,
                "symbol": alert.symbol,
                "exchange": alert.exchange,
                "sector": alert.sector,
                "condition": {
                    "type": alert.condition.condition_type.value,
                    "value": alert.condition.value,
                    "comparison": alert.condition.comparison
                },
                "priority": alert.priority.value,
                "status": alert.status.value,
                "created_at": alert.created_at.isoformat(),
                "expires_at": alert.expires_at.isoformat() if alert.expires_at else None
            }
            for alert in self._active_alerts.values()
            if alert.user_id == user_id
        ]

        result = {
            "user_id": user_id,
            "active_alerts": active_alerts,
            "active_count": len(active_alerts)
        }

        # Include history if requested
        if include_history:
            user_history = self._alert_history.get(user_id, [])
            result["alert_history"] = [
                {
                    "alert_id": alert.alert_id,
                    "instrument_key": alert.instrument_key,
                    "symbol": alert.symbol,
                    "status": alert.status.value,
                    "triggered_at": alert.triggered_at.isoformat() if alert.triggered_at else None,
                    "triggered_value": alert.triggered_value
                }
                for alert in user_history[-10:]  # Last 10 alerts
            ]
            result["history_count"] = len(user_history)

        result["timestamp"] = datetime.now().isoformat()
        return result

    async def get_instrument_alerts(self, instrument_key: str) -> dict[str, Any]:
        """Get all active alerts for an instrument"""
        # Get instrument metadata
        try:
            metadata = await self.instrument_client.get_instrument_metadata(instrument_key)
        except:
            metadata = type('obj', (object,), {
                'symbol': 'Unknown', 'exchange': 'Unknown', 'sector': 'Unknown'
            })()

        instrument_alerts = [
            {
                "alert_id": alert.alert_id,
                "user_id": alert.user_id,
                "condition": {
                    "type": alert.condition.condition_type.value,
                    "value": alert.condition.value
                },
                "priority": alert.priority.value,
                "status": alert.status.value,
                "created_at": alert.created_at.isoformat()
            }
            for alert in self._active_alerts.values()
            if alert.instrument_key == instrument_key
        ]

        return {
            "instrument_key": instrument_key,
            "instrument_metadata": {
                "symbol": metadata.symbol,
                "exchange": metadata.exchange,
                "sector": metadata.sector
            },
            "active_alerts": instrument_alerts,
            "alert_count": len(instrument_alerts),
            "timestamp": datetime.now().isoformat()
        }

    # =============================================================================
    # USER PREFERENCES MANAGEMENT
    # =============================================================================

    async def update_user_preferences(self, user_id: str, preferences: dict[str, Any]) -> dict[str, Any]:
        """Update user alert preferences"""
        if user_id not in self._user_preferences:
            self._user_preferences[user_id] = UserAlertPreferences(user_id=user_id)

        user_prefs = self._user_preferences[user_id]

        # Update global preferences
        if "default_channels" in preferences:
            user_prefs.default_channels = [
                NotificationChannel(ch) for ch in preferences["default_channels"]
            ]

        if "max_alerts_per_hour" in preferences:
            user_prefs.max_alerts_per_hour = preferences["max_alerts_per_hour"]

        if "quiet_hours" in preferences:
            user_prefs.quiet_hours_start = preferences["quiet_hours"].get("start")
            user_prefs.quiet_hours_end = preferences["quiet_hours"].get("end")

        # Update instrument-specific preferences
        if "instrument_preferences" in preferences:
            user_prefs.instrument_preferences.update(preferences["instrument_preferences"])

        # Update metadata-based preferences
        if "sector_preferences" in preferences:
            user_prefs.sector_preferences.update(preferences["sector_preferences"])

        if "exchange_preferences" in preferences:
            user_prefs.exchange_preferences.update(preferences["exchange_preferences"])

        return {
            "user_id": user_id,
            "status": "updated",
            "preferences": {
                "default_channels": [ch.value for ch in user_prefs.default_channels],
                "max_alerts_per_hour": user_prefs.max_alerts_per_hour,
                "quiet_hours": {
                    "start": user_prefs.quiet_hours_start,
                    "end": user_prefs.quiet_hours_end
                },
                "instrument_count": len(user_prefs.instrument_preferences),
                "sector_count": len(user_prefs.sector_preferences)
            },
            "updated_at": datetime.now().isoformat()
        }

    # =============================================================================
    # INTEGRATION WITH TRAILING STOP SERVICE
    # =============================================================================

    async def create_trailing_stop_alert(self,
                                       user_id: str,
                                       trailing_stop_id: str,
                                       instrument_key: str) -> dict[str, Any]:
        """Create alert for trailing stop events"""
        # Get instrument metadata
        metadata = await self.instrument_client.get_instrument_metadata(instrument_key)

        # Create special trailing stop alert condition
        condition = AlertCondition(
            condition_type=AlertType.TRAILING_STOP_TRIGGERED,
            value=0.0,  # Not used for trailing stops
            comparison="triggered"
        )

        alert_result = await self.create_price_alert(
            user_id=user_id,
            instrument_key=instrument_key,
            condition=condition,
            priority=AlertPriority.HIGH,
            custom_message=f"Trailing stop triggered for {metadata.symbol} (Stop ID: {trailing_stop_id})"
        )

        # Link to trailing stop
        alert_result["trailing_stop_id"] = trailing_stop_id
        alert_result["alert_category"] = "trailing_stop"

        return alert_result

    # =============================================================================
    # CLEANUP AND MONITORING
    # =============================================================================

    async def _cleanup_price_subscriptions(self):
        """Clean up inactive price subscriptions"""
        instruments_to_remove = []

        for instrument_key, subscription in self._price_subscriptions.items():
            # Check if any active alerts exist for this instrument
            has_active_alerts = any(
                alert.instrument_key == instrument_key and alert.status == AlertStatus.ACTIVE
                for alert in self._active_alerts.values()
            )

            if not has_active_alerts:
                instruments_to_remove.append(instrument_key)

        for instrument_key in instruments_to_remove:
            del self._price_subscriptions[instrument_key]
            logger.debug(f"Removed price subscription for {instrument_key}")

    async def get_service_status(self) -> dict[str, Any]:
        """Get alert service status and statistics"""
        return {
            "service": "AlertService",
            "status": "running" if self._monitoring_task and not self._monitoring_task.done() else "stopped",
            "statistics": {
                "active_alerts": len(self._active_alerts),
                "monitored_instruments": len(self._price_subscriptions),
                "registered_users": len(self._user_preferences),
                "total_notifications": len(self._notifications)
            },
            "configuration": {
                "check_interval": self.check_interval,
                "max_check_failures": self.max_check_failures,
                "retry_attempts": self.notification_retry_attempts
            },
            "timestamp": datetime.now().isoformat()
        }

    async def shutdown(self):
        """Shutdown alert service"""
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass

        logger.info("Alert service shutdown complete")
