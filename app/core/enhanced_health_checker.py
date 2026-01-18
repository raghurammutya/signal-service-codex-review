"""
Enhanced Health Checker with Real Metrics Integration

Replaces runtime error-throwing health checks with real metrics collection
and provides positive coverage (200ms metrics) for production monitoring.
"""
import asyncio
import time
import psutil
import aiohttp
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from enum import Enum
import logging

from app.services.metrics_service import get_metrics_collector
from app.utils.redis import get_redis_client
from app.core.config import settings
from app.errors import HealthCheckError
from common.storage.database import get_timescaledb_session

logger = logging.getLogger(__name__)


class ComponentStatus(Enum):
    UP = "up"
    DOWN = "down"
    DEGRADED = "degraded"


class HealthStatus(Enum):
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DEGRADED = "degraded"


class EnhancedHealthChecker:
    """
    Enhanced health checker with real metrics collection.
    
    Provides positive coverage and real performance metrics instead of 
    runtime errors for production health monitoring.
    """
    
    def __init__(self):
        self.metrics_collector = get_metrics_collector()
        self.redis_client = None
        self.session = None
        self.health_thresholds = {
            'response_time_ms': {
                'excellent': 50,
                'good': 100,
                'acceptable': 200,
                'poor': 500
            },
            'error_rate': {
                'excellent': 0.01,  # 1%
                'good': 0.02,       # 2%
                'acceptable': 0.05, # 5%
                'poor': 0.10        # 10%
            },
            'success_rate': {
                'excellent': 0.99,  # 99%
                'good': 0.95,       # 95%
                'acceptable': 0.90, # 90%
                'poor': 0.85        # 85%
            },
            'cpu_percent': {
                'excellent': 50,
                'good': 70,
                'acceptable': 85,
                'poor': 95
            },
            'memory_percent': {
                'excellent': 60,
                'good': 75,
                'acceptable': 90,
                'poor': 95
            }
        }
    
    async def initialize(self):
        """Initialize health checker with connections."""
        try:
            self.redis_client = await get_redis_client()
            await self.metrics_collector.initialize()
            self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5.0))
        except Exception as e:
            logger.error(f"Failed to initialize health checker: {e}")
    
    async def check_overall_health(self) -> Dict[str, Any]:
        """
        Perform comprehensive health check with real metrics.
        
        Returns detailed health assessment with 200ms target response time.
        """
        start_time = time.time()
        
        try:
            # Run all health checks concurrently for speed
            health_checks = await asyncio.gather(
                self._check_redis_health(),
                self._check_database_health(),
                self._check_signal_processing_health(),
                self._check_external_services_health(),
                self._check_system_resources(),
                return_exceptions=True
            )
            
            # Process results
            redis_health, db_health, signal_health, external_health, system_health = health_checks
            
            # Calculate overall health score
            component_scores = {}
            component_statuses = {}
            
            for name, health_result in [
                ('redis', redis_health),
                ('database', db_health), 
                ('signal_processing', signal_health),
                ('external_services', external_health),
                ('system', system_health)
            ]:
                if isinstance(health_result, Exception):
                    component_scores[name] = 0
                    component_statuses[name] = ComponentStatus.DOWN.value
                else:
                    component_scores[name] = health_result.get('health_score', 50)
                    component_statuses[name] = health_result.get('status', ComponentStatus.DEGRADED.value)
            
            # Calculate overall score
            overall_score = sum(component_scores.values()) / len(component_scores)
            
            # Determine overall status
            if overall_score >= 90:
                overall_status = ComponentStatus.UP.value
                health_status = HealthStatus.HEALTHY.value
            elif overall_score >= 70:
                overall_status = ComponentStatus.DEGRADED.value
                health_status = HealthStatus.DEGRADED.value
            else:
                overall_status = ComponentStatus.DOWN.value
                health_status = HealthStatus.UNHEALTHY.value
            
            response_time_ms = (time.time() - start_time) * 1000
            
            return {
                'status': overall_status,
                'health_status': health_status,
                'overall_health_score': round(overall_score, 1),
                'response_time_ms': round(response_time_ms, 2),
                'timestamp': datetime.utcnow().isoformat(),
                'details': {
                    'redis': redis_health if not isinstance(redis_health, Exception) else {'status': ComponentStatus.DOWN.value, 'error': str(redis_health)},
                    'database': db_health if not isinstance(db_health, Exception) else {'status': ComponentStatus.DOWN.value, 'error': str(db_health)},
                    'signal_processing': signal_health if not isinstance(signal_health, Exception) else {'status': ComponentStatus.DOWN.value, 'error': str(signal_health)},
                    'external_services': external_health if not isinstance(external_services, Exception) else {'status': ComponentStatus.DOWN.value, 'error': str(external_health)},
                    'system': system_health if not isinstance(system_health, Exception) else {'status': ComponentStatus.DOWN.value, 'error': str(system_health)}
                },
                'component_scores': component_scores,
                'metrics_summary': self._get_metrics_summary()
            }
            
        except Exception as e:
            logger.error(f"Overall health check failed: {e}")
            return {
                'status': ComponentStatus.DOWN.value,
                'health_status': HealthStatus.UNHEALTHY.value,
                'error': str(e),
                'response_time_ms': (time.time() - start_time) * 1000,
                'timestamp': datetime.utcnow().isoformat()
            }
    
    async def _check_redis_health(self) -> Dict[str, Any]:
        """Check Redis health with real metrics collection."""
        start_time = time.time()
        
        try:
            if not self.redis_client:
                raise HealthCheckError("Redis client not initialized")
            
            # Test Redis connectivity
            ping_result = await self.redis_client.ping()
            if not ping_result:
                raise HealthCheckError("Redis ping failed")
            
            # Get Redis info
            redis_info = await self.redis_client.info()
            
            response_time_ms = (time.time() - start_time) * 1000
            
            # Calculate health score based on response time and connection health
            health_score = self._calculate_response_time_score(response_time_ms)
            
            # Check connection health
            connected_clients = redis_info.get('connected_clients', 0)
            used_memory_bytes = redis_info.get('used_memory', 0)
            
            # Adjust score based on Redis metrics
            if connected_clients > 100:  # Too many connections
                health_score -= 10
            if used_memory_bytes > 1024 * 1024 * 1024:  # > 1GB memory usage
                health_score -= 5
            
            status = ComponentStatus.UP.value if health_score >= 70 else ComponentStatus.DEGRADED.value
            
            return {
                'status': status,
                'health_score': max(0, min(100, health_score)),
                'response_time_ms': round(response_time_ms, 2),
                'details': {
                    'connected_clients': connected_clients,
                    'used_memory_mb': round(used_memory_bytes / (1024 * 1024), 2),
                    'role': redis_info.get('role', 'unknown'),
                    'redis_version': redis_info.get('redis_version', 'unknown')
                },
                'timestamp': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            return {
                'status': ComponentStatus.DOWN.value,
                'health_score': 0,
                'error': str(e),
                'response_time_ms': (time.time() - start_time) * 1000,
                'timestamp': datetime.utcnow().isoformat()
            }
    
    async def _check_database_health(self) -> Dict[str, Any]:
        """Check TimescaleDB health with real metrics collection."""
        start_time = time.time()
        
        try:
            # Test database connectivity
            async with get_timescaledb_session() as session:
                # Simple query to test connectivity
                result = await session.execute(text("SELECT 1 as test"))
                test_value = result.scalar()
                
                if test_value != 1:
                    raise HealthCheckError("Database query returned unexpected result")
                
                # Get database statistics
                db_stats_query = text("""
                    SELECT 
                        pg_database_size(current_database()) as db_size_bytes,
                        (SELECT count(*) FROM pg_stat_activity WHERE state = 'active') as active_connections,
                        (SELECT count(*) FROM pg_stat_activity) as total_connections
                """)
                
                stats_result = await session.execute(db_stats_query)
                stats = stats_result.fetchone()
                
            response_time_ms = (time.time() - start_time) * 1000
            
            # Calculate health score
            health_score = self._calculate_response_time_score(response_time_ms)
            
            # Adjust based on database metrics
            if stats and stats.active_connections > 20:  # Too many active connections
                health_score -= 10
            
            status = ComponentStatus.UP.value if health_score >= 70 else ComponentStatus.DEGRADED.value
            
            return {
                'status': status,
                'health_score': max(0, min(100, health_score)),
                'response_time_ms': round(response_time_ms, 2),
                'details': {
                    'database_size_mb': round(stats.db_size_bytes / (1024 * 1024), 2) if stats else 0,
                    'active_connections': stats.active_connections if stats else 0,
                    'total_connections': stats.total_connections if stats else 0
                },
                'timestamp': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return {
                'status': ComponentStatus.DOWN.value,
                'health_score': 0,
                'error': str(e),
                'response_time_ms': (time.time() - start_time) * 1000,
                'timestamp': datetime.utcnow().isoformat()
            }
    
    async def _check_signal_processing_health(self) -> Dict[str, Any]:
        """Check signal processing health with real metrics from metrics collector."""
        try:
            # Get real processing metrics
            greeks_metrics = self.metrics_collector.get_greeks_performance_metrics()
            error_rate = self.metrics_collector.get_error_rate()
            processing_rate = self.metrics_collector.get_processing_rate()
            
            # Calculate health score based on real metrics
            health_score = 100
            
            # Penalize high error rates
            if error_rate > self.health_thresholds['error_rate']['poor']:
                health_score -= 30
            elif error_rate > self.health_thresholds['error_rate']['acceptable']:
                health_score -= 15
            elif error_rate > self.health_thresholds['error_rate']['good']:
                health_score -= 5
            
            # Penalize low success rates
            greeks_success_rate = greeks_metrics.get('success_rate', 1.0)
            if greeks_success_rate < self.health_thresholds['success_rate']['poor']:
                health_score -= 30
            elif greeks_success_rate < self.health_thresholds['success_rate']['acceptable']:
                health_score -= 15
            elif greeks_success_rate < self.health_thresholds['success_rate']['good']:
                health_score -= 5
            
            # Penalize slow processing
            avg_duration = greeks_metrics.get('average_duration_ms', 0)
            if avg_duration > 500:  # > 500ms is slow
                health_score -= 20
            elif avg_duration > 200:  # > 200ms is concerning
                health_score -= 10
            
            status = ComponentStatus.UP.value if health_score >= 70 else ComponentStatus.DEGRADED.value
            
            return {
                'status': status,
                'health_score': max(0, min(100, health_score)),
                'greeks_success_rate': greeks_success_rate,
                'error_rate': error_rate,
                'processing_rate_per_minute': processing_rate,
                'average_processing_time_ms': avg_duration,
                'details': greeks_metrics,
                'timestamp': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Signal processing health check failed: {e}")
            return {
                'status': ComponentStatus.DOWN.value,
                'health_score': 0,
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }
    
    async def _check_external_services_health(self) -> Dict[str, Any]:
        """Check external services health with real HTTP requests."""
        try:
            if not self.session:
                raise HealthCheckError("HTTP session not initialized")
            
            # Define services to check
            services = {}
            if hasattr(settings, 'INSTRUMENT_SERVICE_URL'):
                services['instrument_service'] = f"{settings.INSTRUMENT_SERVICE_URL}/health"
            if hasattr(settings, 'TICKER_SERVICE_URL'):
                services['ticker_service'] = f"{settings.TICKER_SERVICE_URL}/health"
            if hasattr(settings, 'SUBSCRIPTION_SERVICE_URL'):
                services['subscription_service'] = f"{settings.SUBSCRIPTION_SERVICE_URL}/health"
            
            service_results = {}
            healthy_services = 0
            total_response_time = 0
            
            # Check each service
            for service_name, health_url in services.items():
                start_time = time.time()
                try:
                    async with self.session.get(health_url) as response:
                        response_time_ms = (time.time() - start_time) * 1000
                        total_response_time += response_time_ms
                        
                        if response.status == 200:
                            service_results[service_name] = {
                                'status': ComponentStatus.UP.value,
                                'response_time_ms': round(response_time_ms, 2),
                                'status_code': response.status
                            }
                            healthy_services += 1
                        else:
                            service_results[service_name] = {
                                'status': ComponentStatus.DOWN.value,
                                'response_time_ms': round(response_time_ms, 2),
                                'status_code': response.status
                            }
                            
                except asyncio.TimeoutError:
                    service_results[service_name] = {
                        'status': ComponentStatus.DOWN.value,
                        'error': 'timeout',
                        'response_time_ms': 5000  # Timeout limit
                    }
                except Exception as e:
                    service_results[service_name] = {
                        'status': ComponentStatus.DOWN.value,
                        'error': str(e),
                        'response_time_ms': (time.time() - start_time) * 1000
                    }
            
            # Calculate overall external services health
            if not services:
                health_score = 100  # No external dependencies configured
                status = ComponentStatus.UP.value
            else:
                health_percentage = healthy_services / len(services)
                health_score = health_percentage * 100
                
                if health_percentage >= 1.0:
                    status = ComponentStatus.UP.value
                elif health_percentage >= 0.5:
                    status = ComponentStatus.DEGRADED.value
                else:
                    status = ComponentStatus.DOWN.value
            
            avg_response_time = total_response_time / len(services) if services else 0
            
            return {
                'status': status,
                'health_score': round(health_score, 1),
                'healthy_services': healthy_services,
                'total_services': len(services),
                'average_response_time_ms': round(avg_response_time, 2),
                'service_details': service_results,
                'timestamp': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"External services health check failed: {e}")
            return {
                'status': ComponentStatus.DOWN.value,
                'health_score': 0,
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }
    
    async def _check_system_resources(self) -> Dict[str, Any]:
        """Check system resources with real psutil metrics."""
        try:
            process = psutil.Process()
            
            # Get process metrics
            memory_info = process.memory_info()
            memory_mb = memory_info.rss / (1024 * 1024)
            memory_percent = process.memory_percent()
            cpu_percent = process.cpu_percent(interval=0.1)
            
            # Get system metrics
            system_memory = psutil.virtual_memory()
            system_cpu = psutil.cpu_percent(interval=0.1)
            
            # Calculate health score
            health_score = 100
            
            # Penalize high CPU usage
            if cpu_percent > self.health_thresholds['cpu_percent']['poor']:
                health_score -= 30
            elif cpu_percent > self.health_thresholds['cpu_percent']['acceptable']:
                health_score -= 15
            elif cpu_percent > self.health_thresholds['cpu_percent']['good']:
                health_score -= 5
            
            # Penalize high memory usage
            if memory_percent > self.health_thresholds['memory_percent']['poor']:
                health_score -= 30
            elif memory_percent > self.health_thresholds['memory_percent']['acceptable']:
                health_score -= 15
            elif memory_percent > self.health_thresholds['memory_percent']['good']:
                health_score -= 5
            
            # Penalize high system resource usage
            if system_memory.percent > 95:
                health_score -= 10
            if system_cpu > 90:
                health_score -= 10
            
            status = ComponentStatus.UP.value if health_score >= 70 else ComponentStatus.DEGRADED.value
            
            return {
                'status': status,
                'health_score': max(0, min(100, health_score)),
                'process_memory_mb': round(memory_mb, 2),
                'process_memory_percent': round(memory_percent, 2),
                'process_cpu_percent': round(cpu_percent, 2),
                'system_memory_percent': round(system_memory.percent, 2),
                'system_cpu_percent': round(system_cpu, 2),
                'details': {
                    'threads': process.num_threads(),
                    'connections': len(process.connections()),
                    'system_memory_total_gb': round(system_memory.total / (1024**3), 2),
                    'system_memory_available_gb': round(system_memory.available / (1024**3), 2)
                },
                'timestamp': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"System resources health check failed: {e}")
            return {
                'status': ComponentStatus.DOWN.value,
                'health_score': 0,
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }
    
    def _calculate_response_time_score(self, response_time_ms: float) -> int:
        """Calculate health score based on response time."""
        thresholds = self.health_thresholds['response_time_ms']
        
        if response_time_ms <= thresholds['excellent']:
            return 100
        elif response_time_ms <= thresholds['good']:
            return 90
        elif response_time_ms <= thresholds['acceptable']:
            return 75
        elif response_time_ms <= thresholds['poor']:
            return 60
        else:
            return 40
    
    def _get_metrics_summary(self) -> Dict[str, Any]:
        """Get summary of key metrics for health assessment."""
        try:
            return {
                'request_rate_per_minute': self.metrics_collector.get_request_rate(),
                'processing_rate_per_minute': self.metrics_collector.get_processing_rate(),
                'error_rate': self.metrics_collector.get_error_rate(),
                'average_response_time_ms': self.metrics_collector.get_average_response_time(),
                'health_score': self.metrics_collector.get_health_score().get('overall_score', 0),
                'timestamp': datetime.utcnow().isoformat()
            }
        except Exception as e:
            logger.error(f"Failed to get metrics summary: {e}")
            return {'error': str(e)}
    
    async def close(self):
        """Clean up resources."""
        if self.session:
            await self.session.close()


# Global enhanced health checker instance
_enhanced_health_checker: Optional[EnhancedHealthChecker] = None


async def get_enhanced_health_checker() -> EnhancedHealthChecker:
    """Get or create enhanced health checker instance."""
    global _enhanced_health_checker
    if _enhanced_health_checker is None:
        _enhanced_health_checker = EnhancedHealthChecker()
        await _enhanced_health_checker.initialize()
    return _enhanced_health_checker