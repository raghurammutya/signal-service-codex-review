"""
Centralized Client Factory

Provides managed lifecycle for all external service clients with consistent
configuration, proper resource cleanup, and circuit breaker patterns.
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncContextManager

logger = logging.getLogger(__name__)


class CircuitBreakerConfig:
    """Centralized circuit breaker configuration for all clients."""

    def __init__(self):
        # Default circuit breaker settings
        self.max_failures = 3
        self.timeout_seconds = 60
        self.base_delay = 1.0
        self.max_delay = 30.0
        self.max_retries = 3

        # Service-specific overrides
        self.service_configs = {
            'ticker_service': {
                'max_failures': 3,
                'timeout_seconds': 60,
                'max_retries': 2
            },
            'user_service': {
                'max_failures': 5,
                'timeout_seconds': 45,
                'max_retries': 3
            },
            'alert_service': {
                'max_failures': 2,
                'timeout_seconds': 30,
                'max_retries': 2
            },
            'comms_service': {
                'max_failures': 2,
                'timeout_seconds': 30,
                'max_retries': 2
            },
            'marketplace_service': {
                'max_failures': 3,
                'timeout_seconds': 45,
                'max_retries': 3
            }
        }

    def get_config(self, service_name: str) -> dict[str, Any]:
        """Get circuit breaker config for specific service."""
        service_config = self.service_configs.get(service_name, {})

        return {
            'max_failures': service_config.get('max_failures', self.max_failures),
            'timeout_seconds': service_config.get('timeout_seconds', self.timeout_seconds),
            'base_delay': service_config.get('base_delay', self.base_delay),
            'max_delay': service_config.get('max_delay', self.max_delay),
            'max_retries': service_config.get('max_retries', self.max_retries)
        }


class ClientManager:
    """Manages lifecycle and configuration of all external service clients."""

    def __init__(self):
        self.circuit_breaker_config = CircuitBreakerConfig()
        self._clients: dict[str, Any] = {}
        self._client_configs: dict[str, dict] = {}

    def register_client_config(self, service_name: str, client_class: type, **kwargs):
        """Register a client configuration for lazy initialization."""
        self._client_configs[service_name] = {
            'class': client_class,
            'kwargs': kwargs
        }

    async def get_client(self, service_name: str):
        """Get or create a managed client with proper configuration."""
        if service_name not in self._clients:
            if service_name not in self._client_configs:
                raise ValueError(f"Client config not registered for {service_name}")

            config = self._client_configs[service_name]
            client_class = config['class']
            kwargs = config['kwargs']

            # Add circuit breaker config
            cb_config = self.circuit_breaker_config.get_config(service_name)
            kwargs.update(cb_config)

            # Create client
            client = client_class(**kwargs)

            # Apply centralized configuration
            if hasattr(client, 'apply_circuit_breaker_config'):
                client.apply_circuit_breaker_config(cb_config)

            self._clients[service_name] = client
            logger.info(f"Created managed client for {service_name}")

        return self._clients[service_name]

    async def close_all_clients(self):
        """Close all managed clients to prevent resource leaks."""
        for service_name, client in self._clients.items():
            try:
                if hasattr(client, 'close_session'):
                    await client.close_session()
                elif hasattr(client, 'close'):
                    if asyncio.iscoroutinefunction(client.close):
                        await client.close()
                    else:
                        client.close()
                logger.debug(f"Closed client for {service_name}")
            except Exception as e:
                logger.warning(f"Error closing client {service_name}: {e}")

        self._clients.clear()
        logger.info("All clients closed")

    @asynccontextmanager
    async def get_client_context(self, service_name: str):
        """Get client with automatic cleanup context manager."""
        client = await self.get_client(service_name)

        # Use client's context manager if available
        if hasattr(client, '__aenter__'):
            async with client as managed_client:
                yield managed_client
        else:
            try:
                yield client
            finally:
                # Cleanup if needed
                if hasattr(client, 'close_session'):
                    try:
                        await client.close_session()
                    except Exception as e:
                        logger.warning(f"Error cleaning up {service_name}: {e}")


# Global client manager instance
_client_manager: ClientManager | None = None


def get_client_manager() -> ClientManager:
    """Get or create global client manager."""
    global _client_manager
    if _client_manager is None:
        _client_manager = ClientManager()
        _register_default_clients(_client_manager)
    return _client_manager


def _register_default_clients(manager: ClientManager):
    """Register all default service clients."""

    # Import client classes
    from app.clients.alert_service_client import AlertServiceClient
    from app.clients.comms_service_client import CommsServiceClient
    from app.clients.historical_data_client import HistoricalDataClient
    from app.clients.ticker_service_client import TickerServiceClient
    from app.clients.user_service_client import UserServiceClient
    from app.services.instrument_service_client import InstrumentServiceClient

    # Register client configurations
    manager.register_client_config(
        'ticker_service',
        TickerServiceClient
    )

    manager.register_client_config(
        'user_service',
        UserServiceClient
    )

    manager.register_client_config(
        'alert_service',
        AlertServiceClient
    )

    manager.register_client_config(
        'comms_service',
        CommsServiceClient
    )

    manager.register_client_config(
        'historical_data',
        HistoricalDataClient
    )

    manager.register_client_config(
        'instrument_service',
        InstrumentServiceClient
    )


# Convenience functions for common client access patterns
@asynccontextmanager
async def get_ticker_client() -> AsyncContextManager:
    """Get ticker service client with managed lifecycle."""
    manager = get_client_manager()
    async with manager.get_client_context('ticker_service') as client:
        yield client


@asynccontextmanager
async def get_user_client() -> AsyncContextManager:
    """Get user service client with managed lifecycle."""
    manager = get_client_manager()
    async with manager.get_client_context('user_service') as client:
        yield client


@asynccontextmanager
async def get_alert_client() -> AsyncContextManager:
    """Get alert service client with managed lifecycle."""
    manager = get_client_manager()
    async with manager.get_client_context('alert_service') as client:
        yield client


@asynccontextmanager
async def get_comms_client() -> AsyncContextManager:
    """Get comms service client with managed lifecycle."""
    manager = get_client_manager()
    async with manager.get_client_context('comms_service') as client:
        yield client


@asynccontextmanager
async def get_historical_data_client() -> AsyncContextManager:
    """Get historical data client with managed lifecycle."""
    manager = get_client_manager()
    async with manager.get_client_context('historical_data') as client:
        yield client


async def shutdown_all_clients():
    """Shutdown all managed clients - call during application shutdown."""
    manager = get_client_manager()
    await manager.close_all_clients()
    logger.info("All service clients shutdown")


# Client health checking
async def check_all_clients_health() -> dict[str, Any]:
    """Check health of all managed clients."""
    manager = get_client_manager()
    health_results = {}

    for service_name in ['ticker_service', 'user_service', 'alert_service', 'comms_service']:
        try:
            client = await manager.get_client(service_name)
            if hasattr(client, 'health_check'):
                if asyncio.iscoroutinefunction(client.health_check):
                    health = await client.health_check()
                else:
                    health = client.health_check()
                health_results[service_name] = {'status': 'healthy' if health else 'unhealthy'}
            else:
                health_results[service_name] = {'status': 'no_health_check'}
        except Exception as e:
            health_results[service_name] = {
                'status': 'error',
                'error': str(e)
            }

    return health_results
