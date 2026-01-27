"""
CORS API Endpoints Integration Test

Tests CORS configuration against actual signal service API endpoints to ensure
proper handling of cross-origin requests in production scenarios.
"""
import os
from unittest.mock import Mock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# Mock the config service for testing
@pytest.fixture
def mock_config_service():
    with patch('common.config_service.client.ConfigServiceClient') as mock_client:
        mock_instance = Mock()
        mock_client.return_value = mock_instance
        mock_instance.get_config.return_value = {
            'CORS_ALLOWED_ORIGINS': 'https://app.stocksblitz.com,https://admin.stocksblitz.com',
            'environment': 'production'
        }
        yield mock_instance

@pytest.fixture
def cors_test_app():
    """Create a test FastAPI app with CORS middleware for testing."""
    app = FastAPI()

    # Import and apply CORS configuration
    from common.cors_config import add_cors_middleware
    add_cors_middleware(app, environment="production")

    # Add test endpoints that mirror signal service APIs
    @app.get("/api/v2/signals/realtime")
    async def get_realtime_signals():
        return {"status": "success", "signals": []}

    @app.post("/api/v2/signals/batch")
    async def process_batch_signals(data: dict):
        return {"status": "success", "processed": len(data.get("signals", []))}

    @app.get("/api/v2/indicators")
    async def get_indicators():
        return {"status": "success", "indicators": []}

    @app.get("/health")
    async def health_check():
        return {"status": "healthy"}

    @app.get("/monitoring")
    async def monitoring():
        return {"status": "ok", "metrics": {}}

    return app

class TestCORSAPIEndpoints:
    """Test CORS configuration against actual API endpoints."""

    @pytest.mark.integration
    def test_cors_preflight_realtime_signals(self, cors_test_app, mock_config_service):
        """Test CORS preflight for realtime signals endpoint."""
        with patch.dict(os.environ, {
            'CORS_ALLOWED_ORIGINS': 'https://app.stocksblitz.com,https://admin.stocksblitz.com',
            'ENVIRONMENT': 'production'
        }):
            client = TestClient(cors_test_app)

            # Preflight OPTIONS request
            response = client.options(
                "/api/v2/signals/realtime",
                headers={
                    "Origin": "https://app.stocksblitz.com",
                    "Access-Control-Request-Method": "GET",
                    "Access-Control-Request-Headers": "Content-Type,Authorization"
                }
            )

            assert response.status_code == 200
            assert response.headers.get("Access-Control-Allow-Origin") == "https://app.stocksblitz.com"
            assert "GET" in response.headers.get("Access-Control-Allow-Methods", "")
            assert response.headers.get("Access-Control-Allow-Headers") is not None

    @pytest.mark.integration
    def test_cors_actual_request_batch_signals(self, cors_test_app, mock_config_service):
        """Test CORS on actual POST request to batch signals."""
        with patch.dict(os.environ, {
            'CORS_ALLOWED_ORIGINS': 'https://app.stocksblitz.com,https://admin.stocksblitz.com',
            'ENVIRONMENT': 'production'
        }):
            client = TestClient(cors_test_app)

            response = client.post(
                "/api/v2/signals/batch",
                json={"signals": [{"symbol": "AAPL", "type": "buy"}]},
                headers={
                    "Origin": "https://app.stocksblitz.com",
                    "Content-Type": "application/json"
                }
            )

            assert response.status_code == 200
            assert response.headers.get("Access-Control-Allow-Origin") == "https://app.stocksblitz.com"
            assert response.json()["status"] == "success"

    @pytest.mark.integration
    def test_cors_blocked_invalid_origin(self, cors_test_app, mock_config_service):
        """Test that invalid origins are properly blocked."""
        with patch.dict(os.environ, {
            'CORS_ALLOWED_ORIGINS': 'https://app.stocksblitz.com,https://admin.stocksblitz.com',
            'ENVIRONMENT': 'production'
        }):
            client = TestClient(cors_test_app)

            # Request from blocked origin
            response = client.options(
                "/api/v2/signals/realtime",
                headers={
                    "Origin": "https://malicious-site.com",
                    "Access-Control-Request-Method": "GET"
                }
            )

            # Should not include CORS headers for blocked origin
            assert response.headers.get("Access-Control-Allow-Origin") != "https://malicious-site.com"

    @pytest.mark.integration
    def test_cors_monitoring_endpoints(self, cors_test_app, mock_config_service):
        """Test CORS on monitoring and health endpoints."""
        with patch.dict(os.environ, {
            'CORS_ALLOWED_ORIGINS': 'https://app.stocksblitz.com,https://admin.stocksblitz.com',
            'ENVIRONMENT': 'production'
        }):
            client = TestClient(cors_test_app)

            # Test health endpoint
            response = client.get(
                "/health",
                headers={"Origin": "https://admin.stocksblitz.com"}
            )

            assert response.status_code == 200
            assert response.headers.get("Access-Control-Allow-Origin") == "https://admin.stocksblitz.com"

            # Test monitoring endpoint
            response = client.get(
                "/monitoring",
                headers={"Origin": "https://admin.stocksblitz.com"}
            )

            assert response.status_code == 200
            assert response.headers.get("Access-Control-Allow-Origin") == "https://admin.stocksblitz.com"

    @pytest.mark.integration
    def test_cors_credentials_handling(self, cors_test_app, mock_config_service):
        """Test CORS credentials handling for authenticated requests."""
        with patch.dict(os.environ, {
            'CORS_ALLOWED_ORIGINS': 'https://app.stocksblitz.com,https://admin.stocksblitz.com',
            'ENVIRONMENT': 'production'
        }):
            client = TestClient(cors_test_app)

            # Preflight with credentials
            response = client.options(
                "/api/v2/indicators",
                headers={
                    "Origin": "https://app.stocksblitz.com",
                    "Access-Control-Request-Method": "GET",
                    "Access-Control-Request-Headers": "Authorization,Content-Type"
                }
            )

            assert response.status_code == 200
            # Should allow credentials for authenticated endpoints
            assert response.headers.get("Access-Control-Allow-Credentials") == "true"

    @pytest.mark.integration
    def test_cors_complex_headers_validation(self, cors_test_app, mock_config_service):
        """Test CORS with complex request headers typical in signal service."""
        with patch.dict(os.environ, {
            'CORS_ALLOWED_ORIGINS': 'https://app.stocksblitz.com,https://admin.stocksblitz.com',
            'ENVIRONMENT': 'production'
        }):
            client = TestClient(cors_test_app)

            # Request with multiple custom headers
            response = client.options(
                "/api/v2/signals/realtime",
                headers={
                    "Origin": "https://app.stocksblitz.com",
                    "Access-Control-Request-Method": "GET",
                    "Access-Control-Request-Headers": "X-User-ID,X-Session-Token,X-Request-ID,Authorization,Content-Type"
                }
            )

            assert response.status_code == 200
            assert response.headers.get("Access-Control-Allow-Origin") == "https://app.stocksblitz.com"

            # Verify that complex headers are allowed
            allowed_headers = response.headers.get("Access-Control-Allow-Headers", "")
            expected_headers = ["X-User-ID", "X-Session-Token", "Authorization", "Content-Type"]

            for header in expected_headers:
                assert header.lower() in allowed_headers.lower()


class TestCORSProductionCompliance:
    """Test CORS configuration compliance with production security requirements."""

    @pytest.mark.integration
    def test_production_wildcard_rejection(self, mock_config_service):
        """Test that wildcard origins are rejected in production."""
        from common.cors_config import get_allowed_origins

        with patch.dict(os.environ, {
            'CORS_ALLOWED_ORIGINS': '*',
            'ENVIRONMENT': 'production'
        }), pytest.raises(ValueError, match="Wildcard origins not permitted in production"):
            get_allowed_origins("production")

    @pytest.mark.integration
    def test_production_subdomain_wildcard_rejection(self, mock_config_service):
        """Test that subdomain wildcards are rejected in production."""
        from common.cors_config import get_allowed_origins

        with patch.dict(os.environ, {
            'CORS_ALLOWED_ORIGINS': 'https://*.stocksblitz.com',
            'ENVIRONMENT': 'production'
        }), pytest.raises(ValueError, match="Wildcard origins not permitted in production"):
            get_allowed_origins("production")

    @pytest.mark.integration
    def test_production_explicit_origins_required(self, mock_config_service):
        """Test that production requires explicit CORS origins."""
        from common.cors_config import get_allowed_origins

        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="CORS_ALLOWED_ORIGINS must be configured for production"):
                get_allowed_origins("production")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
