#!/usr/bin/env python3
"""
Subscription Storage Models - Phase 2 Migration

SUB_001: Subscription Manager Migration
- Updated storage schema to use instrument_key as primary index
- Migration utilities for existing token-based subscriptions  
- Registry integration for subscription validation
- Performance monitoring and health checks
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import json
import uuid
from app.sdk import InstrumentClient, create_instrument_client

logger = logging.getLogger(__name__)

class SubscriptionStatus(Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    MIGRATING = "migrating"
    ERROR = "error"

class SubscriptionType(Enum):
    REAL_TIME_QUOTES = "real_time_quotes"
    MARKET_DEPTH = "market_depth"
    TRADES = "trades"
    OHLC = "ohlc"
    NEWS = "news"
    CORPORATE_ACTIONS = "corporate_actions"
    
class DataFrequency(Enum):
    TICK = "tick"
    SECOND = "1s"
    MINUTE = "1m"
    FIVE_MINUTE = "5m"
    HOUR = "1h"
    DAY = "1d"

@dataclass
class SubscriptionPreferences:
    """User subscription preferences using instrument_key"""
    max_subscriptions: int = 100
    default_frequency: DataFrequency = DataFrequency.TICK
    auto_subscribe_sectors: List[str] = field(default_factory=list)
    excluded_exchanges: List[str] = field(default_factory=list)
    notification_channels: List[str] = field(default_factory=lambda: ["websocket"])
    rate_limiting: Dict[str, int] = field(default_factory=lambda: {"max_per_second": 1000})

@dataclass
class Subscription:
    """
    Core subscription model with instrument_key as primary identifier
    
    Phase 2 Migration: All subscriptions indexed by instrument_key,
    with registry metadata integration and performance monitoring.
    """
    subscription_id: str
    user_id: str
    instrument_key: str                    # Primary identifier - NO tokens
    symbol: str                           # Enriched from registry
    exchange: str                         # Enriched from registry  
    sector: str                          # Enriched from registry
    subscription_type: SubscriptionType
    data_frequency: DataFrequency
    status: SubscriptionStatus
    created_at: datetime = field(default_factory=datetime.now)
    last_updated: datetime = field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None
    
    # Subscription configuration
    filters: Dict[str, Any] = field(default_factory=dict)
    delivery_config: Dict[str, Any] = field(default_factory=dict)
    
    # Performance and monitoring
    message_count: int = 0
    last_message_at: Optional[datetime] = None
    error_count: int = 0
    last_error_at: Optional[datetime] = None
    
    # Migration tracking
    migrated_from_token: Optional[str] = None  # Track legacy token migration
    migration_timestamp: Optional[datetime] = None
    
    # Internal fields - not exposed
    _registry_metadata: Optional[Dict[str, Any]] = None
    _delivery_endpoint: Optional[str] = None

@dataclass
class SubscriptionMigrationRecord:
    """Record tracking subscription migration from token to instrument_key"""
    migration_id: str
    original_token: str
    instrument_key: str
    user_id: str
    migration_status: str
    migration_timestamp: datetime
    validation_results: Dict[str, Any] = field(default_factory=dict)
    rollback_data: Optional[Dict[str, Any]] = None

class SubscriptionStorage:
    """
    Subscription Storage Layer - Phase 2 Migration
    
    SUB_001: Storage operations using instrument_key indexing with
    migration utilities and registry integration.
    """
    
    def __init__(self, 
                 instrument_client: Optional[InstrumentClient] = None,
                 redis_client=None,
                 database_client=None):
        """
        Initialize subscription storage
        
        Args:
            instrument_client: Phase 1 SDK client for metadata
            redis_client: Redis for caching and real-time data
            database_client: Persistent storage for subscriptions
        """
        self.instrument_client = instrument_client or create_instrument_client()
        self.redis_client = redis_client  # Mock for now
        self.database_client = database_client  # Mock for now
        
        # In-memory storage for development/testing
        self._subscriptions: Dict[str, Subscription] = {}
        self._user_subscriptions: Dict[str, List[str]] = {}  # user_id -> subscription_ids
        self._instrument_subscriptions: Dict[str, List[str]] = {}  # instrument_key -> subscription_ids
        self._migration_records: Dict[str, SubscriptionMigrationRecord] = {}
        
        # Performance tracking
        self._performance_metrics = {
            "total_subscriptions": 0,
            "active_subscriptions": 0,
            "migration_count": 0,
            "error_count": 0,
            "last_performance_check": datetime.now()
        }
    
    # =============================================================================
    # CORE SUBSCRIPTION OPERATIONS (instrument_key-based)
    # =============================================================================
    
    async def create_subscription(self,
                                user_id: str,
                                instrument_key: str,
                                subscription_type: SubscriptionType,
                                data_frequency: DataFrequency = DataFrequency.TICK,
                                filters: Optional[Dict[str, Any]] = None,
                                delivery_config: Optional[Dict[str, Any]] = None,
                                expires_in_hours: Optional[int] = None) -> Subscription:
        """
        Create new subscription using instrument_key
        
        Args:
            user_id: User identifier
            instrument_key: Primary identifier (e.g., "AAPL_NASDAQ_EQUITY")
            subscription_type: Type of subscription
            data_frequency: Data delivery frequency
            filters: Optional data filters
            delivery_config: Delivery configuration
            expires_in_hours: Optional expiration time
            
        Returns:
            Subscription: Created subscription with metadata
        """
        # Validate instrument via registry
        try:
            metadata = await self.instrument_client.get_instrument_metadata(instrument_key)
        except Exception as e:
            logger.error(f"Failed to validate instrument {instrument_key}: {e}")
            raise ValueError(f"Invalid instrument: {instrument_key}")
        
        # Check user subscription limits
        user_subs = self._user_subscriptions.get(user_id, [])
        if len(user_subs) >= 100:  # Default limit
            raise ValueError(f"User {user_id} has reached subscription limit")
        
        # Create subscription
        subscription_id = f"sub_{instrument_key}_{user_id}_{uuid.uuid4().hex[:8]}"
        expires_at = datetime.now() + timedelta(hours=expires_in_hours) if expires_in_hours else None
        
        subscription = Subscription(
            subscription_id=subscription_id,
            user_id=user_id,
            instrument_key=instrument_key,
            symbol=metadata.symbol,
            exchange=metadata.exchange,
            sector=metadata.sector or "Unknown",
            subscription_type=subscription_type,
            data_frequency=data_frequency,
            status=SubscriptionStatus.ACTIVE,
            expires_at=expires_at,
            filters=filters or {},
            delivery_config=delivery_config or {"channel": "websocket"},
            _registry_metadata=self._convert_metadata_to_dict(metadata)
        )
        
        # Store subscription
        await self._store_subscription(subscription)
        
        logger.info(f"Subscription created: {subscription_id} for {instrument_key} ({metadata.symbol})")
        
        return subscription
    
    async def get_subscription(self, subscription_id: str) -> Optional[Subscription]:
        """Get subscription by ID"""
        return self._subscriptions.get(subscription_id)
    
    async def get_user_subscriptions(self, user_id: str, status_filter: Optional[SubscriptionStatus] = None) -> List[Subscription]:
        """Get all subscriptions for a user"""
        subscription_ids = self._user_subscriptions.get(user_id, [])
        subscriptions = []
        
        for sub_id in subscription_ids:
            subscription = self._subscriptions.get(sub_id)
            if subscription:
                if status_filter is None or subscription.status == status_filter:
                    subscriptions.append(subscription)
        
        return subscriptions
    
    async def get_instrument_subscriptions(self, instrument_key: str) -> List[Subscription]:
        """Get all subscriptions for an instrument"""
        subscription_ids = self._instrument_subscriptions.get(instrument_key, [])
        subscriptions = []
        
        for sub_id in subscription_ids:
            subscription = self._subscriptions.get(sub_id)
            if subscription and subscription.status == SubscriptionStatus.ACTIVE:
                subscriptions.append(subscription)
        
        return subscriptions
    
    async def update_subscription_status(self, subscription_id: str, status: SubscriptionStatus) -> bool:
        """Update subscription status"""
        subscription = self._subscriptions.get(subscription_id)
        if not subscription:
            return False
        
        subscription.status = status
        subscription.last_updated = datetime.now()
        
        # Update performance metrics
        self._update_performance_metrics()
        
        logger.info(f"Subscription {subscription_id} status updated to {status.value}")
        return True
    
    async def cancel_subscription(self, subscription_id: str, user_id: str) -> bool:
        """Cancel subscription with user validation"""
        subscription = self._subscriptions.get(subscription_id)
        if not subscription:
            return False
        
        if subscription.user_id != user_id:
            raise ValueError("Unauthorized: User cannot cancel this subscription")
        
        subscription.status = SubscriptionStatus.CANCELLED
        subscription.last_updated = datetime.now()
        
        # Remove from active indexes
        await self._remove_from_indexes(subscription)
        
        logger.info(f"Subscription cancelled: {subscription_id}")
        return True
    
    # =============================================================================
    # MIGRATION UTILITIES (token → instrument_key)
    # =============================================================================
    
    async def migrate_token_subscription(self,
                                       user_id: str,
                                       legacy_token: str,
                                       subscription_type: SubscriptionType,
                                       data_frequency: DataFrequency = DataFrequency.TICK) -> SubscriptionMigrationRecord:
        """
        Migrate legacy token-based subscription to instrument_key
        
        Args:
            user_id: User identifier
            legacy_token: Legacy instrument token
            subscription_type: Subscription type
            data_frequency: Data frequency
            
        Returns:
            SubscriptionMigrationRecord: Migration tracking record
        """
        migration_id = f"migration_{legacy_token}_{user_id}_{uuid.uuid4().hex[:8]}"
        
        try:
            # Attempt to resolve token to instrument_key via registry
            # This is a simplified lookup - in practice would use comprehensive token mapping
            instrument_key = await self._resolve_token_to_key(legacy_token)
            
            if not instrument_key:
                raise ValueError(f"Cannot resolve token {legacy_token} to instrument_key")
            
            # Create new subscription
            subscription = await self.create_subscription(
                user_id=user_id,
                instrument_key=instrument_key,
                subscription_type=subscription_type,
                data_frequency=data_frequency
            )
            
            # Mark as migrated
            subscription.migrated_from_token = legacy_token
            subscription.migration_timestamp = datetime.now()
            
            # Create migration record
            migration_record = SubscriptionMigrationRecord(
                migration_id=migration_id,
                original_token=legacy_token,
                instrument_key=instrument_key,
                user_id=user_id,
                migration_status="completed",
                migration_timestamp=datetime.now(),
                validation_results={
                    "subscription_created": True,
                    "instrument_validated": True,
                    "metadata_enriched": True
                }
            )
            
            self._migration_records[migration_id] = migration_record
            self._performance_metrics["migration_count"] += 1
            
            logger.info(f"Token migration completed: {legacy_token} → {instrument_key}")
            
            return migration_record
            
        except Exception as e:
            # Create failed migration record
            migration_record = SubscriptionMigrationRecord(
                migration_id=migration_id,
                original_token=legacy_token,
                instrument_key="",
                user_id=user_id,
                migration_status="failed",
                migration_timestamp=datetime.now(),
                validation_results={
                    "error": str(e),
                    "subscription_created": False
                }
            )
            
            self._migration_records[migration_id] = migration_record
            self._performance_metrics["error_count"] += 1
            
            logger.error(f"Token migration failed: {legacy_token} - {e}")
            raise
    
    async def bulk_migrate_subscriptions(self, migration_requests: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Bulk migrate multiple token-based subscriptions
        
        Args:
            migration_requests: List of migration requests
            
        Returns:
            Dict: Migration results summary
        """
        results = {
            "total_requested": len(migration_requests),
            "successful_migrations": 0,
            "failed_migrations": 0,
            "migration_records": [],
            "errors": []
        }
        
        for request in migration_requests:
            try:
                migration_record = await self.migrate_token_subscription(
                    user_id=request["user_id"],
                    legacy_token=request["legacy_token"],
                    subscription_type=SubscriptionType(request["subscription_type"]),
                    data_frequency=DataFrequency(request.get("data_frequency", "tick"))
                )
                
                results["successful_migrations"] += 1
                results["migration_records"].append(migration_record.migration_id)
                
            except Exception as e:
                results["failed_migrations"] += 1
                results["errors"].append({
                    "token": request["legacy_token"],
                    "user_id": request["user_id"],
                    "error": str(e)
                })
        
        return results
    
    # =============================================================================
    # REGISTRY INTEGRATION AND VALIDATION
    # =============================================================================
    
    async def validate_subscription(self, subscription_id: str) -> Dict[str, Any]:
        """
        Validate subscription against registry
        
        Args:
            subscription_id: Subscription to validate
            
        Returns:
            Dict: Validation results
        """
        subscription = self._subscriptions.get(subscription_id)
        if not subscription:
            return {"valid": False, "error": "Subscription not found"}
        
        try:
            # Validate instrument still exists in registry
            metadata = await self.instrument_client.get_instrument_metadata(subscription.instrument_key)
            
            # Check if metadata has changed
            current_metadata = self._convert_metadata_to_dict(metadata)
            stored_metadata = subscription._registry_metadata or {}
            
            metadata_changed = (
                stored_metadata.get("symbol") != current_metadata.get("symbol") or
                stored_metadata.get("exchange") != current_metadata.get("exchange") or
                stored_metadata.get("sector") != current_metadata.get("sector")
            )
            
            if metadata_changed:
                # Update subscription with new metadata
                subscription.symbol = metadata.symbol
                subscription.exchange = metadata.exchange
                subscription.sector = metadata.sector or "Unknown"
                subscription._registry_metadata = current_metadata
                subscription.last_updated = datetime.now()
                
                logger.info(f"Subscription {subscription_id} metadata updated from registry")
            
            return {
                "valid": True,
                "instrument_key": subscription.instrument_key,
                "metadata_changed": metadata_changed,
                "current_metadata": current_metadata,
                "validation_timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Subscription validation failed for {subscription_id}: {e}")
            return {
                "valid": False,
                "error": str(e),
                "instrument_key": subscription.instrument_key,
                "validation_timestamp": datetime.now().isoformat()
            }
    
    async def refresh_subscription_metadata(self, instrument_key: str) -> int:
        """
        Refresh metadata for all subscriptions of an instrument
        
        Args:
            instrument_key: Instrument to refresh
            
        Returns:
            int: Number of subscriptions updated
        """
        subscriptions = await self.get_instrument_subscriptions(instrument_key)
        updated_count = 0
        
        try:
            metadata = await self.instrument_client.get_instrument_metadata(instrument_key)
            current_metadata = self._convert_metadata_to_dict(metadata)
            
            for subscription in subscriptions:
                subscription.symbol = metadata.symbol
                subscription.exchange = metadata.exchange
                subscription.sector = metadata.sector or "Unknown"
                subscription._registry_metadata = current_metadata
                subscription.last_updated = datetime.now()
                updated_count += 1
            
            logger.info(f"Refreshed metadata for {updated_count} subscriptions of {instrument_key}")
            
        except Exception as e:
            logger.error(f"Failed to refresh metadata for {instrument_key}: {e}")
        
        return updated_count
    
    # =============================================================================
    # PERFORMANCE MONITORING AND HEALTH CHECKS
    # =============================================================================
    
    async def get_subscription_metrics(self) -> Dict[str, Any]:
        """Get subscription performance metrics"""
        active_subs = len([s for s in self._subscriptions.values() if s.status == SubscriptionStatus.ACTIVE])
        
        return {
            "subscription_counts": {
                "total": len(self._subscriptions),
                "active": active_subs,
                "paused": len([s for s in self._subscriptions.values() if s.status == SubscriptionStatus.PAUSED]),
                "cancelled": len([s for s in self._subscriptions.values() if s.status == SubscriptionStatus.CANCELLED])
            },
            "migration_metrics": {
                "total_migrations": self._performance_metrics["migration_count"],
                "successful_migrations": len([r for r in self._migration_records.values() if r.migration_status == "completed"]),
                "failed_migrations": len([r for r in self._migration_records.values() if r.migration_status == "failed"])
            },
            "performance_metrics": self._performance_metrics,
            "timestamp": datetime.now().isoformat()
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """Subscription storage health check"""
        try:
            # Test registry connectivity
            test_key = "AAPL_NASDAQ_EQUITY"
            start_time = datetime.now()
            await self.instrument_client.get_instrument_metadata(test_key)
            registry_response_time = (datetime.now() - start_time).total_seconds() * 1000
            
            # Check storage health
            storage_healthy = len(self._subscriptions) >= 0  # Basic check
            
            return {
                "service": "SubscriptionStorage",
                "healthy": storage_healthy and registry_response_time < 200,
                "registry_connectivity": {
                    "accessible": True,
                    "response_time_ms": registry_response_time,
                    "within_sla": registry_response_time < 200
                },
                "storage_status": {
                    "accessible": storage_healthy,
                    "total_subscriptions": len(self._subscriptions),
                    "active_subscriptions": len([s for s in self._subscriptions.values() if s.status == SubscriptionStatus.ACTIVE])
                },
                "last_check": datetime.now().isoformat()
            }
            
        except Exception as e:
            return {
                "service": "SubscriptionStorage",
                "healthy": False,
                "error": str(e),
                "registry_connectivity": {"accessible": False},
                "last_check": datetime.now().isoformat()
            }
    
    # =============================================================================
    # INTERNAL UTILITIES
    # =============================================================================
    
    async def _store_subscription(self, subscription: Subscription):
        """Store subscription in all indexes"""
        self._subscriptions[subscription.subscription_id] = subscription
        
        # Update user index
        if subscription.user_id not in self._user_subscriptions:
            self._user_subscriptions[subscription.user_id] = []
        self._user_subscriptions[subscription.user_id].append(subscription.subscription_id)
        
        # Update instrument index
        if subscription.instrument_key not in self._instrument_subscriptions:
            self._instrument_subscriptions[subscription.instrument_key] = []
        self._instrument_subscriptions[subscription.instrument_key].append(subscription.subscription_id)
        
        # Update metrics
        self._update_performance_metrics()
    
    async def _remove_from_indexes(self, subscription: Subscription):
        """Remove subscription from indexes"""
        # Remove from user index
        if subscription.user_id in self._user_subscriptions:
            if subscription.subscription_id in self._user_subscriptions[subscription.user_id]:
                self._user_subscriptions[subscription.user_id].remove(subscription.subscription_id)
        
        # Remove from instrument index
        if subscription.instrument_key in self._instrument_subscriptions:
            if subscription.subscription_id in self._instrument_subscriptions[subscription.instrument_key]:
                self._instrument_subscriptions[subscription.instrument_key].remove(subscription.subscription_id)
    
    async def _resolve_token_to_key(self, token: str) -> Optional[str]:
        """
        Resolve legacy token to instrument_key
        
        In practice, this would use a comprehensive token mapping service
        For now, mock resolution based on token pattern
        """
        # Mock token resolution
        token_mappings = {
            "256265": "AAPL_NASDAQ_EQUITY",
            "408065": "GOOGL_NASDAQ_EQUITY", 
            "492033": "MSFT_NASDAQ_EQUITY",
            "738561": "TSLA_NASDAQ_EQUITY"
        }
        
        return token_mappings.get(token)
    
    def _convert_metadata_to_dict(self, metadata) -> Dict[str, Any]:
        """Convert metadata object to dictionary"""
        return {
            "instrument_key": metadata.instrument_key,
            "symbol": metadata.symbol,
            "exchange": metadata.exchange,
            "sector": metadata.sector,
            "instrument_type": metadata.instrument_type,
            "lot_size": metadata.lot_size,
            "tick_size": metadata.tick_size,
            "updated_at": datetime.now().isoformat()
        }
    
    def _update_performance_metrics(self):
        """Update internal performance metrics"""
        self._performance_metrics.update({
            "total_subscriptions": len(self._subscriptions),
            "active_subscriptions": len([s for s in self._subscriptions.values() if s.status == SubscriptionStatus.ACTIVE]),
            "last_performance_check": datetime.now()
        })
    
    async def cleanup_expired_subscriptions(self) -> int:
        """Clean up expired subscriptions"""
        expired_count = 0
        current_time = datetime.now()
        
        for subscription in list(self._subscriptions.values()):
            if (subscription.expires_at and current_time > subscription.expires_at and 
                subscription.status == SubscriptionStatus.ACTIVE):
                
                subscription.status = SubscriptionStatus.CANCELLED
                subscription.last_updated = current_time
                await self._remove_from_indexes(subscription)
                expired_count += 1
        
        if expired_count > 0:
            logger.info(f"Cleaned up {expired_count} expired subscriptions")
        
        return expired_count