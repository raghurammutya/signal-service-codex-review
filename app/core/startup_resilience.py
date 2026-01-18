"""
Startup Resilience Module

Provides bounded retry strategies and graceful degradation for critical service dependencies
during application startup to handle transient failures without immediate crash.
"""
import asyncio
import logging
import time
from typing import Callable, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class StartupResilienceConfig:
    """Configuration for startup resilience patterns."""
    
    def __init__(self):
        # Config service resilience
        self.config_service_max_retries = 5
        self.config_service_base_delay = 1.0
        self.config_service_max_delay = 30.0
        self.config_service_timeout = 10.0
        
        # Database resilience  
        self.database_max_retries = 3
        self.database_base_delay = 2.0
        self.database_max_delay = 15.0
        
        # Redis resilience
        self.redis_max_retries = 3
        self.redis_base_delay = 1.0
        self.redis_max_delay = 10.0


async def retry_with_backoff(
    operation: Callable,
    operation_name: str,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    exceptions: tuple = (Exception,)
) -> Any:
    """
    Retry an operation with exponential backoff.
    
    Args:
        operation: The operation to retry
        operation_name: Human-readable name for logging
        max_retries: Maximum number of retry attempts
        base_delay: Base delay in seconds
        max_delay: Maximum delay between retries
        exceptions: Tuple of exceptions to catch and retry on
        
    Returns:
        Result of the operation
        
    Raises:
        The last exception if all retries fail
    """
    last_exception = None
    
    for attempt in range(max_retries + 1):
        try:
            if asyncio.iscoroutinefunction(operation):
                result = await operation()
            else:
                result = operation()
                
            if attempt > 0:
                logger.info(f"{operation_name} succeeded on attempt {attempt + 1}")
            
            return result
            
        except exceptions as e:
            last_exception = e
            
            if attempt < max_retries:
                # Calculate delay with exponential backoff and jitter
                delay = min(base_delay * (2 ** attempt), max_delay)
                jitter = delay * 0.1 * (0.5 - asyncio.get_event_loop().time() % 1)
                total_delay = delay + jitter
                
                logger.warning(
                    f"{operation_name} failed on attempt {attempt + 1}/{max_retries + 1}: {e}. "
                    f"Retrying in {total_delay:.2f}s..."
                )
                
                await asyncio.sleep(total_delay)
            else:
                logger.error(f"{operation_name} failed after {max_retries + 1} attempts: {e}")
    
    raise last_exception


class StartupHealthChecker:
    """Validates critical dependencies during startup with resilience."""
    
    def __init__(self, config: StartupResilienceConfig = None):
        self.config = config or StartupResilienceConfig()
        self.startup_time = datetime.utcnow()
        self.dependency_status = {}
    
    async def check_config_service_resilient(self, client) -> bool:
        """Check config service with bounded retries."""
        
        async def health_check():
            if hasattr(client, 'health_check_async'):
                return await client.health_check_async()
            else:
                return client.health_check()
        
        try:
            await retry_with_backoff(
                operation=health_check,
                operation_name="Config service health check",
                max_retries=self.config.config_service_max_retries,
                base_delay=self.config.config_service_base_delay,
                max_delay=self.config.config_service_max_delay
            )
            
            self.dependency_status['config_service'] = {
                'status': 'healthy',
                'last_check': datetime.utcnow().isoformat()
            }
            return True
            
        except Exception as e:
            self.dependency_status['config_service'] = {
                'status': 'failed',
                'error': str(e),
                'last_check': datetime.utcnow().isoformat()
            }
            logger.critical(f"Config service permanently unavailable after retries: {e}")
            return False
    
    async def check_database_resilient(self, get_db_func) -> bool:
        """Check database connectivity with bounded retries."""
        
        async def db_health_check():
            try:
                # Test basic database connectivity
                if asyncio.iscoroutinefunction(get_db_func):
                    db = await get_db_func()
                else:
                    db = get_db_func()
                    
                # Simple connectivity test
                if hasattr(db, 'pool') and db.pool:
                    return True
                return False
            except Exception as e:
                logger.warning(f"Database health check failed: {e}")
                raise
        
        try:
            await retry_with_backoff(
                operation=db_health_check,
                operation_name="Database connectivity check",
                max_retries=self.config.database_max_retries,
                base_delay=self.config.database_base_delay,
                max_delay=self.config.database_max_delay
            )
            
            self.dependency_status['database'] = {
                'status': 'healthy',
                'last_check': datetime.utcnow().isoformat()
            }
            return True
            
        except Exception as e:
            self.dependency_status['database'] = {
                'status': 'degraded',
                'error': str(e),
                'last_check': datetime.utcnow().isoformat()
            }
            logger.error(f"Database connectivity issues after retries: {e}")
            return False
    
    async def check_redis_resilient(self, get_redis_func) -> bool:
        """Check Redis connectivity with bounded retries."""
        
        async def redis_health_check():
            try:
                if asyncio.iscoroutinefunction(get_redis_func):
                    redis_client = await get_redis_func()
                else:
                    redis_client = get_redis_func()
                    
                # Test Redis with simple ping
                if hasattr(redis_client, 'ping'):
                    if asyncio.iscoroutinefunction(redis_client.ping):
                        await redis_client.ping()
                    else:
                        redis_client.ping()
                return True
            except Exception as e:
                logger.warning(f"Redis health check failed: {e}")
                raise
        
        try:
            await retry_with_backoff(
                operation=redis_health_check,
                operation_name="Redis connectivity check", 
                max_retries=self.config.redis_max_retries,
                base_delay=self.config.redis_base_delay,
                max_delay=self.config.redis_max_delay
            )
            
            self.dependency_status['redis'] = {
                'status': 'healthy',
                'last_check': datetime.utcnow().isoformat()
            }
            return True
            
        except Exception as e:
            self.dependency_status['redis'] = {
                'status': 'degraded',
                'error': str(e),
                'last_check': datetime.utcnow().isoformat()
            }
            # Redis is not critical - can run without caching
            logger.warning(f"Redis unavailable - continuing without caching: {e}")
            return False
    
    def get_startup_summary(self) -> dict:
        """Get summary of startup health checks."""
        startup_duration = (datetime.utcnow() - self.startup_time).total_seconds()
        
        critical_services = ['config_service']
        critical_healthy = all(
            self.dependency_status.get(svc, {}).get('status') == 'healthy'
            for svc in critical_services
        )
        
        return {
            'startup_duration_seconds': startup_duration,
            'critical_services_healthy': critical_healthy,
            'dependency_status': self.dependency_status,
            'startup_completed_at': datetime.utcnow().isoformat()
        }


# Global startup health checker
_startup_checker: Optional[StartupHealthChecker] = None


def get_startup_checker() -> StartupHealthChecker:
    """Get or create global startup health checker."""
    global _startup_checker
    if _startup_checker is None:
        _startup_checker = StartupHealthChecker()
    return _startup_checker


async def validate_startup_dependencies():
    """
    Validate all critical startup dependencies with resilience.
    
    Returns True if all critical dependencies are healthy, False otherwise.
    """
    checker = get_startup_checker()
    
    logger.info("Starting dependency validation with resilience...")
    
    # Check config service (critical)
    config_healthy = False
    try:
        from app.core.config import _get_config_client
        client = _get_config_client()
        if client:
            config_healthy = await checker.check_config_service_resilient(client)
    except Exception as e:
        logger.critical(f"Config service validation failed: {e}")
    
    if not config_healthy:
        logger.critical("Critical dependency failure: Config service unavailable")
        return False
    
    # Check database (important but can degrade gracefully)
    try:
        from common.storage.database import get_database
        await checker.check_database_resilient(get_database)
    except Exception as e:
        logger.error(f"Database validation failed: {e}")
    
    # Check Redis (optional)
    try:
        from app.utils.redis import get_redis_client
        await checker.check_redis_resilient(get_redis_client)
    except Exception as e:
        logger.warning(f"Redis validation failed: {e}")
    
    # Log startup summary
    summary = checker.get_startup_summary()
    logger.info(f"Startup validation completed in {summary['startup_duration_seconds']:.2f}s")
    logger.info(f"Critical services healthy: {summary['critical_services_healthy']}")
    
    return summary['critical_services_healthy']