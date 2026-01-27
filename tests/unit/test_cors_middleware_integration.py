"""
CORS Middleware Integration Tests

Focused tests for CORS middleware setup, FastAPI integration, and runtime behavior.
Tests the actual middleware configuration and request/response handling.
"""
import os
from unittest.mock import Mock, patch

import pytest

# FastAPI imports with fallbacks
import importlib.util
if importlib.util.find_spec('starlette.responses'):
    FASTAPI_AVAILABLE = True
else:
    # Create mock classes if FastAPI not available
    FASTAPI_AVAILABLE = False

    class FastAPI:
        def __init__(self, *args, **kwargs):
            self.middleware_stack = []
            self.user_middleware = []
            self.routes = []

        def add_middleware(self, middleware_cls, **kwargs):
            self.middleware_stack.append({'cls': middleware_cls, 'kwargs': kwargs})
            self.user_middleware.append(Mock(cls=middleware_cls, kwargs=kwargs))
            return self

        def get(self, path):
            def decorator(func):
                self.routes.append({'method': 'GET', 'path': path, 'func': func})
                return func
            return decorator

    class CORSMiddleware:
        def __init__(self, app, **kwargs):
            self.app = app
            self.kwargs = kwargs

        async def __call__(self, scope, receive, send):
            return await self.app(scope, receive, send)

    class TestClient:
        def __init__(self, app):
            self.app = app

        def options(self, path, headers=None):
            return Mock(status_code=200, headers={})

        def get(self, path, headers=None):
            return Mock(status_code=200, headers={}, json=lambda: {"status": "ok"})

    class Request:
        def __init__(self, headers=None):
            self.headers = headers or {}

    class Response:
        def __init__(self, content="", headers=None):
            self.headers = headers or {}

# Import CORS configuration
from common.cors_config import add_cors_middleware


class TestCORSMiddlewareConfiguration:
    """Test CORS middleware configuration and setup."""

    def test_middleware_added_to_fastapi_app(self):
        """Test that CORS middleware is properly added to FastAPI app."""
        app = FastAPI()
        initial_middleware_count = len(app.middleware_stack)

        with patch.dict(os.environ, {"CORS_ALLOWED_ORIGINS": "https://app.stocksblitz.com"}, clear=True):
            add_cors_middleware(app, "production")

            # Should have added middleware
            assert len(app.middleware_stack) > initial_middleware_count

    def test_middleware_configuration_order(self):
        """Test that CORS middleware is configured in correct order."""
        app = FastAPI()

        # Add some existing middleware
        app.add_middleware(Mock, name="existing_middleware")
        existing_count = len(app.middleware_stack)

        with patch.dict(os.environ, {"CORS_ALLOWED_ORIGINS": "https://app.stocksblitz.com"}, clear=True):
            add_cors_middleware(app, "production")

            # Should have added CORS middleware
            assert len(app.middleware_stack) == existing_count + 1

    def test_middleware_origin_configuration(self):
        """Test CORS middleware origin configuration."""
        app = FastAPI()
        origins = "https://app.stocksblitz.com,https://dashboard.stocksblitz.com"

        with patch.dict(os.environ, {"CORS_ALLOWED_ORIGINS": origins}, clear=True), patch('common.cors_config.CORSMiddleware') as MockCORSMiddleware:
            add_cors_middleware(app, "production")

            # Verify CORSMiddleware was instantiated with correct origins
            MockCORSMiddleware.assert_called_once()
            call_kwargs = MockCORSMiddleware.call_args[1]

            expected_origins = ["https://app.stocksblitz.com", "https://dashboard.stocksblitz.com"]
            assert call_kwargs["allow_origins"] == expected_origins

    def test_middleware_credentials_configuration(self):
        """Test CORS middleware credentials configuration."""
        app = FastAPI()

        with patch.dict(os.environ, {"CORS_ALLOWED_ORIGINS": "https://app.stocksblitz.com"}, clear=True), patch('common.cors_config.CORSMiddleware') as MockCORSMiddleware:
            add_cors_middleware(app, "production")

            call_kwargs = MockCORSMiddleware.call_args[1]
            assert call_kwargs["allow_credentials"] is True

    def test_middleware_methods_configuration(self):
        """Test CORS middleware HTTP methods configuration."""
        app = FastAPI()

        with patch.dict(os.environ, {"CORS_ALLOWED_ORIGINS": "https://app.stocksblitz.com"}, clear=True), patch('common.cors_config.CORSMiddleware') as MockCORSMiddleware:
            add_cors_middleware(app, "production")

            call_kwargs = MockCORSMiddleware.call_args[1]
            expected_methods = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]

            for method in expected_methods:
                assert method in call_kwargs["allow_methods"]

    def test_middleware_headers_configuration(self):
        """Test CORS middleware headers configuration."""
        app = FastAPI()

        with patch.dict(os.environ, {"CORS_ALLOWED_ORIGINS": "https://app.stocksblitz.com"}, clear=True), patch('common.cors_config.CORSMiddleware') as MockCORSMiddleware:
            add_cors_middleware(app, "production")

            call_kwargs = MockCORSMiddleware.call_args[1]
            expected_headers = [
                "Authorization", "Content-Type", "X-User-ID",
                "X-Gateway-Secret", "X-API-Key", "X-Internal-API-Key", "Accept"
            ]

            for header in expected_headers:
                assert header in call_kwargs["allow_headers"]

    def test_middleware_exposed_headers_configuration(self):
        """Test CORS middleware exposed headers configuration."""
        app = FastAPI()

        with patch.dict(os.environ, {"CORS_ALLOWED_ORIGINS": "https://app.stocksblitz.com"}, clear=True), patch('common.cors_config.CORSMiddleware') as MockCORSMiddleware:
            add_cors_middleware(app, "production")

            call_kwargs = MockCORSMiddleware.call_args[1]
            expected_exposed = ["X-Total-Count", "X-Page-Count", "X-Rate-Limit-Remaining"]

            for header in expected_exposed:
                assert header in call_kwargs["expose_headers"]


class TestCORSMiddlewareRuntimeBehavior:
    """Test CORS middleware runtime behavior and request handling."""

    @pytest.fixture
    def cors_app(self):
        """Create FastAPI app with CORS middleware configured."""
        app = FastAPI()

        @app.get("/test")
        async def test_endpoint():
            return {"message": "test response"}

        @app.post("/api/signals")
        async def signals_endpoint():
            return {"status": "created"}

        with patch.dict(os.environ, {"CORS_ALLOWED_ORIGINS": "https://app.stocksblitz.com"}, clear=True):
            add_cors_middleware(app, "production")

        return app

    @pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not available")
    def test_cors_preflight_request_handling(self, cors_app):
        """Test CORS preflight request handling."""
        client = TestClient(cors_app)

        # Send preflight request
        response = client.options(
            "/test",
            headers={
                "Origin": "https://app.stocksblitz.com",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Content-Type"
            }
        )

        # Should handle preflight successfully
        assert response.status_code in [200, 204]

    @pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not available")
    def test_cors_actual_request_handling(self, cors_app):
        """Test CORS actual request handling."""
        client = TestClient(cors_app)

        # Send actual request with origin
        response = client.get(
            "/test",
            headers={"Origin": "https://app.stocksblitz.com"}
        )

        # Should handle request successfully
        assert response.status_code == 200

    def test_cors_middleware_environment_specific_behavior(self):
        """Test environment-specific CORS middleware behavior."""
        # Production app
        prod_app = FastAPI()
        with patch.dict(os.environ, {"CORS_ALLOWED_ORIGINS": "https://app.stocksblitz.com"}, clear=True), patch('common.cors_config.CORSMiddleware') as MockCORSMiddleware:
            add_cors_middleware(prod_app, "production")

            prod_kwargs = MockCORSMiddleware.call_args[1]
            prod_origins = prod_kwargs["allow_origins"]

        # Development app
        dev_app = FastAPI()
        with patch.dict(os.environ, {"CORS_ALLOWED_ORIGINS": "http://localhost:3000,https://app.stocksblitz.com"}, clear=True), patch('common.cors_config.CORSMiddleware') as MockCORSMiddleware:
            add_cors_middleware(dev_app, "development")

            dev_kwargs = MockCORSMiddleware.call_args[1]
            dev_origins = dev_kwargs["allow_origins"]

        # Development should allow localhost
        assert any("localhost" in origin for origin in dev_origins)

        # Production should not have localhost (in this test case)
        assert not any("localhost" in origin for origin in prod_origins)

    def test_cors_middleware_error_propagation(self):
        """Test CORS middleware error propagation."""
        app = FastAPI()

        # Test with invalid CORS configuration
        with patch.dict(os.environ, {}, clear=True), pytest.raises(ValueError, match="CORS configuration failed"):
            add_cors_middleware(app, "production")

    def test_cors_middleware_logging_behavior(self):
        """Test CORS middleware logging behavior."""
        app = FastAPI()

        with patch('common.cors_config.logger') as mock_logger, patch.dict(os.environ, {"CORS_ALLOWED_ORIGINS": "https://app.stocksblitz.com"}, clear=True):
            add_cors_middleware(app, "production")

            # Should log successful configuration
            mock_logger.info.assert_called_with(
                "CORS middleware configured for production with 1 allowed origins"
            )


class TestCORSMiddlewareSecurityBehavior:
    """Test security aspects of CORS middleware behavior."""

    def test_cors_origin_validation_behavior(self):
        """Test CORS origin validation in middleware."""
        app = FastAPI()
        allowed_origins = ["https://app.stocksblitz.com", "https://dashboard.stocksblitz.com"]

        with patch.dict(os.environ, {"CORS_ALLOWED_ORIGINS": ",".join(allowed_origins)}, clear=True), patch('common.cors_config.CORSMiddleware') as MockCORSMiddleware:
            add_cors_middleware(app, "production")

            # Verify only allowed origins are configured
            call_kwargs = MockCORSMiddleware.call_args[1]
            configured_origins = call_kwargs["allow_origins"]

            assert set(configured_origins) == set(allowed_origins)
            assert "*" not in configured_origins

    def test_cors_credentials_security_configuration(self):
        """Test CORS credentials security configuration."""
        app = FastAPI()

        with patch.dict(os.environ, {"CORS_ALLOWED_ORIGINS": "https://app.stocksblitz.com"}, clear=True), patch('common.cors_config.CORSMiddleware') as MockCORSMiddleware:
            add_cors_middleware(app, "production")

            call_kwargs = MockCORSMiddleware.call_args[1]

            # Credentials should be enabled for auth, but origins should be specific
            assert call_kwargs["allow_credentials"] is True
            assert call_kwargs["allow_origins"] != ["*"]  # No wildcard with credentials

    def test_cors_method_security_restrictions(self):
        """Test CORS method security restrictions."""
        app = FastAPI()

        with patch.dict(os.environ, {"CORS_ALLOWED_ORIGINS": "https://app.stocksblitz.com"}, clear=True), patch('common.cors_config.CORSMiddleware') as MockCORSMiddleware:
            add_cors_middleware(app, "production")

            call_kwargs = MockCORSMiddleware.call_args[1]
            allowed_methods = call_kwargs["allow_methods"]

            # Should not allow dangerous methods
            dangerous_methods = ["TRACE", "CONNECT", "PATCH"]
            for method in dangerous_methods:
                assert method not in allowed_methods

    def test_cors_header_security_restrictions(self):
        """Test CORS header security restrictions."""
        app = FastAPI()

        with patch.dict(os.environ, {"CORS_ALLOWED_ORIGINS": "https://app.stocksblitz.com"}, clear=True), patch('common.cors_config.CORSMiddleware') as MockCORSMiddleware:
            add_cors_middleware(app, "production")

            call_kwargs = MockCORSMiddleware.call_args[1]
            allowed_headers = call_kwargs["allow_headers"]

            # Should not allow all headers (wildcard)
            assert "*" not in allowed_headers

            # Should include necessary headers but be restrictive
            assert "Authorization" in allowed_headers
            assert "Content-Type" in allowed_headers
            assert "X-Gateway-Secret" in allowed_headers


class TestCORSMiddlewareIntegrationWithMainApp:
    """Test CORS middleware integration with the main Signal Service application."""

    def test_cors_integration_with_signal_service_app(self):
        """Test CORS integration with the main Signal Service application structure."""
        # Mock the main Signal Service app
        mock_signal_app = FastAPI()

        # Mock settings that would be used in main app
        mock_settings = Mock()
        mock_settings.environment = "production"

        with patch('app.core.config.settings', mock_settings), patch.dict(os.environ, {"CORS_ALLOWED_ORIGINS": "https://app.stocksblitz.com"}, clear=True):
            configured_app = add_cors_middleware(mock_signal_app, mock_settings.environment)

            assert configured_app is mock_signal_app
            assert len(mock_signal_app.middleware_stack) > 0

    def test_cors_configuration_with_api_routers(self):
        """Test CORS configuration works with API routers."""
        app = FastAPI()

        # Mock API router inclusion (like in main.py)
        mock_router = Mock()
        app.include_router = Mock()

        with patch.dict(os.environ, {"CORS_ALLOWED_ORIGINS": "https://app.stocksblitz.com"}, clear=True):
            # Configure CORS first
            add_cors_middleware(app, "production")

            # Then include routers (simulating main app structure)
            app.include_router(mock_router, prefix="/api/v2")

            # Should have both middleware and router
            assert len(app.middleware_stack) > 0
            app.include_router.assert_called_once()

    def test_cors_with_signal_service_endpoints(self):
        """Test CORS configuration with typical Signal Service endpoints."""
        app = FastAPI()

        # Add typical Signal Service endpoints
        @app.get("/health")
        async def health():
            return {"status": "healthy"}

        @app.get("/api/v2/signals/realtime")
        async def realtime_signals():
            return {"signals": []}

        @app.post("/api/v2/signals/batch")
        async def batch_signals():
            return {"batch_id": "123"}

        with patch.dict(os.environ, {"CORS_ALLOWED_ORIGINS": "https://app.stocksblitz.com"}, clear=True):
            configured_app = add_cors_middleware(app, "production")

            # Should configure CORS for all endpoints
            assert configured_app is app
            assert len(app.middleware_stack) > 0

    def test_cors_configuration_order_with_other_middleware(self):
        """Test CORS middleware order with other Signal Service middleware."""
        app = FastAPI()

        # Add other middleware (simulating Signal Service middleware stack)
        app.add_middleware(Mock, name="authentication_middleware")
        app.add_middleware(Mock, name="rate_limiting_middleware")

        middleware_before_cors = len(app.middleware_stack)

        with patch.dict(os.environ, {"CORS_ALLOWED_ORIGINS": "https://app.stocksblitz.com"}, clear=True):
            add_cors_middleware(app, "production")

            # CORS should be added to existing middleware stack
            assert len(app.middleware_stack) == middleware_before_cors + 1

    def test_cors_environment_detection_from_settings(self):
        """Test CORS environment detection from Signal Service settings."""
        app = FastAPI()

        # Mock Signal Service settings
        mock_settings = Mock()
        mock_settings.environment = "staging"

        with patch('app.core.config.settings', mock_settings), patch.dict(os.environ, {"CORS_ALLOWED_ORIGINS": "https://staging.stocksblitz.com"}, clear=True):
            configured_app = add_cors_middleware(app, mock_settings.environment)

            assert configured_app is app


class TestCORSMiddlewarePerformanceAndMonitoring:
    """Test CORS middleware performance and monitoring aspects."""

    def test_cors_middleware_performance_impact(self):
        """Test CORS middleware performance impact measurement."""
        app = FastAPI()

        # Measure middleware addition performance
        import time

        start_time = time.time()
        with patch.dict(os.environ, {"CORS_ALLOWED_ORIGINS": "https://app.stocksblitz.com"}, clear=True):
            add_cors_middleware(app, "production")
        end_time = time.time()

        # CORS configuration should be fast
        configuration_time = end_time - start_time
        assert configuration_time < 1.0  # Should complete in less than 1 second

    def test_cors_configuration_metrics(self):
        """Test CORS configuration metrics and monitoring."""
        app = FastAPI()

        # Track configuration metrics
        config_metrics = {
            "origins_count": 0,
            "methods_count": 0,
            "headers_count": 0,
            "configuration_time": 0
        }

        with patch.dict(os.environ, {"CORS_ALLOWED_ORIGINS": "https://app.stocksblitz.com,https://dashboard.stocksblitz.com"}, clear=True), patch('common.cors_config.CORSMiddleware') as MockCORSMiddleware:
            import time
            start_time = time.time()

            add_cors_middleware(app, "production")

            end_time = time.time()
            config_metrics["configuration_time"] = end_time - start_time

            # Extract configuration metrics
            call_kwargs = MockCORSMiddleware.call_args[1]
            config_metrics["origins_count"] = len(call_kwargs["allow_origins"])
            config_metrics["methods_count"] = len(call_kwargs["allow_methods"])
            config_metrics["headers_count"] = len(call_kwargs["allow_headers"])

        # Verify reasonable configuration metrics
        assert config_metrics["origins_count"] == 2
        assert config_metrics["methods_count"] >= 5  # At least GET, POST, PUT, DELETE, OPTIONS
        assert config_metrics["headers_count"] >= 7  # At least the required headers
        assert config_metrics["configuration_time"] < 1.0

    def test_cors_middleware_health_check_integration(self):
        """Test CORS middleware integration with health checks."""
        app = FastAPI()

        @app.get("/health")
        async def health():
            return {"cors_enabled": True, "status": "healthy"}

        with patch.dict(os.environ, {"CORS_ALLOWED_ORIGINS": "https://app.stocksblitz.com"}, clear=True):
            configured_app = add_cors_middleware(app, "production")

            if FASTAPI_AVAILABLE:
                client = TestClient(configured_app)
                response = client.get("/health")

                # Health endpoint should work with CORS
                assert response.status_code == 200
                data = response.json()
                assert data["cors_enabled"] is True


def run_cors_middleware_tests():
    """Run all CORS middleware integration tests."""
    print("🔍 Running CORS Middleware Integration Tests...")

    test_classes = [
        TestCORSMiddlewareConfiguration,
        TestCORSMiddlewareRuntimeBehavior,
        TestCORSMiddlewareSecurityBehavior,
        TestCORSMiddlewareIntegrationWithMainApp,
        TestCORSMiddlewarePerformanceAndMonitoring
    ]

    total_tests = 0
    passed_tests = 0

    for test_class in test_classes:
        class_name = test_class.__name__
        print(f"\n📋 Testing {class_name}...")

        # Get test methods
        test_methods = [method for method in dir(test_class) if method.startswith('test_')]
        total_tests += len(test_methods)

        try:
            # Handle test class with fixtures
            test_instance = test_class()

            for test_method in test_methods:
                try:
                    method = getattr(test_instance, test_method)

                    # Handle pytest fixtures
                    if hasattr(method, '__code__') and 'cors_app' in method.__code__.co_varnames:
                        # Create mock cors_app fixture
                        mock_cors_app = FastAPI()
                        method(mock_cors_app)
                    else:
                        method()

                    passed_tests += 1
                    print(f"  ✅ {test_method}")
                except Exception as e:
                    print(f"  ❌ {test_method}: {e}")
        except Exception as e:
            print(f"  ❌ Failed to initialize {class_name}: {e}")

    print(f"\n📊 Test Results: {passed_tests}/{total_tests} tests passed")

    if passed_tests == total_tests:
        print("\n✅ All CORS middleware tests passed!")
        print("\n🔧 CORS Middleware Coverage:")
        print("  - FastAPI application integration")
        print("  - Middleware configuration parameters")
        print("  - Runtime request/response handling")
        print("  - Security behavior and restrictions")
        print("  - Signal Service application integration")
        print("  - Performance and monitoring aspects")
    else:
        print(f"\n⚠️  {total_tests - passed_tests} CORS middleware tests need attention")

    return passed_tests == total_tests


if __name__ == "__main__":
    success = run_cors_middleware_tests()
    exit(0 if success else 1)
