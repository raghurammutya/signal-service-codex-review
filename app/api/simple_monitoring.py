"""
Simple Enhanced Monitoring API for Signal Service

Minimal implementation that works without external dependencies.
Provides basic monitoring endpoints for immediate functionality testing.
"""
from datetime import datetime

from fastapi import APIRouter

router = APIRouter(prefix="/monitoring", tags=["simple-monitoring"])


@router.get("/status")
async def monitoring_status():
    """Simple status endpoint to test router functionality"""
    return {
        "status": "operational",
        "service": "simple_enhanced_monitoring",
        "timestamp": datetime.utcnow().isoformat(),
        "message": "Enhanced monitoring router is working"
    }


@router.get("/health-summary")
async def health_summary():
    """Basic health summary without external dependencies"""
    return {
        "service_health": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "uptime_estimate": "running",
        "basic_metrics": {
            "endpoint_accessible": True,
            "router_functional": True,
            "timestamp_generation": "working"
        }
    }


@router.get("/component-status")
async def component_status():
    """Check availability of monitoring components"""

    # Check if components can be imported
    components = {}

    import importlib.util

    # Check component availability without importing
    components["health_checker"] = "available" if importlib.util.find_spec("app.core.health_checker") else "not_available"
    components["circuit_breaker"] = "available" if importlib.util.find_spec("app.core.circuit_breaker") else "not_available"
    components["enhanced_metrics"] = "available" if importlib.util.find_spec("monitoring.enhanced_metrics") else "not_available"
    components["prometheus"] = "available" if importlib.util.find_spec("prometheus_client") else "not_available"

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "component_availability": components,
        "monitoring_router": "functional"
    }


@router.get("/basic-metrics")
async def basic_metrics():
    """Provide basic system metrics without external dependencies"""

    import psutil

    try:
        # Basic system metrics
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "system_metrics": {
                "cpu_usage_percent": cpu_percent,
                "memory_usage_percent": memory.percent,
                "memory_available_gb": round(memory.available / (1024**3), 2),
                "memory_total_gb": round(memory.total / (1024**3), 2)
            },
            "service_metrics": {
                "current_time": datetime.utcnow().isoformat(),
                "endpoint_response": "functional",
                "router_status": "operational"
            }
        }
    except Exception as e:
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "error": str(e),
            "status": "error_collecting_metrics",
            "fallback_metrics": {
                "router_functional": True,
                "timestamp_generation": "working"
            }
        }


@router.get("/deployment-test")
async def deployment_test():
    """Test endpoint for validating deployment success"""
    return {
        "deployment_status": "success",
        "router_registration": "confirmed",
        "endpoint_accessibility": "verified",
        "timestamp": datetime.utcnow().isoformat(),
        "test_result": "PASS - Enhanced monitoring router is accessible and functional"
    }
