"""
Stream Abuse Protection Service

Enhancement 2: Add rate limiting and per-connection caps for public/common signal subscriptions.
- Log abuse events and reject excessive subscriptions.
- Protect against DoS attacks and resource exhaustion.
"""
import asyncio
import json
import time
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Set, Optional, Any, List, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
from uuid import uuid4

from app.utils.redis import get_redis_client
from app.core.config import settings
from app.services.unified_entitlement_service import get_unified_entitlement_service, EntitlementResult

logger = logging.getLogger(__name__)


class StreamType(Enum):
    """Types of signal streams with different protection levels."""
    PUBLIC = "public"           # Free signals (most restrictive)
    COMMON = "common"          # Basic tier signals  
    PREMIUM = "premium"        # Premium tier signals (least restrictive)
    MARKETPLACE = "marketplace" # Marketplace signals (moderate restrictions)


@dataclass
class ConnectionLimits:
    """Rate limits and connection caps for different stream types."""
    # Connection limits
    max_concurrent_connections: int
    max_subscriptions_per_connection: int
    
    # Rate limits (per minute)
    max_subscription_requests: int
    max_messages_sent: int
    
    # Abuse thresholds
    rapid_subscription_threshold: int  # Max subscriptions in 10 seconds
    burst_message_threshold: int      # Max messages in 5 seconds


@dataclass
class AbuseEvent:
    """Abuse event for audit logging."""
    event_id: str
    client_id: str
    user_id: Optional[str]
    event_type: str
    severity: str
    timestamp: str
    details: Dict[str, Any]
    action_taken: str


class StreamAbuseProtectionService:
    """Service for protecting public signal streams from abuse."""
    
    # Fallback limits if marketplace service is unavailable
    FALLBACK_LIMITS = {
        StreamType.PUBLIC: ConnectionLimits(
            max_concurrent_connections=50,      # Max 50 connections per user
            max_subscriptions_per_connection=10, # Max 10 symbols per connection
            max_subscription_requests=30,        # 30 subscription changes per minute
            max_messages_sent=1000,              # 1000 messages per minute  
            rapid_subscription_threshold=5,      # Max 5 subscriptions in 10 seconds
            burst_message_threshold=50           # Max 50 messages in 5 seconds
        ),
        StreamType.COMMON: ConnectionLimits(
            max_concurrent_connections=100,
            max_subscriptions_per_connection=25,
            max_subscription_requests=60,
            max_messages_sent=2000,
            rapid_subscription_threshold=10,
            burst_message_threshold=100
        ),
        StreamType.PREMIUM: ConnectionLimits(
            max_concurrent_connections=500,
            max_subscriptions_per_connection=100,
            max_subscription_requests=200,
            max_messages_sent=10000,
            rapid_subscription_threshold=25,
            burst_message_threshold=250
        ),
        StreamType.MARKETPLACE: ConnectionLimits(
            max_concurrent_connections=200,
            max_subscriptions_per_connection=50,
            max_subscription_requests=120,
            max_messages_sent=5000,
            rapid_subscription_threshold=15,
            burst_message_threshold=150
        )
    }
    
    def __init__(self):
        self.redis_client = None
        self.marketplace_client = None
        
        # Tracking keys
        self.connection_key_prefix = "stream_abuse:connections:"
        self.subscription_key_prefix = "stream_abuse:subscriptions:"
        self.rate_limit_key_prefix = "stream_abuse:rate_limit:"
        self.abuse_log_key = "stream_abuse:events"
        
        # Time windows
        self.rate_limit_window = 60      # 1 minute
        self.rapid_subscription_window = 10  # 10 seconds
        self.burst_message_window = 5    # 5 seconds
    
    async def initialize(self):
        """Initialize the service."""
        self.redis_client = await get_redis_client()
        
        # Initialize marketplace client for dynamic limits
        try:
            from app.services.marketplace_client import create_marketplace_client
            self.marketplace_client = create_marketplace_client()
        except Exception as e:
            logger.warning(f"Could not initialize marketplace client: {e}")
            self.marketplace_client = None
        
        logger.info("Stream abuse protection service initialized")
    
    
    def _get_tier_limits_from_unified_tier(self, tier: str, stream_type: StreamType) -> ConnectionLimits:
        """
        CONSOLIDATED: Get connection limits from unified tier information.
        Replaces _get_user_limits for consistent tier-based limits.
        """
        # Define tier multipliers relative to base (free) limits
        tier_multipliers = {
            "free": 1.0,
            "standard": 2.0,
            "premium": 5.0,
            "enterprise": 10.0
        }
        
        multiplier = tier_multipliers.get(tier, 1.0)
        base_limits = self.FALLBACK_LIMITS[stream_type]
        
        # Apply multiplier to all limits
        return ConnectionLimits(
            max_concurrent_connections=int(base_limits.max_concurrent_connections * multiplier),
            max_subscriptions_per_connection=int(base_limits.max_subscriptions_per_connection * multiplier),
            max_subscription_requests=int(base_limits.max_subscription_requests * multiplier),
            max_messages_sent=int(base_limits.max_messages_sent * multiplier),
            rapid_subscription_threshold=int(base_limits.rapid_subscription_threshold * multiplier),
            burst_message_threshold=int(base_limits.burst_message_threshold * multiplier)
        )
    
    
    async def check_connection_allowed(
        self,
        client_id: str,
        user_id: Optional[str],
        stream_type: StreamType,
        client_metadata: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if a new connection is allowed - delegates to unified entitlement service.
        
        Args:
            client_id: Unique client identifier
            user_id: User ID (if authenticated)
            stream_type: Type of stream being accessed
            client_metadata: Additional client metadata
            
        Returns:
            Tuple of (allowed, reason_if_denied)
        """
        try:
            # CONSOLIDATED: No legacy fallbacks - all connections must go through unified entitlement
            if not user_id:
                # Unauthenticated connections not allowed for any stream type
                logger.warning(f"Unauthenticated connection denied for client {client_id} (stream: {stream_type.value})")
                return False, "Authentication required for all stream access"
            
            # PRODUCTION: Connection-level validation should check user capabilities, not specific streams
            # Specific stream access is validated at subscription time with real stream keys
            entitlement_service = await get_unified_entitlement_service()
            user_data = await entitlement_service._get_user_entitlements(user_id)
            
            if not user_data:
                result = EntitlementResult(is_allowed=False, reason="Unable to verify user entitlements")
            else:
                user_tier = user_data.get("tier", "free")
                
                # Check if user tier supports the requested stream type
                stream_access_matrix = {
                    StreamType.PUBLIC: ["free", "standard", "premium", "enterprise"],
                    StreamType.COMMON: ["free", "standard", "premium", "enterprise"], 
                    StreamType.MARKETPLACE: ["standard", "premium", "enterprise"],
                    StreamType.PREMIUM: ["premium", "enterprise"]
                }
                
                allowed_tiers = stream_access_matrix.get(stream_type, [])
                
                if user_tier in allowed_tiers:
                    result = EntitlementResult(is_allowed=True, user_tier=user_tier)
                    logger.info(f"User {user_id} tier '{user_tier}' authorized for {stream_type.value} streams")
                else:
                    result = EntitlementResult(
                        is_allowed=False,
                        reason=f"{stream_type.value} access requires {' or '.join(allowed_tiers)} tier (current: {user_tier})",
                        user_tier=user_tier
                    )
            
            if result.is_allowed:
                logger.info(f"Connection allowed for client {client_id} (stream: {stream_type.value})")
                return True, None
            else:
                logger.warning(f"Connection denied for client {client_id}: {result.reason}")
                return False, result.reason
            
        except Exception as e:
            logger.error(f"Error checking connection permission: {e}")
            # CONSOLIDATED: No legacy fallback - fail secure on unified service errors
            return False, "Entitlement service error - access denied for security"
    
    async def check_subscription_allowed(
        self,
        client_id: str,
        user_id: Optional[str],
        stream_type: StreamType,
        new_subscriptions: List[str],
        current_subscriptions: Optional[Set[str]] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if subscription changes are allowed.
        
        Args:
            client_id: Client identifier
            user_id: User ID (if authenticated)
            stream_type: Stream type being accessed
            new_subscriptions: List of new symbols to subscribe to
            current_subscriptions: Current subscriptions (if available)
            
        Returns:
            Tuple of (allowed, reason_if_denied)
        """
        try:
            # CONSOLIDATED: Get limits via unified entitlement service instead of legacy path
            if not user_id:
                return False, "Authentication required for subscription changes"
            
            entitlement_service = await get_unified_entitlement_service()
            user_data = await entitlement_service._get_user_entitlements(user_id)
            
            if not user_data:
                return False, "Unable to verify user entitlements for subscription limits"
            
            # Get tier-based limits from unified service
            user_tier = user_data.get("tier", "free")
            limits = self._get_tier_limits_from_unified_tier(user_tier, stream_type)
            
            # Check total subscription count
            if current_subscriptions:
                total_after_change = len(current_subscriptions) + len(new_subscriptions)
            else:
                total_after_change = len(new_subscriptions)
            
            if total_after_change > limits.max_subscriptions_per_connection:
                await self._log_abuse_event(
                    client_id=client_id,
                    user_id=user_id,
                    event_type="max_subscriptions_exceeded",
                    severity="MEDIUM",
                    details={
                        "requested_total": total_after_change,
                        "max_allowed": limits.max_subscriptions_per_connection,
                        "stream_type": stream_type.value,
                        "new_subscriptions": new_subscriptions
                    },
                    action_taken="subscription_rejected"
                )
                return False, f"Maximum subscriptions exceeded ({total_after_change}/{limits.max_subscriptions_per_connection})"
            
            # Check subscription rate limiting
            subscription_rate = await self._check_subscription_rate(client_id, user_id, stream_type)
            if subscription_rate >= limits.max_subscription_requests:
                await self._log_abuse_event(
                    client_id=client_id,
                    user_id=user_id,
                    event_type="subscription_rate_limit_exceeded",
                    severity="MEDIUM", 
                    details={
                        "current_rate": subscription_rate,
                        "max_allowed": limits.max_subscription_requests,
                        "stream_type": stream_type.value
                    },
                    action_taken="subscription_rejected"
                )
                return False, "Subscription rate limit exceeded. Please slow down."
            
            # Check for rapid subscription changes (potential DoS)
            rapid_changes = await self._check_rapid_subscription_changes(client_id, user_id)
            if rapid_changes >= limits.rapid_subscription_threshold:
                await self._log_abuse_event(
                    client_id=client_id,
                    user_id=user_id,
                    event_type="rapid_subscription_changes",
                    severity="HIGH",
                    details={
                        "rapid_changes": rapid_changes,
                        "threshold": limits.rapid_subscription_threshold,
                        "window_seconds": self.rapid_subscription_window,
                        "stream_type": stream_type.value
                    },
                    action_taken="subscription_rejected_temporary_ban"
                )
                
                # Temporary ban for rapid changes
                await self._apply_temporary_ban(client_id, user_id, duration_minutes=5)
                return False, "Too many rapid subscription changes. Temporarily banned for 5 minutes."
            
            # Record subscription change
            await self._record_subscription_change(client_id, user_id, stream_type, new_subscriptions)
            
            return True, None
            
        except Exception as e:
            logger.error(f"Error checking subscription permission: {e}")
            # FAIL SECURE: Deny access on error instead of being permissive
            return False, "Subscription entitlement service error - access denied for security"
    
    async def check_message_rate(
        self,
        client_id: str,
        user_id: Optional[str],
        stream_type: StreamType,
        message_count: int = 1
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if sending messages is within rate limits.
        
        Args:
            client_id: Client identifier
            user_id: User ID
            stream_type: Stream type
            message_count: Number of messages being sent
            
        Returns:
            Tuple of (allowed, reason_if_denied)
        """
        try:
            # CONSOLIDATED: Get limits via unified entitlement service instead of legacy path
            if not user_id:
                return False, "Authentication required for message rate limiting"
            
            entitlement_service = await get_unified_entitlement_service()
            user_data = await entitlement_service._get_user_entitlements(user_id)
            
            if not user_data:
                return False, "Unable to verify user entitlements for message rate limits"
            
            # Get tier-based limits from unified service
            user_tier = user_data.get("tier", "free")
            limits = self._get_tier_limits_from_unified_tier(user_tier, stream_type)
            
            # Check message rate limit
            current_rate = await self._get_message_rate(client_id, user_id, stream_type)
            if current_rate + message_count > limits.max_messages_sent:
                await self._log_abuse_event(
                    client_id=client_id,
                    user_id=user_id,
                    event_type="message_rate_limit_exceeded",
                    severity="MEDIUM",
                    details={
                        "current_rate": current_rate,
                        "message_count": message_count,
                        "max_allowed": limits.max_messages_sent,
                        "stream_type": stream_type.value
                    },
                    action_taken="message_rate_limited"
                )
                return False, "Message rate limit exceeded"
            
            # Check burst message protection
            burst_rate = await self._get_burst_message_rate(client_id, user_id)
            if burst_rate + message_count > limits.burst_message_threshold:
                await self._log_abuse_event(
                    client_id=client_id,
                    user_id=user_id,
                    event_type="burst_message_limit_exceeded",
                    severity="HIGH",
                    details={
                        "burst_rate": burst_rate,
                        "message_count": message_count,
                        "threshold": limits.burst_message_threshold,
                        "window_seconds": self.burst_message_window,
                        "stream_type": stream_type.value
                    },
                    action_taken="burst_protection_activated"
                )
                return False, "Message burst limit exceeded"
            
            # Record message send
            await self._record_messages_sent(client_id, user_id, stream_type, message_count)
            
            return True, None
            
        except Exception as e:
            logger.error(f"Error checking message rate: {e}")
            # FAIL SECURE: Deny access on error instead of being permissive
            return False, "Message rate entitlement service error - access denied for security"
    
    async def cleanup_connection(
        self,
        client_id: str,
        user_id: Optional[str],
        stream_type: StreamType
    ):
        """Clean up tracking data for disconnected client."""
        try:
            # Remove connection tracking
            connection_key = f"{self.connection_key_prefix}{stream_type.value}:{user_id or client_id}"
            await self.redis_client.srem(connection_key, client_id)
            
            # Remove subscription tracking
            subscription_key = f"{self.subscription_key_prefix}{client_id}"
            await self.redis_client.delete(subscription_key)
            
            logger.info(f"Cleaned up tracking for client {client_id}")
            
        except Exception as e:
            logger.error(f"Error cleaning up connection: {e}")
    
    async def get_abuse_statistics(self) -> Dict[str, Any]:
        """Get abuse protection statistics for monitoring."""
        try:
            stats = {}
            
            # Get recent abuse events
            recent_events = await self.redis_client.lrange(self.abuse_log_key, 0, 100)
            stats["recent_abuse_events"] = len(recent_events)
            
            # Get connection counts by stream type
            for stream_type in StreamType:
                key = f"{self.connection_key_prefix}{stream_type.value}:*"
                keys = await self.redis_client.keys(key)
                total_connections = 0
                for key in keys:
                    count = await self.redis_client.scard(key)
                    total_connections += count
                stats[f"connections_{stream_type.value}"] = total_connections
            
            # Get ban statistics
            ban_keys = await self.redis_client.keys("stream_abuse:ban:*")
            stats["active_bans"] = len(ban_keys)
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting abuse statistics: {e}")
            return {}
    
    async def _get_user_connection_count(self, user_id: str, stream_type: StreamType) -> int:
        """Get current connection count for user."""
        connection_key = f"{self.connection_key_prefix}{stream_type.value}:{user_id}"
        return await self.redis_client.scard(connection_key)
    
    async def _check_connection_rate(self, client_id: str, user_id: Optional[str]) -> int:
        """Check connection rate for abuse detection."""
        key = f"{self.rate_limit_key_prefix}connect:{user_id or client_id}"
        current = await self.redis_client.get(key)
        if current:
            await self.redis_client.incr(key)
            return int(current) + 1
        else:
            await self.redis_client.setex(key, self.rate_limit_window, 1)
            return 1
    
    async def _check_ban_status(self, client_id: str, user_id: Optional[str]) -> Tuple[bool, Optional[str]]:
        """Check if client/user is banned."""
        # Check client ban
        client_ban_key = f"stream_abuse:ban:client:{client_id}"
        client_ban = await self.redis_client.get(client_ban_key)
        if client_ban:
            return True, f"Client banned: {client_ban.decode()}"
        
        # Check user ban
        if user_id:
            user_ban_key = f"stream_abuse:ban:user:{user_id}"
            user_ban = await self.redis_client.get(user_ban_key)
            if user_ban:
                return True, f"User banned: {user_ban.decode()}"
        
        return False, None
    
    async def _record_connection(
        self,
        client_id: str,
        user_id: Optional[str],
        stream_type: StreamType,
        metadata: Optional[Dict[str, Any]]
    ):
        """Record successful connection for tracking."""
        connection_key = f"{self.connection_key_prefix}{stream_type.value}:{user_id or client_id}"
        await self.redis_client.sadd(connection_key, client_id)
        await self.redis_client.expire(connection_key, 3600)  # 1 hour expiry
    
    async def _check_subscription_rate(self, client_id: str, user_id: Optional[str], stream_type: StreamType) -> int:
        """Check subscription change rate."""
        key = f"{self.rate_limit_key_prefix}subscription:{stream_type.value}:{user_id or client_id}"
        current = await self.redis_client.get(key)
        if current:
            await self.redis_client.incr(key)
            return int(current) + 1
        else:
            await self.redis_client.setex(key, self.rate_limit_window, 1)
            return 1
    
    async def _check_rapid_subscription_changes(self, client_id: str, user_id: Optional[str]) -> int:
        """Check for rapid subscription changes (DoS protection)."""
        key = f"{self.rate_limit_key_prefix}rapid_sub:{user_id or client_id}"
        current = await self.redis_client.get(key)
        if current:
            await self.redis_client.incr(key)
            return int(current) + 1
        else:
            await self.redis_client.setex(key, self.rapid_subscription_window, 1)
            return 1
    
    async def _record_subscription_change(
        self,
        client_id: str,
        user_id: Optional[str],
        stream_type: StreamType,
        subscriptions: List[str]
    ):
        """Record subscription change for tracking."""
        # Just increment counters - actual recording is handled by rate check
        pass
    
    async def _get_message_rate(self, client_id: str, user_id: Optional[str], stream_type: StreamType) -> int:
        """Get current message rate."""
        key = f"{self.rate_limit_key_prefix}messages:{stream_type.value}:{user_id or client_id}"
        current = await self.redis_client.get(key)
        return int(current) if current else 0
    
    async def _get_burst_message_rate(self, client_id: str, user_id: Optional[str]) -> int:
        """Get current burst message rate."""
        key = f"{self.rate_limit_key_prefix}burst:{user_id or client_id}"
        current = await self.redis_client.get(key)
        return int(current) if current else 0
    
    async def _record_messages_sent(
        self,
        client_id: str,
        user_id: Optional[str],
        stream_type: StreamType,
        count: int
    ):
        """Record messages sent for rate limiting."""
        # Update minute window
        key = f"{self.rate_limit_key_prefix}messages:{stream_type.value}:{user_id or client_id}"
        current = await self.redis_client.get(key)
        if current:
            await self.redis_client.incrby(key, count)
        else:
            await self.redis_client.setex(key, self.rate_limit_window, count)
        
        # Update burst window
        burst_key = f"{self.rate_limit_key_prefix}burst:{user_id or client_id}"
        burst_current = await self.redis_client.get(burst_key)
        if burst_current:
            await self.redis_client.incrby(burst_key, count)
        else:
            await self.redis_client.setex(burst_key, self.burst_message_window, count)
    
    async def _apply_temporary_ban(self, client_id: str, user_id: Optional[str], duration_minutes: int):
        """Apply temporary ban for abuse."""
        ban_reason = f"Temporary ban for {duration_minutes} minutes due to abuse"
        
        # Ban client
        client_ban_key = f"stream_abuse:ban:client:{client_id}"
        await self.redis_client.setex(client_ban_key, duration_minutes * 60, ban_reason)
        
        # Ban user if available
        if user_id:
            user_ban_key = f"stream_abuse:ban:user:{user_id}"
            await self.redis_client.setex(user_ban_key, duration_minutes * 60, ban_reason)
        
        logger.warning(f"Applied temporary ban to client {client_id} (user: {user_id}) for {duration_minutes} minutes")
    
    async def _log_abuse_event(
        self,
        client_id: str,
        user_id: Optional[str],
        event_type: str,
        severity: str,
        details: Dict[str, Any],
        action_taken: str
    ):
        """Log abuse event for monitoring and analysis."""
        event = AbuseEvent(
            event_id=str(uuid4()),
            client_id=client_id,
            user_id=user_id,
            event_type=event_type,
            severity=severity,
            timestamp=datetime.now(timezone.utc).isoformat(),
            details=details,
            action_taken=action_taken
        )
        
        # Log to structured logs
        abuse_logger = logging.getLogger("audit.stream_abuse")
        abuse_logger.warning(json.dumps(asdict(event)))
        
        # Store in Redis for real-time monitoring
        await self.redis_client.lpush(self.abuse_log_key, json.dumps(asdict(event)))
        await self.redis_client.ltrim(self.abuse_log_key, 0, 1000)  # Keep last 1000 events
        
        # Log to main logger based on severity
        if severity == "CRITICAL":
            logger.critical(f"STREAM ABUSE: {event_type} - {details}")
        elif severity == "HIGH":
            logger.error(f"STREAM ABUSE: {event_type} - {details}")
        else:
            logger.warning(f"Stream abuse detected: {event_type} - client: {client_id}")


# Global instance
_abuse_protection_service = None


async def get_stream_abuse_protection() -> StreamAbuseProtectionService:
    """Get global stream abuse protection service instance."""
    global _abuse_protection_service
    if _abuse_protection_service is None:
        _abuse_protection_service = StreamAbuseProtectionService()
        await _abuse_protection_service.initialize()
    return _abuse_protection_service