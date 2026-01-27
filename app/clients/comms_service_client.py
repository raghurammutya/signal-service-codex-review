"""
Comms Service Client - API delegation for signal_service

Replaces app/services/email_integration.py with proper service-to-service API calls.
Follows Architecture v3.0 - API Delegation Era patterns from CLAUDE.md
"""
import asyncio
from typing import Any

import aiohttp

from app.clients.shared_metadata import MetadataBuilder, ServiceClientBase, SignalDataTransformer
from app.core.config import settings
from app.utils.logging_config import get_logger

logger = get_logger(__name__)


class CommsServiceClient(ServiceClientBase):
    """
    Client for delegating email/communication operations to dedicated comms_service.

    Replaces the 553-line email_integration.py with API delegation pattern.
    Uses Internal API Key for service-to-service authentication.
    """

    def __init__(self, comms_service_url: str = None):
        super().__init__("COMMS", 8086)
        if comms_service_url:
            self._service_url = comms_service_url

        logger.info(f"CommsServiceClient initialized with URL: {self._get_service_url()}")

    def _get_comms_service_url(self) -> str:
        """Get comms service URL"""
        return getattr(settings, 'COMMS_SERVICE_URL', 'http://localhost:8001')
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

    async def send_signal_email(
        self,
        to_email: str,
        signal_data: dict[str, Any],
        template: str = "signal_notification",
        priority: str = "normal"
    ) -> dict[str, Any]:
        """
        Send signal notification email via comms_service API.

        Replaces direct SMTP sending with API delegation.
        """
        await self.ensure_session()

        try:
            # Transform signal data to comms_service format using shared utilities
            email_request = {
                "to": [to_email],
                "template": template,
                "priority": priority,
                "template_data": SignalDataTransformer.extract_template_data(
                    signal_data,
                    priority=priority,
                    include_user_info=True
                ),
                "metadata": MetadataBuilder.build_signal_metadata(
                    signal_data,
                    metadata_type="signal_notification"
                )
            }

            async with self.session.post(
                f"{self._get_service_url()}/api/v1/email/send",
                json=email_request
            ) as response:
                if response.status == 200 or response.status == 201:
                    result = await response.json()
                    logger.info(f"Signal email sent successfully to {to_email}")
                    return result
                error_text = await response.text()
                logger.error(f"Failed to send email: {response.status} - {error_text}")
                return {"success": False, "error": f"HTTP {response.status}"}

        except Exception as e:
            logger.error(f"Error sending signal email: {e}")
            return {"success": False, "error": str(e)}

    async def send_bulk_signal_emails(
        self,
        email_list: list[dict[str, Any]],
        template: str = "signal_notification"
    ) -> dict[str, Any]:
        """Send multiple signal emails efficiently via comms_service bulk API"""
        await self.ensure_session()

        try:
            # Transform to comms_service bulk format
            bulk_request = {
                "emails": [
                    {
                        "to": [email.get("to_email")],
                        "template": template,
                        "template_data": email.get("template_data", {}),
                        "metadata": {
                            "source": "signal_service",
                            "batch_id": email.get("batch_id"),
                            "signal_id": email.get("signal_id")
                        }
                    }
                    for email in email_list
                ]
            }

            async with self.session.post(
                f"{self._get_service_url()}/api/v1/email/bulk",
                json=bulk_request
            ) as response:
                if response.status == 200 or response.status == 201:
                    result = await response.json()
                    logger.info(f"Sent {len(email_list)} bulk signal emails successfully")
                    return result
                error_text = await response.text()
                logger.error(f"Failed to send bulk emails: {response.status} - {error_text}")
                return {"success": False, "error": f"HTTP {response.status}"}

        except Exception as e:
            logger.error(f"Error sending bulk signal emails: {e}")
            return {"success": False, "error": str(e)}

    async def send_command_response_email(
        self,
        to_email: str,
        command: str,
        result: dict[str, Any]
    ) -> dict[str, Any]:
        """Send command response email via comms_service"""
        await self.ensure_session()

        try:
            email_request = {
                "to": [to_email],
                "template": "command_response",
                "template_data": {
                    "command": command,
                    "success": result.get("success", False),
                    "message": result.get("message", "Command processed"),
                    "result_data": result
                },
                "metadata": {
                    "source": "signal_service",
                    "type": "command_response"
                }
            }

            async with self.session.post(
                f"{self._get_service_url()}/api/v1/email/send",
                json=email_request
            ) as response:
                if response.status == 200 or response.status == 201:
                    result = await response.json()
                    logger.info(f"Command response email sent to {to_email}")
                    return result
                error_text = await response.text()
                logger.error(f"Failed to send command response: {response.status} - {error_text}")
                return {"success": False, "error": f"HTTP {response.status}"}

        except Exception as e:
            logger.error(f"Error sending command response email: {e}")
            return {"success": False, "error": str(e)}

    async def get_email_templates(self) -> dict[str, Any]:
        """Get available email templates from comms_service"""
        await self.ensure_session()

        try:
            async with self.session.get(
                f"{self._get_service_url()}/api/v1/email/templates"
            ) as response:
                if response.status == 200:
                    return await response.json()
                logger.error(f"Failed to get email templates: {response.status}")
                raise RuntimeError(f"Comms service unavailable - cannot get email templates: HTTP {response.status}")

        except Exception as e:
            logger.error(f"Error getting email templates: {e}")
            raise RuntimeError(f"Comms service connection failed - cannot get email templates: {e}") from e

    async def validate_email_address(self, email: str) -> dict[str, Any]:
        """Validate email address via comms_service"""
        await self.ensure_session()

        try:
            async with self.session.post(
                f"{self._get_service_url()}/api/v1/email/validate",
                json={"email": email}
            ) as response:
                if response.status == 200:
                    return await response.json()
                logger.error(f"Failed to validate email: {response.status}")
                raise RuntimeError(f"Comms service unavailable - cannot validate email: HTTP {response.status}")

        except Exception as e:
            logger.error(f"Error validating email: {e}")
            raise RuntimeError(f"Comms service connection failed - cannot validate email: {e}") from e

    async def get_email_delivery_status(self, email_id: str) -> dict[str, Any] | None:
        """Get email delivery status from comms_service"""
        await self.ensure_session()

        try:
            async with self.session.get(
                f"{self._get_service_url()}/api/v1/email/status/{email_id}"
            ) as response:
                if response.status == 200:
                    return await response.json()
                error_msg = f"Failed to get email status: {response.status}"
                logger.error(error_msg)
                from app.errors import CommsServiceError
                raise CommsServiceError(error_msg, status_code=response.status)

        except Exception as e:
            logger.error(f"Error getting email status: {e}")
            from app.errors import CommsServiceError
            raise CommsServiceError(f"Email status retrieval failed: {str(e)}") from e

    async def process_inbound_email_webhook(
        self,
        webhook_data: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Process inbound email webhook - delegate to comms_service for parsing,
        then handle signal-specific commands locally.
        """
        try:
            # Extract basic email info
            from_email = webhook_data.get("from_email")
            subject = webhook_data.get("subject", "")
            body = webhook_data.get("body_plain", "")

            # Simple command extraction (replace complex parsing logic)
            command = self._extract_command(subject, body)

            if command:
                logger.info(f"Processing email command: {command} from {from_email}")

                # Handle signal-specific commands
                if command.startswith(("subscribe", "unsubscribe", "status", "help")):
                    result = await self._handle_signal_command(command, from_email, webhook_data)

                    # Send response via comms_service
                    await self.send_command_response_email(from_email, command, result)

                    return {"success": True, "command": command, "result": result}

            logger.info(f"No valid command found in email from {from_email}")
            return {"success": False, "error": "No valid command found"}

        except Exception as e:
            logger.error(f"Error processing inbound email: {e}")
            return {"success": False, "error": str(e)}

    def _extract_command(self, subject: str, body: str) -> str | None:
        """Extract command from email subject and body"""
        text = f"{subject} {body}".lower()

        # Simple command detection
        commands = ["subscribe", "unsubscribe", "status", "help", "pause", "resume"]
        for command in commands:
            if command in text:
                return command

        return None

    async def _handle_signal_command(
        self,
        command: str,
        email: str,
        webhook_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Handle signal-specific email commands"""
        try:
            if command == "help":
                return {
                    "success": True,
                    "message": "Available commands: subscribe, unsubscribe, status, help",
                    "commands": ["subscribe <signal_id>", "unsubscribe <signal_id>", "status", "help"]
                }
            if command == "status":
                return {
                    "success": True,
                    "message": "Signal service is running",
                    "status": "active"
                }
            # For other commands, we'd typically query signal_service APIs
            return {
                "success": False,
                "message": f"Command {command} not fully implemented in API delegation mode"
            }

        except Exception as e:
            logger.error(f"Error handling signal command: {e}")
            return {"success": False, "error": str(e)}

    async def health_check(self) -> bool:
        """Check if comms_service is healthy"""
        await self.ensure_session()

        try:
            async with self.session.get(
                f"{self._get_service_url()}/health"
            ) as response:
                return response.status == 200
        except Exception as e:
            logger.warning(f"Comms service health check failed: {e}")
            return False

    async def close(self):
        """Close HTTP session"""
        if self.session:
            await self.session.close()
            self.session = None


# Singleton instance for application use
_comms_client = None

def get_comms_service_client() -> CommsServiceClient:
    """Get comms service client instance via centralized factory"""
    from app.clients.client_factory import get_client_manager

    # For backward compatibility, maintain sync interface
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    client_manager = get_client_manager()
    return loop.run_until_complete(client_manager.get_client('comms_service'))


# Compatibility function to replace email_integration service
async def get_email_integration_service():
    """
    Compatibility function that returns comms service client.

    This replaces the original get_email_integration_service() function
    to maintain API compatibility while delegating to comms_service.
    """
    return get_comms_service_client()
