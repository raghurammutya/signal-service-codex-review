#!/usr/bin/env python3
"""
Broker Factory - Phase 1 Migration

CLIENT_002: Unified broker client factory with multi-broker support
- Creates broker clients with instrument_key-first interface
- Automatic broker selection and configuration
- Connection pooling and rate limiting
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.brokers.base_broker_client import BaseBrokerClient, BrokerConfig, BrokerType
from app.brokers.kite_client import create_kite_client

logger = logging.getLogger(__name__)

@dataclass
class BrokerCredentials:
    """Broker authentication credentials"""
    broker_type: BrokerType
    api_key: str
    api_secret: str
    access_token: str | None = None
    additional_params: dict[str, Any] | None = None

class BrokerFactory:
    """
    Factory for creating and managing broker clients

    CLIENT_002: Provides unified access to multiple brokers with
    instrument_key-first interface and automatic token resolution.
    """

    def __init__(self):
        self._clients: dict[BrokerType, BaseBrokerClient] = {}
        self._default_broker: BrokerType | None = None
        self._connection_pool_size = 5

    async def create_client(self, credentials: BrokerCredentials) -> BaseBrokerClient:
        """
        Create broker client from credentials

        Args:
            credentials: Broker authentication details

        Returns:
            BaseBrokerClient: Ready-to-use broker client
        """
        broker_type = credentials.broker_type

        # Check if client already exists
        if broker_type in self._clients:
            logger.debug(f"Returning existing {broker_type.value} client")
            return self._clients[broker_type]

        try:
            client = await self._create_client_impl(credentials)

            # Connect to broker
            connected = await client.connect()
            if not connected:
                raise RuntimeError(f"Failed to connect to {broker_type.value}")

            # Cache the client
            self._clients[broker_type] = client

            # set as default if it's the first one
            if self._default_broker is None:
                self._default_broker = broker_type

            logger.info(f"Created and connected {broker_type.value} client")
            return client

        except Exception as e:
            logger.error(f"Failed to create {broker_type.value} client: {e}")
            raise RuntimeError(f"Broker client creation failed: {e}") from e

    async def _create_client_impl(self, credentials: BrokerCredentials) -> BaseBrokerClient:
        """Internal client creation implementation"""
        broker_type = credentials.broker_type

        if broker_type == BrokerType.KITE:
            return create_kite_client(
                api_key=credentials.api_key,
                access_token=credentials.access_token,
                api_secret=credentials.api_secret
            )

        if broker_type == BrokerType.ZERODHA:
            # Zerodha client implementation
            return self._create_zerodha_client(credentials)

        if broker_type == BrokerType.IBKR:
            # IBKR client implementation
            return self._create_ibkr_client(credentials)

        if broker_type == BrokerType.UPSTOX:
            # Upstox client implementation
            return self._create_upstox_client(credentials)

        if broker_type == BrokerType.MOCK:
            # Mock client for testing
            return self._create_mock_client(credentials)

        raise ValueError(f"Unsupported broker type: {broker_type}")

    def get_client(self, broker_type: BrokerType | None = None) -> BaseBrokerClient:
        """
        Get broker client by type

        Args:
            broker_type: Specific broker, or None for default

        Returns:
            BaseBrokerClient: Broker client instance
        """
        target_broker = broker_type or self._default_broker

        if target_broker is None:
            raise RuntimeError("No broker clients available")

        if target_broker not in self._clients:
            raise ValueError(f"Broker client not found: {target_broker.value}")

        return self._clients[target_broker]

    def get_default_broker(self) -> BrokerType | None:
        """Get default broker type"""
        return self._default_broker

    def set_default_broker(self, broker_type: BrokerType):
        """set default broker"""
        if broker_type not in self._clients:
            raise ValueError(f"Broker client not available: {broker_type.value}")

        self._default_broker = broker_type
        logger.info(f"Default broker set to: {broker_type.value}")

    def get_available_brokers(self) -> list[BrokerType]:
        """Get list of available broker clients"""
        return list(self._clients.keys())

    async def health_check_all(self) -> dict[BrokerType, dict[str, Any]]:
        """
        Health check all broker connections

        Returns:
            dict: Health status for each broker
        """
        health_results = {}

        for broker_type, client in self._clients.items():
            try:
                health_results[broker_type] = await client.health_check()
            except Exception as e:
                health_results[broker_type] = {
                    "healthy": False,
                    "error": str(e),
                    "broker": broker_type.value
                }

        return health_results

    async def disconnect_all(self):
        """Disconnect all broker clients"""
        for broker_type, client in self._clients.items():
            try:
                await client.disconnect()
                logger.info(f"Disconnected from {broker_type.value}")
            except Exception as e:
                logger.error(f"Error disconnecting from {broker_type.value}: {e}")

        self._clients.clear()
        self._default_broker = None

    # =============================================================================
    # PLACEHOLDER IMPLEMENTATIONS FOR OTHER BROKERS
    # =============================================================================

    def _create_zerodha_client(self, credentials: BrokerCredentials) -> BaseBrokerClient:
        """Create Zerodha client (placeholder)"""
        # TODO: Implement ZerodhaBrokerClient
        logger.warning("Zerodha client not yet implemented, using mock client")
        return self._create_mock_client(credentials)

    def _create_ibkr_client(self, credentials: BrokerCredentials) -> BaseBrokerClient:
        """Create IBKR client (placeholder)"""
        # TODO: Implement IBKRBrokerClient
        logger.warning("IBKR client not yet implemented, using mock client")
        return self._create_mock_client(credentials)

    def _create_upstox_client(self, credentials: BrokerCredentials) -> BaseBrokerClient:
        """Create Upstox client (placeholder)"""
        # TODO: Implement UpstoxBrokerClient
        logger.warning("Upstox client not yet implemented, using mock client")
        return self._create_mock_client(credentials)

    def _create_mock_client(self, credentials: BrokerCredentials) -> BaseBrokerClient:
        """Create mock client for testing"""
        from app.brokers.mock_client import MockBrokerClient

        config = BrokerConfig(
            broker_type=BrokerType.MOCK,
            api_key=credentials.api_key,
            api_secret=credentials.api_secret,
            access_token=credentials.access_token
        )

        return MockBrokerClient(config)

class MultiBrokerClient:
    """
    Multi-broker client with automatic broker selection

    CLIENT_002: Provides unified interface to multiple brokers
    with automatic failover and load balancing.
    """

    def __init__(self, factory: BrokerFactory):
        self.factory = factory
        self._broker_priorities: dict[str, list[BrokerType]] = {}

    async def place_order(self,
                         instrument_key: str,
                         side: str,
                         quantity: int,
                         broker_preference: BrokerType | None = None,
                         **kwargs):
        """
        Place order with automatic broker selection

        Args:
            instrument_key: Primary identifier
            side: BUY/SELL
            quantity: Order quantity
            broker_preference: Preferred broker, or automatic selection
            **kwargs: Additional order parameters

        Returns:
            BrokerOrder: Order result from selected broker
        """
        # Determine broker to use
        target_broker = broker_preference or self.factory.get_default_broker()
        if target_broker is None:
            raise RuntimeError("No brokers available for order placement")

        # Try primary broker
        try:
            client = self.factory.get_client(target_broker)
            return await client.place_order(
                instrument_key=instrument_key,
                side=side,
                quantity=quantity,
                **kwargs
            )
        except Exception as e:
            logger.warning(f"Order failed on {target_broker.value}: {e}")

            # Try fallback brokers if available
            available_brokers = self.factory.get_available_brokers()
            for fallback_broker in available_brokers:
                if fallback_broker != target_broker:
                    try:
                        logger.info(f"Attempting fallback to {fallback_broker.value}")
                        client = self.factory.get_client(fallback_broker)
                        return await client.place_order(
                            instrument_key=instrument_key,
                            side=side,
                            quantity=quantity,
                            **kwargs
                        )
                    except Exception as fallback_error:
                        logger.warning(f"Fallback failed on {fallback_broker.value}: {fallback_error}")
                        continue

            # All brokers failed
            raise RuntimeError(f"Order placement failed on all available brokers: {e}") from e

    async def get_best_quote(self, instrument_key: str) -> dict[str, Any]:
        """
        Get best quote across all brokers

        Args:
            instrument_key: Primary identifier

        Returns:
            dict: Best quote with broker information
        """
        available_brokers = self.factory.get_available_brokers()

        # Get quotes from all brokers concurrently
        tasks = []
        for broker_type in available_brokers:
            client = self.factory.get_client(broker_type)
            tasks.append(self._get_quote_with_broker_info(client, instrument_key, broker_type))

        # Wait for all quotes
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        valid_quotes = []
        for result in results:
            if isinstance(result, Exception):
                logger.warning(f"Quote fetch failed: {result}")
                continue
            valid_quotes.append(result)

        if not valid_quotes:
            raise RuntimeError("No quotes available from any broker")

        # Find best bid/ask
        bid_quotes = [q for q in valid_quotes if q["bid"] is not None]
        ask_quotes = [q for q in valid_quotes if q["ask"] is not None]

        best_bid = max(bid_quotes, key=lambda x: x["bid"], default=None) if bid_quotes else None
        best_ask = min(ask_quotes, key=lambda x: x["ask"], default=None) if ask_quotes else None

        return {
            "instrument_key": instrument_key,
            "best_bid": best_bid,
            "best_ask": best_ask,
            "all_quotes": valid_quotes,
            "timestamp": datetime.now().isoformat()
        }

    async def _get_quote_with_broker_info(self, client: BaseBrokerClient,
                                        instrument_key: str,
                                        broker_type: BrokerType) -> dict[str, Any]:
        """Get quote with broker information"""
        quote = await client.get_quote(instrument_key)
        return {
            "broker": broker_type.value,
            "ltp": quote.ltp,
            "bid": quote.bid,
            "ask": quote.ask,
            "volume": quote.volume,
            "timestamp": quote.timestamp
        }

# Global factory instance
_broker_factory: BrokerFactory | None = None

def get_broker_factory() -> BrokerFactory:
    """Get global broker factory instance"""
    global _broker_factory
    if _broker_factory is None:
        _broker_factory = BrokerFactory()
    return _broker_factory

async def create_multi_broker_client(credentials_list: list[BrokerCredentials]) -> MultiBrokerClient:
    """
    Create multi-broker client with multiple broker connections

    Args:
        credentials_list: list of broker credentials

    Returns:
        MultiBrokerClient: Ready-to-use multi-broker client
    """
    factory = get_broker_factory()

    # Create all broker clients
    for credentials in credentials_list:
        await factory.create_client(credentials)

    return MultiBrokerClient(factory)
