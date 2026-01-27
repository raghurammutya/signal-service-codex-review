"""
Comprehensive API endpoint testing for v2 routes
Tests all critical API endpoints with authentication, validation, and error handling
"""

from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from httpx import AsyncClient

from app.errors import ConfigurationError, ExternalFunctionExecutionError
from app.main import app


class TestV2RealTimeEndpoints:
    """Test real-time API endpoints"""

    @pytest.fixture
    async def client(self):
        """Create test client"""
        async with AsyncClient(app=app, base_url="http://test") as ac:
            yield ac

    @pytest.fixture
    def mock_auth_headers(self):
        """Mock authentication headers"""
        return {
            "X-User-ID": "test_user_123",
            "X-Gateway-Secret": "test-gateway-secret",
            "Authorization": "Bearer test-token"
        }

    @pytest.fixture
    def sample_tick_data(self):
        """Sample tick data for testing"""
        return {
            "instrument_key": "NSE@RELIANCE@EQ",
            "ltp": {"value": 2500.50, "currency": "INR"},
            "high": {"value": 2510.00},
            "low": {"value": 2490.00},
            "open": {"value": 2495.00},
            "volume": 1500000,
            "timestamp": datetime.now(UTC).isoformat()
        }

    # Real-time Endpoints

    @patch('app.core.auth.get_current_user_from_gateway')
    @patch('app.services.greeks_calculator.GreeksCalculator.calculate_greeks')
    async def test_realtime_greeks_calculation(self, mock_calculate, mock_auth, client, mock_auth_headers, sample_tick_data):
        """Test real-time Greeks calculation endpoint"""
        mock_auth.return_value = {"user_id": "test_user_123", "role": "premium"}
        mock_calculate.return_value = {
            "delta": 0.65,
            "gamma": 0.08,
            "theta": -0.02,
            "vega": 0.15,
            "rho": 0.05
        }

        response = await client.post(
            "/api/v2/realtime/greeks",
            json={
                "instrument_key": "NSE@RELIANCE@EQ",
                "option_type": "CALL",
                "strike": 2500,
                "expiry": "2024-12-26",
                "spot_price": 2500.50,
                "volatility": 0.25
            },
            headers=mock_auth_headers
        )

        assert response.status_code == 200
        data = response.json()

        assert "greeks" in data
        assert data["greeks"]["delta"] == 0.65
        assert data["greeks"]["gamma"] == 0.08

    @patch('app.core.auth.get_current_user_from_gateway')
    @patch('app.services.pandas_ta_executor.PandasTAExecutor.execute_indicators')
    async def test_realtime_technical_indicators(self, mock_execute, mock_auth, client, mock_auth_headers):
        """Test real-time technical indicators endpoint"""
        mock_auth.return_value = {"user_id": "test_user_123", "role": "basic"}
        mock_execute.return_value = {
            "rsi_14": 68.5,
            "sma_20": 2485.30,
            "ema_12": 2492.10,
            "macd_signal": 0.75
        }

        response = await client.post(
            "/api/v2/realtime/indicators",
            json={
                "instrument_key": "NSE@RELIANCE@EQ",
                "indicators": ["rsi", "sma", "ema", "macd"],
                "parameters": {
                    "rsi_period": 14,
                    "sma_period": 20,
                    "ema_period": 12
                }
            },
            headers=mock_auth_headers
        )

        assert response.status_code == 200
        data = response.json()

        assert "indicators" in data
        assert data["indicators"]["rsi_14"] == 68.5
        assert data["indicators"]["sma_20"] == 2485.30

    @patch('app.core.auth.get_current_user_from_gateway')
    async def test_realtime_unauthorized_access(self, mock_auth, client):
        """Test unauthorized access to real-time endpoints"""
        mock_auth.side_effect = Exception("Invalid token")

        response = await client.post(
            "/api/v2/realtime/greeks",
            json={"instrument_key": "NSE@RELIANCE@EQ"},
            headers={"Authorization": "Bearer invalid-token"}
        )

        assert response.status_code == 401

    @patch('app.core.auth.get_current_user_from_gateway')
    async def test_realtime_input_validation(self, mock_auth, client, mock_auth_headers):
        """Test input validation on real-time endpoints"""
        mock_auth.return_value = {"user_id": "test_user_123", "role": "basic"}

        # Missing required fields
        response = await client.post(
            "/api/v2/realtime/greeks",
            json={
                "instrument_key": "INVALID",
                # Missing required fields
            },
            headers=mock_auth_headers
        )

        assert response.status_code == 422  # Validation error

    # Historical Data Endpoints

    @patch('app.core.auth.get_current_user_from_gateway')
    @patch('app.clients.ticker_service_client.TickerServiceClient.get_historical_data')
    async def test_historical_data_retrieval(self, mock_historical, mock_auth, client, mock_auth_headers):
        """Test historical data retrieval endpoint"""
        mock_auth.return_value = {"user_id": "test_user_123", "role": "premium"}
        mock_historical.return_value = {
            "data": [
                {
                    "timestamp": "2024-12-20T09:15:00Z",
                    "open": 2495.00,
                    "high": 2510.00,
                    "low": 2490.00,
                    "close": 2505.50,
                    "volume": 1200000
                }
            ],
            "total_records": 1
        }

        response = await client.get(
            "/api/v2/historical/data",
            params={
                "instrument_key": "NSE@RELIANCE@EQ",
                "timeframe": "1day",
                "start_date": "2024-12-20",
                "end_date": "2024-12-20"
            },
            headers=mock_auth_headers
        )

        assert response.status_code == 200
        data = response.json()

        assert "data" in data
        assert len(data["data"]) == 1
        assert data["data"][0]["close"] == 2505.50

    @patch('app.core.auth.get_current_user_from_gateway')
    async def test_historical_data_date_validation(self, mock_auth, client, mock_auth_headers):
        """Test date validation for historical data"""
        mock_auth.return_value = {"user_id": "test_user_123", "role": "basic"}

        # Invalid date format
        response = await client.get(
            "/api/v2/historical/data",
            params={
                "instrument_key": "NSE@RELIANCE@EQ",
                "timeframe": "1day",
                "start_date": "invalid-date",
                "end_date": "2024-12-20"
            },
            headers=mock_auth_headers
        )

        assert response.status_code == 422


class TestV2WebSocketEndpoints:
    """Test WebSocket real-time streaming endpoints"""

    @pytest.fixture
    async def client(self):
        async with AsyncClient(app=app, base_url="http://test") as ac:
            yield ac

    @patch('app.core.auth.get_current_user_from_gateway')
    async def test_websocket_subscription_creation(self, mock_auth, client):
        """Test WebSocket subscription creation"""
        mock_auth.return_value = {"user_id": "test_user_123", "role": "premium"}

        response = await client.post(
            "/api/v2/websocket/subscribe",
            json={
                "instrument_keys": ["NSE@RELIANCE@EQ", "NSE@TCS@EQ"],
                "data_types": ["ticks", "greeks", "indicators"],
                "subscription_id": "sub_123"
            },
            headers={
                "X-User-ID": "test_user_123",
                "Authorization": "Bearer test-token"
            }
        )

        assert response.status_code == 200
        data = response.json()

        assert "subscription_id" in data
        assert "websocket_url" in data
        assert data["status"] == "subscribed"

    @patch('app.core.auth.get_current_user_from_gateway')
    async def test_websocket_subscription_limits(self, mock_auth, client):
        """Test WebSocket subscription limits by user role"""
        mock_auth.return_value = {"user_id": "test_user_123", "role": "basic"}

        # Too many instruments for basic user
        response = await client.post(
            "/api/v2/websocket/subscribe",
            json={
                "instrument_keys": ["NSE@STOCK" + str(i) + "@EQ" for i in range(100)],  # 100 instruments
                "data_types": ["ticks"]
            },
            headers={
                "X-User-ID": "test_user_123",
                "Authorization": "Bearer test-token"
            }
        )

        assert response.status_code == 403  # Forbidden due to limits


class TestV2BatchProcessingEndpoints:
    """Test batch processing endpoints"""

    @pytest.fixture
    async def client(self):
        async with AsyncClient(app=app, base_url="http://test") as ac:
            yield ac

    @patch('app.core.auth.get_current_user_from_gateway')
    @patch('app.services.batch_processor.BatchProcessor.process_batch')
    async def test_batch_greeks_calculation(self, mock_process, mock_auth, client):
        """Test batch Greeks calculation"""
        mock_auth.return_value = {"user_id": "test_user_123", "role": "premium"}
        mock_process.return_value = {
            "job_id": "batch_123",
            "status": "processing",
            "total_items": 5,
            "estimated_completion": "2024-12-20T10:00:00Z"
        }

        response = await client.post(
            "/api/v2/batch/greeks",
            json={
                "instruments": [
                    {
                        "instrument_key": "NSE@RELIANCE@EQ",
                        "option_type": "CALL",
                        "strike": 2500,
                        "expiry": "2024-12-26"
                    },
                    {
                        "instrument_key": "NSE@TCS@EQ",
                        "option_type": "PUT",
                        "strike": 3800,
                        "expiry": "2024-12-26"
                    }
                ],
                "market_data": {
                    "volatility": 0.25,
                    "risk_free_rate": 0.06
                }
            },
            headers={
                "X-User-ID": "test_user_123",
                "Authorization": "Bearer test-token"
            }
        )

        assert response.status_code == 202  # Accepted
        data = response.json()

        assert "job_id" in data
        assert data["status"] == "processing"

    @patch('app.core.auth.get_current_user_from_gateway')
    async def test_batch_job_status(self, mock_auth, client):
        """Test batch job status retrieval"""
        mock_auth.return_value = {"user_id": "test_user_123", "role": "premium"}

        with patch('app.services.batch_processor.BatchProcessor.get_job_status') as mock_status:
            mock_status.return_value = {
                "job_id": "batch_123",
                "status": "completed",
                "progress": 100,
                "results_url": "/api/v2/batch/results/batch_123"
            }

            response = await client.get(
                "/api/v2/batch/status/batch_123",
                headers={
                    "X-User-ID": "test_user_123",
                    "Authorization": "Bearer test-token"
                }
            )

            assert response.status_code == 200
            data = response.json()

            assert data["status"] == "completed"
            assert data["progress"] == 100


class TestV2SignalExecutionEndpoints:
    """Test signal execution endpoints (MinIO script execution)"""

    @pytest.fixture
    async def client(self):
        async with AsyncClient(app=app, base_url="http://test") as ac:
            yield ac

    @patch('app.core.auth.get_current_user_from_gateway')
    @patch('app.services.external_function_executor.ExternalFunctionExecutor.execute_single_function_with_acl')
    async def test_custom_script_execution(self, mock_execute, mock_auth, client):
        """Test custom script execution endpoint"""
        mock_auth.return_value = {"user_id": "test_user_123", "role": "premium"}
        mock_execute.return_value = {
            "signals": [
                {
                    "name": "momentum",
                    "value": 1.5,
                    "direction": "BUY",
                    "confidence": 0.8
                }
            ],
            "execution_time": 1.25,
            "timestamp": datetime.now(UTC).isoformat()
        }

        response = await client.post(
            "/api/v2/signals/execute",
            json={
                "script_id": "user_script_123",
                "instrument_key": "NSE@RELIANCE@EQ",
                "parameters": {
                    "threshold": 0.05,
                    "period": 14
                }
            },
            headers={
                "X-User-ID": "test_user_123",
                "Authorization": "Bearer test-token"
            }
        )

        assert response.status_code == 200
        data = response.json()

        assert "signals" in data
        assert len(data["signals"]) == 1
        assert data["signals"][0]["name"] == "momentum"

    @patch('app.core.auth.get_current_user_from_gateway')
    async def test_script_execution_security_failure(self, mock_auth, client):
        """Test script execution with security failure"""
        mock_auth.return_value = {"user_id": "test_user_123", "role": "basic"}

        with patch('app.services.external_function_executor.ExternalFunctionExecutor.execute_single_function_with_acl') as mock_execute:
            mock_execute.side_effect = ExternalFunctionExecutionError("Malicious code detected")

            response = await client.post(
                "/api/v2/signals/execute",
                json={
                    "script_id": "malicious_script",
                    "instrument_key": "NSE@RELIANCE@EQ",
                    "parameters": {}
                },
                headers={
                    "X-User-ID": "test_user_123",
                    "Authorization": "Bearer test-token"
                }
            )

            assert response.status_code == 400
            data = response.json()

            assert "error" in data
            assert "malicious code" in data["error"].lower()


class TestV2AdminEndpoints:
    """Test administrative endpoints"""

    @pytest.fixture
    async def client(self):
        async with AsyncClient(app=app, base_url="http://test") as ac:
            yield ac

    @patch('app.core.auth.get_current_user_from_gateway')
    async def test_admin_system_health(self, mock_auth, client):
        """Test system health endpoint"""
        mock_auth.return_value = {"user_id": "admin_123", "role": "admin"}

        with patch('app.services.external_function_executor.ExternalFunctionExecutor.get_metrics') as mock_metrics:
            mock_metrics.return_value = {
                "security_features": {
                    "malicious_code_detection": True,
                    "crash_prevention": True,
                    "acl_enforcement": True
                },
                "system_stability": {
                    "is_stable": True,
                    "memory_usage_mb": 245.6,
                    "cpu_percent": 15.2
                }
            }

            response = await client.get(
                "/api/v2/admin/system/health",
                headers={
                    "X-User-ID": "admin_123",
                    "Authorization": "Bearer admin-token"
                }
            )

            assert response.status_code == 200
            data = response.json()

            assert "security_features" in data
            assert data["security_features"]["malicious_code_detection"] is True

    @patch('app.core.auth.get_current_user_from_gateway')
    async def test_admin_access_control(self, mock_auth, client):
        """Test admin endpoint access control"""
        mock_auth.return_value = {"user_id": "user_123", "role": "basic"}  # Non-admin user

        response = await client.get(
            "/api/v2/admin/system/health",
            headers={
                "X-User-ID": "user_123",
                "Authorization": "Bearer user-token"
            }
        )

        assert response.status_code == 403  # Forbidden


class TestV2ErrorHandling:
    """Test error handling across all endpoints"""

    @pytest.fixture
    async def client(self):
        async with AsyncClient(app=app, base_url="http://test") as ac:
            yield ac

    async def test_missing_authentication(self, client):
        """Test requests without authentication"""
        response = await client.get("/api/v2/realtime/indicators")
        assert response.status_code in [401, 403]

    @patch('app.core.auth.get_current_user_from_gateway')
    async def test_service_unavailable_errors(self, mock_auth, client):
        """Test handling of service unavailable errors"""
        mock_auth.return_value = {"user_id": "test_user_123", "role": "premium"}

        with patch('app.services.greeks_calculator.GreeksCalculator.calculate_greeks') as mock_calculate:
            mock_calculate.side_effect = ConfigurationError("Service temporarily unavailable")

            response = await client.post(
                "/api/v2/realtime/greeks",
                json={
                    "instrument_key": "NSE@RELIANCE@EQ",
                    "option_type": "CALL",
                    "strike": 2500,
                    "expiry": "2024-12-26"
                },
                headers={
                    "X-User-ID": "test_user_123",
                    "Authorization": "Bearer test-token"
                }
            )

            assert response.status_code == 503  # Service Unavailable

    @patch('app.core.auth.get_current_user_from_gateway')
    async def test_rate_limiting(self, mock_auth, client):
        """Test rate limiting behavior"""
        mock_auth.return_value = {"user_id": "test_user_123", "role": "basic"}

        # Simulate rate limit exceeded
        with patch('app.middleware.ratelimit.RateLimiter.check_rate_limit') as mock_rate_limit:
            mock_rate_limit.return_value = False  # Rate limit exceeded

            response = await client.get(
                "/api/v2/realtime/indicators",
                headers={
                    "X-User-ID": "test_user_123",
                    "Authorization": "Bearer test-token"
                }
            )

            assert response.status_code == 429  # Too Many Requests

    async def test_invalid_endpoints(self, client):
        """Test requests to non-existent endpoints"""
        response = await client.get("/api/v2/nonexistent/endpoint")
        assert response.status_code == 404

    @patch('app.core.auth.get_current_user_from_gateway')
    async def test_malformed_json_requests(self, mock_auth, client):
        """Test handling of malformed JSON requests"""
        mock_auth.return_value = {"user_id": "test_user_123", "role": "basic"}

        response = await client.post(
            "/api/v2/realtime/indicators",
            data="invalid-json",  # Not valid JSON
            headers={
                "X-User-ID": "test_user_123",
                "Authorization": "Bearer test-token",
                "Content-Type": "application/json"
            }
        )

        assert response.status_code == 422  # Unprocessable Entity
