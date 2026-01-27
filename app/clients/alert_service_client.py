"""
Alert Service Client - API delegation for signal_service

Replaces app/services/alert_manager.py with proper service-to-service API calls.
Follows Architecture v3.0 - API Delegation Era patterns from CLAUDE.md
"""
import asyncio
from enum import Enum
from typing import Any

import aiohttp

from app.clients.shared_metadata import MetadataBuilder, ServiceClientBase, SignalDataTransformer
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

class AlertServiceClient(ServiceClientBase):
    """
    Client for delegating alert operations to dedicated alert_service.

    Replaces the 837-line alert_manager.py with API delegation pattern.
    Uses Internal API Key for service-to-service authentication.
    """

    def __init__(self, alert_service_url: str = None):
        super().__init__("ALERT", 8085)
        if alert_service_url:
            self._service_url = alert_service_url

        logger.info(f"AlertServiceClient initialized with URL: {self._get_service_url()}")

    def _get_alert_service_url(self) -> str:
        """Get alert service URL"""
        return getattr(settings, 'ALERT_SERVICE_URL', 'http://localhost:8000')
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

    async def close_session(self):
        """Close HTTP session to prevent resource leaks"""
        if self.session:
            await self.session.close()
            self.session = None

    async def __aenter__(self):
        """Async context manager entry"""
        await self.ensure_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit with automatic session cleanup"""
        await self.close_session()

    async def send_signal_alert(
        self,
        user_id: str,
        alert_data: dict[str, Any],
        channels: list[str] = None,
        priority: str = "medium"
    ) -> dict[str, Any]:
        """
        Send signal alert via alert_service API.

        Replaces direct alert delivery with API delegation.
        """
        await self.ensure_session()

        try:
            # Transform signal alert data to alert_service format using shared utilities
            alert_request = {
                "alert_type": "signal",
                "user_id": user_id,
                "priority": priority,
                "channels": channels if channels is not None else self._get_required_channels(),
                "condition_config": SignalDataTransformer.extract_condition_config(alert_data),
                "metadata": MetadataBuilder.build_signal_metadata(
                    alert_data,
                    metadata_type="signal_alert",
                    extra_fields={"priority": priority}
                )
            }

            async with self.session.post(
                f"{self._get_service_url()}/api/v1/alerts",
                json=alert_request
            ) as response:
                if response.status == 200 or response.status == 201:
                    result = await response.json()
                    logger.info(f"Signal alert sent successfully for user {user_id}")
                    return result
                error_text = await response.text()
                logger.error(f"Failed to send alert: {response.status} - {error_text}")
                return {"success": False, "error": f"HTTP {response.status}"}

        except Exception as e:
            logger.error(f"Error sending signal alert: {e}")
            return {"success": False, "error": str(e)}

    async def get_user_notification_preferences(self, user_id: str) -> dict[str, Any]:
        """Get user notification preferences from alert_service"""
        await self.ensure_session()

        try:
            async with self.session.get(
                f"{self.alert_service_url}/api/v1/notifications/preferences",
                params={"user_id": user_id}
            ) as response:
                if response.status == 200:
                    return await response.json()
                logger.error(f"Failed to get preferences for user {user_id}: {response.status}")
                raise RuntimeError(f"Alert service unavailable - cannot get user preferences: HTTP {response.status}")

        except Exception as e:
            logger.error(f"Error getting notification preferences: {e}")
            raise RuntimeError(f"Alert service connection failed - cannot get user preferences: {e}") from e

    def _get_required_channels(self) -> list[str]:
        """Get required channels - no fallback defaults"""
        # FAIL FAST: Require explicit channel configuration
        raise RuntimeError("Alert channels not specified - cannot send alert without explicit channel configuration")

    async def update_user_notification_preferences(
        self,
        user_id: str,
        preferences: dict[str, Any]
    ) -> dict[str, Any]:
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
                error_text = await response.text()
                logger.error(f"Failed to update preferences: {response.status} - {error_text}")
                return {"success": False, "error": f"HTTP {response.status}"}

        except Exception as e:
            logger.error(f"Error updating notification preferences: {e}")
            return {"success": False, "error": str(e)}

    async def send_bulk_signal_alerts(
        self,
        alerts: list[dict[str, Any]]
    ) -> dict[str, Any]:
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
                error_text = await response.text()
                logger.error(f"Failed to send bulk alerts: {response.status} - {error_text}")
                return {"success": False, "error": f"HTTP {response.status}"}

        except Exception as e:
            logger.error(f"Error sending bulk signal alerts: {e}")
            return {"success": False, "error": str(e)}

    async def get_alert_status(self, alert_id: str) -> dict[str, Any] | None:
        """Get alert delivery status from alert_service"""
        await self.ensure_session()

        try:
            async with self.session.get(
                f"{self.alert_service_url}/api/v1/alerts/{alert_id}/status"
            ) as response:
                if response.status == 200:
                    return await response.json()
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

# Singleton instance for application use - migrated to centralized factory
_alert_client = None

def get_alert_service_client() -> AlertServiceClient:
    """Get alert service client instance via centralized factory"""
    from app.clients.client_factory import get_client_manager

    # For backward compatibility, maintain sync interface
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    client_manager = get_client_manager()
    return loop.run_until_complete(client_manager.get_client('alert_service'))
