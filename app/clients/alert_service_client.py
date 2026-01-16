"""
Alert Service Client - API delegation for signal_service

Replaces app/services/alert_manager.py with proper service-to-service API calls.
Follows Architecture v3.0 - API Delegation Era patterns from CLAUDE.md
"""
import asyncio
import json
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum
import aiohttp
import logging

from app.core.config import settings
from app.utils.logging_config import get_logger

logger = get_logger(__name__)

class AlertPriority(Enum):
    """Alert priority levels (maintained for compatibility)"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

class AlertChannel(Enum):
    """Alert delivery channels (maintained for compatibility)"""
    UI = "ui"
    TELEGRAM = "telegram"
    EMAIL = "email"
    WEBHOOK = "webhook"
    SMS = "sms"
    SLACK = "slack"

class AlertServiceClient:
    """
    Client for delegating alert operations to dedicated alert_service.
    
    Replaces the 837-line alert_manager.py with API delegation pattern.
    Uses Internal API Key for service-to-service authentication.
    """
    
    def __init__(self, alert_service_url: str = None):
        self.alert_service_url = alert_service_url or self._get_alert_service_url()
        self.internal_api_key = self._get_internal_api_key()
        self.session: Optional[aiohttp.ClientSession] = None
        
        logger.info(f"AlertServiceClient initialized with URL: {self.alert_service_url}")
    
    def _get_alert_service_url(self) -> str:
        """Get alert service URL from config service exclusively (Architecture Principle #1: Config service exclusivity)"""
        try:
            from common.config_service.client import ConfigServiceClient
            from app.core.config import settings
            
            config_client = ConfigServiceClient(
                service_name="signal_service",
                environment=settings.environment,
                timeout=5
            )
            
            alert_url = config_client.get_service_url("alert_service")
            if not alert_url:
                raise ValueError("alert_service URL not found in config_service")
            return alert_url
            
        except Exception as e:
            raise RuntimeError(f"Failed to get alert service URL from config_service: {e}. No hardcoded fallbacks allowed per architecture.")
    
    def _get_internal_api_key(self) -> str:
        """Get internal API key for service-to-service authentication"""
        # From CLAUDE.md: Internal API Key for all service-to-service auth
        api_key = getattr(settings, 'internal_api_key', None)
        if not api_key:
            raise ValueError("INTERNAL_API_KEY not configured in settings - required for service-to-service authentication")
        return api_key
    
    async def ensure_session(self):
        """Ensure HTTP session is created"""
        if not self.session:
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30),
                headers={'X-Internal-API-Key': self.internal_api_key}
            )
    
    async def send_signal_alert(
        self,
        user_id: str,
        alert_data: Dict[str, Any],
        channels: List[str] = None,
        priority: str = "medium"
    ) -> Dict[str, Any]:
        """
        Send signal alert via alert_service API.
        
        Replaces direct alert delivery with API delegation.
        """
        await self.ensure_session()
        
        try:
            # Transform signal alert data to alert_service format
            alert_request = {
                "alert_type": "signal",
                "user_id": user_id,
                "priority": priority,
                "channels": channels or ["ui", "telegram"],
                "condition_config": {
                    "signal_type": alert_data.get("signal_type"),
                    "symbol": alert_data.get("symbol"),
                    "instrument_key": alert_data.get("instrument_key"),
                    "message": alert_data.get("message"),
                    "value": alert_data.get("value"),
                    "timestamp": alert_data.get("timestamp", datetime.utcnow().isoformat())
                },
                "metadata": {
                    "source": "signal_service",
                    "signal_id": alert_data.get("signal_id"),
                    "strategy_id": alert_data.get("strategy_id")
                }
            }
            
            async with self.session.post(
                f"{self.alert_service_url}/api/v1/alerts",
                json=alert_request
            ) as response:
                if response.status == 200 or response.status == 201:
                    result = await response.json()
                    logger.info(f"Signal alert sent successfully for user {user_id}")
                    return result
                else:
                    error_text = await response.text()
                    logger.error(f"Failed to send alert: {response.status} - {error_text}")
                    return {"success": False, "error": f"HTTP {response.status}"}
                    
        except Exception as e:
            logger.error(f"Error sending signal alert: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_user_notification_preferences(self, user_id: str) -> Dict[str, Any]:
        """Get user notification preferences from alert_service"""
        await self.ensure_session()
        
        try:
            async with self.session.get(
                f"{self.alert_service_url}/api/v1/notifications/preferences",
                params={"user_id": user_id}
            ) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.warning(f"Failed to get preferences for user {user_id}: {response.status}")
                    return self._get_default_preferences()
                    
        except Exception as e:
            logger.error(f"Error getting notification preferences: {e}")
            return self._get_default_preferences()
    
    def _get_default_preferences(self) -> Dict[str, Any]:
        """Default notification preferences fallback"""
        return {
            "channels": ["ui", "telegram"],
            "priority_filter": "medium",
            "signal_types": ["buy", "sell", "alert"],
            "quiet_hours": None,
            "rate_limit": {"max_per_hour": 10}
        }
    
    async def update_user_notification_preferences(
        self,
        user_id: str,
        preferences: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update user notification preferences via alert_service"""
        await self.ensure_session()
        
        try:
            async with self.session.put(
                f"{self.alert_service_url}/api/v1/notifications/preferences",
                json={"user_id": user_id, **preferences}
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    logger.info(f"Updated notification preferences for user {user_id}")
                    return result
                else:
                    error_text = await response.text()
                    logger.error(f"Failed to update preferences: {response.status} - {error_text}")
                    return {"success": False, "error": f"HTTP {response.status}"}
                    
        except Exception as e:
            logger.error(f"Error updating notification preferences: {e}")
            return {"success": False, "error": str(e)}
    
    async def send_bulk_signal_alerts(
        self,
        alerts: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Send multiple signal alerts efficiently via alert_service bulk API"""
        await self.ensure_session()
        
        try:
            # Transform to alert_service bulk format
            bulk_request = {
                "alerts": [
                    {
                        "alert_type": "signal",
                        "user_id": alert.get("user_id"),
                        "priority": alert.get("priority", "medium"),
                        "channels": alert.get("channels", ["ui", "telegram"]),
                        "condition_config": alert.get("signal_data", {}),
                        "metadata": {
                            "source": "signal_service",
                            "batch_id": alert.get("batch_id")
                        }
                    }
                    for alert in alerts
                ]
            }
            
            async with self.session.post(
                f"{self.alert_service_url}/api/v1/alerts/bulk",
                json=bulk_request
            ) as response:
                if response.status == 200 or response.status == 201:
                    result = await response.json()
                    logger.info(f"Sent {len(alerts)} bulk signal alerts successfully")
                    return result
                else:
                    error_text = await response.text()
                    logger.error(f"Failed to send bulk alerts: {response.status} - {error_text}")
                    return {"success": False, "error": f"HTTP {response.status}"}
                    
        except Exception as e:
            logger.error(f"Error sending bulk signal alerts: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_alert_status(self, alert_id: str) -> Optional[Dict[str, Any]]:
        """Get alert delivery status from alert_service"""
        await self.ensure_session()
        
        try:
            async with self.session.get(
                f"{self.alert_service_url}/api/v1/alerts/{alert_id}/status"
            ) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.warning(f"Failed to get alert status: {response.status}")
                    return None
                    
        except Exception as e:
            logger.error(f"Error getting alert status: {e}")
            return None
    
    async def health_check(self) -> bool:
        """Check if alert_service is healthy"""
        await self.ensure_session()
        
        try:
            async with self.session.get(
                f"{self.alert_service_url}/health"
            ) as response:
                return response.status == 200
        except Exception as e:
            logger.warning(f"Alert service health check failed: {e}")
            return False
    
    async def close(self):
        """Close HTTP session"""
        if self.session:
            await self.session.close()
            self.session = None

# Singleton instance for application use
_alert_client = None

def get_alert_service_client() -> AlertServiceClient:
    """Get singleton alert service client instance"""
    global _alert_client
    if _alert_client is None:
        _alert_client = AlertServiceClient()
    return _alert_client