# Indicator Aggregation Manager - Deduplication and Coordination
import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from app.utils.logging_utils import log_exception, log_info, log_warning
from app.utils.redis import get_redis_client


class MonitoringTier(Enum):
    """Monitoring tiers for resource allocation"""
    REAL_TIME = "real_time"
    HIGH_FREQUENCY = "high_frequency"
    PERIODIC = "periodic"
    ON_DEMAND = "on_demand"


@dataclass
class IndicatorSubscription:
    """Represents a shared indicator computation with multiple subscribers"""
    indicator_key: str
    specification: dict
    primary_subscriber: str
    subscribers: dict[str, dict] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_computation: datetime | None = None
    computation_count: int = 0
    current_tier: MonitoringTier = MonitoringTier.PERIODIC

    def add_subscriber(self, user_id: str, request: dict):
        """Add a new subscriber to this indicator"""
        self.subscribers[user_id] = {
            "request": request,
            "subscribed_at": datetime.utcnow(),
            "threshold_config": request.get("threshold_configuration", {}),
            "alert_config": request.get("alert_configuration", {}),
            "monitoring_tier": request.get("subscription_context", {}).get("monitoring_tier", "periodic")
        }

        # Update optimal tier based on new subscriber
        self.current_tier = self._determine_optimal_tier()

    def remove_subscriber(self, user_id: str) -> bool:
        """Remove a subscriber from this indicator. Returns True if no subscribers left."""
        if user_id in self.subscribers:
            del self.subscribers[user_id]

            if self.subscribers:
                # Re-evaluate tier with remaining subscribers
                self.current_tier = self._determine_optimal_tier()

        return len(self.subscribers) == 0

    def _determine_optimal_tier(self) -> MonitoringTier:
        """Determine optimal monitoring tier based on all subscribers"""
        if not self.subscribers:
            return MonitoringTier.ON_DEMAND

        tiers = [MonitoringTier(sub["monitoring_tier"])
                for sub in self.subscribers.values()]

        # Highest tier wins (real_time > high_frequency > periodic > on_demand)
        tier_priority = {
            MonitoringTier.REAL_TIME: 4,
            MonitoringTier.HIGH_FREQUENCY: 3,
            MonitoringTier.PERIODIC: 2,
            MonitoringTier.ON_DEMAND: 1
        }

        highest_tier = max(tiers, key=lambda t: tier_priority.get(t, 0))
        return highest_tier

    def get_all_alert_configs(self) -> list[dict]:
        """Get all alert configurations from subscribers"""
        return [sub["alert_config"] for sub in self.subscribers.values()]

    def get_resource_requirements(self) -> dict:
        """Calculate combined resource requirements"""
        total_subscribers = len(self.subscribers)

        return {
            "computation_priority": self.current_tier.value,
            "subscriber_count": total_subscribers,
            "estimated_cost_multiplier": 1.0 / total_subscribers,  # Cost sharing
            "alert_channels": self._get_unique_alert_channels(),
            "max_computation_frequency": self._get_max_frequency()
        }

    def _get_unique_alert_channels(self) -> set[str]:
        """Get unique alert channels across all subscribers"""
        channels = set()
        for sub in self.subscribers.values():
            channels.update(sub["alert_config"].get("channels", []))
        return channels

    def _get_max_frequency(self) -> str:
        """Get the highest frequency requirement among subscribers"""
        frequencies = [sub["request"]["indicator_specification"].get("computation_frequency", "periodic")
                      for sub in self.subscribers.values()]

        freq_priority = {"real_time": 4, "1m": 3, "5m": 2, "1h": 1, "4h": 0}
        max_freq = max(frequencies, key=lambda f: freq_priority.get(f, 0))
        return max_freq


class IndicatorAggregationManager:
    """
    Manages deduplication and aggregation of identical indicator requests
    Coordinates between subscription_service and signal_service
    """

    def __init__(self):
        self.redis_client = None
        self.active_indicators: dict[str, IndicatorSubscription] = {}
        self.user_subscriptions: dict[str, set[str]] = defaultdict(set)  # user_id -> indicator_keys

        # Stream names for coordination
        self.streams = {
            "indicator_requests": "signal_indicator_requests",
            "computation_requests": "signal_computation_requests",
            "computation_results": "signal_computation_results",
            "unsubscription_events": "signal_unsubscription_events"
        }

        log_info("IndicatorAggregationManager initialized")

    async def initialize(self):
        """Initialize Redis connection and load existing state"""
        try:
            self.redis_client = await get_redis_client()
            await self._load_existing_subscriptions()
            log_info("IndicatorAggregationManager initialized with Redis")
        except Exception as e:
            log_exception(f"Failed to initialize IndicatorAggregationManager: {e}")
            raise

    def generate_indicator_key(self, symbol: str, indicator_name: str,
                             timeframe: str, parameters: dict) -> str:
        """Generate unique key for indicator deduplication"""

        # Sort parameters for consistent hashing
        sorted_params = json.dumps(parameters, sort_keys=True)
        param_hash = hashlib.md5(sorted_params.encode()).hexdigest()[:8]

        return f"indicator:{symbol}:{indicator_name}:{timeframe}:{param_hash}"

    async def process_indicator_request(self, request: dict) -> dict:
        """Process new indicator request with smart deduplication"""
        try:
            user_id = request["user_id"]
            spec = request["indicator_specification"]

            indicator_key = self.generate_indicator_key(
                spec["symbol"],
                spec["indicator_name"],
                spec["timeframe"],
                spec["parameters"]
            )

            log_info(f"🔍 Processing indicator request: {indicator_key} for user {user_id}")

            # Check if this exact indicator is already being computed
            if indicator_key in self.active_indicators:
                existing = self.active_indicators[indicator_key]

                # Add user to existing indicator subscription
                existing.add_subscriber(user_id, request)
                self.user_subscriptions[user_id].add(indicator_key)

                # Update computation tier if needed
                if existing.current_tier != existing._determine_optimal_tier():
                    await self._update_monitoring_tier(indicator_key, existing.current_tier)

                await self._persist_subscription_state(indicator_key, existing)

                log_info(f"✅ Subscribed user {user_id} to existing indicator {indicator_key}")
                log_info(f"📊 Indicator {indicator_key} now has {len(existing.subscribers)} subscribers")

                return {
                    "action": "subscribed_to_existing",
                    "indicator_key": indicator_key,
                    "existing_subscribers": len(existing.subscribers),
                    "computation_sharing": True,
                    "cost_reduction_estimate": f"{80 + min(15, len(existing.subscribers) * 3)}%",
                    "monitoring_tier": existing.current_tier.value
                }
            # Create new indicator computation
            subscription = IndicatorSubscription(
                indicator_key=indicator_key,
                specification=spec,
                primary_subscriber=user_id
            )

            subscription.add_subscriber(user_id, request)
            self.active_indicators[indicator_key] = subscription
            self.user_subscriptions[user_id].add(indicator_key)

            # Send to signal_service for computation
            await self._create_signal_computation(subscription)
            await self._persist_subscription_state(indicator_key, subscription)

            log_info(f"✅ Created new indicator computation: {indicator_key}")

            return {
                "action": "created_new_indicator",
                "indicator_key": indicator_key,
                "computation_required": True,
                "monitoring_tier": subscription.current_tier.value,
                "estimated_setup_time": "30-60 seconds"
            }

        except Exception as e:
            log_exception(f"Failed to process indicator request: {e}")
            return {
                "action": "error",
                "error": str(e)
            }

    async def _create_signal_computation(self, subscription: IndicatorSubscription):
        """Create actual computation in signal_service"""
        try:
            signal_request = {
                "action": "create_computation",
                "indicator_key": subscription.indicator_key,
                "specification": subscription.specification,
                "monitoring_tier": subscription.current_tier.value,
                "subscribers": list(subscription.subscribers.keys()),
                "resource_requirements": subscription.get_resource_requirements(),
                "alert_configs": subscription.get_all_alert_configs(),
                "created_at": subscription.created_at.isoformat()
            }

            # Send to signal_service via Redis Stream
            await self.redis_client.xadd(
                self.streams["computation_requests"],
                {
                    "request_data": json.dumps(signal_request),
                    "timestamp": datetime.utcnow().isoformat()
                }
            )

            log_info(f"📤 Sent computation request to signal_service: {subscription.indicator_key}")

        except Exception as e:
            log_exception(f"Failed to create signal computation: {e}")
            raise

    async def _update_monitoring_tier(self, indicator_key: str, new_tier: MonitoringTier):
        """Update monitoring tier for existing computation"""
        try:
            update_request = {
                "action": "update_tier",
                "indicator_key": indicator_key,
                "new_tier": new_tier.value,
                "timestamp": datetime.utcnow().isoformat()
            }

            await self.redis_client.xadd(
                self.streams["computation_requests"],
                {
                    "request_data": json.dumps(update_request),
                    "timestamp": datetime.utcnow().isoformat()
                }
            )

            log_info(f"📊 Updated monitoring tier for {indicator_key} to {new_tier.value}")

        except Exception as e:
            log_exception(f"Failed to update monitoring tier: {e}")

    async def unsubscribe_user_from_indicator(self, user_id: str, indicator_key: str) -> dict:
        """Remove user from specific indicator subscription"""
        try:
            if indicator_key not in self.active_indicators:
                return {"action": "not_found", "indicator_key": indicator_key}

            subscription = self.active_indicators[indicator_key]
            no_subscribers_left = subscription.remove_subscriber(user_id)

            # Remove from user's subscription set
            self.user_subscriptions[user_id].discard(indicator_key)

            if no_subscribers_left:
                # No one subscribing to this indicator anymore - clean up
                await self._cleanup_indicator_computation(indicator_key)
                del self.active_indicators[indicator_key]
                await self._remove_subscription_state(indicator_key)

                log_info(f"🧹 Cleaned up indicator {indicator_key} - no subscribers remaining")

                return {
                    "action": "indicator_removed",
                    "indicator_key": indicator_key,
                    "reason": "no_subscribers_remaining"
                }
            # Re-evaluate monitoring tier with remaining subscribers
            old_tier = subscription.current_tier
            new_tier = subscription._determine_optimal_tier()

            if old_tier != new_tier:
                await self._update_monitoring_tier(indicator_key, new_tier)

            await self._persist_subscription_state(indicator_key, subscription)

            log_info(f"📊 Updated {indicator_key}: {len(subscription.subscribers)} subscribers, tier: {new_tier.value}")

            return {
                "action": "subscriber_removed",
                "indicator_key": indicator_key,
                "remaining_subscribers": len(subscription.subscribers),
                "tier_changed": old_tier != new_tier,
                "new_tier": new_tier.value if old_tier != new_tier else None
            }

        except Exception as e:
            log_exception(f"Failed to unsubscribe user from indicator: {e}")
            return {"action": "error", "error": str(e)}

    async def unsubscribe_user_from_all(self, user_id: str) -> dict:
        """Remove user from all indicator subscriptions"""
        try:
            user_indicators = self.user_subscriptions[user_id].copy()
            results = []

            for indicator_key in user_indicators:
                result = await self.unsubscribe_user_from_indicator(user_id, indicator_key)
                results.append(result)

            # Clear user's subscription set
            if user_id in self.user_subscriptions:
                del self.user_subscriptions[user_id]

            log_info(f"🧹 Cleaned up all {len(user_indicators)} indicators for user {user_id}")

            return {
                "action": "user_unsubscribed_from_all",
                "user_id": user_id,
                "indicators_affected": len(user_indicators),
                "cleanup_results": results
            }

        except Exception as e:
            log_exception(f"Failed to unsubscribe user from all indicators: {e}")
            return {"action": "error", "error": str(e)}

    async def _cleanup_indicator_computation(self, indicator_key: str):
        """Stop computation in signal_service"""
        try:
            cleanup_request = {
                "action": "stop_computation",
                "indicator_key": indicator_key,
                "reason": "no_subscribers",
                "timestamp": datetime.utcnow().isoformat()
            }

            await self.redis_client.xadd(
                self.streams["computation_requests"],
                {
                    "request_data": json.dumps(cleanup_request),
                    "timestamp": datetime.utcnow().isoformat()
                }
            )

            log_info(f"📤 Sent cleanup request for {indicator_key}")

        except Exception as e:
            log_exception(f"Failed to cleanup indicator computation: {e}")

    async def _persist_subscription_state(self, indicator_key: str, subscription: IndicatorSubscription):
        """Persist subscription state to Redis"""
        try:
            state_data = {
                "indicator_key": indicator_key,
                "specification": subscription.specification,
                "primary_subscriber": subscription.primary_subscriber,
                "subscribers": subscription.subscribers,
                "created_at": subscription.created_at.isoformat(),
                "current_tier": subscription.current_tier.value,
                "computation_count": subscription.computation_count
            }

            await self.redis_client.setex(
                f"indicator_state:{indicator_key}",
                3600 * 24,  # 24 hours TTL
                json.dumps(state_data, default=str)
            )

        except Exception as e:
            log_exception(f"Failed to persist subscription state: {e}")

    async def _remove_subscription_state(self, indicator_key: str):
        """Remove subscription state from Redis"""
        try:
            await self.redis_client.delete(f"indicator_state:{indicator_key}")
        except Exception as e:
            log_exception(f"Failed to remove subscription state: {e}")

    async def _load_existing_subscriptions(self):
        """Load existing subscription state from Redis"""
        try:
            pattern = "indicator_state:*"
            keys = await self.redis_client.keys(pattern)

            for key in keys:
                try:
                    state_data = await self.redis_client.get(key)
                    if state_data:
                        data = json.loads(state_data)

                        # Reconstruct subscription object
                        subscription = IndicatorSubscription(
                            indicator_key=data["indicator_key"],
                            specification=data["specification"],
                            primary_subscriber=data["primary_subscriber"],
                            current_tier=MonitoringTier(data["current_tier"]),
                            computation_count=data.get("computation_count", 0)
                        )

                        # Restore subscribers
                        for user_id, sub_data in data["subscribers"].items():
                            subscription.subscribers[user_id] = sub_data
                            self.user_subscriptions[user_id].add(data["indicator_key"])

                        self.active_indicators[data["indicator_key"]] = subscription

                except Exception as e:
                    log_warning(f"Failed to load subscription state from {key}: {e}")
                    continue

            log_info(f"📚 Loaded {len(self.active_indicators)} existing indicator subscriptions")

        except Exception as e:
            log_exception(f"Failed to load existing subscriptions: {e}")

    def get_statistics(self) -> dict:
        """Get aggregation statistics"""
        total_indicators = len(self.active_indicators)
        total_subscribers = sum(len(sub.subscribers) for sub in self.active_indicators.values())

        tier_distribution = defaultdict(int)
        for subscription in self.active_indicators.values():
            tier_distribution[subscription.current_tier.value] += 1

        return {
            "total_active_indicators": total_indicators,
            "total_unique_subscriptions": total_subscribers,
            "average_subscribers_per_indicator": total_subscribers / max(1, total_indicators),
            "tier_distribution": dict(tier_distribution),
            "resource_efficiency": {
                "computation_sharing_rate": (total_subscribers - total_indicators) / max(1, total_subscribers),
                "estimated_cost_savings": f"{min(90, (total_subscribers - total_indicators) * 15)}%"
            }
        }


# Global instance
indicator_aggregation_manager = IndicatorAggregationManager()
