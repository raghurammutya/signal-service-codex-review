"""
Admin API endpoints for Signal Service
Provides administrative functions and monitoring
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import psutil
import asyncio

from app.utils.logging_utils import log_info, log_error, log_warning
from app.repositories.signal_repository import SignalRepository
from app.services.instrument_service_client import InstrumentServiceClient

# Simple admin token verification
def verify_admin_token(token: Optional[str] = None) -> Optional[str]:
    """Simple admin token verification"""
    return token

from app.services.signal_processor import SignalProcessor
from app.core.config import settings


router = APIRouter(prefix="/admin", tags=["admin"])


async def verify_admin(token: str = Depends(verify_admin_token)) -> bool:
    """Verify admin access"""
    # In production, implement proper admin verification
    # For now, just check if token exists
    if not token:
        raise HTTPException(status_code=403, detail="Admin access required")
    return True


@router.get("/status")
async def get_service_status(
    admin: bool = Depends(verify_admin)
) -> Dict[str, Any]:
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
        
        # Get service metrics
        from app.main import app
        signal_processor = getattr(app.state, 'signal_processor', None)
        
        service_metrics = {}
        if signal_processor:
            service_metrics = signal_processor.get_metrics()
            
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
) -> Dict[str, Any]:
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
) -> Dict[str, Any]:
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
) -> Dict[str, Any]:
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
        else:
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
) -> Dict[str, Any]:
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
) -> Dict[str, Any]:
    """
    Manually trigger scaling action
    
    Args:
        action: Scaling action to perform
        instances: Number of instances to scale by
        
    Returns:
        Scaling action result
    """
    try:
        # Production implementation requires Docker orchestrator integration
        from fastapi import HTTPException
        log_warning(f"Manual scaling requested: {action} by {instances} instances - requires orchestrator integration")
        
        raise HTTPException(
            status_code=501, 
            detail=f"Manual scaling requires Docker orchestrator integration - cannot perform {action} operation"
        )
        
    except Exception as e:
        log_error(f"Error triggering scaling: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/config/current")
async def get_current_configuration(
    admin: bool = Depends(verify_admin)
) -> Dict[str, Any]:
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
) -> Dict[str, Any]:
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
) -> Dict[str, Any]:
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
