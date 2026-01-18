"""
Dashboard registration for Signal Service with localhost:8500 dynamic dashboard
"""
import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional
import httpx

logger = logging.getLogger(__name__)

class DashboardRegistrar:
    """Manages registration with the dynamic dashboard"""
    
<<<<<<< HEAD
    def __init__(self, dashboard_url: str = None, service_url: str = None):
        # Get URLs from config_service exclusively (Architecture Principle #1: Config service exclusivity)
        if dashboard_url is None:
            try:
                from common.config_service.client import ConfigServiceClient
                from app.core.config import settings
                
                config_client = ConfigServiceClient(
                    service_name="signal_service",
                    environment=settings.environment,
                    timeout=5
                )
                dashboard_url = config_client.get_config("DASHBOARD_SERVICE_URL")
                if not dashboard_url:
                    raise ValueError("DASHBOARD_SERVICE_URL not found in config_service")
            except Exception as e:
                raise RuntimeError(f"Failed to get dashboard URL from config_service: {e}. No hardcoded fallbacks allowed per architecture.")
        
        if service_url is None:
            try:
                from common.config_service.client import ConfigServiceClient
                from app.core.config import settings
                
                config_client = ConfigServiceClient(
                    service_name="signal_service",
                    environment=settings.environment,
                    timeout=5
                )
                service_url = config_client.get_config("SIGNAL_SERVICE_URL")
                if not service_url:
                    raise ValueError("SIGNAL_SERVICE_URL not found in config_service")
            except Exception as e:
                raise RuntimeError(f"Failed to get service URL from config_service: {e}. No hardcoded fallbacks allowed per architecture.")
                
        self.dashboard_url = dashboard_url
        self.service_url = service_url
=======
    def __init__(self, dashboard_url: str = None):
        if dashboard_url is None:
            from app.core.config import settings
            if not hasattr(settings, 'DASHBOARD_URL'):
                raise RuntimeError("DASHBOARD_URL not configured in config_service - cannot register with dashboard")
            dashboard_url = settings.DASHBOARD_URL
        self.dashboard_url = dashboard_url
        
        # Get service configuration from config service
        from app.core.config import settings
        if not hasattr(settings, 'SERVICE_HOST') or not hasattr(settings, 'SERVICE_PORT'):
            raise RuntimeError("SERVICE_HOST and SERVICE_PORT not configured in config_service")
        
        self.service_url = f"http://{settings.SERVICE_HOST}:{settings.SERVICE_PORT}"
>>>>>>> compliance-violations-fixed
        self.registration_endpoint = f"{dashboard_url}/api/services/register"
        self.health_update_endpoint = f"{dashboard_url}/api/services/health"
        self.registration_interval = 30  # seconds
        self.is_registered = False
        
    async def register_service(self) -> bool:
        """Register Signal Service with the dynamic dashboard"""
        try:
            # Get configuration from config_service exclusively (Architecture Principle #1: Config service exclusivity)
            try:
                from common.config_service.client import ConfigServiceClient
                from app.core.config import settings
                
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
                raise RuntimeError(f"Failed to get service configuration from config_service: {e}. No hardcoded fallbacks allowed per architecture.")
            
            service_config = {
                "service_name": service_name,
                "service_id": "signal_service", 
                "service_type": "signal_processing",
<<<<<<< HEAD
                "host": service_host,
                "port": int(service_port),
                # Architecture Principle #3: API versioning is mandatory - all health endpoints must be versioned
                "health_endpoint": f"{self.service_url}/api/v1/health/dashboard",
                "detailed_health_endpoint": f"{self.service_url}/api/v1/health/detailed", 
                "cluster_health_endpoint": f"{self.service_url}/api/v1/health/cluster",
                "metrics_endpoint": f"{self.service_url}/api/v1/health/metrics",
=======
                "host": settings.SERVICE_HOST,
                "port": int(settings.SERVICE_PORT),
                "health_endpoint": f"{self.service_url}/health/dashboard",
                "detailed_health_endpoint": f"{self.service_url}/health/detailed",
                "cluster_health_endpoint": f"{self.service_url}/health/cluster",
                "metrics_endpoint": f"{self.service_url}/health/metrics",
>>>>>>> compliance-violations-fixed
                "api_base_url": f"{self.service_url}/api/v2",
                
                # Service metadata
                "metadata": {
                    "version": "2.0.0",
                    "description": "Real-time options Greeks calculation and signal processing service",
                    "capabilities": [
                        "real_time_greeks_calculation",
                        "moneyness_analytics", 
                        "market_profile_computation",
                        "frequency_based_feeds",
                        "horizontal_scaling",
                        "websocket_streaming",
                        "batch_processing"
                    ],
                    "api_version": "v2",
                    "websocket_endpoint": f"{self.service_url}/api/v2/signals/subscriptions/websocket",
                    "documentation_url": f"{self.service_url}/docs"
                },
                
                # Health check configuration
                "health_config": {
                    "check_interval_seconds": 30,
                    "timeout_seconds": 10,
                    "healthy_threshold": 2,
                    "unhealthy_threshold": 3
                },
                
                # Scaling configuration
                "scaling_config": {
                    "supports_horizontal_scaling": True,
                    "min_instances": 1,
                    "max_instances": 10,
                    "auto_scaling_enabled": True,
                    "scaling_metrics": [
                        "cpu_percent",
                        "memory_percent", 
                        "queue_size",
                        "requests_per_minute"
                    ]
                },
                
                # Dashboard display configuration
                "dashboard_config": {
                    "display_name": service_name,
                    "icon": "📊",
                    "color": "#4A90E2",
                    "category": "Core Services",
                    "priority": 3,
                    "show_instances": True,
                    "show_scaling_controls": True,
                    "show_performance_metrics": True
                }
            }
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    self.registration_endpoint,
                    json=service_config,
                    headers={"Content-Type": "application/json"}
                )
                
                if response.status_code == 200:
                    self.is_registered = True
                    logger.info("Successfully registered with dynamic dashboard")
                    return True
                else:
                    logger.error(f"Dashboard registration failed: {response.status_code} - {response.text}")
                    return False
                    
        except httpx.ConnectError:
            logger.warning(f"Could not connect to dashboard at {self.dashboard_url} - dashboard may not be running")
            return False
        except Exception as e:
            logger.error(f"Dashboard registration failed: {e}")
            return False
    
    async def start_health_updates(self, distributed_health_manager) -> None:
        """Start periodic health updates to the dashboard"""
        while True:
            try:
                if not self.is_registered:
                    # Try to register first
                    await self.register_service()
                    await asyncio.sleep(10)
                    continue
                
                # Send health update
                await self._send_health_update(distributed_health_manager)
                await asyncio.sleep(self.registration_interval)
                
            except Exception as e:
                logger.error(f"Health update failed: {e}")
                await asyncio.sleep(30)  # Wait before retrying
    
    async def _send_health_update(self, distributed_health_manager) -> None:
        """Send health update to the dashboard"""
        try:
            # Get cluster health data
            health_data = await distributed_health_manager.get_cluster_health_for_dashboard()
            
            # Format for dashboard
            update_payload = {
                "service_id": "signal_service",
                "timestamp": datetime.utcnow().isoformat(),
                "health_data": health_data
            }
            
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(
                    self.health_update_endpoint,
                    json=update_payload,
                    headers={"Content-Type": "application/json"}
                )
                
                if response.status_code != 200:
                    logger.warning(f"Health update failed: {response.status_code}")
                    
        except httpx.ConnectError:
            logger.debug("Dashboard not reachable for health update")
        except Exception as e:
            logger.error(f"Health update error: {e}")
    
    async def unregister_service(self) -> None:
        """Unregister service from dashboard"""
        try:
            unregister_endpoint = f"{self.dashboard_url}/api/services/unregister"
            
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(
                    unregister_endpoint,
                    json={"service_id": "signal_service"},
                    headers={"Content-Type": "application/json"}
                )
                
                if response.status_code == 200:
                    logger.info("Successfully unregistered from dashboard")
                else:
                    logger.warning(f"Unregistration failed: {response.status_code}")
                    
        except Exception as e:
            logger.error(f"Unregistration error: {e}")
    
    async def send_scaling_notification(self, scaling_event: Dict[str, Any]) -> None:
        """Send scaling notification to dashboard"""
        try:
            scaling_endpoint = f"{self.dashboard_url}/api/services/scaling-event"
            
            notification = {
                "service_id": "signal_service",
                "timestamp": datetime.utcnow().isoformat(),
                "event_type": scaling_event.get("action", "unknown"),
                "details": scaling_event
            }
            
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(
                    scaling_endpoint,
                    json=notification,
                    headers={"Content-Type": "application/json"}
                )
                
        except Exception as e:
            logger.error(f"Scaling notification error: {e}")


class DashboardIntegration:
    """Main integration class for dashboard connectivity"""
    
    def __init__(self, dashboard_url: str = None):
<<<<<<< HEAD
        # Get dashboard URL from config_service exclusively (Architecture Principle #1: Config service exclusivity)
        if dashboard_url is None:
            try:
                from common.config_service.client import ConfigServiceClient
                from app.core.config import settings
                
                config_client = ConfigServiceClient(
                    service_name="signal_service",
                    environment=settings.environment,
                    timeout=5
                )
                dashboard_url = config_client.get_config("DASHBOARD_SERVICE_URL")
                if not dashboard_url:
                    raise ValueError("DASHBOARD_SERVICE_URL not found in config_service")
            except Exception as e:
                raise RuntimeError(f"Failed to get dashboard URL from config_service: {e}. No hardcoded fallbacks allowed per architecture.")
                
=======
        if dashboard_url is None:
            from app.core.config import settings
            if not hasattr(settings, 'DASHBOARD_URL'):
                raise RuntimeError("DASHBOARD_URL not configured in config_service")
            dashboard_url = settings.DASHBOARD_URL
>>>>>>> compliance-violations-fixed
        self.registrar = DashboardRegistrar(dashboard_url)
        self.background_tasks = []
    
    async def initialize(self, distributed_health_manager) -> None:
        """Initialize dashboard integration"""
        try:
            # Register with dashboard
            await self.registrar.register_service()
            
            # Start background health updates
            health_task = asyncio.create_task(
                self.registrar.start_health_updates(distributed_health_manager)
            )
            self.background_tasks.append(health_task)
            
            logger.info("Dashboard integration initialized")
            
        except Exception as e:
            logger.error(f"Dashboard integration initialization failed: {e}")
    
    async def handle_scaling_event(self, scaling_event: Dict[str, Any]) -> None:
        """Handle scaling events and notify dashboard"""
        try:
            await self.registrar.send_scaling_notification(scaling_event)
            logger.info(f"Scaling event sent to dashboard: {scaling_event['action']}")
        except Exception as e:
            logger.error(f"Failed to send scaling event: {e}")
    
    async def shutdown(self) -> None:
        """Shutdown dashboard integration"""
        try:
            # Cancel background tasks
            for task in self.background_tasks:
                task.cancel()
            
            # Wait for tasks to complete
            if self.background_tasks:
                await asyncio.gather(*self.background_tasks, return_exceptions=True)
            
            # Unregister from dashboard
            await self.registrar.unregister_service()
            
            logger.info("Dashboard integration shutdown complete")
            
        except Exception as e:
            logger.error(f"Dashboard integration shutdown error: {e}")


# Dashboard data formatting utilities
def format_instance_data_for_dashboard(instances: list) -> Dict[str, Any]:
    """Format instance data specifically for dashboard display"""
    # Get service port from config_service exclusively (Architecture Principle #1: Config service exclusivity)
    try:
        from common.config_service.client import ConfigServiceClient
        from app.core.config import settings
        
        config_client = ConfigServiceClient(
            service_name="signal_service",
            environment=settings.environment,
            timeout=5
        )
        service_port = config_client.get_config("SERVICE_PORT")
        if not service_port:
            raise ValueError("SERVICE_PORT not found in config_service")
            
    except Exception as e:
        raise RuntimeError(f"Failed to get service port from config_service: {e}. No hardcoded fallbacks allowed per architecture.")
    
    return {
        "instances": [
            {
                "id": inst["instance_id"],
                "name": inst["container_name"],
                "status": inst["status"],
                "host": inst["host"],
<<<<<<< HEAD
                "port": int(service_port),
=======
                "port": int(inst.get("port", 8003)),
>>>>>>> compliance-violations-fixed
                "uptime": inst["uptime_seconds"],
                "cpu_usage": inst["load_metrics"].get("cpu_percent", 0),
                "memory_usage": inst["load_metrics"].get("memory_percent", 0),
                "requests_per_minute": inst["load_metrics"].get("requests_per_minute", 0),
                "queue_size": inst["load_metrics"].get("queue_size", 0),
                "assigned_instruments": inst["assigned_instruments_count"],
<<<<<<< HEAD
                # Architecture Principle #3: API versioning is mandatory - health endpoints must be versioned
                "health_endpoint": f"http://{inst['host']}:{service_port}/api/v1/health/detailed"
=======
                "health_endpoint": f"http://{inst['host']}:{inst.get('port', 8003)}/health/detailed"
>>>>>>> compliance-violations-fixed
            }
            for inst in instances
        ],
        "cluster_summary": {
            "total_instances": len(instances),
            "healthy_instances": sum(1 for inst in instances if inst["status"] == "healthy"),
            "unhealthy_instances": sum(1 for inst in instances if inst["status"] == "unhealthy"),
            "error_instances": sum(1 for inst in instances if inst["status"] == "error")
        }
    }

def create_scaling_event_data(action: str, current_instances: int, target_instances: int, reason: str) -> Dict[str, Any]:
    """Create scaling event data for dashboard notifications"""
    return {
        "action": action,  # scale_up, scale_down, maintain
        "current_instances": current_instances,
        "target_instances": target_instances,
        "reason": reason,
        "timestamp": datetime.utcnow().isoformat(),
        "service_id": "signal_service"
    }

def format_performance_metrics_for_dashboard(cluster_metrics: Dict[str, Any]) -> Dict[str, Any]:
    """Format performance metrics for dashboard charts"""
    return {
        "throughput": {
            "requests_per_minute": cluster_metrics.get("total_requests_per_minute", 0),
            "signals_processed_per_minute": cluster_metrics.get("total_requests_per_minute", 0) * 0.8  # Estimated
        },
        "resource_usage": {
            "average_cpu_percent": cluster_metrics.get("average_cpu_percent", 0),
            "average_memory_percent": cluster_metrics.get("average_memory_percent", 0)
        },
        "queue_metrics": {
            "total_queue_size": cluster_metrics.get("total_queue_size", 0),
            "average_queue_size": cluster_metrics.get("total_queue_size", 0) / max(cluster_metrics.get("total_instances", 1), 1)
        },
        "business_metrics": {
            "total_assigned_instruments": cluster_metrics.get("total_assigned_instruments", 0),
            "instruments_per_instance": cluster_metrics.get("total_assigned_instruments", 0) / max(cluster_metrics.get("total_instances", 1), 1)
        }
    }