#!/usr/bin/env python3
"""
Subscription Manager Service - Phase 2 Migration

SUB_001: Subscription Manager Migration
- All subscription APIs require instrument_key parameters
- Registry-validated subscription management
- Performance monitoring and health checks
- Migration utilities with data integrity validation
"""

import asyncio
import logging
import time
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import datetime, timedelta
from typing import Any

from app.sdk import InstrumentClient, create_instrument_client

from .models import (
    DataFrequency,
    Subscription,
    SubscriptionPreferences,
    SubscriptionStatus,
    SubscriptionStorage,
    SubscriptionType,
)

logger = logging.getLogger(__name__)

class SubscriptionManager:
    """
    Subscription Manager - Phase 2 Migration

    SUB_001: Complete subscription management using instrument_key as primary
    identifier with automatic registry validation and performance monitoring.
    """

    def __init__(self,
                 storage: SubscriptionStorage | None = None,
                 instrument_client: InstrumentClient | None = None,
                 max_user_subscriptions: int = 100,
                 cleanup_interval_minutes: int = 60):
        """
        Initialize subscription manager

        Args:
            storage: Subscription storage layer
            instrument_client: Phase 1 SDK client
            max_user_subscriptions: Maximum subscriptions per user
            cleanup_interval_minutes: Cleanup task interval
        """
        self.storage = storage or SubscriptionStorage(instrument_client)
        self.instrument_client = instrument_client or create_instrument_client()
        self.max_user_subscriptions = max_user_subscriptions
        self.cleanup_interval_minutes = cleanup_interval_minutes

        # User preferences storage
        self._user_preferences: dict[str, SubscriptionPreferences] = {}

        # Performance monitoring
        self._operation_metrics = {
            "subscribe_calls": 0,
            "unsubscribe_calls": 0,
            "validation_calls": 0,
            "migration_calls": 0,
            "avg_response_time_ms": 0.0,
            "error_count": 0,
            "last_metrics_reset": datetime.now()
        }

        # Background tasks
        self._cleanup_task: asyncio.Task | None = None
        self._monitoring_task: asyncio.Task | None = None

        # Event callbacks
        self._subscription_callbacks: dict[str, list[Callable]] = {
            "created": [],
            "cancelled": [],
            "updated": [],
            "error": []
        }

    async def start(self):
        """Start subscription manager background tasks"""
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        self._monitoring_task = asyncio.create_task(self._monitoring_loop())
        logger.info("Subscription manager started")

    async def stop(self):
        """Stop subscription manager and cleanup tasks"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
        if self._monitoring_task:
            self._monitoring_task.cancel()

        try:
            if self._cleanup_task:
                await self._cleanup_task
            if self._monitoring_task:
                await self._monitoring_task
        except asyncio.CancelledError:
            pass

        logger.info("Subscription manager stopped")

    # =============================================================================
    # CORE SUBSCRIPTION OPERATIONS (instrument_key-based)
    # =============================================================================

    async def subscribe(self,
                       user_id: str,
                       instrument_key: str,
                       subscription_type: SubscriptionType,
                       data_frequency: DataFrequency = DataFrequency.TICK,
                       filters: dict[str, Any] | None = None,
                       delivery_config: dict[str, Any] | None = None) -> dict[str, Any]:
        """
        Subscribe to instrument data using instrument_key

        Args:
            user_id: User identifier
            instrument_key: Primary identifier (e.g., "AAPL_NASDAQ_EQUITY")
            subscription_type: Type of data subscription
            data_frequency: Data delivery frequency
            filters: Optional data filters
            delivery_config: Delivery configuration

        Returns:
            Dict: Subscription result with metadata
        """
        start_time = time.time()

        try:
            # Validate user subscription limits
            await self._validate_user_limits(user_id)

            # Check for existing subscription
            existing_sub = await self._find_existing_subscription(
                user_id, instrument_key, subscription_type
            )

            if existing_sub:
                # Reactivate existing subscription if cancelled
                if existing_sub.status == SubscriptionStatus.CANCELLED:
                    await self.storage.update_subscription_status(
                        existing_sub.subscription_id, SubscriptionStatus.ACTIVE
                    )
                    result = await self._create_subscription_response(existing_sub, "reactivated")
                else:
                    result = await self._create_subscription_response(existing_sub, "existing")
            else:
                # Create new subscription
                subscription = await self.storage.create_subscription(
                    user_id=user_id,
                    instrument_key=instrument_key,
                    subscription_type=subscription_type,
                    data_frequency=data_frequency,
                    filters=filters,
                    delivery_config=delivery_config
                )

                result = await self._create_subscription_response(subscription, "created")

                # Notify callbacks
                await self._notify_callbacks("created", subscription)

            # Update metrics
            response_time = (time.time() - start_time) * 1000
            self._operation_metrics["subscribe_calls"] += 1
            await self._update_response_time_metric(response_time)

            logger.info(f"Subscription operation completed for {instrument_key}: {result['action']}")

            return result

        except Exception as e:
            self._operation_metrics["error_count"] += 1
            logger.error(f"Subscription failed for {user_id}/{instrument_key}: {e}")
            raise

    async def unsubscribe(self, user_id: str, subscription_id: str) -> dict[str, Any]:
        """
        Unsubscribe from data feed

        Args:
            user_id: User identifier
            subscription_id: Subscription to cancel

        Returns:
            Dict: Unsubscribe result
        """
        start_time = time.time()

        try:
            # Cancel subscription
            success = await self.storage.cancel_subscription(subscription_id, user_id)

            if not success:
                raise ValueError(f"Subscription not found or unauthorized: {subscription_id}")

            # Get subscription details for response
            subscription = await self.storage.get_subscription(subscription_id)

            result = {
                "subscription_id": subscription_id,
                "instrument_key": subscription.instrument_key if subscription else "unknown",
                "symbol": subscription.symbol if subscription else "Unknown",
                "status": "cancelled",
                "cancelled_at": datetime.now().isoformat()
            }

            # Notify callbacks
            if subscription:
                await self._notify_callbacks("cancelled", subscription)

            # Update metrics
            response_time = (time.time() - start_time) * 1000
            self._operation_metrics["unsubscribe_calls"] += 1
            await self._update_response_time_metric(response_time)

            logger.info(f"Unsubscribed: {subscription_id}")

            return result

        except Exception as e:
            self._operation_metrics["error_count"] += 1
            logger.error(f"Unsubscribe failed for {subscription_id}: {e}")
            raise

    async def get_user_subscriptions(self, user_id: str) -> dict[str, Any]:
        """
        Get all subscriptions for a user with enriched metadata

        Args:
            user_id: User identifier

        Returns:
            Dict: User subscriptions with metadata
        """
        try:
            subscriptions = await self.storage.get_user_subscriptions(user_id)

            # Convert to response format with enriched data
            subscription_data = []
            for sub in subscriptions:
                sub_data = {
                    "subscription_id": sub.subscription_id,
                    "instrument_key": sub.instrument_key,
                    "instrument_metadata": {
                        "symbol": sub.symbol,
                        "exchange": sub.exchange,
                        "sector": sub.sector
                    },
                    "subscription_type": sub.subscription_type.value,
                    "data_frequency": sub.data_frequency.value,
                    "status": sub.status.value,
                    "created_at": sub.created_at.isoformat(),
                    "last_updated": sub.last_updated.isoformat(),
                    "message_count": sub.message_count,
                    "last_message_at": sub.last_message_at.isoformat() if sub.last_message_at else None
                }
                subscription_data.append(sub_data)

            return {
                "user_id": user_id,
                "total_subscriptions": len(subscription_data),
                "active_subscriptions": len([s for s in subscription_data if s["status"] == "active"]),
                "subscriptions": subscription_data,
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Failed to get subscriptions for user {user_id}: {e}")
            raise

    async def get_instrument_subscriptions(self, instrument_key: str) -> dict[str, Any]:
        """
        Get all subscriptions for an instrument

        Args:
            instrument_key: Instrument identifier

        Returns:
            Dict: Instrument subscriptions
        """
        try:
            subscriptions = await self.storage.get_instrument_subscriptions(instrument_key)

            # Get instrument metadata
            try:
                metadata = await self.instrument_client.get_instrument_metadata(instrument_key)
                instrument_info = {
                    "symbol": metadata.symbol,
                    "exchange": metadata.exchange,
                    "sector": metadata.sector,
                    "instrument_type": metadata.instrument_type
                }
            except:
                instrument_info = {
                    "symbol": "Unknown",
                    "exchange": "Unknown",
                    "sector": "Unknown",
                    "instrument_type": "Unknown"
                }

            subscription_summary = []
            for sub in subscriptions:
                summary = {
                    "subscription_id": sub.subscription_id,
                    "user_id": sub.user_id,
                    "subscription_type": sub.subscription_type.value,
                    "data_frequency": sub.data_frequency.value,
                    "status": sub.status.value,
                    "created_at": sub.created_at.isoformat()
                }
                subscription_summary.append(summary)

            return {
                "instrument_key": instrument_key,
                "instrument_metadata": instrument_info,
                "total_subscriptions": len(subscription_summary),
                "subscriptions": subscription_summary,
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Failed to get subscriptions for instrument {instrument_key}: {e}")
            raise

    # =============================================================================
    # SUBSCRIPTION MIGRATION UTILITIES
    # =============================================================================

    async def migrate_user_subscriptions(self, user_id: str, token_mappings: dict[str, str]) -> dict[str, Any]:
        """
        Migrate user's token-based subscriptions to instrument_key

        Args:
            user_id: User identifier
            token_mappings: Mapping from token to instrument_key

        Returns:
            Dict: Migration results
        """
        start_time = time.time()

        try:
            migration_requests = []
            for token, instrument_key in token_mappings.items():
                migration_requests.append({
                    "user_id": user_id,
                    "legacy_token": token,
                    "subscription_type": "real_time_quotes",  # Default type
                    "data_frequency": "tick"
                })

            # Perform bulk migration
            migration_results = await self.storage.bulk_migrate_subscriptions(migration_requests)

            # Update metrics
            response_time = (time.time() - start_time) * 1000
            self._operation_metrics["migration_calls"] += 1
            await self._update_response_time_metric(response_time)

            logger.info(f"User migration completed for {user_id}: {migration_results['successful_migrations']} successful")

            return {
                "user_id": user_id,
                "migration_results": migration_results,
                "migration_time_ms": response_time,
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            self._operation_metrics["error_count"] += 1
            logger.error(f"User migration failed for {user_id}: {e}")
            raise

    async def validate_subscription_registry(self, subscription_id: str) -> dict[str, Any]:
        """
        Validate subscription against registry

        Args:
            subscription_id: Subscription to validate

        Returns:
            Dict: Validation results
        """
        start_time = time.time()

        try:
            validation_result = await self.storage.validate_subscription(subscription_id)

            # Update metrics
            response_time = (time.time() - start_time) * 1000
            self._operation_metrics["validation_calls"] += 1
            await self._update_response_time_metric(response_time)

            return validation_result

        except Exception as e:
            self._operation_metrics["error_count"] += 1
            logger.error(f"Subscription validation failed for {subscription_id}: {e}")
            raise

    # =============================================================================
    # USER PREFERENCES MANAGEMENT
    # =============================================================================

    async def update_user_preferences(self, user_id: str, preferences: dict[str, Any]) -> dict[str, Any]:
        """Update user subscription preferences"""

        current_prefs = self._user_preferences.get(user_id, SubscriptionPreferences())

        # Update preferences
        if "max_subscriptions" in preferences:
            current_prefs.max_subscriptions = preferences["max_subscriptions"]

        if "default_frequency" in preferences:
            current_prefs.default_frequency = DataFrequency(preferences["default_frequency"])

        if "auto_subscribe_sectors" in preferences:
            current_prefs.auto_subscribe_sectors = preferences["auto_subscribe_sectors"]

        if "excluded_exchanges" in preferences:
            current_prefs.excluded_exchanges = preferences["excluded_exchanges"]

        if "rate_limiting" in preferences:
            current_prefs.rate_limiting = preferences["rate_limiting"]

        self._user_preferences[user_id] = current_prefs

        return {
            "user_id": user_id,
            "preferences_updated": True,
            "preferences": asdict(current_prefs),
            "updated_at": datetime.now().isoformat()
        }

    async def get_user_preferences(self, user_id: str) -> dict[str, Any]:
        """Get user subscription preferences"""

        preferences = self._user_preferences.get(user_id, SubscriptionPreferences())

        return {
            "user_id": user_id,
            "preferences": asdict(preferences),
            "timestamp": datetime.now().isoformat()
        }

    # =============================================================================
    # PERFORMANCE MONITORING AND HEALTH CHECKS
    # =============================================================================

    async def get_performance_metrics(self) -> dict[str, Any]:
        """Get subscription manager performance metrics"""

        storage_metrics = await self.storage.get_subscription_metrics()

        return {
            "subscription_manager": {
                "operation_metrics": self._operation_metrics,
                "avg_response_time_ms": self._operation_metrics["avg_response_time_ms"],
                "error_rate": self._operation_metrics["error_count"] / max(1, self._operation_metrics["subscribe_calls"])
            },
            "storage_metrics": storage_metrics,
            "system_health": {
                "cleanup_task_running": self._cleanup_task and not self._cleanup_task.done(),
                "monitoring_task_running": self._monitoring_task and not self._monitoring_task.done()
            },
            "timestamp": datetime.now().isoformat()
        }

    async def health_check(self) -> dict[str, Any]:
        """Comprehensive health check"""

        try:
            # Check storage health
            storage_health = await self.storage.health_check()

            # Check background tasks
            tasks_healthy = (
                self._cleanup_task and not self._cleanup_task.done() and
                self._monitoring_task and not self._monitoring_task.done()
            )

            # Calculate overall health
            overall_healthy = (
                storage_health["healthy"] and
                tasks_healthy and
                self._operation_metrics["error_count"] < 100  # Threshold
            )

            return {
                "service": "SubscriptionManager",
                "healthy": overall_healthy,
                "storage_health": storage_health,
                "background_tasks": {
                    "cleanup_running": self._cleanup_task and not self._cleanup_task.done(),
                    "monitoring_running": self._monitoring_task and not self._monitoring_task.done()
                },
                "performance": {
                    "avg_response_time_ms": self._operation_metrics["avg_response_time_ms"],
                    "error_count": self._operation_metrics["error_count"],
                    "total_operations": self._operation_metrics["subscribe_calls"] + self._operation_metrics["unsubscribe_calls"]
                },
                "last_check": datetime.now().isoformat()
            }

        except Exception as e:
            return {
                "service": "SubscriptionManager",
                "healthy": False,
                "error": str(e),
                "last_check": datetime.now().isoformat()
            }

    # =============================================================================
    # EVENT CALLBACKS AND NOTIFICATIONS
    # =============================================================================

    def register_callback(self, event_type: str, callback: Callable):
        """Register callback for subscription events"""
        if event_type in self._subscription_callbacks:
            self._subscription_callbacks[event_type].append(callback)
        else:
            raise ValueError(f"Unknown event type: {event_type}")

    async def _notify_callbacks(self, event_type: str, subscription: Subscription):
        """Notify registered callbacks"""
        for callback in self._subscription_callbacks.get(event_type, []):
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(event_type, subscription)
                else:
                    callback(event_type, subscription)
            except Exception as e:
                logger.error(f"Callback notification failed: {e}")

    # =============================================================================
    # INTERNAL UTILITIES
    # =============================================================================

    async def _validate_user_limits(self, user_id: str):
        """Validate user subscription limits"""
        user_subs = await self.storage.get_user_subscriptions(user_id, SubscriptionStatus.ACTIVE)
        user_prefs = self._user_preferences.get(user_id, SubscriptionPreferences())

        if len(user_subs) >= user_prefs.max_subscriptions:
            raise ValueError(f"User {user_id} has reached subscription limit: {user_prefs.max_subscriptions}")

    async def _find_existing_subscription(self,
                                        user_id: str,
                                        instrument_key: str,
                                        subscription_type: SubscriptionType) -> Subscription | None:
        """Find existing subscription for user/instrument/type"""
        user_subs = await self.storage.get_user_subscriptions(user_id)

        for sub in user_subs:
            if (sub.instrument_key == instrument_key and
                sub.subscription_type == subscription_type):
                return sub

        return None

    async def _create_subscription_response(self, subscription: Subscription, action: str) -> dict[str, Any]:
        """Create standardized subscription response"""
        return {
            "subscription_id": subscription.subscription_id,
            "instrument_key": subscription.instrument_key,
            "instrument_metadata": {
                "symbol": subscription.symbol,
                "exchange": subscription.exchange,
                "sector": subscription.sector
            },
            "subscription_type": subscription.subscription_type.value,
            "data_frequency": subscription.data_frequency.value,
            "status": subscription.status.value,
            "action": action,
            "created_at": subscription.created_at.isoformat(),
            "last_updated": subscription.last_updated.isoformat()
        }

    async def _update_response_time_metric(self, response_time_ms: float):
        """Update rolling average response time"""
        current_avg = self._operation_metrics["avg_response_time_ms"]
        total_calls = (self._operation_metrics["subscribe_calls"] +
                      self._operation_metrics["unsubscribe_calls"] +
                      self._operation_metrics["validation_calls"])

        if total_calls > 0:
            self._operation_metrics["avg_response_time_ms"] = (
                (current_avg * (total_calls - 1) + response_time_ms) / total_calls
            )

    async def _cleanup_loop(self):
        """Background cleanup task"""
        while True:
            try:
                await asyncio.sleep(self.cleanup_interval_minutes * 60)

                # Clean up expired subscriptions
                expired_count = await self.storage.cleanup_expired_subscriptions()

                if expired_count > 0:
                    logger.info(f"Cleanup: removed {expired_count} expired subscriptions")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cleanup loop error: {e}")
                await asyncio.sleep(60)  # Wait before retrying

    async def _monitoring_loop(self):
        """Background monitoring task"""
        while True:
            try:
                await asyncio.sleep(300)  # 5 minutes

                # Reset metrics periodically
                time_since_reset = datetime.now() - self._operation_metrics["last_metrics_reset"]
                if time_since_reset > timedelta(hours=1):
                    # Archive current metrics and reset
                    self._operation_metrics = {
                        "subscribe_calls": 0,
                        "unsubscribe_calls": 0,
                        "validation_calls": 0,
                        "migration_calls": 0,
                        "avg_response_time_ms": 0.0,
                        "error_count": 0,
                        "last_metrics_reset": datetime.now()
                    }

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Monitoring loop error: {e}")
                await asyncio.sleep(300)


# =============================================================================
# SUBSCRIPTION MANAGER FACTORY
# =============================================================================

async def create_subscription_manager(**kwargs) -> SubscriptionManager:
    """Create and initialize subscription manager"""
    manager = SubscriptionManager(**kwargs)
    await manager.start()
    return manager

@asynccontextmanager
async def subscription_manager_context(**kwargs):
    """Context manager for subscription manager lifecycle"""
    manager = await create_subscription_manager(**kwargs)
    try:
        yield manager
    finally:
        await manager.stop()
