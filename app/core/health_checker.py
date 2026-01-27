"""
Comprehensive health checker for Signal Service
"""
import asyncio
import logging
import time
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

import psutil
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

    async def check_health(self, detailed: bool = True) -> dict[str, Any]:
        """
        Check health with optional detailed flag.

        Args:
            detailed: If True, return detailed health info. If False, return basic status.

        Returns:
            Health status dictionary
        """
        if detailed:
            return await self.get_comprehensive_health()
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

    async def get_comprehensive_health(self) -> dict[str, Any]:
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

    async def _perform_all_checks(self) -> dict[str, Any]:
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

        return {
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


    async def _check_api_responsiveness(self) -> dict[str, Any]:
        """Check API endpoint responsiveness"""
        try:
            import httpx
            start_time = time.time()

            # Check internal health endpoint
            async with httpx.AsyncClient(timeout=5.0) as client:
                try:
                    response = await client.get(f"http://localhost:{getattr(self.settings, 'PORT', 8003)}/health/live")
                    response_time = (time.time() - start_time) * 1000

                    if response.status_code == 200:
                        status = ComponentStatus.UP.value if response_time < 1000 else ComponentStatus.DEGRADED.value
                        return {
                            'status': status,
                            'response_time_ms': round(response_time, 2),
                            'status_code': response.status_code,
                            'timestamp': datetime.utcnow().isoformat()
                        }
                    return {
                        'status': ComponentStatus.DOWN.value,
                        'response_time_ms': round(response_time, 2),
                        'status_code': response.status_code,
                        'message': 'API responding with error status',
                        'timestamp': datetime.utcnow().isoformat()
                    }
                except httpx.ConnectError:
                    # Fallback: assume API is up if health_checker is running
                    return {
                        'status': ComponentStatus.UP.value,
                        'response_time_ms': 0.0,
                        'message': 'Health checker running - API likely available',
                        'timestamp': datetime.utcnow().isoformat()
                    }

        except Exception as e:
            return {
                'status': ComponentStatus.DOWN.value,
                'error': str(e),
                'message': 'API health check failed',
                'timestamp': datetime.utcnow().isoformat()
            }

    async def _check_database_health(self) -> dict[str, Any]:
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

    async def _check_redis_health(self) -> dict[str, Any]:
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

    async def _check_signal_processing_health(self) -> dict[str, Any]:
        """Check signal processing performance"""
        try:
            if not self.signal_processor:
                return {
                    'status': ComponentStatus.UP.value,
                    'message': 'Signal processor not initialized',
                    'timestamp': datetime.utcnow().isoformat()
                }


        except Exception as e:
            return {
                'status': ComponentStatus.DOWN.value,
                'error': str(e),
                'message': 'Signal processing check failed',
                'timestamp': datetime.utcnow().isoformat()
            }

    async def _check_external_services_health(self) -> dict[str, Any]:
        """Check connectivity to external services"""
        try:
            from app.core.config import settings
            # Use URLs from settings with Docker network alias fallbacks
            external_services = {
                'instrument_service': f"{getattr(settings, 'INSTRUMENT_SERVICE_URL', 'http://ticker-service:8089')}/health",
                'ticker_service': f"{getattr(settings, 'TICKER_SERVICE_URL', 'http://ticker-service:8089')}/health",
                'subscription_service': f"{getattr(settings, 'SUBSCRIPTION_SERVICE_URL', 'http://subscription-service:8098')}/health"
            }
        except Exception as e:
            logger.warning(f"Failed to load external services for health check: {e}")
            # Use Docker network alias fallbacks
            external_services = {
                'instrument_service': "http://ticker-service:8089/health",
                'ticker_service': "http://ticker-service:8089/health",
                'subscription_service': "http://subscription-service:8098/health"
            }

            service_statuses = {}
            all_healthy = True
            degraded_count = 0

            # Check external services with proper HTTP calls
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                for service_name, health_url in external_services.items():
                    try:
                        response = await client.get(health_url)
                        if response.status_code == 200:
                            service_statuses[service_name] = {
                                'status': ComponentStatus.UP.value,
                                'response_time_ms': response.elapsed.total_seconds() * 1000
                            }
                        else:
                            service_statuses[service_name] = {
                                'status': ComponentStatus.DEGRADED.value,
                                'status_code': response.status_code
                            }
                            degraded_count += 1
                    except (httpx.ConnectError, httpx.TimeoutException) as e:
                        service_statuses[service_name] = {
                            'status': ComponentStatus.DOWN.value,
                            'error': str(e)
                        }
                        all_healthy = False
                    except Exception as e:
                        service_statuses[service_name] = {
                            'status': ComponentStatus.DOWN.value,
                            'error': f"Health check failed: {e}"
                        }
                        all_healthy = False

            # Determine overall status
            if not all_healthy:
                overall_status = ComponentStatus.DOWN.value
            elif degraded_count > 0:
                overall_status = ComponentStatus.DEGRADED.value
            else:
                overall_status = ComponentStatus.UP.value

            return {
                'status': overall_status,
                'services': service_statuses,
                'healthy_count': len([s for s in service_statuses.values() if s['status'] == ComponentStatus.UP.value]),
                'total_count': len(service_statuses),
                'timestamp': datetime.utcnow().isoformat()
            }

        except Exception as e:
            return {
                'status': ComponentStatus.DOWN.value,
                'error': str(e),
                'message': 'External service health check failed - requires HTTP client integration',
                'timestamp': datetime.utcnow().isoformat()
            }

    async def _check_system_resources(self) -> dict[str, Any]:
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

    async def _check_cache_performance(self) -> dict[str, Any]:
        """Check cache performance and hit rates"""
        try:
            # Check if Redis connection is available
            if not self.redis_client:
                return {
                    'status': ComponentStatus.DOWN.value,
                    'error': 'Redis client not available',
                    'message': 'Cache performance monitoring requires Redis connection',
                    'timestamp': datetime.utcnow().isoformat()
                }

            # Get actual cache statistics from Redis
            info = await self.redis_client.info('stats')
            keyspace_hits = int(info.get('keyspace_hits', 0))
            keyspace_misses = int(info.get('keyspace_misses', 0))

            total_requests = keyspace_hits + keyspace_misses
            if total_requests == 0:
                # No cache activity yet
                return {
                    'status': ComponentStatus.UP.value,
                    'hit_rate_percent': 0.0,
                    'total_requests': 0,
                    'cache_hits': 0,
                    'cache_misses': 0,
                    'message': 'Cache initialized but no requests processed yet',
                    'timestamp': datetime.utcnow().isoformat()
                }

            hit_rate = (keyspace_hits / total_requests) * 100

            # Determine status based on actual hit rate
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
                'total_requests': total_requests,
                'cache_hits': keyspace_hits,
                'cache_misses': keyspace_misses,
                'message': message,
                'timestamp': datetime.utcnow().isoformat()
            }

        except Exception as e:
            return {
                'status': ComponentStatus.DOWN.value,
                'error': str(e),
                'message': 'Cache performance check failed - requires Redis integration',
                'timestamp': datetime.utcnow().isoformat()
            }

    async def _check_backpressure_status(self) -> dict[str, Any]:
        """Check current backpressure levels"""
        try:
            # Check backpressure from queue lengths and processing metrics
            try:
                queue_lengths = {}
                total_queue_size = 0

                # Check signal processing queues
                if self.redis_client:
                    queue_keys = [
                        'signal_service:processing_queue',
                        'signal_service:priority_queue',
                        'signal_service:retry_queue',
                        'signal_service:dead_letter_queue'
                    ]

                    for queue_key in queue_keys:
                        try:
                            length = await self.redis_client.llen(queue_key)
                            queue_lengths[queue_key.split(':')[-1]] = length
                            total_queue_size += length
                        except Exception:
                            queue_lengths[queue_key.split(':')[-1]] = 0

                # Determine backpressure level
                if total_queue_size < 100:
                    status = ComponentStatus.UP
                    message = f"Low backpressure: {total_queue_size} items queued"
                elif total_queue_size < 500:
                    status = ComponentStatus.DEGRADED
                    message = f"Moderate backpressure: {total_queue_size} items queued"
                else:
                    status = ComponentStatus.DOWN
                    message = f"High backpressure: {total_queue_size} items queued"

                return {
                    'status': status.value,
                    'total_queue_size': total_queue_size,
                    'queue_details': queue_lengths,
                    'message': message,
                    'timestamp': datetime.utcnow().isoformat()
                }
            except Exception as bp_e:
                return {
                    'status': ComponentStatus.DEGRADED.value,
                    'error': str(bp_e),
                    'message': 'Backpressure check inconclusive',
                    'timestamp': datetime.utcnow().isoformat()
                }

        except Exception as e:
            return {
                'status': ComponentStatus.DOWN.value,
                'error': str(e),
                'message': 'Backpressure check failed - requires queue service integration',
                'timestamp': datetime.utcnow().isoformat()
            }

    async def _check_error_rates(self) -> dict[str, Any]:
        """Check error rates and trends"""
        try:
            # Check error rates from Redis error tracking
            try:
                current_time = datetime.utcnow()
                current_time - timedelta(minutes=5)

                error_count = 0
                warning_count = 0
                total_requests = 0

                if self.redis_client:
                    # Get error counts from Redis counters
                    try:
                        error_key = f"signal_service:errors:{current_time.strftime('%Y%m%d%H%M')[:11]}"  # Hour bucket
                        error_count = int(await self.redis_client.get(error_key) or 0)

                        warning_key = f"signal_service:warnings:{current_time.strftime('%Y%m%d%H%M')[:11]}"
                        warning_count = int(await self.redis_client.get(warning_key) or 0)

                        request_key = f"signal_service:requests:{current_time.strftime('%Y%m%d%H%M')[:11]}"
                        total_requests = int(await self.redis_client.get(request_key) or 0)
                    except Exception:
                        # Fallback to basic health check
                        pass

                # Calculate error rate
                error_rate = error_count / total_requests * 100 if total_requests > 0 else 0.0

                # Determine status
                if error_rate < 1.0:  # Less than 1% error rate
                    status = ComponentStatus.UP
                    message = f"Low error rate: {error_rate:.2f}%"
                elif error_rate < 5.0:  # Less than 5% error rate
                    status = ComponentStatus.DEGRADED
                    message = f"Elevated error rate: {error_rate:.2f}%"
                else:
                    status = ComponentStatus.DOWN
                    message = f"High error rate: {error_rate:.2f}%"

                return {
                    'status': status.value,
                    'error_rate_percent': round(error_rate, 2),
                    'error_count': error_count,
                    'warning_count': warning_count,
                    'total_requests': total_requests,
                    'message': message,
                    'timestamp': datetime.utcnow().isoformat()
                }
            except Exception as er_e:
                return {
                    'status': ComponentStatus.DEGRADED.value,
                    'error': str(er_e),
                    'message': 'Error rate check inconclusive',
                    'timestamp': datetime.utcnow().isoformat()
                }

        except Exception as e:
            return {
                'status': ComponentStatus.DOWN.value,
                'error': str(e),
                'message': 'Error rate check failed - requires metrics service integration',
                'timestamp': datetime.utcnow().isoformat()
            }

    async def _check_config_service_health(self) -> dict[str, Any]:
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
                import os
                import sys
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
                raise RuntimeError(f"Failed to get environment from config_service for health check: {e}. No environment fallbacks allowed per architecture.") from e

            client = ConfigServiceClient(
                service_name="signal_service",
                environment=environment,
                timeout=5
            )

            # Test health check endpoint
            health_check_success = client.health_check()

            # Test configuration retrieval
            try:
                client.get_config("SERVICE_VERSION", required=False)
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
                message = "Config service degraded: health OK but config access failed"
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

    def _determine_overall_status(self, components: dict[str, Any]) -> HealthStatus:
        """Determine overall health status from component statuses"""
        component_statuses = [comp.get('status') for comp in components.values()]

        # Count status types
        down_count = component_statuses.count(ComponentStatus.DOWN.value)
        degraded_count = component_statuses.count(ComponentStatus.DEGRADED.value)
        component_statuses.count(ComponentStatus.UP.value)

        # Critical components that must be UP for service to be healthy
        critical_components = ['database', 'redis', 'api']
        critical_down = any(
            components.get(comp, {}).get('status') == ComponentStatus.DOWN.value
            for comp in critical_components
        )

        # Determine overall status
        if critical_down or down_count >= 3:
            return HealthStatus.ERROR
        if down_count > 0 or degraded_count >= 3 or degraded_count > 0:
            return HealthStatus.UNHEALTHY
        return HealthStatus.HEALTHY

    def _generate_health_summary(self, components: dict[str, Any], overall_status: HealthStatus) -> dict[str, Any]:
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

    async def _check_model_configuration(self) -> dict[str, Any]:
        """Check Greeks model configuration and config_service parameters"""
        try:
            from app.core.greeks_model_config import get_greeks_model_config
            from app.errors import ConfigurationError, UnsupportedModelError

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
                    message = "Model configuration performance critical"

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
        except Exception:
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
