# Subscription Service Client for Signal Service
import logging
import time
from typing import Any

import httpx

from ..core.config import settings

logger = logging.getLogger(__name__)


class SignalSubscriptionError(Exception):
    """Exception raised for subscription service errors"""


class QuotaExceededException(SignalSubscriptionError):
    """Exception raised when user exceeds quotas"""


class PermissionDeniedException(SignalSubscriptionError):
    """Exception raised when user lacks permissions"""


class SignalSubscriptionClient:
    """
    Client for integrating signal_service with subscription_service
    Handles signal computation quotas, threshold monitoring limits, and resource allocation
    """

    def __init__(self, base_url: str = None, timeout: float = 10.0):
        self.base_url = base_url or settings.SUBSCRIPTION_SERVICE_URL
        self.timeout = timeout
        self.client_name = "signal_service"

        logger.info(f"SignalSubscriptionClient initialized with URL: {self.base_url}")

    def _get_headers(self, user_id: str = None) -> dict[str, str]:
        """Get request headers with service authentication"""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Service-Name": self.client_name,
            "X-Request-ID": f"signal_{int(time.time())}"
        }

        if user_id:
            headers["X-User-ID"] = user_id

        return headers

    async def validate_threshold_creation(self, user_id: str, threshold_config: dict) -> dict[str, Any]:
        """
        Validate if user can create a threshold based on their subscription

        Args:
            user_id: User requesting threshold creation
            threshold_config: Threshold configuration details

        Returns:
            dict with validation result, monitoring tier, and resource allocation
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/thresholds/configure",
                    json={
                        "user_id": user_id,
                        "threshold_config": {
                            "name": threshold_config.get("name", "Unknown Threshold"),
                            "symbols": [threshold_config.get("symbol", "")],
                            "signal_type": threshold_config.get("signal_type", "technical_indicators"),
                            "indicator": threshold_config.get("indicator_name", ""),
                            "threshold_conditions": {
                                "operator": threshold_config.get("threshold_type", "greater_than"),
                                "value": threshold_config.get("threshold_value", 0),
                                "duration_seconds": 30
                            },
                            "monitoring_frequency": self._determine_monitoring_frequency(threshold_config),
                            "alert_config": {
                                "channels": threshold_config.get("alert_channels", ["ui"]),
                                "cooldown_minutes": threshold_config.get("cooldown_minutes", 5)
                            }
                        }
                    },
                    headers=self._get_headers(user_id)
                )

                if response.status_code == 200:
                    data = response.json()
                    return {
                        "allowed": True,
                        "threshold_id": data.get("threshold_id"),
                        "monitoring_tier": data.get("monitoring_tier", "periodic"),
                        "allocated_resources": data.get("allocated_resources", {}),
                        "estimated_resource_usage": data.get("estimated_resource_usage", {}),
                        "reason": "Threshold creation approved"
                    }
                if response.status_code == 403:
                    error_data = response.json()
                    return {
                        "allowed": False,
                        "reason": error_data.get("error", {}).get("message", "Threshold creation denied"),
                        "details": error_data.get("error", {}).get("details", {})
                    }
                return {
                    "allowed": False,
                    "reason": f"Validation failed with status {response.status_code}"
                }

        except Exception as e:
            logger.exception(f"Failed to validate threshold creation: {e}")
            return {
                "allowed": False,
                "reason": f"Validation error: {str(e)}"
            }

    async def allocate_signal_resources(self, user_id: str, computation_request: dict) -> dict[str, Any]:
        """
        Request resource allocation for signal computation

        Args:
            user_id: User requesting computation
            computation_request: Details of computation to be performed

        Returns:
            dict with allocation result and resource limits
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/signals/allocate",
                    json={
                        "user_id": user_id,
                        "signal_request": {
                            "computation_type": computation_request.get("computation_type", "technical_indicators"),
                            "symbols": computation_request.get("symbols", []),
                            "computation_intensity": self._assess_computation_intensity(computation_request),
                            "estimated_duration_ms": computation_request.get("estimated_duration_ms", 500),
                            "required_data_sources": computation_request.get("data_sources", ["market_data"])
                        }
                    },
                    headers=self._get_headers(user_id)
                )

                if response.status_code == 200:
                    data = response.json()
                    return {
                        "granted": data.get("allocation_granted", False),
                        "worker_id": data.get("allocated_resources", {}).get("signal_worker_id"),
                        "computation_slots": data.get("allocated_resources", {}).get("computation_slots", 1),
                        "priority_level": data.get("allocated_resources", {}).get("priority_level", "normal"),
                        "max_execution_time_ms": data.get("allocated_resources", {}).get("max_execution_time_ms", 1000),
                        "resource_limits": data.get("resource_limits", {}),
                        "fallback_options": data.get("fallback_options", {})
                    }
                error_data = response.json()
                return {
                    "granted": False,
                    "reason": error_data.get("error", {}).get("message", "Resource allocation denied")
                }

        except Exception as e:
            logger.exception(f"Failed to allocate signal resources: {e}")
            return {
                "granted": False,
                "reason": f"Allocation error: {str(e)}"
            }

    async def update_signal_usage(self, user_id: str, computation_result: dict) -> bool:
        """
        Update signal usage after computation completion

        Args:
            user_id: User who performed computation
            computation_result: Results and metrics from computation

        Returns:
            True if usage was recorded successfully
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/signals/usage",
                    json={
                        "user_id": user_id,
                        "computation_completed": {
                            "signal_type": computation_result.get("signal_type", "technical_indicators"),
                            "computation_count": computation_result.get("computation_count", 1),
                            "symbols_processed": computation_result.get("symbols", []),
                            "execution_time_ms": computation_result.get("execution_time_ms", 0),
                            "memory_used_mb": computation_result.get("memory_used_mb", 0),
                            "data_points_consumed": computation_result.get("data_points_consumed", 0),
                            "worker_id": computation_result.get("worker_id", "unknown")
                        },
                        "metadata": {
                            "computation_quality": computation_result.get("quality", "high"),
                            "error_count": computation_result.get("error_count", 0),
                            "cache_hit_rate": computation_result.get("cache_hit_rate", 0.0)
                        }
                    },
                    headers=self._get_headers(user_id)
                )

                if response.status_code == 200:
                    data = response.json()
                    logger.info(f"Signal usage recorded for user {user_id}: {data.get('updated_quotas', {})}")
                    return True
                logger.warning(f"Failed to record signal usage: {response.status_code}")
                return False

        except Exception as e:
            logger.exception(f"Failed to update signal usage: {e}")
            return False

    async def check_signal_quotas(self, user_id: str, period: str = "today") -> dict[str, Any]:
        """
        Check user's current signal computation quotas

        Args:
            user_id: User to check quotas for
            period: Time period ('today', 'this_hour', 'this_month')

        Returns:
            dict with quota usage and limits
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/api/signals/quotas/{user_id}",
                    params={"period": period},
                    headers=self._get_headers(user_id)
                )

                if response.status_code == 200:
                    return response.json()
                logger.warning(f"Failed to check signal quotas: {response.status_code}")
                return {
                    "user_id": user_id,
                    "signal_usage": {},
                    "error": f"Failed to retrieve quotas: {response.status_code}"
                }

        except Exception as e:
            logger.exception(f"Failed to check signal quotas: {e}")
            return {
                "user_id": user_id,
                "signal_usage": {},
                "error": str(e)
            }

    async def get_threshold_monitoring_status(self, user_id: str) -> dict[str, Any]:
        """
        Get user's threshold monitoring status and capacity

        Args:
            user_id: User to check status for

        Returns:
            dict with threshold monitoring status
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/api/thresholds/status/{user_id}",
                    headers=self._get_headers(user_id)
                )

                if response.status_code == 200:
                    return response.json()
                return {
                    "user_id": user_id,
                    "active_thresholds": [],
                    "monitoring_capacity": {
                        "thresholds_active": 0,
                        "thresholds_limit": 0
                    },
                    "error": f"Failed to retrieve status: {response.status_code}"
                }

        except Exception as e:
            logger.exception(f"Failed to get threshold monitoring status: {e}")
            return {
                "user_id": user_id,
                "active_thresholds": [],
                "error": str(e)
            }

    async def request_resource_optimization(self, user_id: str, current_thresholds: list[str]) -> dict[str, Any]:
        """
        Request optimization recommendations for user's thresholds

        Args:
            user_id: User to optimize for
            current_thresholds: list of current threshold IDs

        Returns:
            dict with optimization suggestions
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/thresholds/optimize",
                    json={
                        "user_id": user_id,
                        "optimization_request": {
                            "current_thresholds": current_thresholds,
                            "performance_metrics": {
                                "avg_computation_time_ms": 150,
                                "cache_hit_rate": 0.75,
                                "false_positive_rate": 0.1
                            }
                        }
                    },
                    headers=self._get_headers(user_id)
                )

                if response.status_code == 200:
                    return response.json()
                return {
                    "optimization_suggestions": [],
                    "error": f"Optimization request failed: {response.status_code}"
                }

        except Exception as e:
            logger.exception(f"Failed to request resource optimization: {e}")
            return {
                "optimization_suggestions": [],
                "error": str(e)
            }

    async def check_feature_access(self, user_id: str, feature: str) -> bool:
        """
        Check if user has access to a specific signal feature

        Args:
            user_id: User to check
            feature: Feature name (e.g., 'greeks_calculation', 'real_time_alerts')

        Returns:
            True if user has access to the feature
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/api/features/check/{user_id}/{feature}",
                    headers=self._get_headers(user_id)
                )

                if response.status_code == 200:
                    data = response.json()
                    return data.get("allowed", False)
                logger.warning(f"Feature access check failed: {response.status_code}")
                return False

        except Exception as e:
            logger.exception(f"Failed to check feature access: {e}")
            return False

    def _determine_monitoring_frequency(self, threshold_config: dict) -> str:
        """Determine monitoring frequency based on threshold configuration"""
        signal_type = threshold_config.get("signal_type", "technical_indicators")
        time_sensitivity = threshold_config.get("time_sensitivity", "periodic")

        if signal_type == "greeks" and time_sensitivity == "immediate":
            return "real_time"
        if time_sensitivity in ["immediate", "near_term"]:
            return "high_frequency"
        return "periodic"

    def _assess_computation_intensity(self, computation_request: dict) -> str:
        """Assess computation intensity based on request details"""
        computation_type = computation_request.get("computation_type", "technical_indicators")
        symbols_count = len(computation_request.get("symbols", []))

        if computation_type == "greeks" and symbols_count > 20:
            return "high"
        if computation_type == "greeks" or symbols_count > 10:
            return "medium"
        return "low"


# Global client instance
signal_subscription_client = SignalSubscriptionClient()

# Backward compatibility alias expected by some tests
SubscriptionServiceClient = SignalSubscriptionClient
