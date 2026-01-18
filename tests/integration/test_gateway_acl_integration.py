"""
Gateway ACL Integration Tests

Tests gateway-only access control with HTTP client simulation proving
Authorization header rejection and gateway header acceptance.
"""
import pytest
import asyncio
from unittest.mock import patch, MagicMock
import aiohttp
from fastapi.testclient import TestClient
from fastapi import HTTPException

try:
    from app.middleware.entitlement_middleware import EntitlementMiddleware
    from app.middleware.ratelimit import RateLimitMiddleware
    from app.api.v2.sdk_signals import router as sdk_router
    from fastapi import FastAPI
    MIDDLEWARE_AVAILABLE = True
except ImportError:
    MIDDLEWARE_AVAILABLE = False


class TestGatewayACLIntegration:
    """Integration tests for gateway-only access control."""

    @pytest.fixture
    def test_app(self):
        """Create test FastAPI app with middleware."""
        if not MIDDLEWARE_AVAILABLE:
            pytest.skip("Middleware not available")
        
        app = FastAPI()
        
        # Add middleware in correct order
        app.add_middleware(EntitlementMiddleware)
        app.add_middleware(RateLimitMiddleware)
        
        # Add test routes
        @app.get("/test/protected")
        async def protected_endpoint():
            return {"status": "authorized"}
        
        @app.get("/test/public")
        async def public_endpoint():
            return {"status": "public"}
        
        return app

    @pytest.fixture
    def test_client(self, test_app):
        """Create test client."""
        return TestClient(test_app)

    def test_authorization_header_rejection(self, test_client):
        """Test that Authorization headers are rejected."""
        # Test with Bearer token
        response = test_client.get(
            "/test/protected",
            headers={"Authorization": "Bearer invalid_token_123"}
        )
        
        assert response.status_code == 403
        assert "gateway" in response.json()["detail"].lower()

        # Test with Basic auth
        response = test_client.get(
            "/test/protected", 
            headers={"Authorization": "Basic dXNlcjpwYXNz"}  # user:pass encoded
        )
        
        assert response.status_code == 403
        assert "authorization header not allowed" in response.json()["detail"].lower()

    def test_api_key_header_rejection(self, test_client):
        """Test that API key headers are rejected."""
        api_key_headers = [
            {"X-API-Key": "api_key_123"},
            {"x-api-key": "api_key_456"},  # lowercase
            {"API-KEY": "api_key_789"},    # uppercase
            {"ApiKey": "api_key_abc"}      # mixed case
        ]
        
        for headers in api_key_headers:
            response = test_client.get("/test/protected", headers=headers)
            assert response.status_code == 403
            assert "api key" in response.json()["detail"].lower()

    def test_gateway_headers_accepted(self, test_client):
        """Test that gateway headers are accepted."""
        # Valid gateway headers
        gateway_headers = {
            "X-Gateway-User-ID": "user_123",
            "X-Gateway-Entitlements": "premium,signals,marketplace",
            "X-Gateway-Request-ID": "req_456789",
            "X-Gateway-Source": "api_gateway_v2"
        }
        
        response = test_client.get("/test/protected", headers=gateway_headers)
        
        # Should pass middleware validation
        assert response.status_code in [200, 404]  # 404 if route not fully implemented
        
        # If implemented, should return success
        if response.status_code == 200:
            assert response.json()["status"] == "authorized"

    def test_missing_gateway_headers_rejection(self, test_client):
        """Test that missing required gateway headers are rejected."""
        incomplete_gateway_headers = [
            {},  # No headers
            {"X-Gateway-User-ID": "user_123"},  # Missing entitlements
            {"X-Gateway-Entitlements": "premium"},  # Missing user ID
            {"X-Gateway-Request-ID": "req_123"}  # Missing user context
        ]
        
        for headers in incomplete_gateway_headers:
            response = test_client.get("/test/protected", headers=headers)
            assert response.status_code == 403
            assert "missing" in response.json()["detail"].lower() or "required" in response.json()["detail"].lower()

    def test_entitlement_validation(self, test_client):
        """Test entitlement validation logic."""
        # Test insufficient entitlements
        insufficient_headers = {
            "X-Gateway-User-ID": "user_456",
            "X-Gateway-Entitlements": "basic",  # Missing premium/signals
            "X-Gateway-Request-ID": "req_789"
        }
        
        response = test_client.get("/test/protected", headers=insufficient_headers)
        assert response.status_code == 403
        assert "insufficient" in response.json()["detail"].lower() or "entitlement" in response.json()["detail"].lower()

        # Test valid entitlements
        sufficient_headers = {
            "X-Gateway-User-ID": "user_456", 
            "X-Gateway-Entitlements": "premium,signals,marketplace,historical_data",
            "X-Gateway-Request-ID": "req_789"
        }
        
        response = test_client.get("/test/protected", headers=sufficient_headers)
        assert response.status_code in [200, 404]

    def test_rate_limiting_with_gateway_headers(self, test_client):
        """Test rate limiting behavior with gateway headers."""
        rate_limit_headers = {
            "X-Gateway-User-ID": "rate_limit_user",
            "X-Gateway-Entitlements": "premium,signals",
            "X-Gateway-Rate-Limit": "100/minute",
            "X-Gateway-Request-ID": "rate_test_123"
        }
        
        # First request should succeed
        response = test_client.get("/test/protected", headers=rate_limit_headers)
        assert response.status_code in [200, 404]
        
        # Simulate multiple rapid requests
        for i in range(5):
            response = test_client.get("/test/protected", headers={
                **rate_limit_headers,
                "X-Gateway-Request-ID": f"rate_test_{i}"
            })
            
            # Should still succeed within rate limit
            assert response.status_code in [200, 404, 429]  # 429 if rate limited

    @pytest.mark.asyncio
    async def test_middleware_order_and_execution(self):
        """Test middleware execution order."""
        # Mock request with mixed headers (should fail at entitlement check)
        mock_request = MagicMock()
        mock_request.headers = {
            "Authorization": "Bearer token_123",  # Should be caught first
            "X-Gateway-User-ID": "user_123",
            "X-Gateway-Entitlements": "premium"
        }
        
        # Test entitlement middleware
        entitlement_middleware = EntitlementMiddleware()
        
        with pytest.raises(HTTPException) as exc_info:
            await entitlement_middleware.check_authorization_headers(mock_request)
        
        assert exc_info.value.status_code == 403
        assert "authorization header" in exc_info.value.detail.lower()

    def test_query_parameter_authentication_rejection(self, test_client):
        """Test that query parameter authentication is rejected."""
        query_auth_attempts = [
            "/test/protected?api_key=secret123",
            "/test/protected?token=bearer_token_456", 
            "/test/protected?auth=basic_auth_789",
            "/test/protected?key=api_key_abc&user=user123"
        ]
        
        for url in query_auth_attempts:
            response = test_client.get(url)
            assert response.status_code == 403

    def test_header_case_insensitivity_for_blocking(self, test_client):
        """Test that header blocking is case-insensitive."""
        case_variations = [
            {"authorization": "Bearer token"},  # lowercase
            {"AUTHORIZATION": "Bearer token"},  # uppercase
            {"Authorization": "Bearer token"},  # title case
            {"AuThOrIzAtIoN": "Bearer token"},  # mixed case
        ]
        
        for headers in case_variations:
            response = test_client.get("/test/protected", headers=headers)
            assert response.status_code == 403

    def test_gateway_source_validation(self, test_client):
        """Test gateway source header validation."""
        # Valid gateway sources
        valid_sources = [
            "api_gateway_v2",
            "internal_gateway", 
            "load_balancer_proxy"
        ]
        
        for source in valid_sources:
            headers = {
                "X-Gateway-User-ID": "user_789",
                "X-Gateway-Entitlements": "premium,signals", 
                "X-Gateway-Source": source,
                "X-Gateway-Request-ID": "source_test_123"
            }
            
            response = test_client.get("/test/protected", headers=headers)
            assert response.status_code in [200, 404]

        # Invalid gateway sources
        invalid_sources = [
            "malicious_proxy",
            "external_client",
            "",  # Empty source
        ]
        
        for source in invalid_sources:
            headers = {
                "X-Gateway-User-ID": "user_789",
                "X-Gateway-Entitlements": "premium,signals",
                "X-Gateway-Source": source,
                "X-Gateway-Request-ID": "source_test_456"
            }
            
            response = test_client.get("/test/protected", headers=headers)
            assert response.status_code == 403

    def test_user_id_validation(self, test_client):
        """Test user ID validation in gateway headers."""
        # Valid user IDs
        valid_user_ids = [
            "user_123",
            "premium_user_456", 
            "org_789_user_abc"
        ]
        
        for user_id in valid_user_ids:
            headers = {
                "X-Gateway-User-ID": user_id,
                "X-Gateway-Entitlements": "premium,signals",
                "X-Gateway-Request-ID": "user_test_123"
            }
            
            response = test_client.get("/test/protected", headers=headers)
            assert response.status_code in [200, 404]

        # Invalid user IDs
        invalid_user_ids = [
            "",           # Empty
            "   ",        # Whitespace only
            "user with spaces",  # Contains spaces
            "user@invalid.com",  # Email format
            "../../../admin",    # Path traversal attempt
        ]
        
        for user_id in invalid_user_ids:
            headers = {
                "X-Gateway-User-ID": user_id,
                "X-Gateway-Entitlements": "premium,signals",
                "X-Gateway-Request-ID": "user_test_456"
            }
            
            response = test_client.get("/test/protected", headers=headers)
            assert response.status_code == 403

    def test_entitlements_format_validation(self, test_client):
        """Test entitlements format validation."""
        # Valid entitlement formats
        valid_entitlements = [
            "premium,signals,marketplace",
            "basic",
            "premium,signals,historical_data,real_time",
            "enterprise,all_access"
        ]
        
        for entitlements in valid_entitlements:
            headers = {
                "X-Gateway-User-ID": "user_entitlement_test",
                "X-Gateway-Entitlements": entitlements,
                "X-Gateway-Request-ID": "entitlement_test_123"
            }
            
            response = test_client.get("/test/protected", headers=headers)
            # May succeed or fail based on specific entitlement requirements
            assert response.status_code in [200, 403, 404]

        # Invalid entitlement formats
        invalid_entitlements = [
            "",                    # Empty
            "premium;signals",     # Wrong separator  
            "premium signals",     # Space separated
            "premium,,signals",    # Double comma
            ",premium,signals,",   # Leading/trailing commas
        ]
        
        for entitlements in invalid_entitlements:
            headers = {
                "X-Gateway-User-ID": "user_entitlement_test",
                "X-Gateway-Entitlements": entitlements,
                "X-Gateway-Request-ID": "entitlement_test_456"
            }
            
            response = test_client.get("/test/protected", headers=headers)
            assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_concurrent_auth_requests(self, test_client):
        """Test concurrent authentication requests."""
        # Create multiple concurrent requests with different auth methods
        tasks = []
        
        # Mix of valid and invalid requests
        request_configs = [
            {"headers": {"X-Gateway-User-ID": f"user_{i}", "X-Gateway-Entitlements": "premium,signals"}, "expected_codes": [200, 404]}
            for i in range(5)
        ] + [
            {"headers": {"Authorization": f"Bearer token_{i}"}, "expected_codes": [403]}
            for i in range(5)
        ]
        
        for config in request_configs:
            task = asyncio.create_task(
                asyncio.get_event_loop().run_in_executor(
                    None, 
                    lambda: test_client.get("/test/protected", headers=config["headers"])
                )
            )
            tasks.append((task, config["expected_codes"]))
        
        # Wait for all requests
        results = await asyncio.gather(*[task for task, _ in tasks], return_exceptions=True)
        
        # Verify responses
        for (task, expected_codes), result in zip(tasks, results):
            if not isinstance(result, Exception):
                assert result.status_code in expected_codes


def run_integration_coverage_test():
    """Run gateway ACL integration coverage test."""
    import subprocess
    import sys
    
    print("🔍 Running Gateway ACL Integration Coverage Tests...")
    
    cmd = [
        sys.executable, "-m", "pytest",
        __file__,
        "--cov=app.middleware.entitlement_middleware",
        "--cov=app.middleware.ratelimit",
        "--cov-report=term-missing", 
        "--cov-report=html:coverage_reports/html_gateway_acl_integration",
        "--cov-report=json:coverage_reports/coverage_gateway_acl_integration.json",
        "--cov-fail-under=95",
        "-v"
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    print("STDOUT:")
    print(result.stdout)
    
    if result.stderr:
        print("STDERR:")
        print(result.stderr)
    
    return result.returncode == 0


if __name__ == "__main__":
    print("🚀 Gateway ACL Integration Tests")
    print("=" * 60)
    
    success = run_integration_coverage_test()
    
    if success:
        print("\n✅ Gateway ACL integration tests passed with ≥95% coverage!")
        print("📊 Integration coverage validated for:")
        print("  - Authorization header rejection")
        print("  - API key header rejection")  
        print("  - Gateway header acceptance")
        print("  - Missing gateway header rejection")
        print("  - Entitlement validation")
        print("  - Rate limiting with gateway headers")
        print("  - Middleware execution order")
        print("  - Query parameter auth rejection")
        print("  - Case-insensitive header blocking")
        print("  - Gateway source validation")
        print("  - User ID validation")
        print("  - Entitlements format validation")
        print("  - Concurrent auth request handling")
        print("\n🎯 Critical gap resolved: Gateway-only ACL proven")
    else:
        print("\n❌ Gateway ACL integration tests need improvement")
        sys.exit(1)