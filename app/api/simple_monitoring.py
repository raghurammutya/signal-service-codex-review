"""
Simple Enhanced Monitoring API for Signal Service

Minimal implementation that works without external dependencies.
Provides basic monitoring endpoints for immediate functionality testing.
"""
from typing import Dict, Any
from fastapi import APIRouter, HTTPException
from datetime import datetime
import json

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
    
    try:
        from app.core.health_checker import get_health_checker
        components["health_checker"] = "available"
    except ImportError:
        components["health_checker"] = "not_available"
    
    try:
        from app.core.circuit_breaker import get_circuit_breaker_manager  
        components["circuit_breaker"] = "available"
    except ImportError:
        components["circuit_breaker"] = "not_available"
    
    try:
        from monitoring.enhanced_metrics import get_enhanced_metrics_collector
        components["enhanced_metrics"] = "available"
    except ImportError:
        components["enhanced_metrics"] = "not_available"
    
    try:
        from prometheus_client import generate_latest
        components["prometheus"] = "available"
    except ImportError:
        components["prometheus"] = "not_available"
    
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "component_availability": components,
        "monitoring_router": "functional"
    }


@router.get("/basic-metrics")
async def basic_metrics():
    """Provide basic system metrics without external dependencies"""
    import psutil
    import time
    
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