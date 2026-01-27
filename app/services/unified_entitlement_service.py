"""
Unified Entitlement Service

Consolidates all entitlement checks into a single decision path, replacing:
1. EntitlementMiddleware (HTTP middleware for API access)
2. SignalStreamContract (Stream subscription entitlements)
3. StreamAbuseProtectionService (Rate limiting and abuse prevention)

ARCHITECTURE COMPLIANCE:
- Single source of truth for all entitlement decisions
- Uses marketplace_service API for subscription data
- Implements unified caching and rate limiting
- Fail-secure by default when external services unavailable
"""
import json
import logging
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

import httpx

from app.core.config import settings
from app.utils.redis import get_redis_client

logger = logging.getLogger(__name__)


class AccessType(Enum):
    """Types of access that can be checked."""
    HTTP_API = "http_api"           # HTTP API endpoint access
    STREAM_SUBSCRIPTION = "stream_subscription"  # WebSocket stream subscription
    SIGNAL_DELIVERY = "signal_delivery"          # Signal delivery entitlement


class FeatureType(Enum):
    """Features that require entitlements."""
    FO_GREEKS_ACCESS = "fo_greeks_access"
    PREMIUM_ANALYSIS = "premium_analysis"
    MARKETPLACE_SIGNALS = "marketplace_signals"
    PERSONAL_SIGNALS = "personal_signals"
    PUBLIC_SIGNALS = "public_signals"
    COMMON_INDICATORS = "common_indicators"


class EntitlementTier(Enum):
    """User subscription tiers."""
    FREE = "free"
    STANDARD = "standard"
    PREMIUM = "premium"
    ENTERPRISE = "enterprise"


@dataclass
class AccessLimits:
    """Access limits for different tiers and features."""
    max_concurrent_connections: int
    max_subscriptions_per_connection: int
    max_api_requests_per_minute: int
    max_stream_messages_per_minute: int
    rapid_subscription_threshold: int  # Max in 10 seconds
    burst_message_threshold: int       # Max in 5 seconds


@dataclass
class EntitlementResult:
    """Result of entitlement check."""
    is_allowed: bool
    reason: str | None = None
    user_tier: str | None = None
    limits: AccessLimits | None = None
    subscription_id: str | None = None
    product_id: str | None = None
    execution_token: str | None = None


@dataclass
class AbuseEvent:
    """Abuse event for audit logging."""
    event_id: str
    user_id: str | None
    client_id: str
    event_type: str
    severity: str
    timestamp: str
    details: dict[str, Any]
    action_taken: str


class UnifiedEntitlementService:
    """
    Unified service for all entitlement checks and rate limiting.

    Replaces EntitlementMiddleware, SignalStreamContract, and StreamAbuseProtectionService
    with a single, consistent entitlement decision path.
    """

    # Default limits for each tier
    DEFAULT_LIMITS = {
        EntitlementTier.FREE: AccessLimits(
            max_concurrent_connections=20,
            max_subscriptions_per_connection=5,
            max_api_requests_per_minute=60,
            max_stream_messages_per_minute=500,
            rapid_subscription_threshold=3,
            burst_message_threshold=25
        ),
        EntitlementTier.STANDARD: AccessLimits(
            max_concurrent_connections=50,
            max_subscriptions_per_connection=15,
            max_api_requests_per_minute=180,
            max_stream_messages_per_minute=1500,
            rapid_subscription_threshold=8,
            burst_message_threshold=75
        ),
        EntitlementTier.PREMIUM: AccessLimits(
            max_concurrent_connections=200,
            max_subscriptions_per_connection=50,
            max_api_requests_per_minute=600,
            max_stream_messages_per_minute=5000,
            rapid_subscription_threshold=20,
            burst_message_threshold=200
        ),
        EntitlementTier.ENTERPRISE: AccessLimits(
            max_concurrent_connections=1000,
            max_subscriptions_per_connection=200,
            max_api_requests_per_minute=2000,
            max_stream_messages_per_minute=20000,
            rapid_subscription_threshold=50,
            burst_message_threshold=500
        )
    }

    # F&O routes that require entitlement checking
    PROTECTED_FO_ROUTES = {
        "/api/v2/signals/fo/greeks/",
        "/api/v2/signals/fo/premium-analysis/",
        "/api/v2/signals/fo/option-chain/",
        "/api/v2/signals/fo/",
    }

    # Premium analysis routes
    PREMIUM_ANALYSIS_ROUTES = {
        "/premium-analysis/expiry",
        "/premium-analysis/strike-range",
        "/premium-analysis/term-structure",
        "/premium-analysis/arbitrage-opportunities/",
    }

    def __init__(self):
        self.redis_client = None
        self.marketplace_client = None

        # Cache settings
        self._entitlement_cache = {}
        self._limits_cache = {}
        self._cache_ttl = 300  # 5 minutes

        # Redis key prefixes
        self.connection_key_prefix = "entitlement:connections:"
        self.rate_limit_key_prefix = "entitlement:rate_limit:"
        self.abuse_log_key = "entitlement:abuse_events"
        self.ban_key_prefix = "entitlement:ban:"

        # Time windows
        self.rate_limit_window = 60      # 1 minute
        self.rapid_subscription_window = 10  # 10 seconds
        self.burst_message_window = 5    # 5 seconds

    async def initialize(self):
        """Initialize the service."""
        self.redis_client = await get_redis_client()

        # Get internal API key for marketplace authentication
        internal_api_key = getattr(settings, 'internal_api_key', None)
        if not internal_api_key:
            raise ValueError("INTERNAL_API_KEY not configured - required for marketplace authentication")

        # Initialize marketplace HTTP client with auth headers
        self.marketplace_client = httpx.AsyncClient(
            base_url=settings.MARKETPLACE_SERVICE_URL.rstrip("/"),
            timeout=30.0,
            headers={
                "X-Internal-API-Key": internal_api_key,
                "User-Agent": "signal-service/unified-entitlement",
                "Content-Type": "application/json"
            }
        )

        logger.info("Unified entitlement service initialized")

    async def close(self):
        """Clean up resources."""
        if self.marketplace_client:
            await self.marketplace_client.aclose()

    async def check_http_access(
        self,
        user_id: str,
        request_path: str,
        client_id: str | None = None
    ) -> EntitlementResult:
        """
        Check HTTP API access entitlement.

        Replaces EntitlementMiddleware functionality.

        Args:
            user_id: User ID from gateway headers
            request_path: Request path being accessed
            client_id: Optional client identifier

        Returns:
            EntitlementResult with access decision
        """
        try:
            if not self.redis_client:
                await self.initialize()

            # Skip entitlement check for non-protected routes
            if not self._is_protected_route(request_path):
                return EntitlementResult(is_allowed=True)

            # Skip for health/admin endpoints
            if any(endpoint in request_path for endpoint in ["/health", "/admin", "/docs", "/openapi"]):
                return EntitlementResult(is_allowed=True)

            # Get user entitlements and tier
            user_data = await self._get_user_entitlements(user_id)
            if not user_data:
                return EntitlementResult(
                    is_allowed=False,
                    reason="Unable to verify user entitlements"
                )

            # Check specific feature access
            if self._requires_premium_analysis(request_path):
                required_feature = FeatureType.PREMIUM_ANALYSIS
            elif self._is_fo_route(request_path):
                required_feature = FeatureType.FO_GREEKS_ACCESS
            else:
                # Default to allowing if not specifically protected
                return EntitlementResult(is_allowed=True, user_tier=user_data.get("tier"))

            # Check feature entitlement
            has_access = await self._check_feature_access(user_id, required_feature, user_data)

            if not has_access:
                await self._log_access_denied(
                    user_id=user_id,
                    client_id=client_id,
                    access_type=AccessType.HTTP_API,
                    feature=required_feature.value,
                    request_path=request_path
                )
                return EntitlementResult(
                    is_allowed=False,
                    reason=f"Access denied. {required_feature.value} requires premium subscription.",
                    user_tier=user_data.get("tier")
                )

            # Check rate limiting
            rate_check = await self._check_api_rate_limit(user_id, user_data.get("tier"))
            if not rate_check[0]:
                return EntitlementResult(
                    is_allowed=False,
                    reason=rate_check[1],
                    user_tier=user_data.get("tier")
                )

            return EntitlementResult(
                is_allowed=True,
                user_tier=user_data.get("tier"),
                limits=self._get_tier_limits(user_data.get("tier"))
            )

        except Exception as e:
            logger.error(f"Error checking HTTP access: {e}")
            # Fail secure - deny access on error
            return EntitlementResult(
                is_allowed=False,
                reason="Entitlement service error"
            )

    async def check_stream_access(
        self,
        user_id: str,
        stream_key: str,
        client_id: str,
        execution_token: str | None = None
    ) -> EntitlementResult:
        """
        Check stream subscription entitlement.

        Replaces SignalStreamContract functionality.

        Args:
            user_id: User ID
            stream_key: Stream key being accessed
            client_id: Client identifier
            execution_token: Optional marketplace execution token

        Returns:
            EntitlementResult with access decision
        """
        try:
            if not self.redis_client:
                await self.initialize()

            # Parse stream key to determine type and requirements
            stream_info = self._parse_stream_key(stream_key)
            if not stream_info:
                return EntitlementResult(
                    is_allowed=False,
                    reason="Invalid stream key format"
                )

            # Get user entitlements
            user_data = await self._get_user_entitlements(user_id)
            if not user_data:
                return EntitlementResult(
                    is_allowed=False,
                    reason="Unable to verify user entitlements"
                )

            # Check specific stream type access
            stream_type = stream_info["type"]

            if stream_type == "public":
                # Public streams - always allowed but with rate limits
                required_feature = FeatureType.PUBLIC_SIGNALS
                has_access = True
            elif stream_type == "common":
                # Common indicators - allowed for all tiers
                required_feature = FeatureType.COMMON_INDICATORS
                has_access = True
            elif stream_type == "marketplace":
                # Marketplace signals - require subscription
                required_feature = FeatureType.MARKETPLACE_SIGNALS
                has_access = await self._check_marketplace_access(
                    user_id, stream_info.get("product_id"), execution_token, user_data
                )
            elif stream_type == "personal":
                # Personal signals - owner only
                required_feature = FeatureType.PERSONAL_SIGNALS
                has_access = (stream_info.get("user_id") == user_id)
            else:
                return EntitlementResult(
                    is_allowed=False,
                    reason=f"Unknown stream type: {stream_type}"
                )

            if not has_access:
                await self._log_access_denied(
                    user_id=user_id,
                    client_id=client_id,
                    access_type=AccessType.STREAM_SUBSCRIPTION,
                    feature=required_feature.value,
                    stream_key=stream_key
                )
                return EntitlementResult(
                    is_allowed=False,
                    reason=f"No access to {stream_type} streams",
                    user_tier=user_data.get("tier")
                )

            # Check stream abuse protection
            abuse_check = await self._check_stream_abuse_protection(
                user_id, client_id, stream_key, user_data.get("tier")
            )
            if not abuse_check[0]:
                return EntitlementResult(
                    is_allowed=False,
                    reason=abuse_check[1],
                    user_tier=user_data.get("tier")
                )

            return EntitlementResult(
                is_allowed=True,
                user_tier=user_data.get("tier"),
                limits=self._get_tier_limits(user_data.get("tier")),
                subscription_id=stream_info.get("subscription_id"),
                product_id=stream_info.get("product_id"),
                execution_token=execution_token
            )

        except Exception as e:
            logger.error(f"Error checking stream access: {e}")
            return EntitlementResult(
                is_allowed=False,
                reason="Stream entitlement service error"
            )

    async def check_delivery_access(
        self,
        user_id: str,
        signal_type: str,
        product_id: str | None = None,
        subscription_id: str | None = None
    ) -> EntitlementResult:
        """
        Check signal delivery entitlement.

        Used by SignalDeliveryService for final access validation before delivery.

        Args:
            user_id: User ID
            signal_type: Type of signal being delivered
            product_id: Optional marketplace product ID
            subscription_id: Optional subscription ID

        Returns:
            EntitlementResult with delivery decision
        """
        try:
            # Special handling for system alerts - bypass entitlement check for system user
            if user_id == "system":
                logger.debug("Allowing system alert delivery - bypassing user entitlement check")
                return EntitlementResult(
                    is_allowed=True,
                    user_tier="system",
                    reason="System alert - no user entitlement required"
                )

            # Get user entitlements
            user_data = await self._get_user_entitlements(user_id)
            if not user_data:
                return EntitlementResult(
                    is_allowed=False,
                    reason="Unable to verify user entitlements for delivery"
                )

            # Map signal type to feature
            feature_mapping = {
                "public": FeatureType.PUBLIC_SIGNALS,
                "common": FeatureType.COMMON_INDICATORS,
                "marketplace": FeatureType.MARKETPLACE_SIGNALS,
                "personal": FeatureType.PERSONAL_SIGNALS,
                "fo_greeks": FeatureType.FO_GREEKS_ACCESS,
                "premium_analysis": FeatureType.PREMIUM_ANALYSIS,
                # CONSOLIDATED: Add missing signal types for system alerts
                "threshold_alert": FeatureType.PUBLIC_SIGNALS,  # Threshold alerts are basic functionality
                "threshold_breach": FeatureType.PUBLIC_SIGNALS,  # Threshold breach notifications
                "computation_complete": FeatureType.PUBLIC_SIGNALS,  # Computation status notifications
                "system_alert": FeatureType.PUBLIC_SIGNALS  # System-level alerts
            }

            required_feature = feature_mapping.get(signal_type)
            if not required_feature:
                return EntitlementResult(
                    is_allowed=False,
                    reason=f"Unknown signal type for delivery: {signal_type}"
                )

            # Check feature access
            has_access = await self._check_feature_access(user_id, required_feature, user_data)

            # For marketplace signals, also verify specific product access
            if signal_type == "marketplace" and product_id:
                has_product_access = await self._check_marketplace_product_access(
                    user_id, product_id, user_data
                )
                has_access = has_access and has_product_access

            if not has_access:
                await self._log_access_denied(
                    user_id=user_id,
                    client_id="delivery",
                    access_type=AccessType.SIGNAL_DELIVERY,
                    feature=required_feature.value,
                    product_id=product_id
                )
                return EntitlementResult(
                    is_allowed=False,
                    reason=f"No delivery access for {signal_type} signals",
                    user_tier=user_data.get("tier")
                )

            return EntitlementResult(
                is_allowed=True,
                user_tier=user_data.get("tier"),
                subscription_id=subscription_id,
                product_id=product_id
            )

        except Exception as e:
            logger.error(f"Error checking delivery access: {e}")
            return EntitlementResult(
                is_allowed=False,
                reason="Signal delivery entitlement error"
            )

    async def _get_user_entitlements(self, user_id: str) -> dict[str, Any] | None:
        """
        Get user entitlements and subscription data from marketplace.

        Caches results to avoid repeated API calls.
        """
        cache_key = f"user_entitlements:{user_id}"

        # Check cache first
        if cache_key in self._entitlement_cache:
            cached_data, cached_time = self._entitlement_cache[cache_key]
            if time.time() - cached_time < self._cache_ttl:
                return cached_data

        try:
            # Get user subscriptions from marketplace
            response = await self.marketplace_client.get(
                f"/api/v1/entitlements/user/{user_id}"
            )

            if response.status_code == 200:
                user_data = response.json()

                # Cache the result
                self._entitlement_cache[cache_key] = (user_data, time.time())

                return user_data
            logger.warning(f"Failed to get user entitlements: {response.status_code}")
            return None

        except Exception as e:
            logger.error(f"Error fetching user entitlements: {e}")
            return None

    async def _check_feature_access(
        self,
        user_id: str,
        feature: FeatureType,
        user_data: dict[str, Any]
    ) -> bool:
        """Check if user has access to specific feature."""
        try:
            # Get user's subscription tier
            user_tier = user_data.get("tier", "free")

            # Define feature access matrix
            feature_access = {
                FeatureType.PUBLIC_SIGNALS: ["free", "standard", "premium", "enterprise"],
                FeatureType.COMMON_INDICATORS: ["free", "standard", "premium", "enterprise"],
                FeatureType.FO_GREEKS_ACCESS: ["premium", "enterprise"],
                FeatureType.PREMIUM_ANALYSIS: ["premium", "enterprise"],
                FeatureType.MARKETPLACE_SIGNALS: ["standard", "premium", "enterprise"],
                FeatureType.PERSONAL_SIGNALS: ["premium", "enterprise"]
            }

            allowed_tiers = feature_access.get(feature, [])

            return user_tier in allowed_tiers

        except Exception as e:
            logger.error(f"Error checking feature access: {e}")
            return False

    async def _check_marketplace_access(
        self,
        user_id: str,
        product_id: str | None,
        execution_token: str | None,
        user_data: dict[str, Any]
    ) -> bool:
        """Check marketplace signal access with token validation."""
        if not product_id:
            return False

        try:
            # Verify execution token if provided
            if execution_token:
                # CONSOLIDATED: Use same endpoint as MarketplaceClient for consistency
                token_response = await self.marketplace_client.post(
                    "/api/v1/integration/verify-execution-token",
                    json={
                        "execution_token": execution_token,
                        "product_id": product_id,
                        "user_id": user_id
                    }
                )

                if token_response.status_code == 200:
                    token_data = token_response.json()
                    return token_data.get("is_valid", False)

            # Check user subscriptions for product access
            user_subscriptions = user_data.get("subscriptions", [])
            for subscription in user_subscriptions:
                if (subscription.get("product_id") == product_id and
                    subscription.get("status") == "active"):
                    return True

            return False

        except Exception as e:
            logger.error(f"Error checking marketplace access: {e}")
            return False

    async def _check_marketplace_product_access(
        self,
        user_id: str,
        product_id: str,
        user_data: dict[str, Any]
    ) -> bool:
        """Check if user has active subscription to specific marketplace product."""
        user_subscriptions = user_data.get("subscriptions", [])

        for subscription in user_subscriptions:
            if (subscription.get("product_id") == product_id and
                subscription.get("status") == "active"):
                return True

        return False

    def _is_protected_route(self, path: str) -> bool:
        """Check if route requires entitlement checking."""
        return any(
            path.startswith(protected_route)
            for protected_route in self.PROTECTED_FO_ROUTES
        )

    def _is_fo_route(self, path: str) -> bool:
        """Check if route is F&O related."""
        return any(
            protected_route in path
            for protected_route in self.PROTECTED_FO_ROUTES
        )

    def _requires_premium_analysis(self, path: str) -> bool:
        """Check if route requires premium analysis entitlement."""
        return any(
            premium_route in path
            for premium_route in self.PREMIUM_ANALYSIS_ROUTES
        )

    def _parse_stream_key(self, stream_key: str) -> dict[str, Any] | None:
        """Parse stream key to extract type and metadata."""
        try:
            # Handle different stream key formats:
            # public:SYMBOL:price
            # common:SYMBOL:sma
            # marketplace:PRODUCT_ID:SYMBOL:SIGNAL
            # personal:USER_ID:SIGNAL_ID:SYMBOL

            parts = stream_key.split(":")

            if len(parts) >= 3:
                stream_type = parts[0]

                if stream_type == "public":
                    return {
                        "type": "public",
                        "instrument": parts[1],
                        "indicator": parts[2]
                    }
                if stream_type == "common":
                    return {
                        "type": "common",
                        "instrument": parts[1],
                        "indicator": parts[2]
                    }
                if stream_type == "marketplace" and len(parts) >= 4:
                    return {
                        "type": "marketplace",
                        "product_id": parts[1],
                        "instrument": parts[2],
                        "signal": parts[3]
                    }
                if stream_type == "personal" and len(parts) >= 4:
                    return {
                        "type": "personal",
                        "user_id": parts[1],
                        "signal_id": parts[2],
                        "instrument": parts[3]
                    }

            return None

        except Exception as e:
            logger.error(f"Error parsing stream key: {e}")
            return None

    def _get_tier_limits(self, tier: str | None) -> AccessLimits:
        """Get access limits for user tier."""
        try:
            tier_enum = EntitlementTier(tier) if tier else EntitlementTier.FREE
            return self.DEFAULT_LIMITS[tier_enum]
        except (ValueError, KeyError):
            return self.DEFAULT_LIMITS[EntitlementTier.FREE]

    async def _check_api_rate_limit(self, user_id: str, tier: str | None) -> tuple[bool, str | None]:
        """Check API rate limiting."""
        try:
            limits = self._get_tier_limits(tier)

            # Check API request rate
            rate_key = f"{self.rate_limit_key_prefix}api:{user_id}"
            current_requests = await self.redis_client.get(rate_key)

            if current_requests:
                current_count = int(current_requests)
                if current_count >= limits.max_api_requests_per_minute:
                    await self._log_abuse_event(
                        user_id=user_id,
                        client_id="api",
                        event_type="api_rate_limit_exceeded",
                        severity="MEDIUM",
                        details={
                            "current_requests": current_count,
                            "limit": limits.max_api_requests_per_minute,
                            "tier": tier
                        }
                    )
                    return False, "API rate limit exceeded"

                # Increment counter
                await self.redis_client.incr(rate_key)
            else:
                # First request in window
                await self.redis_client.setex(rate_key, self.rate_limit_window, 1)

            return True, None

        except Exception as e:
            logger.error(f"Error checking API rate limit: {e}")
            return True, None  # Be permissive on error

    async def _check_stream_abuse_protection(
        self,
        user_id: str,
        client_id: str,
        stream_key: str,
        tier: str | None
    ) -> tuple[bool, str | None]:
        """Check stream abuse protection (consolidated from StreamAbuseProtectionService)."""
        try:
            limits = self._get_tier_limits(tier)

            # Check connection count
            connection_key = f"{self.connection_key_prefix}{user_id}"
            connection_count = await self.redis_client.scard(connection_key)

            if connection_count >= limits.max_concurrent_connections:
                return False, f"Maximum concurrent connections exceeded ({connection_count}/{limits.max_concurrent_connections})"

            # Check rapid subscription rate
            rapid_key = f"{self.rate_limit_key_prefix}rapid_sub:{user_id}"
            rapid_count = await self.redis_client.get(rapid_key)

            if rapid_count:
                rapid_int = int(rapid_count)
                if rapid_int >= limits.rapid_subscription_threshold:
                    await self._log_abuse_event(
                        user_id=user_id,
                        client_id=client_id,
                        event_type="rapid_subscription_exceeded",
                        severity="HIGH",
                        details={
                            "rapid_count": rapid_int,
                            "threshold": limits.rapid_subscription_threshold,
                            "stream_key": stream_key
                        }
                    )
                    return False, "Rapid subscription threshold exceeded"

                await self.redis_client.incr(rapid_key)
            else:
                await self.redis_client.setex(rapid_key, self.rapid_subscription_window, 1)

            # Record connection
            await self.redis_client.sadd(connection_key, client_id)
            await self.redis_client.expire(connection_key, 3600)  # 1 hour expiry

            return True, None

        except Exception as e:
            logger.error(f"Error checking stream abuse protection: {e}")
            return True, None

    async def _log_access_denied(
        self,
        user_id: str,
        client_id: str | None,
        access_type: AccessType,
        feature: str,
        **kwargs
    ):
        """Log access denied events."""
        await self._log_abuse_event(
            user_id=user_id,
            client_id=client_id or "unknown",
            event_type="access_denied",
            severity="MEDIUM",
            details={
                "access_type": access_type.value,
                "feature": feature,
                **kwargs
            }
        )

    async def _log_abuse_event(
        self,
        user_id: str,
        client_id: str,
        event_type: str,
        severity: str,
        details: dict[str, Any]
    ):
        """Log abuse/security events for monitoring."""
        try:
            event = AbuseEvent(
                event_id=str(uuid4()),
                user_id=user_id,
                client_id=client_id,
                event_type=event_type,
                severity=severity,
                timestamp=datetime.now(UTC).isoformat(),
                details=details,
                action_taken="access_denied"
            )

            # Log to structured audit logger
            audit_logger = logging.getLogger("audit.entitlement")
            audit_logger.warning(json.dumps(asdict(event)))

            # Store in Redis for monitoring
            await self.redis_client.lpush(self.abuse_log_key, json.dumps(asdict(event)))
            await self.redis_client.ltrim(self.abuse_log_key, 0, 1000)

        except Exception as e:
            logger.error(f"Error logging abuse event: {e}")

    async def cleanup_connection(self, user_id: str, client_id: str):
        """Clean up connection tracking."""
        try:
            connection_key = f"{self.connection_key_prefix}{user_id}"
            await self.redis_client.srem(connection_key, client_id)
        except Exception as e:
            logger.error(f"Error cleaning up connection: {e}")

    async def get_entitlement_stats(self) -> dict[str, Any]:
        """Get entitlement service statistics."""
        try:
            stats = {
                "cache_entries": len(self._entitlement_cache),
                "limits_cache_entries": len(self._limits_cache)
            }

            # Get abuse events count
            abuse_count = await self.redis_client.llen(self.abuse_log_key)
            stats["recent_abuse_events"] = abuse_count

            # Get active connections count
            connection_keys = await self.redis_client.keys(f"{self.connection_key_prefix}*")
            total_connections = 0
            for key in connection_keys:
                count = await self.redis_client.scard(key)
                total_connections += count
            stats["total_active_connections"] = total_connections

            return stats

        except Exception as e:
            logger.error(f"Error getting entitlement stats: {e}")
            return {}


# Global instance
_unified_entitlement_service = None


async def get_unified_entitlement_service() -> UnifiedEntitlementService:
    """Get global unified entitlement service instance."""
    global _unified_entitlement_service
    if _unified_entitlement_service is None:
        _unified_entitlement_service = UnifiedEntitlementService()
        await _unified_entitlement_service.initialize()
    return _unified_entitlement_service
