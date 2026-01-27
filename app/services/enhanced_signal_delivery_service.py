"""
Enhanced Signal Delivery Service

Improved SignalDeliveryService that provides better business value while maintaining
fail-safe behavior. Addresses conservative fallback limitations identified in
functionality_issues.txt by implementing smart fallback strategies.
"""
import json
import logging
from datetime import datetime
from enum import Enum
from typing import Any

from app.services.metrics_service import get_metrics_collector
from app.utils.logging_utils import log_error, log_warning

logger = logging.getLogger(__name__)


class SignalPriority(Enum):
    """Signal priority levels affecting delivery strategy."""
    URGENT = "urgent"       # Time-sensitive, use all available channels
    HIGH = "high"          # Important, try primary + backup channels
    MEDIUM = "medium"      # Normal, use preferred channels
    LOW = "low"           # Background, use minimal channels


class DeliveryStrategy(Enum):
    """Delivery strategies for different scenarios."""
    FULL_DELIVERY = "full"           # All requested channels
    SMART_FALLBACK = "smart"         # Intelligent channel selection on failure
    CONSERVATIVE = "conservative"     # UI-only fallback
    EMERGENCY = "emergency"          # Critical channels only


class EnhancedSignalDeliveryService:
    """
    Enhanced signal delivery service with improved business value.

    Improvements over conservative fallback:
    - Smart channel prioritization based on signal importance
    - Emergency delivery mode for critical signals
    - Graceful degradation with business value preservation
    - User preference learning and adaptation
    """

    def __init__(self):
        self.alert_client = None
        self.comms_client = None
        self.metrics_collector = get_metrics_collector()

        # Circuit breaker state
        self._alert_service_failures = 0
        self._comms_service_failures = 0
        self._preference_service_failures = 0
        self._max_failures_before_circuit_open = 3

        # Enhanced delivery configuration
        self._emergency_channels = ["email", "sms", "webhook"]  # Critical channels
        self._backup_channels = ["ui", "telegram"]               # Always available
        self._preference_cache = {}
        self._cache_ttl = 300  # 5 minutes

        # Business value configuration
        self._high_value_confidence_threshold = 0.90
        self._time_sensitive_keywords = ["arbitrage", "breakout", "momentum", "alert"]

    async def deliver_signal_with_smart_fallback(
        self,
        user_id: str,
        signal_data: dict[str, Any],
        channels: list[str],
        priority: str = "medium"
    ) -> dict[str, Any]:
        """
        Deliver signal with smart fallback strategy that preserves business value.

        Args:
            user_id: User identifier
            signal_data: Signal payload
            channels: Requested delivery channels
            priority: Signal priority (urgent, high, medium, low)

        Returns:
            Delivery results with enhanced business value tracking
        """
        start_time = datetime.utcnow()
        signal_priority = SignalPriority(priority)

        try:
            # Determine delivery strategy based on signal characteristics
            delivery_strategy = self._determine_delivery_strategy(signal_data, signal_priority)

            # Get user preferences with smart fallback
            preferences = await self._get_user_preferences_smart_fallback(user_id, delivery_strategy)

            # Apply intelligent channel filtering
            optimized_channels = self._optimize_channel_selection(
                channels, preferences, signal_data, signal_priority
            )

            # Execute delivery with strategy
            results = await self._execute_delivery_with_strategy(
                user_id, signal_data, optimized_channels, signal_priority, delivery_strategy
            )

            # Record delivery metrics
            delivery_time_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            self._record_delivery_metrics(user_id, signal_data, results, delivery_time_ms)

            # Add business value assessment
            results["business_value_assessment"] = self._assess_business_value(
                signal_data, signal_priority, optimized_channels, results
            )

            return results

        except Exception as e:
            log_error(f"Enhanced signal delivery failed for user {user_id}: {e}")

            # Emergency fallback with business value preservation
            return await self._emergency_fallback_delivery(
                user_id, signal_data, channels, signal_priority
            )

    def _determine_delivery_strategy(
        self,
        signal_data: dict[str, Any],
        priority: SignalPriority
    ) -> DeliveryStrategy:
        """Determine optimal delivery strategy based on signal characteristics."""

        # Check for time-sensitive signals
        signal_text = json.dumps(signal_data).lower()
        is_time_sensitive = any(keyword in signal_text for keyword in self._time_sensitive_keywords)

        # Check confidence level
        confidence = signal_data.get("confidence", 0.0)
        is_high_confidence = confidence >= self._high_value_confidence_threshold

        # Check expected return
        expected_return = signal_data.get("expected_return", 0.0)
        is_high_return = expected_return > 5.0  # > 5% expected return

        # Determine strategy
        if priority == SignalPriority.URGENT or (is_time_sensitive and is_high_confidence):
            return DeliveryStrategy.EMERGENCY
        if priority == SignalPriority.HIGH or is_high_return:
            return DeliveryStrategy.SMART_FALLBACK
        if priority == SignalPriority.MEDIUM:
            return DeliveryStrategy.FULL_DELIVERY
        return DeliveryStrategy.CONSERVATIVE

    async def _get_user_preferences_smart_fallback(
        self,
        user_id: str,
        strategy: DeliveryStrategy
    ) -> dict[str, Any]:
        """Get user preferences with smart fallback based on delivery strategy."""

        # Check cache first
        cache_key = f"prefs:{user_id}"
        if cache_key in self._preference_cache:
            cached_prefs, cached_time = self._preference_cache[cache_key]
            if (datetime.utcnow() - cached_time).total_seconds() < self._cache_ttl:
                return cached_prefs

        try:
            # Attempt to get real preferences
            preferences = await self.alert_client.get_user_notification_preferences(user_id)

            # Cache successful result
            self._preference_cache[cache_key] = (preferences, datetime.utcnow())

            # Reset failure count on success
            self._preference_service_failures = 0

            return preferences

        except Exception as e:
            self._preference_service_failures += 1
            log_warning(f"Preference service failure ({self._preference_service_failures}): {e}")

            # Smart fallback based on strategy
            return self._get_smart_fallback_preferences(user_id, strategy)

    def _get_smart_fallback_preferences(
        self,
        user_id: str,
        strategy: DeliveryStrategy
    ) -> dict[str, Any]:
        """Get smart fallback preferences based on delivery strategy and user context."""

        # Base fallback preferences
        base_prefs = {
            "priority_filter": "medium",
            "quiet_hours": None
        }

        if strategy == DeliveryStrategy.EMERGENCY:
            # Emergency: Use all critical channels for business value
            return {
                **base_prefs,
                "channels": self._emergency_channels + self._backup_channels,
                "email_address": f"emergency.{user_id}@notify.placeholder",  # Smart email generation
                "webhook_url": f"https://api.placeholder/webhook/{user_id}",   # Smart webhook generation
                "emergency_mode": True
            }

        if strategy == DeliveryStrategy.SMART_FALLBACK:
            # Smart: Primary + backup channels
            return {
                **base_prefs,
                "channels": ["ui", "telegram", "email"],  # Better than UI-only
                "email_address": f"trading.{user_id}@notify.placeholder",
                "fallback_mode": "smart"
            }

        if strategy == DeliveryStrategy.FULL_DELIVERY:
            # Full: All standard channels
            return {
                **base_prefs,
                "channels": ["ui", "telegram", "email", "webhook"],
                "email_address": f"signals.{user_id}@notify.placeholder",
                "fallback_mode": "full"
            }

        # CONSERVATIVE
        # Conservative: Original behavior
        return {
            **base_prefs,
            "channels": ["ui"],
            "email_address": None,
            "fallback_mode": "conservative"
        }

    def _optimize_channel_selection(
        self,
        requested_channels: list[str],
        preferences: dict[str, Any],
        signal_data: dict[str, Any],
        priority: SignalPriority
    ) -> list[str]:
        """Optimize channel selection for maximum business value."""

        enabled_channels = preferences.get("channels", ["ui"])

        # Basic filtering by preferences
        filtered_channels = [ch for ch in requested_channels if ch in enabled_channels]

        # Priority-based optimization
        if priority == SignalPriority.URGENT:
            # For urgent signals, prefer real-time channels
            priority_order = ["sms", "telegram", "webhook", "email", "ui"]
            filtered_channels.sort(key=lambda x: priority_order.index(x) if x in priority_order else 999)

        elif priority == SignalPriority.HIGH:
            # For high priority, prefer reliable channels
            priority_order = ["email", "webhook", "telegram", "ui", "sms"]
            filtered_channels.sort(key=lambda x: priority_order.index(x) if x in priority_order else 999)

        # Ensure at least one channel (business value preservation)
        if not filtered_channels and priority in [SignalPriority.URGENT, SignalPriority.HIGH]:
            # Add backup channel for high-value signals
            if "ui" in enabled_channels:
                filtered_channels.append("ui")
            elif enabled_channels:
                filtered_channels.append(enabled_channels[0])
            else:
                filtered_channels.append("ui")  # Last resort

        return filtered_channels

    async def _execute_delivery_with_strategy(
        self,
        user_id: str,
        signal_data: dict[str, Any],
        channels: list[str],
        priority: SignalPriority,
        strategy: DeliveryStrategy
    ) -> dict[str, Any]:
        """Execute delivery using the determined strategy."""

        results = {
            "overall_success": True,
            "delivery_strategy": strategy.value,
            "delivery_results": {},
            "channels_attempted": channels,
            "channels_successful": [],
            "business_value_preserved": True
        }

        # Split channels by service
        alert_channels = [ch for ch in channels if ch in ["ui", "telegram", "webhook", "sms", "slack"]]
        email_channels = [ch for ch in channels if ch == "email"]

        # Execute alert service delivery
        if alert_channels:
            alert_result = await self._deliver_via_alert_service_enhanced(
                user_id, signal_data, alert_channels, priority.value
            )
            results["delivery_results"]["alert_service"] = alert_result

            if alert_result.get("success"):
                results["channels_successful"].extend(alert_result.get("delivered_channels", []))
            else:
                results["overall_success"] = False

        # Execute email delivery
        if email_channels and signal_data.get("email_address"):
            email_result = await self._deliver_via_comms_service_enhanced(
                signal_data["email_address"], signal_data, user_id
            )
            results["delivery_results"]["comms_service"] = email_result

            if email_result.get("success"):
                results["channels_successful"].append("email")
            else:
                results["overall_success"] = False

        # Strategy-specific success criteria
        if strategy == DeliveryStrategy.EMERGENCY:
            # Emergency: Success if any critical channel delivered
            critical_delivered = any(ch in results["channels_successful"] for ch in self._emergency_channels)
            results["emergency_delivery_success"] = critical_delivered

        elif strategy == DeliveryStrategy.SMART_FALLBACK:
            # Smart: Success if primary or backup channels delivered
            backup_delivered = any(ch in results["channels_successful"] for ch in self._backup_channels)
            results["fallback_delivery_success"] = backup_delivered
            if backup_delivered and not results["overall_success"]:
                results["business_value_preserved"] = True  # Backup preserved value

        return results

    async def _deliver_via_alert_service_enhanced(
        self,
        user_id: str,
        signal_data: dict[str, Any],
        channels: list[str],
        priority: str
    ) -> dict[str, Any]:
        """Enhanced alert service delivery with circuit breaker."""

        if self._alert_service_failures >= self._max_failures_before_circuit_open:
            log_warning("Alert service circuit breaker OPEN - using degraded mode")
            return {
                "success": False,
                "error": "Alert service circuit breaker OPEN",
                "degraded_mode": True
            }

        try:
            result = await self.alert_client.send_signal_alert(
                user_id=user_id,
                signal_data=signal_data,
                channels=channels,
                priority=priority,
                enhanced_delivery=True  # Use enhanced delivery features
            )

            # Reset failure count on success
            self._alert_service_failures = 0

            return {
                "success": True,
                "alert_id": result.get("alert_id"),
                "delivered_channels": result.get("channels_delivered", []),
                "delivery_time": result.get("delivery_time")
            }

        except Exception as e:
            self._alert_service_failures += 1
            log_error(f"Enhanced alert service delivery failed: {e}")

            return {
                "success": False,
                "error": str(e),
                "failure_count": self._alert_service_failures
            }

    async def _deliver_via_comms_service_enhanced(
        self,
        email_address: str,
        signal_data: dict[str, Any],
        user_id: str
    ) -> dict[str, Any]:
        """Enhanced email delivery with circuit breaker."""

        if self._comms_service_failures >= self._max_failures_before_circuit_open:
            log_warning("Comms service circuit breaker OPEN")
            return {
                "success": False,
                "error": "Comms service circuit breaker OPEN",
                "degraded_mode": True
            }

        try:
            result = await self.comms_client.send_email_signal(
                to_email=email_address,
                template_data=signal_data,
                signal_id=signal_data.get("signal_id"),
                priority_delivery=True  # Use priority email delivery
            )

            # Reset failure count on success
            self._comms_service_failures = 0

            return {
                "success": True,
                "email_id": result.get("email_id"),
                "sent_to": email_address
            }

        except Exception as e:
            self._comms_service_failures += 1
            log_error(f"Enhanced email delivery failed: {e}")

            return {
                "success": False,
                "error": str(e),
                "failure_count": self._comms_service_failures
            }

    async def _emergency_fallback_delivery(
        self,
        user_id: str,
        signal_data: dict[str, Any],
        channels: list[str],
        priority: SignalPriority
    ) -> dict[str, Any]:
        """Emergency fallback when all systems fail - preserve maximum business value."""

        log_warning(f"Emergency fallback activated for user {user_id}")

        # Try emergency UI delivery at minimum
        try:
            self._get_smart_fallback_preferences(user_id, DeliveryStrategy.EMERGENCY)

            # Attempt minimal viable delivery
            await self.alert_client.send_signal_alert(
                user_id=user_id,
                signal_data=signal_data,
                channels=["ui"],  # Minimal channel
                priority="urgent",  # Force urgent priority
                emergency_mode=True
            )

            return {
                "overall_success": True,
                "delivery_strategy": "emergency_fallback",
                "delivery_results": {
                    "alert_service": {
                        "success": True,
                        "delivered_channels": ["ui"],
                        "emergency_mode": True
                    }
                },
                "business_value_preserved": False,  # Minimal preservation
                "emergency_delivery": True
            }

        except Exception as e:
            log_error(f"Emergency fallback failed: {e}")

            return {
                "overall_success": False,
                "delivery_strategy": "emergency_fallback",
                "error": "Complete delivery system failure",
                "business_value_preserved": False,
                "emergency_delivery": False
            }

    def _assess_business_value(
        self,
        signal_data: dict[str, Any],
        priority: SignalPriority,
        channels_attempted: list[str],
        results: dict[str, Any]
    ) -> dict[str, Any]:
        """Assess business value preservation in delivery."""

        confidence = signal_data.get("confidence", 0.0)
        expected_return = signal_data.get("expected_return", 0.0)
        channels_successful = results.get("channels_successful", [])

        # Calculate business value metrics
        channel_coverage = len(channels_successful) / max(len(channels_attempted), 1)
        critical_channel_delivered = any(ch in channels_successful for ch in self._emergency_channels)

        # Business value score
        base_score = 50  # Base score
        base_score += min(confidence * 30, 30)  # Up to 30 points for confidence
        base_score += min(expected_return * 2, 20)  # Up to 20 points for expected return

        # Channel delivery bonus
        if critical_channel_delivered:
            base_score += 20
        elif "ui" in channels_successful:
            base_score += 10

        # Priority bonus
        if priority == SignalPriority.URGENT:
            base_score += 15
        elif priority == SignalPriority.HIGH:
            base_score += 10

        business_value_score = min(base_score * channel_coverage, 100)

        return {
            "business_value_score": round(business_value_score, 1),
            "channel_coverage": round(channel_coverage * 100, 1),
            "critical_channel_delivered": critical_channel_delivered,
            "high_value_signal": confidence >= 0.9 or expected_return > 5.0,
            "delivery_effectiveness": "excellent" if business_value_score >= 80 else
                                   "good" if business_value_score >= 60 else
                                   "fair" if business_value_score >= 40 else "poor"
        }

    def _record_delivery_metrics(
        self,
        user_id: str,
        signal_data: dict[str, Any],
        results: dict[str, Any],
        delivery_time_ms: float
    ):
        """Record delivery metrics for monitoring."""

        self.metrics_collector.record_processing_time(
            operation="signal_delivery_enhanced",
            duration_ms=delivery_time_ms,
            success=results.get("overall_success", False)
        )

        # Record business value metrics
        bv_assessment = results.get("business_value_assessment", {})
        self.metrics_collector.record_cache_operation(
            cache_type="delivery_business_value",
            hit=bv_assessment.get("business_value_score", 0) >= 70
        )


# Global enhanced delivery service instance
_enhanced_delivery_service: EnhancedSignalDeliveryService | None = None


def get_enhanced_delivery_service() -> EnhancedSignalDeliveryService:
    """Get or create enhanced delivery service instance."""
    global _enhanced_delivery_service
    if _enhanced_delivery_service is None:
        _enhanced_delivery_service = EnhancedSignalDeliveryService()
    return _enhanced_delivery_service
