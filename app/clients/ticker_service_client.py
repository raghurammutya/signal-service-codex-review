"""
Ticker Service Client

Production-ready client for ticker service integration with proper error handling
and config service integration. Handles historical data retrieval for moneyness
and timeframe aggregation.
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Any

import httpx

from app.core.config import settings
from app.errors import DataAccessError, handle_data_access_error
from app.utils.logging_utils import log_error, log_info, log_warning

logger = logging.getLogger(__name__)


class TickerServiceError(Exception):
    """Exception raised when ticker service operations fail"""


class TickerServiceClient:
    """
    Production ticker service client with proper error handling and circuit breaking.

    Integrates with config service for URL resolution and secrets management.
    Provides fail-fast behavior when ticker service is unavailable.
    """

    def __init__(self):
        self.base_url = settings.TICKER_SERVICE_URL
        self.timeout = settings.SERVICE_INTEGRATION_TIMEOUT
        self.internal_api_key = getattr(settings, 'internal_api_key', None)
        self.gateway_secret = settings.gateway_secret

        # Circuit breaker state - async-safe with lock
        self._circuit_breaker_lock = asyncio.Lock()
        self._circuit_breaker_open = False
        self._last_failure_time = None
        self._failure_count = 0
        self.circuit_breaker_timeout = 60  # 60 seconds
        self.max_failures = 3

        if not self.base_url:
            raise TickerServiceError("Ticker service URL not configured in settings")
        if not self.gateway_secret:
            raise TickerServiceError("Gateway secret not configured for ticker service authentication")

        log_info(f"TickerServiceClient initialized with URL: {self.base_url}")

    async def _is_circuit_breaker_open(self) -> bool:
        """Check if circuit breaker is open (async-safe)."""
        async with self._circuit_breaker_lock:
            if not self._circuit_breaker_open:
                return False

            # Check if timeout period has passed
            if (self._last_failure_time and
                datetime.now() - self._last_failure_time > timedelta(seconds=self.circuit_breaker_timeout)):
                # Reset circuit breaker
                self._circuit_breaker_open = False
                self._failure_count = 0
                log_info("Ticker service circuit breaker reset - attempting reconnection")
                return False

            return True

    async def _handle_failure(self, error: Exception):
        """Handle ticker service failure and update circuit breaker state (async-safe)."""
        async with self._circuit_breaker_lock:
            self._failure_count += 1
            self._last_failure_time = datetime.now()

            if self._failure_count >= self.max_failures:
                self._circuit_breaker_open = True
                log_error(f"Ticker service circuit breaker opened after {self._failure_count} failures")

    def _get_headers(self) -> dict[str, str]:
        """Get standard headers for ticker service requests."""
        headers = {
            "X-Gateway-Secret": self.gateway_secret,
            "Content-Type": "application/json",
            "User-Agent": "signal-service/2.0.0"
        }

        if self.internal_api_key:
            headers["Authorization"] = f"Bearer {self.internal_api_key}"

        return headers

    async def health_check(self) -> bool:
        """Check ticker service health."""
        try:
            if await self._is_circuit_breaker_open():
                return False

            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    f"{self.base_url}/health",
                    headers=self._get_headers()
                )

                if response.status_code == 200:
                    # Reset failure count on successful health check
                    async with self._circuit_breaker_lock:
                        self._failure_count = 0
                    return True
                log_warning(f"Ticker service health check failed: {response.status_code}")
                return False

        except Exception as e:
            log_error(f"Ticker service health check error: {e}")
            await self._handle_failure(e)
            return False

    async def get_historical_moneyness_data(
        self,
        underlying: str,
        moneyness_level: float,
        start_time: datetime,
        end_time: datetime,
        timeframe: str = "5m"
    ) -> dict[str, Any] | None:
        """
        Get historical moneyness data from ticker service.

        Args:
            underlying: Underlying symbol (e.g., "AAPL")
            moneyness_level: Moneyness level (e.g., 0.95 for 5% OTM)
            start_time: Start time for historical data
            end_time: End time for historical data
            timeframe: Data timeframe (e.g., "5m", "1h")

        Returns:
            Historical moneyness data or None if service unavailable

        Raises:
            DataAccessError: When ticker service integration required but unavailable
        """
        try:
            if await self._is_circuit_breaker_open():
                raise DataAccessError(
                    f"Ticker service circuit breaker open - historical moneyness data "
                    f"for {underlying} unavailable. Service integration required."
                )

            request_data = {
                "underlying": underlying,
                "moneyness_level": moneyness_level,
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "timeframe": timeframe,
                "include_greeks": True,
                "include_iv": True
            }

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/v1/historical/moneyness",
                    json=request_data,
                    headers=self._get_headers()
                )

                if response.status_code == 200:
                    result = response.json()
                    log_info(f"Retrieved historical moneyness data for {underlying} from ticker service")
                    return result
                if response.status_code == 404:
                    log_warning(f"No historical moneyness data found for {underlying}")
                    return None
                if response.status_code == 503:
                    # Ticker service indicates it needs upstream integration
                    raise DataAccessError(
                        f"Ticker service reports upstream data source unavailable for {underlying} "
                        f"moneyness data - requires market data integration"
                    )
                error_msg = f"Ticker service error {response.status_code}: {response.text}"
                log_error(error_msg)
                raise TickerServiceError(error_msg)

        except httpx.RequestError as e:
            error_msg = f"Ticker service request failed for {underlying}: {e}"
            log_error(error_msg)
            await self._handle_failure(e)
            raise DataAccessError(error_msg) from e
        except DataAccessError:
            raise  # Re-raise DataAccessError as-is
        except Exception as e:
            error_msg = f"Failed to get historical moneyness data for {underlying}: {e}"
            log_error(error_msg)
            await self._handle_failure(e)
            raise handle_data_access_error(e, "fetch", "ticker_service") from e

    async def get_historical_timeframe_data(
        self,
        instrument_key: str,
        timeframe: str,
        start_time: datetime,
        end_time: datetime,
        include_volume: bool = True
    ) -> list[dict[str, Any]] | None:
        """
        Get historical timeframe aggregated data from ticker service.

        Args:
            instrument_key: Instrument identifier
            timeframe: Aggregation timeframe
            start_time: Start time
            end_time: End time
            include_volume: Include volume data

        Returns:
            List of OHLCV data points or None if unavailable
        """
        try:
            if await self._is_circuit_breaker_open():
                raise DataAccessError(
                    f"Ticker service circuit breaker open - timeframe data for "
                    f"{instrument_key} unavailable. Service integration required."
                )

            params = {
                "instrument": instrument_key,
                "timeframe": timeframe,
                "start": start_time.isoformat(),
                "end": end_time.isoformat(),
                "include_volume": include_volume
            }

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/api/v1/historical/timeframe",
                    params=params,
                    headers=self._get_headers()
                )

                if response.status_code == 200:
                    result = response.json()
                    log_info(f"Retrieved {len(result.get('data', []))} timeframe data points for {instrument_key}")
                    return result.get('data', [])
                if response.status_code == 404:
                    log_warning(f"No timeframe data found for {instrument_key}")
                    return None
                error_msg = f"Ticker service timeframe request failed: {response.status_code} - {response.text}"
                log_error(error_msg)
                raise TickerServiceError(error_msg)

        except httpx.RequestError as e:
            error_msg = f"Ticker service timeframe request failed for {instrument_key}: {e}"
            log_error(error_msg)
            await self._handle_failure(e)
            raise DataAccessError(error_msg) from e
        except Exception as e:
            error_msg = f"Failed to get timeframe data for {instrument_key}: {e}"
            log_error(error_msg)
            await self._handle_failure(e)
            raise handle_data_access_error(e, "fetch", "ticker_service") from e

    async def get_current_market_data(
        self,
        instrument_key: str
    ) -> dict[str, Any] | None:
        """
        Get current market data for an instrument.

        Args:
            instrument_key: Instrument identifier

        Returns:
            Current market data or None if unavailable
        """
        try:
            if await self._is_circuit_breaker_open():
                raise DataAccessError(
                    f"Ticker service circuit breaker open - current data for "
                    f"{instrument_key} unavailable. Service integration required."
                )

            async with httpx.AsyncClient(timeout=5) as client:  # Shorter timeout for current data
                response = await client.get(
                    f"{self.base_url}/api/v1/current/{instrument_key}",
                    headers=self._get_headers()
                )

                if response.status_code == 200:
                    result = response.json()
                    log_info(f"Retrieved current market data for {instrument_key}")
                    return result
                if response.status_code == 404:
                    log_warning(f"Current market data not found for {instrument_key}")
                    return None
                error_msg = f"Ticker service current data request failed: {response.status_code} - {response.text}"
                log_error(error_msg)
                raise TickerServiceError(error_msg)

        except httpx.RequestError as e:
            error_msg = f"Ticker service current data request failed for {instrument_key}: {e}"
            log_error(error_msg)
            await self._handle_failure(e)
            raise DataAccessError(error_msg) from e
        except Exception as e:
            error_msg = f"Failed to get current market data for {instrument_key}: {e}"
            log_error(error_msg)
            await self._handle_failure(e)
            raise handle_data_access_error(e, "fetch", "ticker_service") from e


# Global ticker service client instance
_ticker_client_instance: TickerServiceClient | None = None


def get_ticker_service_client() -> TickerServiceClient:
    """Get or create ticker service client instance via factory.

    DEPRECATED: Use 'await get_client_manager().get_client("ticker_service")' instead.
    This function is provided for backward compatibility only.
    """
    # Use the centralized client factory instead of direct instantiation
    import asyncio

    from app.clients.client_factory import get_client_manager

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If we're in an async context, we can't await here
            # Log a warning and suggest using proper async dependency injection
            import logging
            logger = logging.getLogger(__name__)
            logger.warning("get_ticker_service_client() called from async context. Use 'await get_client_manager().get_client(\"ticker_service\")' instead.")
            # Return None to force proper async usage
            return None
        manager = get_client_manager()
        return loop.run_until_complete(manager.get_client('ticker_service'))
    except RuntimeError:
        # No event loop available, suggest proper initialization
        import logging
        logger = logging.getLogger(__name__)
        logger.warning("No event loop available for get_ticker_service_client(). Use proper async initialization.")
        return None


@asynccontextmanager
async def ticker_service_context():
    """Context manager for ticker service operations with proper cleanup."""
    client = get_ticker_service_client()
    try:
        # Verify health before use
        if not await client.health_check():
            raise DataAccessError("Ticker service health check failed - integration required")
        yield client
    except Exception as e:
        log_error(f"Ticker service context error: {e}")
        raise
    finally:
        # Cleanup if needed
        pass
