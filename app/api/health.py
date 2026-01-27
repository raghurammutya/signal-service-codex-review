"""
Health check endpoints for Signal Service
"""
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import PlainTextResponse

from app.core.distributed_health_manager import DistributedHealthManager
from app.core.health_checker import HealthChecker

logger = logging.getLogger(__name__)

# Architecture Principle #3: API versioning is mandatory
# Health endpoints are versioned for consistency with all API endpoints
router = APIRouter(prefix="/api/v1/health", tags=["health"])

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

@router.get("", response_class=PlainTextResponse)
async def basic_health_check():
    """
    Basic health check endpoint - returns 200 OK if service is running
    This is the most basic health check that load balancers can use
    """
    return "OK"

@router.get("/live")
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

@router.get("/ready")
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
        raise HTTPException(
            status_code=503,
            detail=f"Service not ready: {health_data['status']}"
        )

    except Exception as e:
        logger.error(f"Readiness probe failed: {e}")
        raise HTTPException(status_code=503, detail="Service not ready")

@router.get("/detailed")
async def detailed_health_check(checker: HealthChecker = Depends(get_health_checker)):
    """
    Detailed health check with all component information
    Used by monitoring systems and dashboards
    """
    try:
        health_data = await checker.get_comprehensive_health()

        # Set HTTP status code based on health
        status_code = 200
        if health_data['status'] == 'unhealthy' or health_data['status'] == 'error':
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

@router.get("/cluster")
async def cluster_health_check(dist_health: DistributedHealthManager = Depends(get_distributed_health)):
    """
    Cluster-wide health check showing all Signal Service instances
    Used by the dynamic dashboard to show horizontal scaling status
    """
    try:
        cluster_data = await dist_health.get_cluster_health_for_dashboard()

        # Set HTTP status code based on cluster health
        status_code = 200
        if cluster_data['status'] == 'unhealthy' or cluster_data['status'] == 'error':
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

@router.get("/dashboard")
async def dashboard_health_summary(dist_health: DistributedHealthManager = Depends(get_distributed_health)):
    """
    Health summary specifically formatted for the dynamic dashboard at localhost:8500
    This endpoint provides the standardized format expected by the dashboard
    """
    try:
        cluster_data = await dist_health.get_cluster_health_for_dashboard()

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
            service_port = config_client.get_config("SERVICE_PORT")

            if not service_port:
                raise ValueError("SERVICE_PORT not found in config_service")

        except Exception as e:
            raise RuntimeError(f"Failed to get service configuration from config_service: {e}. No hardcoded fallbacks allowed per architecture.")

        # Format according to dashboard expectations
        from app.core.config import settings
        dashboard_format = {
            "service_name": service_name,
            "service_type": "signal_processing",
            "status": "healthy",
            "port": service_port,
            "timestamp": datetime.utcnow().isoformat(),
            "cluster_status": cluster_data['status'],
            "total_instances": len(cluster_data.get('instances', [])),
            "healthy_instances": len([i for i in cluster_data.get('instances', []) if i.get('healthy', False)])
        }

        return dashboard_format

    except Exception as e:
        logger.error(f"Dashboard health summary failed: {e}")
        raise HTTPException(status_code=500, detail=f"Dashboard health check failed: {e}")
