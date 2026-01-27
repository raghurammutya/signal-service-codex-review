"""
Config Administration API

Provides endpoints for managing config-driven budgets and pools.
Allows runtime configuration refresh and validation.
"""
import logging
import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer
from pydantic import BaseModel

from app.config.budget_config import get_budget_manager
from app.config.pool_manager import get_pool_manager
from app.services.metrics_service import get_metrics_collector

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/config", tags=["config-admin"])
security = HTTPBearer()


def verify_admin_token(token: str = Depends(security)) -> str:
    """Verify admin authorization token."""
    expected_admin_token = os.getenv("ADMIN_API_TOKEN")

    if not expected_admin_token:
        raise HTTPException(
            status_code=503,
            detail="Admin API not configured - ADMIN_API_TOKEN required"
        )

    if token.credentials != expected_admin_token:
        raise HTTPException(
            status_code=403,
            detail="Invalid admin authorization token"
        )

    return token.credentials


def _sanitize_config_response(config_dict: dict[str, Any]) -> dict[str, Any]:
    """Sanitize configuration response to prevent sensitive data exposure."""
    # List of keys that should be sanitized/redacted
    sensitive_keys = {
        'password', 'secret', 'key', 'token', 'credential',
        'private', 'cert', 'ssl_key', 'encryption_key'
    }

    def sanitize_recursive(obj):
        if isinstance(obj, dict):
            return {
                k: "***REDACTED***" if any(sens in k.lower() for sens in sensitive_keys)
                else sanitize_recursive(v)
                for k, v in obj.items()
            }
        if isinstance(obj, list):
            return [sanitize_recursive(item) for item in obj]
        return obj

    return sanitize_recursive(config_dict)


class ConfigRefreshRequest(BaseModel):
    """Request to refresh specific configuration sections."""
    sections: list | None = ["all"]
    force: bool = False


class ConfigValidationResponse(BaseModel):
    """Configuration validation response."""
    valid: bool
    sections: dict[str, Any]
    errors: list
    warnings: list


class BudgetConfigResponse(BaseModel):
    """Current budget configuration response."""
    budget_config: dict[str, Any]
    pool_status: dict[str, Any]
    last_refresh: str | None


@router.post("/refresh", response_model=dict[str, Any])
async def refresh_configurations(
    request: ConfigRefreshRequest,
    token: str = Depends(verify_admin_token)
):
    """Refresh configuration from config service."""
    try:
        refresh_results = {}

        # Get managers
        budget_manager = get_budget_manager()
        pool_manager = get_pool_manager()
        metrics_collector = get_metrics_collector()

        if "all" in request.sections or "budget" in request.sections:
            # Refresh budget configuration
            try:
                await budget_manager.get_budget_config(force_refresh=request.force)
                await metrics_collector.refresh_budget_config()
                refresh_results["budget"] = {"status": "success", "message": "Budget configuration refreshed"}
            except Exception as e:
                logger.error(f"Failed to refresh budget config: {e}")
                refresh_results["budget"] = {"status": "error", "message": str(e)}

        if "all" in request.sections or "pools" in request.sections:
            # Refresh pool configurations
            try:
                await pool_manager.refresh_pool_configs()
                refresh_results["pools"] = {"status": "success", "message": "Pool configurations refreshed"}
            except Exception as e:
                logger.error(f"Failed to refresh pool configs: {e}")
                refresh_results["pools"] = {"status": "error", "message": str(e)}

        return {
            "success": True,
            "refreshed_sections": request.sections,
            "results": refresh_results,
            "timestamp": __import__('datetime').datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Configuration refresh failed: {e}")
        raise HTTPException(status_code=500, detail=f"Configuration refresh failed: {e}") from e


@router.get("/validate", response_model=ConfigValidationResponse)
async def validate_configurations(token: str = Depends(verify_admin_token)):
    """Validate current configuration settings."""
    try:
        budget_manager = get_budget_manager()

        # Validate budget configuration
        validation_result = await budget_manager.validate_and_apply_config()

        return ConfigValidationResponse(
            valid=validation_result["valid"],
            sections=validation_result["sections"],
            errors=validation_result["errors"],
            warnings=validation_result["warnings"]
        )

    except Exception as e:
        logger.error(f"Configuration validation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Configuration validation failed: {e}") from e


@router.get("/budget", response_model=BudgetConfigResponse)
async def get_current_budget_config(token: str = Depends(verify_admin_token)):
    """Get current budget configuration and pool status."""
    try:
        budget_manager = get_budget_manager()
        pool_manager = get_pool_manager()

        # Get current budget configuration
        budget_config = await budget_manager.get_budget_config()

        # Get pool status
        pool_status = await pool_manager.get_pool_status()

        # Convert to dictionary for response - sanitize sensitive config values
        budget_dict = budget_config.dict() if hasattr(budget_config, 'dict') else budget_config

        # Remove or sanitize any sensitive configuration values
        # (Currently no sensitive values in budget config, but good practice)
        sanitized_dict = _sanitize_config_response(budget_dict)

        return BudgetConfigResponse(
            budget_config=sanitized_dict,
            pool_status=pool_status,
            last_refresh=__import__('datetime').datetime.now().isoformat()
        )

    except Exception as e:
        logger.error(f"Failed to get budget configuration: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get budget configuration: {e}") from e


@router.get("/pools/status")
async def get_pool_status(token: str = Depends(verify_admin_token)):
    """Get detailed status of all connection pools."""
    try:
        pool_manager = get_pool_manager()
        status = await pool_manager.get_pool_status()

        return {
            "timestamp": __import__('datetime').datetime.now().isoformat(),
            "pool_status": status
        }

    except Exception as e:
        logger.error(f"Failed to get pool status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get pool status: {e}") from e


@router.post("/budget/test-backpressure")
async def test_backpressure_configuration(
    level: str = "moderate",
    duration_seconds: int = 30,
    token: str = Depends(verify_admin_token)
):
    """Test backpressure configuration with specified level."""
    if level not in ["light", "moderate", "heavy"]:
        raise HTTPException(status_code=400, detail="Level must be 'light', 'moderate', or 'heavy'")

    if duration_seconds > 300:  # Max 5 minutes
        raise HTTPException(status_code=400, detail="Duration cannot exceed 300 seconds")

    try:
        metrics_collector = get_metrics_collector()

        # Temporarily activate backpressure for testing
        original_state = metrics_collector.backpressure_state.copy()

        metrics_collector.backpressure_state.update({
            'active': True,
            'level': level,
            'start_time': __import__('time').time(),
            'current_restrictions': {
                'test_mode': True,
                'requested_level': level,
                'duration': duration_seconds
            }
        })

        # Schedule reset after duration
        async def reset_backpressure():
            await __import__('asyncio').sleep(duration_seconds)
            metrics_collector.backpressure_state = original_state

        __import__('asyncio').create_task(reset_backpressure())

        return {
            "success": True,
            "message": f"Backpressure level '{level}' activated for {duration_seconds} seconds",
            "backpressure_state": metrics_collector.backpressure_state,
            "timestamp": __import__('datetime').datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Failed to test backpressure: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to test backpressure: {e}") from e


@router.get("/budget/metrics")
async def get_budget_metrics(token: str = Depends(verify_admin_token)):
    """Get current resource usage against budget limits."""
    try:
        metrics_collector = get_metrics_collector()

        # Get current resource usage
        resource_usage = {
            "concurrent_operations": metrics_collector.concurrent_operations,
            "memory_usage_mb": __import__('psutil').virtual_memory().used / (1024 * 1024),
            "cpu_percent": __import__('psutil').cpu_percent(interval=1),
            "backpressure_state": metrics_collector.backpressure_state
        }

        # Get budget limits
        budget_limits = metrics_collector.budget_guards if metrics_collector.budget_guards else {}

        # Calculate utilization percentages
        utilization = {}
        if budget_limits:
            utilization = {
                "concurrent_operations": (resource_usage["concurrent_operations"] / budget_limits.get("max_concurrent_operations", 1)) * 100,
                "memory": (resource_usage["memory_usage_mb"] / budget_limits.get("max_memory_mb", 1)) * 100,
                "cpu": resource_usage["cpu_percent"]  # Already a percentage
            }

        return {
            "timestamp": __import__('datetime').datetime.now().isoformat(),
            "resource_usage": resource_usage,
            "budget_limits": budget_limits,
            "utilization_percent": utilization
        }

    except Exception as e:
        logger.error(f"Failed to get budget metrics: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get budget metrics: {e}") from e
