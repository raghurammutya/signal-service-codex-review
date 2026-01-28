"""
Config-driven Pool Management

Manages database, Redis, and HTTP client pools with configuration from config service.
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, Optional, Union

if TYPE_CHECKING:
    import httpx

logger = logging.getLogger(__name__)


class ConfigDrivenPoolManager:
    """Manages all connection pools with config service integration."""

    def __init__(self):
        self._db_pool = None
        self._redis_pool = None
        self._http_clients = {}
        self._budget_manager = None
        self._pools_initialized = False

    async def initialize(self):
        """Initialize all pools with config-driven settings."""
        from app.config.budget_config import get_budget_manager
        self._budget_manager = get_budget_manager()

        # Initialize pools concurrently
        await asyncio.gather(
            self._initialize_database_pool(),
            self._initialize_redis_pool(),
            self._initialize_http_client_pool(),
            return_exceptions=True
        )

        self._pools_initialized = True
        logger.info("All connection pools initialized with config-driven settings")

    async def _initialize_database_pool(self):
        """Initialize database connection pool with config settings."""
        try:
            db_config = await self._budget_manager.get_database_pool_config()

            # Import database utilities
            from common.storage.database import create_connection_pool

            self._db_pool = await create_connection_pool(
                min_connections=db_config.min_connections,
                max_connections=db_config.max_connections,
                connection_timeout=db_config.connection_timeout,
                idle_timeout=db_config.idle_timeout,
                max_lifetime=db_config.max_lifetime,
                retry_attempts=db_config.retry_attempts
            )

            logger.info(f"Database pool initialized: min={db_config.min_connections}, max={db_config.max_connections}")

        except Exception as e:
            logger.error(f"Failed to initialize database pool: {e}")
            # Initialize with defaults as fallback
            from common.storage.database import create_connection_pool
            self._db_pool = await create_connection_pool(
                min_connections=5,
                max_connections=20,
                connection_timeout=30.0
            )

    async def _initialize_redis_pool(self):
        """Initialize Redis connection pool with config settings."""
        try:
            redis_config = await self._budget_manager.get_redis_pool_config()

            # Import Redis utilities
            from app.utils.redis import create_redis_pool

            self._redis_pool = await create_redis_pool(
                min_connections=redis_config.min_connections,
                max_connections=redis_config.max_connections,
                connection_timeout=redis_config.connection_timeout,
                socket_timeout=redis_config.socket_timeout,
                retry_attempts=redis_config.retry_attempts,
                retry_delay=redis_config.retry_delay
            )

            logger.info(f"Redis pool initialized: min={redis_config.min_connections}, max={redis_config.max_connections}")

        except Exception as e:
            logger.error(f"Failed to initialize Redis pool: {e}")
            # Initialize with defaults as fallback
            from app.utils.redis import create_redis_pool
            self._redis_pool = await create_redis_pool(
                min_connections=5,
                max_connections=50
            )

    async def _initialize_http_client_pool(self):
        """Initialize HTTP client pools with config settings."""
        try:
            client_config = await self._budget_manager.get_client_pool_config()

            import httpx

            # Create HTTP client with configured pool limits
            limits = httpx.Limits(
                max_connections=client_config.max_connections,
                max_keepalive_connections=client_config.max_keepalive_connections,
                keepalive_expiry=client_config.keepalive_expiry
            )

            timeout = httpx.Timeout(
                timeout=client_config.timeout,
                read=client_config.timeout,
                write=client_config.timeout,
                connect=client_config.timeout
            )

            # Create shared HTTP client for external services
            self._http_clients['shared'] = httpx.AsyncClient(
                limits=limits,
                timeout=timeout,
                max_redirects=client_config.max_retries
            )

            logger.info(f"HTTP client pool initialized: max_conn={client_config.max_connections}, timeout={client_config.timeout}s")

        except Exception as e:
            logger.error(f"Failed to initialize HTTP client pool: {e}")
            # Initialize with defaults as fallback
            import httpx
            self._http_clients['shared'] = httpx.AsyncClient(
                limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
                timeout=httpx.Timeout(30.0)
            )

    async def get_database_connection(self):
        """Get database connection from pool."""
        if not self._pools_initialized:
            await self.initialize()

        if self._db_pool:
            return await self._db_pool.acquire()
        raise RuntimeError("Database pool not initialized")

    @asynccontextmanager
    async def get_database_session(self):
        """Get database session with automatic cleanup."""
        connection = await self.get_database_connection()
        try:
            yield connection
        finally:
            if self._db_pool:
                await self._db_pool.release(connection)

    async def get_redis_connection(self):
        """Get Redis connection from pool."""
        if not self._pools_initialized:
            await self.initialize()

        if self._redis_pool:
            return await self._redis_pool.acquire()
        raise RuntimeError("Redis pool not initialized")

    @asynccontextmanager
    async def get_redis_session(self):
        """Get Redis session with automatic cleanup."""
        connection = await self.get_redis_connection()
        try:
            yield connection
        finally:
            if self._redis_pool:
                await self._redis_pool.release(connection)

    def get_http_client(self, client_name: str = 'shared') -> 'httpx.AsyncClient':
        """Get HTTP client from pool."""
        if not self._pools_initialized:
            raise RuntimeError("HTTP client pool not initialized. Call initialize() first.")

        if client_name in self._http_clients:
            return self._http_clients[client_name]
        # Return shared client as fallback
        return self._http_clients['shared']

    async def refresh_pool_configs(self):
        """Refresh pool configurations from config service."""
        logger.info("Refreshing pool configurations...")

        try:
            # Get updated configurations
            db_config = await self._budget_manager.get_database_pool_config()
            redis_config = await self._budget_manager.get_redis_pool_config()
            client_config = await self._budget_manager.get_client_pool_config()

            # Log configuration changes
            logger.info(f"Updated DB pool config: min={db_config.min_connections}, max={db_config.max_connections}")
            logger.info(f"Updated Redis pool config: min={redis_config.min_connections}, max={redis_config.max_connections}")
            logger.info(f"Updated HTTP client config: max_conn={client_config.max_connections}, timeout={client_config.timeout}s")

            # Note: Actually applying pool config changes would require pool recreation
            # For now, just log the changes. In production, you might implement gradual pool resizing

        except Exception as e:
            logger.error(f"Failed to refresh pool configurations: {e}")

    async def get_pool_status(self) -> dict[str, Any]:
        """Get current pool status and statistics."""
        status = {
            'initialized': self._pools_initialized,
            'pools': {}
        }

        try:
            # Database pool status
            if self._db_pool:
                status['pools']['database'] = {
                    'type': 'database',
                    'available_connections': getattr(self._db_pool, '_free_count', 0),
                    'used_connections': getattr(self._db_pool, '_used_count', 0),
                    'total_connections': getattr(self._db_pool, '_size', 0),
                    'status': 'healthy'
                }
            else:
                status['pools']['database'] = {'status': 'not_initialized'}

            # Redis pool status
            if self._redis_pool:
                status['pools']['redis'] = {
                    'type': 'redis',
                    'available_connections': getattr(self._redis_pool, '_available_count', 0),
                    'used_connections': getattr(self._redis_pool, '_used_count', 0),
                    'status': 'healthy'
                }
            else:
                status['pools']['redis'] = {'status': 'not_initialized'}

            # HTTP client status
            if self._http_clients:
                status['pools']['http_clients'] = {
                    'type': 'http',
                    'client_count': len(self._http_clients),
                    'clients': list(self._http_clients.keys()),
                    'status': 'healthy'
                }
            else:
                status['pools']['http_clients'] = {'status': 'not_initialized'}

        except Exception as e:
            logger.error(f"Error getting pool status: {e}")
            status['error'] = str(e)

        return status

    async def cleanup(self):
        """Cleanup all pools and connections."""
        logger.info("Cleaning up all connection pools...")

        cleanup_tasks = []

        # Close database pool
        if self._db_pool:
            cleanup_tasks.append(self._cleanup_database_pool())

        # Close Redis pool
        if self._redis_pool:
            cleanup_tasks.append(self._cleanup_redis_pool())

        # Close HTTP clients
        if self._http_clients:
            cleanup_tasks.append(self._cleanup_http_clients())

        if cleanup_tasks:
            await asyncio.gather(*cleanup_tasks, return_exceptions=True)

        logger.info("All connection pools cleaned up")

    async def _cleanup_database_pool(self):
        """Cleanup database pool."""
        try:
            await self._db_pool.close()
            self._db_pool = None
        except Exception as e:
            logger.warning(f"Error closing database pool: {e}")

    async def _cleanup_redis_pool(self):
        """Cleanup Redis pool."""
        try:
            await self._redis_pool.close()
            self._redis_pool = None
        except Exception as e:
            logger.warning(f"Error closing Redis pool: {e}")

    async def _cleanup_http_clients(self):
        """Cleanup HTTP clients."""
        try:
            for _name, client in self._http_clients.items():
                await client.aclose()
            self._http_clients.clear()
        except Exception as e:
            logger.warning(f"Error closing HTTP clients: {e}")


# Global pool manager instance
_pool_manager: ConfigDrivenPoolManager | None = None


def get_pool_manager() -> ConfigDrivenPoolManager:
    """Get or create global pool manager instance."""
    global _pool_manager
    if _pool_manager is None:
        _pool_manager = ConfigDrivenPoolManager()
    return _pool_manager


# Convenience functions for backward compatibility
async def get_config_driven_db_session():
    """Get database session from config-driven pool."""
    pool_manager = get_pool_manager()
    return pool_manager.get_database_session()


async def get_config_driven_redis_session():
    """Get Redis session from config-driven pool."""
    pool_manager = get_pool_manager()
    return pool_manager.get_redis_session()


def get_config_driven_http_client(service_name: str = 'shared'):
    """Get HTTP client from config-driven pool."""
    pool_manager = get_pool_manager()
    return pool_manager.get_http_client(service_name)
