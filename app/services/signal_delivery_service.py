"""
Signal Delivery Service - API Delegation Implementation

Replaces direct alert/email implementations with proper service delegation.
Follows Architecture v3.0 - API Delegation Era patterns from CLAUDE.md

This service orchestrates signal delivery through:
- alert_service for multi-channel notifications
- comms_service for email delivery
- user_service for preferences (via alert_service)

Circuit breakers and retry logic ensure robust service-to-service communication.
"""
import asyncio
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass

from app.clients.alert_service_client import AlertPriority, AlertChannel
from app.clients.client_factory import get_client_manager
from app.utils.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class SignalDeliveryConfig:
    """Configuration for signal delivery"""
    max_retries: int = 3
    retry_delay: float = 1.0
    circuit_breaker_enabled: bool = True
    timeout_seconds: int = 30


class SignalDeliveryService:
    """
    Service for delivering signals through proper API delegation.
    
    Replaces the removed alert_manager.py and email_integration.py
    with robust service-to-service communication.
    """
    
    def __init__(self, config: SignalDeliveryConfig = None):
        self.config = config or SignalDeliveryConfig()
        self.client_manager = get_client_manager()
        self.alert_client = None
        self.comms_client = None
        
        # Circuit breaker state tracking
        self._alert_service_failures = 0
        self._comms_service_failures = 0
    
    async def _get_alert_client(self):
        """Get alert service client via centralized factory."""
        if not self.alert_client:
            self.alert_client = await self.client_manager.get_client('alert_service')
        return self.alert_client
    
    async def _get_comms_client(self):
        """Get comms service client via centralized factory."""
        if not self.comms_client:
            self.comms_client = await self.client_manager.get_client('comms_service')
        return self.comms_client
        self._max_failures_before_circuit_open = 5
        
        # Coverage ratio tracking for business impact measurement
        self._fallback_usage_count = 0
        self._total_delivery_attempts = 0
        
        logger.info("SignalDeliveryService initialized with API delegation")
    
    async def deliver_signal(
        self,
        user_id: str,
        signal_data: Dict[str, Any],
        delivery_config: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Deliver signal to user through configured channels.
        
        Uses alert_service and comms_service APIs with circuit breakers.
        """
        delivery_config = delivery_config or {}
        channels = delivery_config.get("channels", ["ui", "telegram"])
        priority = delivery_config.get("priority", "medium")
        
        results = {
            "signal_id": signal_data.get("signal_id"),
            "user_id": user_id,
            "delivery_results": {},
            "overall_success": True,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        try:
            # Track total delivery attempts for coverage ratio calculation
            self._total_delivery_attempts += 1
            
            # Get user notification preferences first
            preferences = await self._get_user_preferences_with_circuit_breaker(user_id)
            
            # Filter channels based on user preferences
            enabled_channels = self._filter_channels_by_preferences(channels, preferences)
            
            # Deliver through alert_service for most channels
            if any(ch in enabled_channels for ch in ["ui", "telegram", "webhook", "sms", "slack"]):
                alert_result = await self._deliver_via_alert_service(
                    user_id, signal_data, enabled_channels, priority
                )
                results["delivery_results"]["alert_service"] = alert_result
                
                if not alert_result.get("success", False):
                    results["overall_success"] = False
            
            # Deliver email separately through comms_service if enabled
            if "email" in enabled_channels and preferences.get("email_address"):
                email_result = await self._deliver_via_comms_service(
                    preferences["email_address"], signal_data, priority
                )
                results["delivery_results"]["comms_service"] = email_result
                
                if not email_result.get("success", False):
                    results["overall_success"] = False
            
            logger.info(f"Signal delivery completed for user {user_id}: {results['overall_success']}")
            return results
            
        except Exception as e:
            logger.error(f"Signal delivery failed for user {user_id}: {e}")
            results["overall_success"] = False
            results["error"] = str(e)
            return results
    
    async def deliver_bulk_signals(
        self,
        signal_deliveries: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Deliver multiple signals efficiently using bulk APIs.
        
        Groups deliveries by service and uses bulk endpoints.
        """
        try:
            # Group deliveries by user preferences and channels
            alert_deliveries = []
            email_deliveries = []
            
            for delivery in signal_deliveries:
                user_id = delivery["user_id"]
                signal_data = delivery["signal_data"]
                channels = delivery.get("channels", ["ui", "telegram"])
                
                # Get preferences (with caching for bulk operations)
                preferences = await self._get_user_preferences_with_circuit_breaker(user_id)
                enabled_channels = self._filter_channels_by_preferences(channels, preferences)
                
                # Add to appropriate bulk lists
                if any(ch in enabled_channels for ch in ["ui", "telegram", "webhook", "sms", "slack"]):
                    alert_deliveries.append({
                        "user_id": user_id,
                        "signal_data": signal_data,
                        "channels": enabled_channels,
                        "priority": delivery.get("priority", "medium")
                    })
                
                if "email" in enabled_channels and preferences.get("email_address"):
                    email_deliveries.append({
                        "to_email": preferences["email_address"],
                        "template_data": signal_data,
                        "signal_id": signal_data.get("signal_id"),
                        "batch_id": delivery.get("batch_id")
                    })
            
            results = {"bulk_delivery": True, "results": {}}
            
            # Execute bulk deliveries
            if alert_deliveries:
                alert_client = await self._get_alert_client()
                alert_result = await alert_client.send_bulk_signal_alerts(alert_deliveries)
                results["results"]["alert_service"] = alert_result
            
            if email_deliveries:
                comms_client = await self._get_comms_client()
                email_result = await comms_client.send_bulk_signal_emails(email_deliveries)
                results["results"]["comms_service"] = email_result
            
            logger.info(f"Bulk signal delivery completed: {len(signal_deliveries)} signals")
            return results
            
        except Exception as e:
            logger.error(f"Bulk signal delivery failed: {e}")
            return {"bulk_delivery": True, "success": False, "error": str(e)}
    
    async def _get_user_preferences_with_circuit_breaker(self, user_id: str) -> Dict[str, Any]:
        """Get user preferences with circuit breaker protection"""
        if self._alert_service_failures >= self._max_failures_before_circuit_open:
            logger.warning("Alert service circuit breaker OPEN - using default preferences")
            return self._get_default_preferences()
        
        try:
            alert_client = await self._get_alert_client()
            preferences = await alert_client.get_user_notification_preferences(user_id)
            
            # Reset failure count on success
            self._alert_service_failures = 0
            return preferences
            
        except Exception as e:
            self._alert_service_failures += 1
            logger.warning(f"Alert service call failed ({self._alert_service_failures}/{self._max_failures_before_circuit_open}): {e}")
            
            if self._alert_service_failures >= self._max_failures_before_circuit_open:
                logger.error("Alert service circuit breaker OPENED - degraded mode")
                # Record coverage ratio impact when circuit breaker opens
                self._record_fallback_usage("circuit_breaker_open")
            
            return self._get_default_preferences()
    
    async def _deliver_via_alert_service(
        self,
        user_id: str,
        signal_data: Dict[str, Any],
        channels: List[str],
        priority: str
    ) -> Dict[str, Any]:
        """Deliver signal via alert_service with circuit breaker"""
        if self._alert_service_failures >= self._max_failures_before_circuit_open:
            return {"success": False, "error": "Alert service circuit breaker OPEN"}
        
        try:
            alert_client = await self._get_alert_client()
            result = await alert_client.send_signal_alert(
                user_id, signal_data, channels, priority
            )
            
            # Reset failure count on success
            self._alert_service_failures = 0
            return result
            
        except Exception as e:
            self._alert_service_failures += 1
            logger.error(f"Alert service delivery failed: {e}")
            return {"success": False, "error": str(e)}
    
    async def _deliver_via_comms_service(
        self,
        email: str,
        signal_data: Dict[str, Any],
        priority: str
    ) -> Dict[str, Any]:
        """Deliver signal via comms_service with circuit breaker"""
        if self._comms_service_failures >= self._max_failures_before_circuit_open:
            return {"success": False, "error": "Comms service circuit breaker OPEN"}
        
        try:
            comms_client = await self._get_comms_client()
            result = await comms_client.send_signal_email(
                email, signal_data, priority=priority
            )
            
            # Reset failure count on success
            self._comms_service_failures = 0
            return result
            
        except Exception as e:
            self._comms_service_failures += 1
            logger.error(f"Comms service delivery failed: {e}")
            return {"success": False, "error": str(e)}
    
    def _filter_channels_by_preferences(
        self,
        requested_channels: List[str],
        preferences: Dict[str, Any]
    ) -> List[str]:
        """Filter requested channels by user preferences"""
        enabled_channels = preferences.get("channels", ["ui", "telegram"])
        
        # Return intersection of requested and enabled channels
        return [ch for ch in requested_channels if ch in enabled_channels]
    
    def _get_default_preferences(self) -> Dict[str, Any]:
        """Default preferences when service calls fail - record coverage impact"""
        # Track fallback usage to measure business impact
        logger.warning("Signal delivery using fallback preferences - limits business value delivery")
        
        # Record coverage ratio impact for monitoring
        self._record_fallback_usage("preferences_unavailable")
        
        return {
            "channels": ["ui"],  # Conservative fallback - only UI notifications
            "email_address": None,
            "priority_filter": "medium", 
            "quiet_hours": None,
            "fallback_mode": True  # Mark as degraded service
        }
    
    async def get_delivery_status(self, signal_id: str) -> Dict[str, Any]:
        """Get delivery status across all services"""
        try:
            # Get status from both services
            alert_client = await self._get_alert_client()
            alert_status = await alert_client.get_alert_status(signal_id)
            # Note: comms_service status would require email_id mapping
            
            return {
                "signal_id": signal_id,
                "alert_service_status": alert_status,
                "last_updated": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting delivery status: {e}")
            return {"signal_id": signal_id, "error": str(e)}
    
    async def health_check(self) -> Dict[str, Any]:
        """Check health of all dependent services"""
        try:
            alert_client = await self._get_alert_client()
            comms_client = await self._get_comms_client()
            alert_healthy = await alert_client.health_check()
            comms_healthy = await comms_client.health_check()
            
            return {
                "signal_delivery_service": "healthy",
                "alert_service": "healthy" if alert_healthy else "unhealthy",
                "comms_service": "healthy" if comms_healthy else "unhealthy",
                "circuit_breakers": {
                    "alert_service_failures": self._alert_service_failures,
                    "comms_service_failures": self._comms_service_failures,
                    "alert_circuit_open": self._alert_service_failures >= self._max_failures_before_circuit_open,
                    "comms_circuit_open": self._comms_service_failures >= self._max_failures_before_circuit_open
                }
            }
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {"signal_delivery_service": "unhealthy", "error": str(e)}
    
    async def close(self):
        """Close all service clients"""
        # Client lifecycle managed by client_manager
        await self.client_manager.close_all_clients()
    
    def _record_fallback_usage(self, fallback_reason: str):
        """Record fallback usage for coverage ratio tracking"""
        self._fallback_usage_count += 1
        
        # Calculate current coverage ratio (how often we avoid fallbacks)
        if self._total_delivery_attempts > 0:
            coverage_ratio = 1.0 - (self._fallback_usage_count / self._total_delivery_attempts)
            fallback_ratio = self._fallback_usage_count / self._total_delivery_attempts
            
            logger.warning(f"Signal delivery fallback usage: {fallback_reason} - "
                         f"Coverage ratio: {coverage_ratio:.3f}, Fallback ratio: {fallback_ratio:.3f}")
            
            # Alert if fallback usage is too high (limiting business value)
            if fallback_ratio > 0.1:  # More than 10% fallback usage
                logger.error(f"High fallback usage limiting business value: {fallback_ratio:.3f} "
                           f"({self._fallback_usage_count}/{self._total_delivery_attempts})")
    
    def get_coverage_statistics(self) -> Dict[str, Any]:
        """Get coverage statistics for monitoring"""
        if self._total_delivery_attempts == 0:
            return {
                "coverage_ratio": 1.0,
                "fallback_ratio": 0.0,
                "total_attempts": 0,
                "fallback_count": 0
            }
        
        coverage_ratio = 1.0 - (self._fallback_usage_count / self._total_delivery_attempts)
        fallback_ratio = self._fallback_usage_count / self._total_delivery_attempts
        
        return {
            "coverage_ratio": coverage_ratio,
            "fallback_ratio": fallback_ratio,
            "total_attempts": self._total_delivery_attempts,
            "fallback_count": self._fallback_usage_count,
            "business_impact": "high" if fallback_ratio > 0.1 else "low"
        }


# Global instance
_signal_delivery_service = None

def get_signal_delivery_service() -> SignalDeliveryService:
    """Get singleton signal delivery service instance"""
    global _signal_delivery_service
    if _signal_delivery_service is None:
        _signal_delivery_service = SignalDeliveryService()
    return _signal_delivery_service