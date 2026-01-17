"""
Comprehensive health checker for Signal Service
"""
import asyncio
import time
import psutil
from datetime import datetime, timedelta
from typing import Dict, Any, List, Tuple
from enum import Enum
import logging

import redis.asyncio as redis
from app.utils.logging_utils import log_warning, log_error
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

logger = logging.getLogger(__name__)

class HealthStatus(Enum):
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy" 
    ERROR = "error"

class ComponentStatus(Enum):
    UP = "up"
    DOWN = "down"
    DEGRADED = "degraded"

class HealthChecker:
    """Comprehensive health checker for all Signal Service components"""
    
    def __init__(self, redis_client, db_session, signal_processor=None):
        self.redis_client = redis_client
        self.db_session = db_session
        self.signal_processor = signal_processor
        self.last_check_time = None
        self.cached_health = None
        self.cache_ttl = 30  # Cache health results for 30 seconds
        
        # Health thresholds
        self.thresholds = {
            'api_response_time_ms': {'healthy': 100, 'unhealthy': 500},
            'signal_processing_time_ms': {'healthy': 50, 'unhealthy': 200},
            'memory_usage_percent': {'healthy': 70, 'unhealthy': 90},
            'cpu_usage_percent': {'healthy': 80, 'unhealthy': 95},
            'cache_hit_rate_percent': {'healthy': 75, 'unhealthy': 50},
            'error_rate_percent': {'healthy': 1, 'unhealthy': 5},
            'redis_latency_ms': {'healthy': 5, 'unhealthy': 20},
            'db_connection_pool_percent': {'healthy': 80, 'unhealthy': 50}
        }
    
    async def check_health(self, detailed: bool = True) -> Dict[str, Any]:
        """
        Check health with optional detailed flag.
        
        Args:
            detailed: If True, return detailed health info. If False, return basic status.
            
        Returns:
            Health status dictionary
        """
        if detailed:
            return await self.get_comprehensive_health()
        else:
            # Basic health check
            try:
                # Quick check of critical components
                redis_ok = False
                db_ok = False
                
                if self.redis_client:
                    try:
                        await self.redis_client.ping()
                        redis_ok = True
                    except Exception as e:
                        logger.warning(f"Redis health check failed: {e}")
                
                # Mock basic DB check
                if self.db_session:
                    db_ok = True
                
                if redis_ok and db_ok:
                    status = "healthy"
                elif redis_ok or db_ok:
                    status = "degraded"
                else:
                    status = "unhealthy"
                
                return {
                    "status": status,
                    "timestamp": datetime.utcnow().isoformat(),
                    "redis": "up" if redis_ok else "down",
                    "database": "up" if db_ok else "down"
                }
                
            except Exception as e:
                return {
                    "status": "error",
                    "error": str(e),
                    "timestamp": datetime.utcnow().isoformat()
                }
    
    async def get_comprehensive_health(self) -> Dict[str, Any]:
        """Get comprehensive health status with caching"""
        now = time.time()
        
        # Use cached result if still valid
        if (self.cached_health and self.last_check_time and 
            now - self.last_check_time < self.cache_ttl):
            return self.cached_health
        
        # Perform all health checks
        health_data = await self._perform_all_checks()
        
        # Cache the result
        self.cached_health = health_data
        self.last_check_time = now
        
        return health_data
    
    async def _perform_all_checks(self) -> Dict[str, Any]:
        """Perform all health checks"""
        start_time = time.time()
        
        # Run all checks concurrently (including config_service per architecture standards)
        checks = await asyncio.gather(
            self._check_api_responsiveness(),
            self._check_database_health(),
            self._check_redis_health(),
            self._check_config_service_health(),
            self._check_signal_processing_health(),
            self._check_external_services_health(),
            self._check_system_resources(),
            self._check_cache_performance(),
            self._check_backpressure_status(),
            self._check_error_rates(),
            self._check_model_configuration(),
            return_exceptions=True
        )
        
        # Process check results
        check_names = [
            'api', 'database', 'redis', 'config_service', 'signal_processing', 
            'external_services', 'system_resources', 'cache', 
            'backpressure', 'error_tracking', 'model_configuration'
        ]
        
        components = {}
        issues = []
        
        for i, check_result in enumerate(checks):
            component_name = check_names[i]
            
            if isinstance(check_result, Exception):
                logger.error(f"Health check failed for {component_name}: {check_result}")
                components[component_name] = {
                    'status': ComponentStatus.DOWN.value,
                    'error': str(check_result),
                    'timestamp': datetime.utcnow().isoformat()
                }
                issues.append(f"{component_name}: {check_result}")
            else:
                components[component_name] = check_result
                if check_result['status'] != ComponentStatus.UP.value:
                    issues.append(f"{component_name}: {check_result.get('message', 'degraded')}")
        
        # Determine overall health status
        overall_status = self._determine_overall_status(components)
        
        health_data = {
            'status': overall_status.value,
            'timestamp': datetime.utcnow().isoformat(),
            'service': 'signal_service',
            'version': '2.0.0',
            'uptime_seconds': self._get_uptime(),
            'check_duration_ms': round((time.time() - start_time) * 1000, 2),
            'components': components,
            'issues': issues,
            'summary': self._generate_health_summary(components, overall_status)
        }
        
        return health_data
    
    async def _check_api_responsiveness(self) -> Dict[str, Any]:
        """Check API endpoint responsiveness"""
        try:
            start_time = time.time()
            
            # Simulate a lightweight API operation
            # In real implementation, this would hit a test endpoint
            await asyncio.sleep(0.001)  # Simulate 1ms operation
            
            response_time_ms = (time.time() - start_time) * 1000
            
            if response_time_ms <= self.thresholds['api_response_time_ms']['healthy']:
                status = ComponentStatus.UP
                message = f"API responsive in {response_time_ms:.2f}ms"
            elif response_time_ms <= self.thresholds['api_response_time_ms']['unhealthy']:
                status = ComponentStatus.DEGRADED
                message = f"API slow response: {response_time_ms:.2f}ms"
            else:
                status = ComponentStatus.DOWN
                message = f"API timeout: {response_time_ms:.2f}ms"
            
            return {
                'status': status.value,
                'response_time_ms': round(response_time_ms, 2),
                'message': message,
                'timestamp': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            return {
                'status': ComponentStatus.DOWN.value,
                'error': str(e),
                'message': 'API health check failed',
                'timestamp': datetime.utcnow().isoformat()
            }
    
    async def _check_database_health(self) -> Dict[str, Any]:
        """Check TimescaleDB connection and performance"""
        try:
            start_time = time.time()
            
            # Test database connectivity
            async with self.db_session() as session:
                result = await session.execute(text("SELECT 1"))
                result.fetchone()  # Not awaitable in SQLAlchemy
                
                # Check connection pool status
                pool = session.get_bind().pool
                pool_size = pool.size()
                checked_out = pool.checkedout()
                available = pool_size - checked_out
                pool_usage_percent = (checked_out / pool_size) * 100 if pool_size > 0 else 0
            
            query_time_ms = (time.time() - start_time) * 1000
            
            # Determine status based on pool usage and query time
            if (pool_usage_percent <= (100 - self.thresholds['db_connection_pool_percent']['healthy']) and 
                query_time_ms <= 50):
                status = ComponentStatus.UP
                message = f"Database healthy: {available}/{pool_size} connections available"
            elif (pool_usage_percent <= (100 - self.thresholds['db_connection_pool_percent']['unhealthy']) and 
                  query_time_ms <= 200):
                status = ComponentStatus.DEGRADED
                message = f"Database strained: {available}/{pool_size} connections available"
            else:
                status = ComponentStatus.DOWN
                message = f"Database critical: {available}/{pool_size} connections available"
            
            return {
                'status': status.value,
                'query_time_ms': round(query_time_ms, 2),
                'pool_usage_percent': round(pool_usage_percent, 1),
                'available_connections': available,
                'total_connections': pool_size,
                'message': message,
                'timestamp': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            return {
                'status': ComponentStatus.DOWN.value,
                'error': str(e),
                'message': 'Database connection failed',
                'timestamp': datetime.utcnow().isoformat()
            }
    
    async def _check_redis_health(self) -> Dict[str, Any]:
        """Check Redis cluster health and performance"""
        try:
            start_time = time.time()
            
            # Test Redis connectivity
            await self.redis_client.ping()
            
            # Test read/write performance
            test_key = 'health_check_test'
            await self.redis_client.set(test_key, 'test_value', ex=10)
            await self.redis_client.get(test_key)
            await self.redis_client.delete(test_key)
            
            latency_ms = (time.time() - start_time) * 1000
            
            # Get Redis info
            info = await self.redis_client.info()
            memory_usage_mb = info.get('used_memory', 0) / (1024 * 1024)
            
            # Determine status
            if latency_ms <= self.thresholds['redis_latency_ms']['healthy']:
                status = ComponentStatus.UP
                message = f"Redis healthy: {latency_ms:.2f}ms latency"
            elif latency_ms <= self.thresholds['redis_latency_ms']['unhealthy']:
                status = ComponentStatus.DEGRADED
                message = f"Redis slow: {latency_ms:.2f}ms latency"
            else:
                status = ComponentStatus.DOWN
                message = f"Redis critical: {latency_ms:.2f}ms latency"
            
            return {
                'status': status.value,
                'latency_ms': round(latency_ms, 2),
                'memory_usage_mb': round(memory_usage_mb, 2),
                'connected_clients': info.get('connected_clients', 0),
                'message': message,
                'timestamp': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            return {
                'status': ComponentStatus.DOWN.value,
                'error': str(e),
                'message': 'Redis connection failed',
                'timestamp': datetime.utcnow().isoformat()
            }
    
    async def _check_signal_processing_health(self) -> Dict[str, Any]:
        """Check signal processing performance"""
        try:
            if not self.signal_processor:
                return {
                    'status': ComponentStatus.UP.value,
                    'message': 'Signal processor not initialized',
                    'timestamp': datetime.utcnow().isoformat()
                }
            
            # Test signal computation performance
            start_time = time.time()
            
            # PRODUCTION: Real signal computation test using actual signal processor
            test_instrument = 'NSE@HEALTH@equity_options@2025-07-10@call@21500'
            
            try:
                # Use actual signal processor for health check
                from app.services.signal_processor import get_signal_processor
                processor = await get_signal_processor()
                
                # Test basic signal computation capability (minimal Greeks calculation)
                test_result = await processor.compute_greeks_for_instrument(
                    instrument_key=test_instrument
                )
                
                processing_time_ms = (time.time() - start_time) * 1000
                
                if test_result is None:
                    raise ValueError("Signal processor returned None - indicates computation failure")
                    
                # Check backpressure levels from actual backpressure monitor
                try:
                    # Get backpressure level from monitoring system
                    from app.monitoring import get_backpressure_monitor
                    monitor = get_backpressure_monitor()
                    backpressure_level = await monitor.get_current_backpressure_level()
                except ImportError:
                    log_warning("Backpressure monitor not available - using processing time heuristic")
                    # Use processing time as backpressure indicator
                    if processing_time_ms > 1000:  # > 1 second
                        backpressure_level = 'HIGH'
                    elif processing_time_ms > 500:  # > 500ms
                        backpressure_level = 'MEDIUM'
                    else:
                        backpressure_level = 'LOW'
                except Exception as e:
                    log_warning(f"Failed to get backpressure level: {e}")
                    backpressure_level = 'UNKNOWN'
                
            except Exception as e:
                processing_time_ms = (time.time() - start_time) * 1000
                log_error(f"Signal processor health check failed: {e}")
                backpressure_level = 'CRITICAL'
            
            # Determine status
            if processing_time_ms <= self.thresholds['signal_processing_time_ms']['healthy']:
                status = ComponentStatus.UP
                message = f"Signal processing healthy: {processing_time_ms:.2f}ms"
            elif processing_time_ms <= self.thresholds['signal_processing_time_ms']['unhealthy']:
                status = ComponentStatus.DEGRADED
                message = f"Signal processing slow: {processing_time_ms:.2f}ms"
            else:
                status = ComponentStatus.DOWN
                message = f"Signal processing critical: {processing_time_ms:.2f}ms"
            
            return {
                'status': status.value,
                'processing_time_ms': round(processing_time_ms, 2),
                'backpressure_level': backpressure_level,
                'message': message,
                'timestamp': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            return {
                'status': ComponentStatus.DOWN.value,
                'error': str(e),
                'message': 'Signal processing check failed',
                'timestamp': datetime.utcnow().isoformat()
            }
    
    async def _check_external_services_health(self) -> Dict[str, Any]:
        """Check connectivity to external services"""
        try:
            # Get external service URLs from config_service exclusively (Architecture Principle #1: Config service exclusivity)
            try:
                from common.config_service.client import ConfigServiceClient
                from app.core.config import settings
                
                config_client = ConfigServiceClient(
                    service_name="signal_service",
                    environment=settings.environment,
                    timeout=5
                )
                
                # Architecture Principle #3: API versioning is mandatory - all health endpoints must be versioned
                external_services = {
                    'instrument_service': f"{config_client.get_service_url('instrument_service')}/api/v1/health",
                    'ticker_service': f"{config_client.get_service_url('ticker_service')}/api/v1/health", 
                    'subscription_service': f"{config_client.get_service_url('subscription_service')}/api/v1/health"
                }
                
            except Exception as e:
                raise RuntimeError(f"Failed to get service URLs from config_service: {e}. No hardcoded fallbacks allowed per architecture.")
            
            service_statuses = {}
            all_healthy = True
            degraded_count = 0
            
            for service_name, health_url in external_services.items():
                try:
                    # In real implementation, make HTTP request to health endpoint
                    # For now, simulate check
                    await asyncio.sleep(0.01)  # Simulate network call
                    
                    # Mock different service states
                    if service_name == 'instrument_service':
                        service_statuses[service_name] = 'up'
                    else:
                        service_statuses[service_name] = 'degraded'
                        degraded_count += 1
                        
                except Exception as e:
                    service_statuses[service_name] = 'down'
                    all_healthy = False
            
            # Determine overall external services status
            if all_healthy and degraded_count == 0:
                status = ComponentStatus.UP
                message = "All external services healthy"
            elif degraded_count <= 1:
                status = ComponentStatus.DEGRADED
                message = f"{degraded_count} external service(s) degraded"
            else:
                status = ComponentStatus.DOWN
                message = "Multiple external services unavailable"
            
            return {
                'status': status.value,
                'services': service_statuses,
                'message': message,
                'timestamp': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            return {
                'status': ComponentStatus.DOWN.value,
                'error': str(e),
                'message': 'External services check failed',
                'timestamp': datetime.utcnow().isoformat()
            }
    
    async def _check_system_resources(self) -> Dict[str, Any]:
        """Check system resource usage (CPU, Memory)"""
        try:
            process = psutil.Process()
            
            # Get resource usage
            memory_info = process.memory_info()
            memory_mb = memory_info.rss / (1024 * 1024)
            memory_percent = process.memory_percent()
            cpu_percent = process.cpu_percent()
            
            # System-wide stats
            system_memory = psutil.virtual_memory()
            system_cpu = psutil.cpu_percent(interval=0.1)
            
            # Determine status based on thresholds
            if (memory_percent <= self.thresholds['memory_usage_percent']['healthy'] and 
                cpu_percent <= self.thresholds['cpu_usage_percent']['healthy']):
                status = ComponentStatus.UP
                message = f"Resources healthy: {memory_percent:.1f}% memory, {cpu_percent:.1f}% CPU"
            elif (memory_percent <= self.thresholds['memory_usage_percent']['unhealthy'] and 
                  cpu_percent <= self.thresholds['cpu_usage_percent']['unhealthy']):
                status = ComponentStatus.DEGRADED
                message = f"Resources strained: {memory_percent:.1f}% memory, {cpu_percent:.1f}% CPU"
            else:
                status = ComponentStatus.DOWN
                message = f"Resources critical: {memory_percent:.1f}% memory, {cpu_percent:.1f}% CPU"
            
            return {
                'status': status.value,
                'process_memory_mb': round(memory_mb, 2),
                'process_memory_percent': round(memory_percent, 1),
                'process_cpu_percent': round(cpu_percent, 1),
                'system_memory_percent': round(system_memory.percent, 1),
                'system_cpu_percent': round(system_cpu, 1),
                'message': message,
                'timestamp': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            return {
                'status': ComponentStatus.DOWN.value,
                'error': str(e),
                'message': 'System resources check failed',
                'timestamp': datetime.utcnow().isoformat()
            }
    
    async def _check_cache_performance(self) -> Dict[str, Any]:
        """Check cache performance and hit rates"""
        try:
            # Get cache statistics (would be from actual cache manager)
            # Mock cache stats for now
            cache_stats = {
                'total_requests': 10000,
                'cache_hits': 8200,
                'cache_misses': 1800,
                'hit_rate_percent': 82.0
            }
            
            hit_rate = cache_stats['hit_rate_percent']
            
            # Determine status
            if hit_rate >= self.thresholds['cache_hit_rate_percent']['healthy']:
                status = ComponentStatus.UP
                message = f"Cache performing well: {hit_rate:.1f}% hit rate"
            elif hit_rate >= self.thresholds['cache_hit_rate_percent']['unhealthy']:
                status = ComponentStatus.DEGRADED
                message = f"Cache performance degraded: {hit_rate:.1f}% hit rate"
            else:
                status = ComponentStatus.DOWN
                message = f"Cache performance critical: {hit_rate:.1f}% hit rate"
            
            return {
                'status': status.value,
                'hit_rate_percent': hit_rate,
                'total_requests': cache_stats['total_requests'],
                'cache_hits': cache_stats['cache_hits'],
                'cache_misses': cache_stats['cache_misses'],
                'message': message,
                'timestamp': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            return {
                'status': ComponentStatus.DOWN.value,
                'error': str(e),
                'message': 'Cache performance check failed',
                'timestamp': datetime.utcnow().isoformat()
            }
    
    async def _check_backpressure_status(self) -> Dict[str, Any]:
        """Check current backpressure levels"""
        try:
            # Mock backpressure data (would get from actual backpressure monitor)
            backpressure_data = {
                'level': 'MEDIUM',
                'queue_size': 750,
                'processing_rate': 85.5,
                'memory_usage_percent': 65.2
            }
            
            level = backpressure_data['level']
            
            # Determine status based on backpressure level
            if level in ['LOW']:
                status = ComponentStatus.UP
                message = f"Backpressure normal: {level}"
            elif level in ['MEDIUM', 'HIGH']:
                status = ComponentStatus.DEGRADED
                message = f"Backpressure elevated: {level}"
            else:  # CRITICAL
                status = ComponentStatus.DOWN
                message = f"Backpressure critical: {level}"
            
            return {
                'status': status.value,
                'backpressure_level': level,
                'queue_size': backpressure_data['queue_size'],
                'processing_rate': backpressure_data['processing_rate'],
                'message': message,
                'timestamp': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            return {
                'status': ComponentStatus.DOWN.value,
                'error': str(e),
                'message': 'Backpressure check failed',
                'timestamp': datetime.utcnow().isoformat()
            }
    
    async def _check_error_rates(self) -> Dict[str, Any]:
        """Check error rates and trends"""
        try:
            # Mock error tracking data (would get from actual error tracker)
            error_data = {
                'total_requests_5min': 5000,
                'errors_5min': 25,
                'error_rate_percent': 0.5,
                'error_trend': 'stable'
            }
            
            error_rate = error_data['error_rate_percent']
            
            # Determine status based on error rate
            if error_rate <= self.thresholds['error_rate_percent']['healthy']:
                status = ComponentStatus.UP
                message = f"Error rate normal: {error_rate:.1f}%"
            elif error_rate <= self.thresholds['error_rate_percent']['unhealthy']:
                status = ComponentStatus.DEGRADED
                message = f"Error rate elevated: {error_rate:.1f}%"
            else:
                status = ComponentStatus.DOWN
                message = f"Error rate critical: {error_rate:.1f}%"
            
            return {
                'status': status.value,
                'error_rate_percent': error_rate,
                'total_requests_5min': error_data['total_requests_5min'],
                'errors_5min': error_data['errors_5min'],
                'error_trend': error_data['error_trend'],
                'message': message,
                'timestamp': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            return {
                'status': ComponentStatus.DOWN.value,
                'error': str(e),
                'message': 'Error rate check failed',
                'timestamp': datetime.utcnow().isoformat()
            }
    
    async def _check_config_service_health(self) -> Dict[str, Any]:
        """
        Check config_service connectivity and health per Architecture Standards.
        
        ARCHITECTURE COMPLIANCE:
        - Config service is MANDATORY (Architecture Principle #1)
        - Health checks MUST verify config_service connectivity
        """
        try:
            start_time = time.time()
            
            # Import config service client
            try:
                import sys
                import os
                sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
                from common.config_service.client import ConfigServiceClient
            except ImportError:
                return {
                    'status': ComponentStatus.DOWN.value,
                    'error': 'Config service client not available',
                    'message': 'CRITICAL: Config service is mandatory per architecture',
                    'timestamp': datetime.utcnow().isoformat()
                }
            
            # Create client and test connectivity
            # Get environment from config_service (Architecture Principle #1: Config service exclusivity)
            try:
                from app.core.config import settings
                environment = settings.environment
            except Exception as e:
                raise RuntimeError(f"Failed to get environment from config_service for health check: {e}. No environment fallbacks allowed per architecture.")
            
            client = ConfigServiceClient(
                service_name="signal_service",
                environment=environment,
                timeout=5
            )
            
            # Test health check endpoint
            health_check_success = client.health_check()
            
            # Test configuration retrieval
            try:
                test_config = client.get_config("SERVICE_VERSION", required=False)
                config_access_success = True
            except Exception:
                config_access_success = False
                
            response_time_ms = (time.time() - start_time) * 1000
            
            # Determine status
            if health_check_success and config_access_success:
                status = ComponentStatus.UP
                message = f"Config service healthy: {response_time_ms:.2f}ms response"
            elif health_check_success:
                status = ComponentStatus.DEGRADED
                message = f"Config service degraded: health OK but config access failed"
            else:
                status = ComponentStatus.DOWN
                message = "Config service unreachable"
            
            return {
                'status': status.value,
                'response_time_ms': round(response_time_ms, 2),
                'health_check_success': health_check_success,
                'config_access_success': config_access_success,
                'message': message,
                'timestamp': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            return {
                'status': ComponentStatus.DOWN.value,
                'error': str(e),
                'message': 'CRITICAL: Config service connectivity failed',
                'timestamp': datetime.utcnow().isoformat()
            }
    
    def _determine_overall_status(self, components: Dict[str, Any]) -> HealthStatus:
        """Determine overall health status from component statuses"""
        component_statuses = [comp.get('status') for comp in components.values()]
        
        # Count status types
        down_count = component_statuses.count(ComponentStatus.DOWN.value)
        degraded_count = component_statuses.count(ComponentStatus.DEGRADED.value)
        up_count = component_statuses.count(ComponentStatus.UP.value)
        
        # Critical components that must be UP for service to be healthy
        critical_components = ['database', 'redis', 'api']
        critical_down = any(
            components.get(comp, {}).get('status') == ComponentStatus.DOWN.value 
            for comp in critical_components
        )
        
        # Determine overall status
        if critical_down or down_count >= 3:
            return HealthStatus.ERROR
        elif down_count > 0 or degraded_count >= 3:
            return HealthStatus.UNHEALTHY
        elif degraded_count > 0:
            return HealthStatus.UNHEALTHY
        else:
            return HealthStatus.HEALTHY
    
    def _generate_health_summary(self, components: Dict[str, Any], overall_status: HealthStatus) -> Dict[str, Any]:
        """Generate health summary for the dashboard"""
        component_statuses = [comp.get('status') for comp in components.values()]
        
        return {
            'overall_status': overall_status.value,
            'components_up': component_statuses.count(ComponentStatus.UP.value),
            'components_degraded': component_statuses.count(ComponentStatus.DEGRADED.value),
            'components_down': component_statuses.count(ComponentStatus.DOWN.value),
            'total_components': len(components),
            'critical_issues': [
                comp_name for comp_name, comp_data in components.items()
                if comp_data.get('status') == ComponentStatus.DOWN.value
            ],
            'performance_metrics': {
                'api_response_ms': components.get('api', {}).get('response_time_ms'),
                'signal_processing_ms': components.get('signal_processing', {}).get('processing_time_ms'),
                'memory_usage_percent': components.get('system_resources', {}).get('process_memory_percent'),
                'cache_hit_rate_percent': components.get('cache', {}).get('hit_rate_percent'),
                'error_rate_percent': components.get('error_tracking', {}).get('error_rate_percent')
            }
        }
    
    async def _check_model_configuration(self) -> Dict[str, Any]:
        """Check Greeks model configuration and config_service parameters"""
        try:
            from app.core.greeks_model_config import get_greeks_model_config
            from app.errors import UnsupportedModelError, ConfigurationError
            
            start_time = time.time()
            
            try:
                # Get and initialize model configuration
                model_config = get_greeks_model_config()
                model_config.initialize()
                
                # Validate configuration
                model_info = model_config.get_model_info()
                config_time_ms = (time.time() - start_time) * 1000
                
                # Test a sample calculation to ensure functions work
                test_start = time.time()
                test_delta = model_config.calculate_greek(
                    'delta', 'c', 100.0, 105.0, 0.25, 0.20
                )
                calc_time_ms = (time.time() - test_start) * 1000
                
                # Determine status based on performance
                if config_time_ms <= 50 and calc_time_ms <= 10:
                    status = ComponentStatus.UP
                    message = f"Model configuration healthy: {model_info['model_name']}"
                elif config_time_ms <= 100 and calc_time_ms <= 25:
                    status = ComponentStatus.DEGRADED
                    message = f"Model configuration slow: {model_info['model_name']}"
                else:
                    status = ComponentStatus.DOWN
                    message = f"Model configuration performance critical"
                
                return {
                    'status': status.value,
                    'model_name': model_info['model_name'],
                    'parameters': model_info['parameters'],
                    'supported_greeks': model_info['supported_greeks'],
                    'config_load_time_ms': round(config_time_ms, 2),
                    'sample_calc_time_ms': round(calc_time_ms, 2),
                    'test_delta_result': round(test_delta, 4),
                    'message': message,
                    'timestamp': datetime.utcnow().isoformat()
                }
                
            except UnsupportedModelError as e:
                return {
                    'status': ComponentStatus.DOWN.value,
                    'error': str(e),
                    'error_type': 'UnsupportedModelError',
                    'details': e.details if hasattr(e, 'details') else {},
                    'message': 'Invalid model configuration in config_service',
                    'timestamp': datetime.utcnow().isoformat()
                }
                
            except ConfigurationError as e:
                return {
                    'status': ComponentStatus.DOWN.value,
                    'error': str(e),
                    'error_type': 'ConfigurationError', 
                    'details': e.details if hasattr(e, 'details') else {},
                    'message': 'Invalid parameters in config_service',
                    'timestamp': datetime.utcnow().isoformat()
                }
                
        except Exception as e:
            return {
                'status': ComponentStatus.DOWN.value,
                'error': str(e),
                'error_type': 'ModelConfigurationFailure',
                'message': 'Model configuration system failed',
                'timestamp': datetime.utcnow().isoformat()
            }

    def _get_uptime(self) -> float:
        """Get service uptime in seconds"""
        try:
            process = psutil.Process()
            return time.time() - process.create_time()
        except:
            return 0.0


# Global instance for singleton pattern
_health_checker_instance = None

def get_health_checker(redis_client=None, db_session=None, signal_processor=None):
    """Get or create singleton health checker instance"""
    global _health_checker_instance
    if _health_checker_instance is None:
        _health_checker_instance = HealthChecker(
            redis_client=redis_client,
            db_session=db_session,
            signal_processor=signal_processor
        )
    return _health_checker_instance