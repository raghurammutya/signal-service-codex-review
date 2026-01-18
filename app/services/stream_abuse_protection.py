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
    
    # NO FALLBACK LIMITS - All limits must come from marketplace service
    # This ensures proper entitlement verification and prevents misconfiguration masking
    
    def __init__(self):
        self.redis_client = None
        self.marketplace_client = None
        self._limits_cache = {}  # Cache user limits
        self._limits_cache_ttl = 300  # 5 minutes cache
        
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
    
    async def _get_user_limits(self, user_id: str, stream_type: StreamType) -> ConnectionLimits:
        """
        Get dynamic connection limits for user based on their subscription.
        Sprint 5A: Replace hardcoded tiers with marketplace-based limits.
        
        Args:
            user_id: User ID
            stream_type: Type of stream being accessed
            
        Returns:
            ConnectionLimits based on user's subscription tier
        """
        cache_key = f"{user_id}:{stream_type.value}"
        
        # Check cache first
        if cache_key in self._limits_cache:
            cached_limits, cached_time = self._limits_cache[cache_key]
            if time.time() - cached_time < self._limits_cache_ttl:
                return cached_limits
        
        # Production requires entitlement verification - no fallback limits
        if not self.marketplace_client or not user_id:
            raise RuntimeError(f"Entitlement verification required for stream access - cannot provide {stream_type} limits without marketplace verification")
        
        # Get entitlements from marketplace - fail if unavailable
        try:
            # Get user's subscription tier from marketplace
            subscriptions_data = await self.marketplace_client.get_user_subscriptions(user_id)
            user_subscriptions = subscriptions_data.get("subscriptions", [])
            
            # Find the best tier among active subscriptions
            best_tier = None
            tier_priority = {"enterprise": 3, "premium": 2, "standard": 1, "free": 0}
            
            for subscription in user_subscriptions:
                if subscription.get("status") == "active":
                    tier = subscription.get("tier", "free")
                    if best_tier is None or tier_priority.get(tier, 0) > tier_priority.get(best_tier, 0):
                        best_tier = tier
            
            # Get tier-specific limits - fail if not found
            if not best_tier:
                raise RuntimeError(f"No active subscription found for user {user_id} - cannot provide stream access")
            
            tier_limits = await self._get_tier_limits(best_tier, stream_type)
            if not tier_limits:
                raise RuntimeError(f"Tier limits not available for {best_tier} - cannot provide {stream_type} access")
            
            limits = tier_limits
                        
        except Exception as e:
            logger.error(f"Entitlement verification failed for user {user_id}: {e}")
            raise RuntimeError(f"Stream access denied - entitlement verification required: {e}")
        
        # Cache the result
        self._limits_cache[cache_key] = (limits, time.time())
        
        return limits
    
    async def _get_tier_limits(self, tier: str, stream_type: StreamType) -> Optional[ConnectionLimits]:
        """
        Get connection limits for a specific tier from marketplace service.
        
        Args:
            tier: Subscription tier (free, standard, premium, enterprise)
            stream_type: Type of stream
            
        Returns:
            ConnectionLimits or None if not found
            
        Raises:
            RuntimeError: If marketplace service is unavailable or limits cannot be retrieved
        """
        if not self.marketplace_client:
            raise RuntimeError(
                f"Marketplace client not available - cannot get tier limits for {tier}/{stream_type.value}. "
                f"Stream access requires active marketplace service integration."
            )
        
        try:
            # Get tier limits directly from marketplace service - NO FALLBACKS
            limits_data = await self.marketplace_client.get_tier_limits(tier, stream_type.value)
            
            if not limits_data:
                raise RuntimeError(
                    f"No tier limits available from marketplace for {tier}/{stream_type.value}. "
                    f"Stream access denied - requires valid subscription tier configuration."
                )
            
            # Parse marketplace response into ConnectionLimits
            return ConnectionLimits(
                max_concurrent_connections=limits_data.get('max_concurrent_connections'),
                max_subscriptions_per_connection=limits_data.get('max_subscriptions_per_connection'),
                max_subscription_requests=limits_data.get('max_subscription_requests'),
                max_messages_sent=limits_data.get('max_messages_sent'),
                rapid_subscription_threshold=limits_data.get('rapid_subscription_threshold'),
                burst_message_threshold=limits_data.get('burst_message_threshold')
            )
            
        except Exception as e:
            raise RuntimeError(
                f"Failed to retrieve tier limits from marketplace for {tier}/{stream_type.value}: {e}. "
                f"Stream access denied - marketplace service integration required."
            )
    
    async def check_connection_allowed(
        self,
        client_id: str,
        user_id: Optional[str],
        stream_type: StreamType,
        client_metadata: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if a new connection is allowed based on abuse protection rules.
        
        Args:
            client_id: Unique client identifier
            user_id: User ID (if authenticated)
            stream_type: Type of stream being accessed
            client_metadata: Additional client metadata
            
        Returns:
            Tuple of (allowed, reason_if_denied)
        """
        try:
            if not self.redis_client:
                await self.initialize()
            
            # Get dynamic limits based on user's subscription
            limits = await self._get_user_limits(user_id or client_id, stream_type)
            
            # Check concurrent connections per user
            if user_id:
                user_connections = await self._get_user_connection_count(user_id, stream_type)
                if user_connections >= limits.max_concurrent_connections:
                    await self._log_abuse_event(
                        client_id=client_id,
                        user_id=user_id,
                        event_type="max_connections_exceeded",
                        severity="MEDIUM",
                        details={
                            "current_connections": user_connections,
                            "max_allowed": limits.max_concurrent_connections,
                            "stream_type": stream_type.value
                        },
                        action_taken="connection_rejected"
                    )
                    return False, f"Maximum concurrent connections exceeded ({user_connections}/{limits.max_concurrent_connections})"
            
            # Check for rapid connection attempts
            connection_rate = await self._check_connection_rate(client_id, user_id)
            if connection_rate > 10:  # Max 10 connections per minute
                await self._log_abuse_event(
                    client_id=client_id,
                    user_id=user_id,
                    event_type="rapid_connection_attempts",
                    severity="HIGH",
                    details={
                        "connection_rate": connection_rate,
                        "threshold": 10,
                        "stream_type": stream_type.value
                    },
                    action_taken="connection_rejected"
                )
                return False, "Too many connection attempts. Please slow down."
            
            # Check if client is banned
            is_banned, ban_reason = await self._check_ban_status(client_id, user_id)
            if is_banned:
                return False, f"Client banned: {ban_reason}"
            
            # Record successful connection
            await self._record_connection(client_id, user_id, stream_type, client_metadata)
            
            logger.info(f"Connection allowed for client {client_id} (stream: {stream_type.value})")
            return True, None
            
        except Exception as e:
            logger.error(f"Error checking connection permission: {e}")
            # Fail secure - cannot verify entitlements, deny connection
            return False, f"Connection denied - entitlement verification failed: {e}"
    
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
            # Get dynamic limits based on user's subscription
            limits = await self._get_user_limits(user_id or client_id, stream_type)
            
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
            # Fail secure - cannot verify subscription limits, deny subscription
            return False, f"Subscription denied - entitlement verification failed: {e}"
    
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
            # Get dynamic limits based on user's subscription
            limits = await self._get_user_limits(user_id or client_id, stream_type)
            
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
            # Fail secure - cannot verify rate limits, deny message
            return False, f"Message denied - rate limit verification failed: {e}"
    
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