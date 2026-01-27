"""
Dashboard registration for Signal Service with localhost:8500 dynamic dashboard
"""
import logging
from datetime import datetime
from typing import Any

import httpx

logger = logging.getLogger(__name__)

class DashboardRegistrar:
    """Manages registration with the dynamic dashboard"""

    def __init__(self, dashboard_url: str = None, service_url: str = None):
        # Get URLs from config_service with Docker network alias fallbacks
        if dashboard_url is None:
            try:
                from app.core.config import settings
                from common.config_service.client import ConfigServiceClient

                config_client = ConfigServiceClient(
                    service_name="signal_service",
                    environment=settings.environment,
                    timeout=5
                )
                dashboard_url = config_client.get_config("DASHBOARD_SERVICE_URL")
                if not dashboard_url:
                    raise ValueError("DASHBOARD_SERVICE_URL not found in config_service")
            except Exception:
                # Fallback to Docker network alias
                dashboard_url = "http://dashboard-service:8500"
                logger.info("✓ Using Docker network alias for dashboard_service: http://dashboard-service:8500")

        if service_url is None:
            try:
                from app.core.config import settings
                service_url = f"http://signal-service:{settings.PORT}"
            except Exception as e:
                logger.warning(f"Failed to get service URL from config: {e}")
                service_url = 'http://signal-service:8003'  # Docker network fallback

        self.dashboard_url = dashboard_url
        self.service_url = service_url
        self.registration_endpoint = f"{dashboard_url}/api/services/register"
        self.health_update_endpoint = f"{dashboard_url}/api/services/health"
        self.registration_interval = 30  # seconds
        self.is_registered = False

    async def register_service(self) -> bool:
        """Register Signal Service with the dynamic dashboard"""
        try:
            # Get configuration from config_service exclusively (Architecture Principle #1: Config service exclusivity)
            try:
                from app.core.config import settings
                from common.config_service.client import ConfigServiceClient

                config_client = ConfigServiceClient(
                    service_name="signal_service",
                    environment=settings.environment,
                    timeout=5
                )

                service_name = config_client.get_config("SERVICE_DISPLAY_NAME")
                if not service_name:
                    raise ValueError("SERVICE_DISPLAY_NAME not found in config_service")
                service_host = config_client.get_config("SERVICE_HOST")
                service_port = config_client.get_config("SERVICE_PORT")

                if not service_host or not service_port:
                    raise ValueError("SERVICE_HOST and SERVICE_PORT not found in config_service")

            except Exception as e:
                raise RuntimeError(f"Failed to get service configuration from config_service: {e}. No hardcoded fallbacks allowed per architecture.") from e

            service_config = {
                "service_name": service_name,
                "service_id": "signal_service",
                "service_type": "signal_processing",
                "service_url": self.service_url,
                "service_host": service_host,
                "service_port": int(service_port),
                "health_endpoint": f"{self.service_url}/api/v1/health",
                "registration_time": datetime.utcnow().isoformat(),
                "status": "starting"
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.registration_endpoint,
                    json=service_config,
                    timeout=10.0
                )

                if response.status_code == 200:
                    self.is_registered = True
                    logger.info(f"✓ Successfully registered Signal Service with dashboard at {self.dashboard_url}")
                    return True
                logger.error(f"Failed to register with dashboard: {response.status_code} - {response.text}")
                return False

        except Exception as e:
            logger.error(f"Dashboard registration failed: {e}")
            return False

    async def update_health_status(self, health_data: dict[str, Any]) -> bool:
        """Update health status with the dashboard"""
        if not self.is_registered:
            logger.warning("Cannot update health status - service not registered")
            return False

        try:
            health_update = {
                "service_id": "signal_service",
                "status": health_data.get('status', 'unknown'),
                "timestamp": datetime.utcnow().isoformat(),
                "health_details": health_data
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.health_update_endpoint,
                    json=health_update,
                    timeout=10.0
                )

                return response.status_code == 200

        except Exception as e:
            logger.error(f"Health status update failed: {e}")
            return False
