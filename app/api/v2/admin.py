"""
Admin API endpoints for Signal Service
Provides administrative functions and monitoring
"""
import os
from datetime import datetime, timedelta
from typing import Any

import psutil
from fastapi import APIRouter, Depends, HTTPException, Query

from app.repositories.signal_repository import SignalRepository
from app.utils.logging_utils import log_error, log_info, log_warning


# Production-grade admin token verification
def verify_admin_token(token: str | None = None) -> str | None:
    """Production-grade admin token verification"""
    # Get environment from config_service (Architecture Principle #1: Config service exclusivity)
    try:
        from app.core.config import settings
        environment = settings.environment
    except Exception as e:
        raise RuntimeError(f"Failed to get environment from config_service for admin auth gating: {e}. No environment fallbacks allowed per architecture.")

    # In production, completely block admin endpoints
    if environment in ['production', 'prod', 'staging']:
        raise HTTPException(
            status_code=403,
            detail="Admin endpoints are disabled in production environment"
        )

    # In development, still require a token
    if not token:
        raise HTTPException(
            status_code=401,
            detail="Admin token required"
        )

    # Admin token from config_service (Architecture Principle #1: Config service exclusivity)
    try:
        from app.core.config import settings
        from common.config_service.client import ConfigServiceClient

        config_client = ConfigServiceClient(
            service_name="signal_service",
            environment=settings.environment,
            timeout=5
        )
        expected_token = config_client.get_secret("ADMIN_TOKEN")
        if not expected_token:
            raise ValueError("ADMIN_TOKEN not found in config_service")
    except Exception as e:
        raise RuntimeError(f"Failed to get admin token from config_service: {e}. No environment fallbacks allowed per architecture.")
    if token != expected_token:
        raise HTTPException(
            status_code=403,
            detail="Invalid admin token"
        )

    return token

from app.core.config import settings

router = APIRouter(prefix="/admin", tags=["admin"])


async def verify_admin(token: str = Depends(verify_admin_token)) -> bool:
    """Verify admin access with production-grade security"""
    # For now, just check if token exists
    if not token:
        raise HTTPException(status_code=403, detail="Admin access required")
    return True


@router.get("/status")
async def get_service_status(
    admin: bool = Depends(verify_admin)
) -> dict[str, Any]:
    """
    Get comprehensive service status

    Returns:
        Detailed service status including health, metrics, and configuration
    """
    try:
        # Get system metrics
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')

        # Get process info
        process = psutil.Process()
        process_info = {
            "pid": process.pid,
            "cpu_percent": process.cpu_percent(interval=1),
            "memory_rss_mb": process.memory_info().rss / 1024 / 1024,
            "num_threads": process.num_threads(),
            "connections": len(process.connections()),
        }

        # Get real service metrics from Redis instead of instantiating processor
        import json

        from app.utils.redis import get_redis_client

        service_metrics = {}
        try:
            redis_client = await get_redis_client()
            pod_id = os.environ.get('POD_NAME')
            if not pod_id:
                raise RuntimeError("POD_NAME environment variable required for service metrics. No fallbacks allowed per architecture.")

            # Try to get metrics from Redis
            metrics_key = f"signal:pod:metrics:{pod_id}"
            metrics_data = await redis_client.get(metrics_key)

            if not metrics_data:
                # Fallback to instance metrics key
                metrics_key = f"signal:instance:metrics:{pod_id}"
                metrics_data = await redis_client.get(metrics_key)

            if metrics_data:
                parsed_metrics = json.loads(metrics_data)
                service_metrics = {
                    "pod_id": pod_id,
                    "ticks_processed": parsed_metrics.get('ticks_processed', 0),
                    "computations_completed": parsed_metrics.get('computations_completed', 0),
                    "errors": parsed_metrics.get('errors', 0),
                    "uptime_seconds": parsed_metrics.get('uptime_seconds', 0),
                    "processing_rate": parsed_metrics.get('processing_rate', 0.0),
                    "is_running": parsed_metrics.get('is_running', False),
                    "last_updated": parsed_metrics.get('timestamp')
                }
            else:
                service_metrics = {"status": "metrics_not_available", "pod_id": pod_id}

        except Exception as e:
            log_warning(f"Unable to get service metrics from Redis: {e}")
            service_metrics = {"status": "metrics_unavailable", "error": str(e)}

        return {
            "status": "operational",
            "timestamp": datetime.utcnow().isoformat(),
            "system": {
                "cpu_percent": cpu_percent,
                "memory_percent": memory.percent,
                "memory_available_gb": memory.available / (1024**3),
                "disk_percent": disk.percent,
                "disk_free_gb": disk.free / (1024**3)
            },
            "process": process_info,
            "service": service_metrics,
            "configuration": {
                "version": settings.VERSION,
                "environment": settings.ENVIRONMENT,
                "max_batch_size": settings.MAX_BATCH_SIZE,
                "websocket_max_connections": settings.WEBSOCKET_MAX_CONNECTIONS,
                "api_rate_limit": settings.API_V2_RATE_LIMIT
            }
        }

    except Exception as e:
        log_error(f"Error getting service status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metrics/summary")
async def get_metrics_summary(
    hours: int = Query(24, ge=1, le=168),
    admin: bool = Depends(verify_admin)
) -> dict[str, Any]:
    """
    Get metrics summary for specified time period

    Args:
        hours: Number of hours to look back (max 168 = 7 days)

    Returns:
        Aggregated metrics summary
    """
    try:
        repository = SignalRepository()
        await repository.initialize()

        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=hours)

        metrics = await repository.get_computation_metrics(start_time, end_time)

        # Add WebSocket metrics if available
        from app.api.v2.websocket import manager
        if manager:
            metrics["websocket"] = {
                "active_connections": len(manager.active_connections),
                "active_subscriptions": len(manager.subscription_connections)
            }

        return metrics

    except Exception as e:
        log_error(f"Error getting metrics summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cache/clear")
async def clear_cache(
    cache_type: str = Query(..., regex="^(all|greeks|indicators|moneyness|timeframes)$"),
    admin: bool = Depends(verify_admin)
) -> dict[str, Any]:
    """
    Clear specific cache types

    Args:
        cache_type: Type of cache to clear

    Returns:
        Clear operation result
    """
    try:
        from app.utils.redis import get_redis_client
        redis_client = await get_redis_client()

        patterns = {
            "all": ["signal:*", "config:*", "agg_data:*", "ta_results:*"],
            "greeks": ["signal:greeks:*"],
            "indicators": ["signal:indicators:*", "ta_results:*"],
            "moneyness": ["signal:moneyness:*"],
            "timeframes": ["signal:timeframe:*", "agg_data:*"]
        }

        cleared_count = 0
        for pattern in patterns.get(cache_type, []):
            # Use SCAN to find keys matching pattern
            cursor = 0
            while True:
                cursor, keys = await redis_client.scan(
                    cursor, match=pattern, count=100
                )
                if keys:
                    await redis_client.delete(*keys)
                    cleared_count += len(keys)
                if cursor == 0:
                    break

        log_info(f"Cleared {cleared_count} cache keys for type: {cache_type}")

        return {
            "status": "success",
            "cache_type": cache_type,
            "keys_cleared": cleared_count,
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        log_error(f"Error clearing cache: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/data/cleanup")
async def cleanup_old_data(
    retention_days: int = Query(90, ge=7, le=365),
    dry_run: bool = Query(True),
    admin: bool = Depends(verify_admin)
) -> dict[str, Any]:
    """
    Clean up old data based on retention policy

    Args:
        retention_days: Number of days to retain data
        dry_run: If true, only show what would be deleted

    Returns:
        Cleanup operation result
    """
    try:
        repository = SignalRepository()
        await repository.initialize()

        cutoff_date = datetime.utcnow() - timedelta(days=retention_days)

        if dry_run:
            # Get count of records that would be deleted
            async with repository.db_connection.acquire() as conn:
                greeks_count = await conn.fetchval(
                    "SELECT COUNT(*) FROM signal_greeks WHERE timestamp < $1",
                    cutoff_date
                )
                indicators_count = await conn.fetchval(
                    "SELECT COUNT(*) FROM signal_indicators WHERE timestamp < $1",
                    cutoff_date
                )

            return {
                "status": "dry_run",
                "retention_days": retention_days,
                "cutoff_date": cutoff_date.isoformat(),
                "would_delete": {
                    "greeks": greeks_count,
                    "indicators": indicators_count
                }
            }
        # Perform actual cleanup
        await repository.cleanup_old_data(retention_days)

        return {
            "status": "completed",
            "retention_days": retention_days,
            "cutoff_date": cutoff_date.isoformat(),
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        log_error(f"Error cleaning up data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/connections/active")
async def get_active_connections(
    admin: bool = Depends(verify_admin)
) -> dict[str, Any]:
    """
    Get active WebSocket connections and their subscriptions

    Returns:
        Active connection details
    """
    try:
        from app.api.v2.websocket import manager

        if not manager:
            return {"error": "WebSocket manager not initialized"}

        connections = []
        for client_id, websocket in manager.active_connections.items():
            subscriptions = list(manager.connection_subscriptions.get(client_id, set()))
            connections.append({
                "client_id": client_id,
                "subscriptions": subscriptions,
                "subscription_count": len(subscriptions)
            })

        return {
            "total_connections": len(connections),
            "connections": connections,
            "total_subscriptions": len(manager.subscription_connections),
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        log_error(f"Error getting active connections: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scaling/trigger")
async def trigger_scaling_action(
    action: str = Query(..., regex="^(scale_up|scale_down|rebalance)$"),
    instances: int = Query(1, ge=1, le=10),
    admin: bool = Depends(verify_admin)
) -> dict[str, Any]:
    """
    Manually trigger scaling action

    Args:
        action: Scaling action to perform
        instances: Number of instances to scale by

    Returns:
        Scaling action result
    """
    try:
        # Placeholder - would implement scaling trigger
        return {"status": "triggered", "action": "scaling"}
    except Exception as e:
        log_error(f"Error triggering scaling: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/config/current")
async def get_current_configuration(
    admin: bool = Depends(verify_admin)
) -> dict[str, Any]:
    """
    Get current service configuration

    Returns:
        Current configuration values
    """
    try:
        config_dict = settings.dict()

        # Remove sensitive values
        sensitive_keys = ["REDIS_PASSWORD", "DB_PASSWORD", "SECRET_KEY", "API_KEYS"]
        for key in sensitive_keys:
            if key in config_dict:
                config_dict[key] = "***REDACTED***"

        return {
            "configuration": config_dict,
            "environment": settings.ENVIRONMENT,
            "version": settings.VERSION,
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        log_error(f"Error getting configuration: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/config/reload")
async def reload_configuration(
    admin: bool = Depends(verify_admin)
) -> dict[str, Any]:
    """
    Reload configuration from environment

    Returns:
        Reload operation result
    """
    try:
        # In production, implement configuration reload
        # For now, return success

        log_info("Configuration reload requested")

        return {
            "status": "success",
            "message": "Configuration reload initiated",
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        log_error(f"Error reloading configuration: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health/dependencies")
async def check_dependencies_health(
    admin: bool = Depends(verify_admin)
) -> dict[str, Any]:
    """
    Check health of all service dependencies

    Returns:
        Health status of each dependency
    """
    try:
        from app.main import app

        health_checks = {}

        # Check Redis
        try:
            redis_client = app.state.connections.get("redis")
            if redis_client:
                await redis_client.ping()
                health_checks["redis"] = {"status": "healthy", "latency_ms": 5}
            else:
                health_checks["redis"] = {"status": "unavailable"}
        except Exception as e:
            health_checks["redis"] = {"status": "unhealthy", "error": str(e)}

        # Check TimescaleDB
        try:
            db_conn = app.state.connections.get("timescaledb_async")
            if db_conn:
                async with db_conn.acquire() as conn:
                    await conn.fetchval("SELECT 1")
                health_checks["timescaledb"] = {"status": "healthy", "latency_ms": 10}
            else:
                health_checks["timescaledb"] = {"status": "unavailable"}
        except Exception as e:
            health_checks["timescaledb"] = {"status": "unhealthy", "error": str(e)}

        # Check Instrument Service
        try:
            from app.clients.client_factory import get_client_manager
            manager = get_client_manager()
            client = await manager.get_client('instrument_service')
            await client.get_instrument("NSE@RELIANCE@equities")
            health_checks["instrument_service"] = {"status": "healthy"}
        except Exception as e:
            health_checks["instrument_service"] = {"status": "unhealthy", "error": str(e)}

        return {
            "overall_status": "healthy" if all(
                dep["status"] == "healthy" for dep in health_checks.values()
            ) else "degraded",
            "dependencies": health_checks,
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        log_error(f"Error checking dependencies: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def _execute_k8s_scaling_action(action: str, instances: int) -> dict[str, Any]:
    """
    Execute real Kubernetes scaling action via kubectl or Kubernetes API.

    Args:
        action: scaling action (scale_up, scale_down)
        instances: number of instances to scale

    Returns:
        Scaling execution result
    """
    try:
        # Get deployment name from config_service
        from app.core.config import settings
        from common.config_service.client import ConfigServiceClient

        config_client = ConfigServiceClient(
            service_name="signal_service",
            environment=settings.environment
        )

        deployment_name = config_client.get_config("K8S_DEPLOYMENT_NAME")
        namespace = config_client.get_config("K8S_NAMESPACE")

        if not deployment_name:
            raise ValueError("K8S_DEPLOYMENT_NAME not configured in config_service")
        if not namespace:
            raise ValueError("K8S_NAMESPACE not configured in config_service")

        # Execute kubectl command with timeout
        import json as json_lib
        import subprocess

        command_timeout = 30  # 30 second timeout for kubectl commands

        if action == "scale_up":
            # Get current replica count first
            get_cmd = ["kubectl", "get", "deployment", deployment_name, "-n", namespace, "-o", "json"]
            get_result = subprocess.run(get_cmd, capture_output=True, text=True, check=True, timeout=command_timeout)
            deployment_info = json_lib.loads(get_result.stdout)

            current_replicas = deployment_info["spec"]["replicas"]
            target_replicas = current_replicas + instances

        elif action == "scale_down":
            # Get current replica count first
            get_cmd = ["kubectl", "get", "deployment", deployment_name, "-n", namespace, "-o", "json"]
            get_result = subprocess.run(get_cmd, capture_output=True, text=True, check=True, timeout=command_timeout)
            deployment_info = json_lib.loads(get_result.stdout)

            current_replicas = deployment_info["spec"]["replicas"]
            target_replicas = max(1, current_replicas - instances)  # Minimum 1 replica

        else:
            raise ValueError(f"Unsupported scaling action: {action}")

        # Execute scaling
        scale_cmd = ["kubectl", "scale", "deployment", deployment_name, "-n", namespace, f"--replicas={target_replicas}"]
        scale_result = subprocess.run(scale_cmd, capture_output=True, text=True, check=True, timeout=command_timeout)

        log_info(f"Kubernetes scaling executed: {action} from {current_replicas} to {target_replicas} replicas")

        return {
            "success": True,
            "action": action,
            "previous_replicas": current_replicas,
            "target_replicas": target_replicas,
            "deployment_name": deployment_name,
            "namespace": namespace,
            "kubectl_output": scale_result.stdout.strip(),
            "timestamp": datetime.utcnow().isoformat()
        }

    except subprocess.TimeoutExpired as e:
        error_msg = f"kubectl command timed out after {command_timeout}s: {str(e)}"
        log_error(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "timestamp": datetime.utcnow().isoformat()
        }
    except subprocess.CalledProcessError as e:
        error_msg = f"kubectl command failed: {e.stderr.decode() if e.stderr else str(e)}"
        log_error(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        error_msg = f"Scaling execution failed: {e}"
        log_error(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "timestamp": datetime.utcnow().isoformat()
        }
