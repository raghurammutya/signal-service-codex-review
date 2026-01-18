"""
Ticker Service Integration Tests

Tests for ticker service client with mocked HTTP responses to verify
historical data retrieval and error handling paths.
"""
import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from app.clients.ticker_service_client import TickerServiceClient, TickerServiceError, ticker_service_context
from app.errors import DataAccessError


class TestTickerServiceClient:
    """Test ticker service client integration."""
    
    @pytest.fixture
    def ticker_client(self):
        """Create ticker service client with mocked settings."""
        with patch('app.clients.ticker_service_client.settings') as mock_settings:
            mock_settings.TICKER_SERVICE_URL = "http://ticker-service.test.com"
            mock_settings.SERVICE_INTEGRATION_TIMEOUT = 30.0
            mock_settings.gateway_secret = "test-gateway-secret"
            mock_settings.internal_api_key = "test-api-key"
            
            return TickerServiceClient()
    
    @pytest.fixture
    def sample_moneyness_response(self):
        """Sample moneyness data response from ticker service."""
        return {
            "data": [
                {
                    "timestamp": "2023-01-01T10:00:00Z",
                    "moneyness": 0.95,
                    "delta": 0.25,
                    "gamma": 0.02,
                    "theta": -0.01,
                    "vega": 0.15,
                    "implied_volatility": 0.22
                },
                {
                    "timestamp": "2023-01-01T10:05:00Z",
                    "moneyness": 0.95,
                    "delta": 0.26,
                    "gamma": 0.021,
                    "theta": -0.009,
                    "vega": 0.16,
                    "implied_volatility": 0.23
                }
            ],
            "metadata": {
                "underlying": "AAPL",
                "moneyness_level": 0.95,
                "total_points": 2
            }
        }
    
    @pytest.fixture
    def sample_timeframe_response(self):
        """Sample timeframe data response from ticker service."""
        return {
            "data": [
                {
                    "timestamp": "2023-01-01T10:00:00Z",
                    "open": 150.0,
                    "high": 151.0,
                    "low": 149.5,
                    "close": 150.5,
                    "volume": 10000
                },
                {
                    "timestamp": "2023-01-01T10:05:00Z",
                    "open": 150.5,
                    "high": 152.0,
                    "low": 150.0,
                    "close": 151.5,
                    "volume": 12000
                }
            ],
            "metadata": {
                "instrument": "AAPL",
                "timeframe": "5m",
                "total_points": 2
            }
        }
    
    async def test_health_check_success(self, ticker_client):
        """Test successful health check."""
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_client.return_value.__aenter__.return_value.get.return_value = mock_response
            
            result = await ticker_client.health_check()
            assert result is True
            assert ticker_client.failure_count == 0
    
    async def test_health_check_failure(self, ticker_client):
        """Test health check failure."""
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = AsyncMock()
            mock_response.status_code = 500
            mock_client.return_value.__aenter__.return_value.get.return_value = mock_response
            
            result = await ticker_client.health_check()
            assert result is False
    
    async def test_get_historical_moneyness_success(self, ticker_client, sample_moneyness_response):
        """Test successful historical moneyness data retrieval."""
        start_time = datetime(2023, 1, 1, 10, 0)
        end_time = datetime(2023, 1, 1, 11, 0)
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.json.return_value = sample_moneyness_response
            mock_client.return_value.__aenter__.return_value.post.return_value = mock_response
            
            result = await ticker_client.get_historical_moneyness_data(
                underlying="AAPL",
                moneyness_level=0.95,
                start_time=start_time,
                end_time=end_time,
                timeframe="5m"
            )
            
            assert result is not None
            assert result["data"] is not None
            assert len(result["data"]) == 2
            assert result["metadata"]["underlying"] == "AAPL"
    
    async def test_get_historical_moneyness_not_found(self, ticker_client):
        """Test historical moneyness data not found."""
        start_time = datetime(2023, 1, 1, 10, 0)
        end_time = datetime(2023, 1, 1, 11, 0)
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = AsyncMock()
            mock_response.status_code = 404
            mock_client.return_value.__aenter__.return_value.post.return_value = mock_response
            
            result = await ticker_client.get_historical_moneyness_data(
                underlying="NONEXISTENT",
                moneyness_level=0.95,
                start_time=start_time,
                end_time=end_time
            )
            
            assert result is None
    
    async def test_get_historical_moneyness_upstream_unavailable(self, ticker_client):
        """Test ticker service upstream unavailable (503)."""
        start_time = datetime(2023, 1, 1, 10, 0)
        end_time = datetime(2023, 1, 1, 11, 0)
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = AsyncMock()
            mock_response.status_code = 503
            mock_client.return_value.__aenter__.return_value.post.return_value = mock_response
            
            with pytest.raises(DataAccessError, match="upstream data source unavailable"):
                await ticker_client.get_historical_moneyness_data(
                    underlying="AAPL",
                    moneyness_level=0.95,
                    start_time=start_time,
                    end_time=end_time
                )
    
    async def test_get_historical_timeframe_success(self, ticker_client, sample_timeframe_response):
        """Test successful timeframe data retrieval."""
        start_time = datetime(2023, 1, 1, 10, 0)
        end_time = datetime(2023, 1, 1, 11, 0)
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.json.return_value = sample_timeframe_response
            mock_client.return_value.__aenter__.return_value.get.return_value = mock_response
            
            result = await ticker_client.get_historical_timeframe_data(
                instrument_key="AAPL",
                timeframe="5m",
                start_time=start_time,
                end_time=end_time
            )
            
            assert result is not None
            assert len(result) == 2
            assert result[0]["open"] == 150.0
    
    async def test_circuit_breaker_behavior(self, ticker_client):
        """Test circuit breaker behavior after multiple failures."""
        # Simulate 3 consecutive failures to trigger circuit breaker
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.side_effect = httpx.RequestError("Connection failed")
            
            start_time = datetime(2023, 1, 1, 10, 0)
            end_time = datetime(2023, 1, 1, 11, 0)
            
            # First 3 failures
            for i in range(3):
                with pytest.raises(DataAccessError):
                    await ticker_client.get_historical_moneyness_data(
                        underlying="AAPL",
                        moneyness_level=0.95,
                        start_time=start_time,
                        end_time=end_time
                    )
            
            # Circuit breaker should now be open
            assert ticker_client.circuit_breaker_open is True
            assert ticker_client.failure_count >= 3
            
            # Next call should fail immediately due to open circuit breaker
            with pytest.raises(DataAccessError, match="circuit breaker open"):
                await ticker_client.get_historical_moneyness_data(
                    underlying="AAPL",
                    moneyness_level=0.95,
                    start_time=start_time,
                    end_time=end_time
                )
    
    async def test_request_timeout_handling(self, ticker_client):
        """Test handling of request timeouts."""
        start_time = datetime(2023, 1, 1, 10, 0)
        end_time = datetime(2023, 1, 1, 11, 0)
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.side_effect = httpx.TimeoutException("Request timed out")
            
            with pytest.raises(DataAccessError, match="request failed"):
                await ticker_client.get_historical_moneyness_data(
                    underlying="AAPL",
                    moneyness_level=0.95,
                    start_time=start_time,
                    end_time=end_time
                )
            
            # Should increment failure count
            assert ticker_client.failure_count > 0
    
    async def test_get_current_market_data_success(self, ticker_client):
        """Test successful current market data retrieval."""
        sample_current_data = {
            "instrument": "AAPL",
            "timestamp": "2023-01-01T10:00:00Z",
            "price": 150.0,
            "bid": 149.9,
            "ask": 150.1,
            "volume": 1000
        }
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.json.return_value = sample_current_data
            mock_client.return_value.__aenter__.return_value.get.return_value = mock_response
            
            result = await ticker_client.get_current_market_data("AAPL")
            
            assert result is not None
            assert result["instrument"] == "AAPL"
            assert result["price"] == 150.0


class TestTickerServiceContext:
    """Test ticker service context manager."""
    
    async def test_context_manager_success(self):
        """Test successful context manager usage."""
        with patch('app.clients.ticker_service_client.get_ticker_service_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.health_check.return_value = True
            mock_get_client.return_value = mock_client
            
            async with ticker_service_context() as client:
                assert client == mock_client
                mock_client.health_check.assert_called_once()
    
    async def test_context_manager_health_check_failure(self):
        """Test context manager with health check failure."""
        with patch('app.clients.ticker_service_client.get_ticker_service_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.health_check.return_value = False
            mock_get_client.return_value = mock_client
            
            with pytest.raises(DataAccessError, match="health check failed"):
                async with ticker_service_context():
                    pass


class TestTickerServiceClientConfiguration:
    """Test ticker service client configuration."""
    
    def test_client_requires_ticker_service_url(self):
        """Test that client requires ticker service URL."""
        with patch('app.clients.ticker_service_client.settings') as mock_settings:
            mock_settings.TICKER_SERVICE_URL = None
            mock_settings.gateway_secret = "test-secret"
            
            with pytest.raises(TickerServiceError, match="Ticker service URL not configured"):
                TickerServiceClient()
    
    def test_client_requires_gateway_secret(self):
        """Test that client requires gateway secret."""
        with patch('app.clients.ticker_service_client.settings') as mock_settings:
            mock_settings.TICKER_SERVICE_URL = "http://ticker.test.com"
            mock_settings.SERVICE_INTEGRATION_TIMEOUT = 30.0
            mock_settings.gateway_secret = None
            
            with pytest.raises(TickerServiceError, match="Gateway secret not configured"):
                TickerServiceClient()
    
    def test_client_headers_generation(self):
        """Test generation of request headers."""
        with patch('app.clients.ticker_service_client.settings') as mock_settings:
            mock_settings.TICKER_SERVICE_URL = "http://ticker.test.com"
            mock_settings.SERVICE_INTEGRATION_TIMEOUT = 30.0
            mock_settings.gateway_secret = "test-gateway-secret"
            mock_settings.internal_api_key = "test-api-key"
            
            client = TickerServiceClient()
            headers = client._get_headers()
            
            assert headers["X-Gateway-Secret"] == "test-gateway-secret"
            assert headers["Authorization"] == "Bearer test-api-key"
            assert headers["Content-Type"] == "application/json"


def main():
    """Run ticker service integration tests."""
    import subprocess
    import sys
    
    print("🔍 Running Ticker Service Integration Tests...")
    
    # Run the tests
    result = subprocess.run([
        sys.executable, '-m', 'pytest', 
        __file__, 
        '-v', 
        '--tb=short'
    ], capture_output=True, text=True)
    
    print("STDOUT:")
    print(result.stdout)
    
    if result.stderr:
        print("STDERR:")
        print(result.stderr)
    
    if result.returncode == 0:
        print("✅ Ticker service integration tests passed!")
        print("\n📋 Integration Coverage:")
        print("  - Historical moneyness data retrieval")
        print("  - Historical timeframe data retrieval")
        print("  - Current market data retrieval")
        print("  - Circuit breaker behavior")
        print("  - Request timeout handling")
        print("  - Health check integration")
        print("  - Configuration validation")
        print("  - Context manager usage")
    else:
        print("❌ Ticker service integration tests failed!")
        return 1
    
    return 0


if __name__ == "__main__":
    exit_code = main()
    exit(exit_code)