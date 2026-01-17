"""
Health check endpoints for Signal Service
"""
import asyncio
from datetime import datetime
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, Depends, Response
from fastapi.responses import PlainTextResponse
import logging

from app.core.health_checker import HealthChecker, HealthStatus
from app.core.distributed_health_manager import DistributedHealthManager

logger = logging.getLogger(__name__)

router = APIRouter()

# Global health checker instance (will be initialized in main.py)
health_checker: HealthChecker = None
distributed_health: DistributedHealthManager = None

def get_health_checker():
    """Dependency to get health checker instance"""
    if not health_checker:
        raise HTTPException(status_code=503, detail="Health checker not initialized")
    return health_checker

def get_distributed_health():
    """Dependency to get distributed health manager"""
    if not distributed_health:
        raise HTTPException(status_code=503, detail="Distributed health manager not initialized")
    return distributed_health

@router.get("/health", response_class=PlainTextResponse)
async def basic_health_check():
    """
    Basic health check endpoint - returns 200 OK if service is running
    This is the most basic health check that load balancers can use
    """
    return "OK"

@router.get("/health/live")
async def liveness_probe():
    """
    Kubernetes liveness probe - checks if the service should be restarted
    Returns 200 if service is alive, 503 if it should be restarted
    """
    try:
        # Very basic check - just ensure the service can respond
        return {
            "status": "alive",
            "timestamp": datetime.utcnow().isoformat(),
            "service": "signal_service"
        }
    except Exception as e:
        logger.error(f"Liveness probe failed: {e}")
        raise HTTPException(status_code=503, detail="Service not alive")

@router.get("/health/ready")
async def readiness_probe(checker: HealthChecker = Depends(get_health_checker)):
    """
    Kubernetes readiness probe - checks if service is ready to handle requests
    Returns 200 if ready, 503 if not ready to serve traffic
    """
    try:
        health_data = await checker.get_comprehensive_health()
        
        # Service is ready if status is healthy or unhealthy (but not error)
        if health_data['status'] in ['healthy', 'unhealthy']:
            return {
                "status": "ready",
                "timestamp": health_data['timestamp'],
                "service": "signal_service",
                "components_status": health_data['summary']
            }
        else:
            raise HTTPException(
                status_code=503, 
                detail=f"Service not ready: {health_data['status']}"
            )
            
    except Exception as e:
        logger.error(f"Readiness probe failed: {e}")
        raise HTTPException(status_code=503, detail="Service not ready")

@router.get("/health/detailed")
async def detailed_health_check(checker: HealthChecker = Depends(get_health_checker)):
    """
    Detailed health check with all component information
    Used by monitoring systems and dashboards
    """
    try:
        health_data = await checker.get_comprehensive_health()
        
        # Set HTTP status code based on health
        status_code = 200
        if health_data['status'] == 'unhealthy':
            status_code = 503  # Service Unavailable
        elif health_data['status'] == 'error':
            status_code = 503  # Service Unavailable
        
        import json
        return Response(
            content=json.dumps(health_data, default=str),
            status_code=status_code,
            media_type="application/json"
        )
        
    except Exception as e:
        logger.error(f"Detailed health check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Health check failed: {e}")

@router.get("/health/cluster")
async def cluster_health_check(dist_health: DistributedHealthManager = Depends(get_distributed_health)):
    """
    Cluster-wide health check showing all Signal Service instances
    Used by the dynamic dashboard to show horizontal scaling status
    """
    try:
        cluster_data = await dist_health.get_cluster_health_for_dashboard()
        
        # Set HTTP status code based on cluster health
        status_code = 200
        if cluster_data['status'] == 'unhealthy':
            status_code = 503
        elif cluster_data['status'] == 'error':
            status_code = 503
        
        import json
        return Response(
            content=json.dumps(cluster_data, default=str),
            status_code=status_code,
            media_type="application/json"
        )
        
    except Exception as e:
        logger.error(f"Cluster health check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Cluster health check failed: {e}")

@router.get("/health/dashboard")
async def dashboard_health_summary(dist_health: DistributedHealthManager = Depends(get_distributed_health)):
    """
    Health summary specifically formatted for the dynamic dashboard at localhost:8500
    This endpoint provides the standardized format expected by the dashboard
    """
    try:
        cluster_data = await dist_health.get_cluster_health_for_dashboard()
        
        # Format according to dashboard expectations
        from app.core.config import settings
        dashboard_format = {
            "service_name": "Signal Service",
            "service_type": "signal_processing",
            "port": settings.SERVICE_PORT,
            "status": cluster_data['status'],
            "timestamp": cluster_data['timestamp'],
            "health_endpoint": "/health/dashboard",
            "detailed_endpoint": "/health/detailed",
            "cluster_endpoint": "/health/cluster",
            
            # Instance information for horizontal scaling display
            "instances": cluster_data['instances'],
            "cluster_summary": {
                "total_instances": cluster_data['cluster_metrics']['total_instances'],
                "healthy_instances": cluster_data['cluster_metrics']['healthy_instances'],
                "unhealthy_instances": cluster_data['cluster_metrics']['unhealthy_instances'],
                "error_instances": cluster_data['cluster_metrics']['error_instances']
            },
            
            # Performance metrics
            "performance_metrics": {
                "total_requests_per_minute": cluster_data['cluster_metrics']['total_requests_per_minute'],
                "average_cpu_percent": cluster_data['cluster_metrics']['average_cpu_percent'],
                "average_memory_percent": cluster_data['cluster_metrics']['average_memory_percent'],
                "total_queue_size": cluster_data['cluster_metrics']['total_queue_size'],
                "total_assigned_instruments": cluster_data['cluster_metrics']['total_assigned_instruments']
            },
            
            # Scaling information
            "scaling_info": {
                "current_instances": cluster_data['cluster_metrics']['total_instances'],
                "recommendation": cluster_data['scaling_recommendation'],
                "load_distribution": cluster_data['load_distribution']
            },
            
            # Service-specific metadata
            "service_metadata": {
                "version": "2.0.0",
                "capabilities": [
                    "real_time_greeks",
                    "moneyness_calculation", 
                    "market_profile",
                    "frequency_management",
                    "horizontal_scaling"
                ],
                "api_version": "v2",
                "websocket_support": True
            }
        }
        
        return dashboard_format
        
    except Exception as e:
        logger.error(f"Dashboard health summary failed: {e}")
        raise HTTPException(status_code=500, detail=f"Dashboard health failed: {e}")

@router.get("/health/metrics")
async def health_metrics():
    """
    Prometheus-compatible health metrics
    Used by monitoring systems for alerting and dashboards
    """
    try:
        if not health_checker:
            raise HTTPException(status_code=503, detail="Health checker not available")
            
        health_data = await health_checker.get_comprehensive_health()
        
        # Convert health data to Prometheus metrics format
        metrics = []
        
        # Overall health status (1 = healthy, 0.5 = unhealthy, 0 = error)
        status_value = 1 if health_data['status'] == 'healthy' else (0.5 if health_data['status'] == 'unhealthy' else 0)
        metrics.append(f'signal_service_health_status {status_value}')
        
        # Component health metrics
        for component_name, component_data in health_data['components'].items():
            component_status = 1 if component_data.get('status') == 'up' else 0
            metrics.append(f'signal_service_component_health{{component="{component_name}"}} {component_status}')
        
        # Performance metrics
        summary = health_data.get('summary', {})
        perf_metrics = summary.get('performance_metrics', {})
        
        for metric_name, value in perf_metrics.items():
            if value is not None:
                metrics.append(f'signal_service_{metric_name} {value}')
        
        # Uptime
        metrics.append(f'signal_service_uptime_seconds {health_data["uptime_seconds"]}')
        
        # Check duration
        metrics.append(f'signal_service_health_check_duration_seconds {health_data["check_duration_ms"] / 1000}')
        
        return PlainTextResponse('\n'.join(metrics))
        
    except Exception as e:
        logger.error(f"Health metrics failed: {e}")
        raise HTTPException(status_code=500, detail="Metrics unavailable")

@router.get("/health/components/{component_name}")
async def component_health(component_name: str, checker: HealthChecker = Depends(get_health_checker)):
    """
    Get health status for a specific component
    Useful for debugging specific issues
    """
    try:
        health_data = await checker.get_comprehensive_health()
        
        components = health_data.get('components', {})
        if component_name not in components:
            raise HTTPException(status_code=404, detail=f"Component '{component_name}' not found")
        
        component_data = components[component_name]
        
        # Set status code based on component health
        status_code = 200
        if component_data.get('status') == 'degraded':
            status_code = 503
        elif component_data.get('status') == 'down':
            status_code = 503
        
        import json
        return Response(
            content=json.dumps({
                "component": component_name,
                "status": component_data.get('status'),
                "details": component_data,
                "timestamp": datetime.utcnow().isoformat()
            }, default=str),
            status_code=status_code,
            media_type="application/json"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Component health check failed for {component_name}: {e}")
        raise HTTPException(status_code=500, detail=f"Component health check failed: {e}")

@router.post("/health/refresh")
async def refresh_health_cache(checker: HealthChecker = Depends(get_health_checker)):
    """
    Force refresh of health check cache
    Useful for immediate health status updates
    """
    try:
        # Clear cached health data
        checker.cached_health = None
        checker.last_check_time = None
        
        # Perform fresh health check
        health_data = await checker.get_comprehensive_health()
        
        return {
            "message": "Health cache refreshed",
            "timestamp": health_data['timestamp'],
            "status": health_data['status']
        }
        
    except Exception as e:
        logger.error(f"Health cache refresh failed: {e}")
        raise HTTPException(status_code=500, detail=f"Cache refresh failed: {e}")

# Health check initialization functions
def initialize_health_checker(redis_client, db_session, signal_processor=None):
    """Initialize the global health checker"""
    global health_checker
    health_checker = HealthChecker(redis_client, db_session, signal_processor)
    logger.info("Health checker initialized")

def initialize_distributed_health(redis_client, instance_id: str = None):
    """Initialize the global distributed health manager"""
    global distributed_health
    distributed_health = DistributedHealthManager(redis_client, instance_id)
    logger.info(f"Distributed health manager initialized with instance_id: {distributed_health.instance_id}")

async def start_health_monitoring():
    """Start background health monitoring tasks"""
    if not distributed_health or not health_checker:
        logger.error("Health components not initialized")
        return
    
    # Register this instance
    await distributed_health.register_instance(health_checker)
    
    # Start background tasks
    tasks = [
        asyncio.create_task(distributed_health.start_heartbeat(health_checker)),
        asyncio.create_task(periodic_cleanup())
    ]
    
    logger.info("Health monitoring started")
    return tasks

async def periodic_cleanup():
    """Periodic cleanup of dead instances"""
    while True:
        try:
            if distributed_health:
                await distributed_health.cleanup_dead_instances()
            await asyncio.sleep(60)  # Cleanup every minute
        except Exception as e:
            logger.error(f"Periodic cleanup failed: {e}")
            await asyncio.sleep(30)  # Retry after 30 seconds

async def shutdown_health_monitoring():
    """Gracefully shutdown health monitoring"""
    if distributed_health:
        await distributed_health.shutdown()
        logger.info("Health monitoring shutdown complete")