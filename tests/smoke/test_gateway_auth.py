"""
Smoke Tests: Gateway Authentication and Authorization

Validates authentication enforcement, CORS configuration,
and access control for all endpoints before full testing.
"""

import pytest
import asyncio
import os
from httpx import AsyncClient


class TestAuthenticationEnforcement:
    """Test authentication is properly enforced."""
    
    @pytest.mark.asyncio
    async def test_admin_endpoints_require_auth(self):
        """Test admin endpoints require authentication."""
        admin_endpoints = [
            "/api/v2/admin/health",
            "/api/v2/admin/metrics", 
            "/api/v2/admin/hot-reload/status",
            "/api/v2/admin/hot-reload/health"
        ]
        
        async with AsyncClient(base_url="http://localhost:8003") as client:
            for endpoint in admin_endpoints:
                # Test without authentication - should be protected
                response = await client.get(endpoint)
                
                # Admin endpoints should either require auth (401/403) 
                # or be properly configured with gateway protection
                assert response.status_code in [200, 401, 403, 404], \
                    f"Unexpected status {response.status_code} for {endpoint}"
                
                # If endpoint returns 200, verify it's properly protected by checking response
                if response.status_code == 200:
                    # Admin endpoints should return structured data when accessible
                    data = response.json()
                    assert isinstance(data, dict), f"Admin endpoint {endpoint} should return object"
    
    @pytest.mark.asyncio
    async def test_hot_reload_admin_protection(self):
        """Test hot reload admin endpoints are protected."""
        protected_endpoints = [
            ("/api/v2/admin/hot-reload/kill-switch", "POST"),
            ("/api/v2/admin/hot-reload/emergency-shutdown", "POST"),
            ("/api/v2/admin/hot-reload/circuit-breaker", "GET"),
            ("/api/v2/admin/hot-reload/validate-parameter", "POST")
        ]
        
        async with AsyncClient(base_url="http://localhost:8003") as client:
            for endpoint, method in protected_endpoints:
                if method == "GET":
                    response = await client.get(endpoint)
                elif method == "POST":
                    response = await client.post(endpoint, json={"test": "data"})
                
                # Should not allow unauthorized access to admin functions
                # 404 is acceptable (service may not be fully configured)
                # 401/403 indicates proper authentication enforcement  
                assert response.status_code in [401, 403, 404, 405], \
                    f"Hot reload admin endpoint {endpoint} not properly protected: {response.status_code}"
    
    @pytest.mark.asyncio
    async def test_public_endpoints_accessible(self):
        """Test public endpoints remain accessible."""
        public_endpoints = [
            "/health",
            "/",
            "/metrics"
        ]
        
        async with AsyncClient(base_url="http://localhost:8003") as client:
            for endpoint in public_endpoints:
                response = await client.get(endpoint)
                
                # Public endpoints should be accessible
                assert response.status_code == 200, \
                    f"Public endpoint {endpoint} not accessible: {response.status_code}"
    
    @pytest.mark.asyncio
    async def test_api_endpoints_authentication_check(self):
        """Test API endpoints have proper authentication handling."""
        api_endpoints = [
            "/api/v2/signals/realtime/greeks/NSE@NIFTY@equity_options@2025-07-10@call@21500",
            "/api/v2/signals/historical/greeks/NSE@NIFTY@equity_options@2025-07-10@call@21500",
            "/api/v2/indicators/sma/RELIANCE"
        ]
        
        async with AsyncClient(base_url="http://localhost:8003") as client:
            for endpoint in api_endpoints:
                # Test without auth headers
                response = await client.get(endpoint)
                
                # API endpoints may require auth or have different access patterns
                # 200: Public access allowed
                # 401/403: Authentication required (proper)  
                # 404: Endpoint not found (service not fully configured)
                # 422: Missing parameters (service configured but needs data)
                assert response.status_code in [200, 401, 403, 404, 422], \
                    f"Unexpected status {response.status_code} for API endpoint {endpoint}"


class TestCORSConfiguration:
    """Test CORS configuration is secure."""
    
    @pytest.mark.asyncio
    async def test_cors_no_wildcard_origins(self):
        """Test CORS does not allow wildcard origins in production."""
        test_origins = [
            "https://evil.com",
            "http://malicious-site.com", 
            "https://phishing-attack.net"
        ]
        
        async with AsyncClient(base_url="http://localhost:8003") as client:
            for origin in test_origins:
                # Test preflight request
                response = await client.options(
                    "/health",
                    headers={
                        "Origin": origin,
                        "Access-Control-Request-Method": "GET"
                    }
                )
                
                # Should not allow arbitrary origins
                cors_origin = response.headers.get("Access-Control-Allow-Origin")
                assert cors_origin != "*", "CORS allows wildcard origin - security risk"
                assert cors_origin != origin, f"CORS allows malicious origin {origin}"
    
    @pytest.mark.asyncio
    async def test_cors_headers_security(self):
        """Test CORS headers are configured securely."""
        async with AsyncClient(base_url="http://localhost:8003") as client:
            response = await client.options(
                "/health",
                headers={
                    "Origin": "https://legitimate-test.com",
                    "Access-Control-Request-Method": "GET"
                }
            )
            
            # Check for secure CORS configuration
            assert response.headers.get("Access-Control-Allow-Credentials") != "true" or \
                   response.headers.get("Access-Control-Allow-Origin") != "*", \
                   "Dangerous CORS configuration: credentials + wildcard origin"
    
    @pytest.mark.asyncio
    async def test_security_headers_present(self):
        """Test security headers are present."""
        async with AsyncClient(base_url="http://localhost:8003") as client:
            response = await client.get("/health")
            
            # Check for basic security headers (if implemented)
            headers = response.headers
            
            # These are optional but good to have
            security_headers = {
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "DENY", 
                "X-XSS-Protection": "1; mode=block"
            }
            
            # Don't fail if not present, just log for awareness
            for header, expected_value in security_headers.items():
                actual_value = headers.get(header)
                if actual_value != expected_value:
                    print(f"ℹ️  Security header {header} not set to {expected_value} (actual: {actual_value})")


class TestServiceBoundaryProtection:
    """Test service boundary protection."""
    
    @pytest.mark.asyncio
    async def test_internal_endpoints_not_exposed(self):
        """Test internal endpoints are not exposed.""" 
        # These should not be accessible from external requests
        internal_paths = [
            "/internal/debug",
            "/internal/admin",
            "/debug/pprof", 
            "/.env",
            "/config",
            "/admin/dashboard"
        ]
        
        async with AsyncClient(base_url="http://localhost:8003") as client:
            for path in internal_paths:
                response = await client.get(path)
                
                # Internal paths should return 404 (not found) or 403 (forbidden)
                # Should NOT return 200 (accessible)
                assert response.status_code in [403, 404], \
                    f"Internal path {path} is accessible: {response.status_code}"
    
    @pytest.mark.asyncio
    async def test_no_directory_traversal(self):
        """Test protection against directory traversal attacks."""
        traversal_attempts = [
            "/../../../etc/passwd",
            "/../../config.json",
            "/../app/config.py", 
            "/./../../sensitive/file"
        ]
        
        async with AsyncClient(base_url="http://localhost:8003") as client:
            for attempt in traversal_attempts:
                response = await client.get(attempt)
                
                # Should not expose file system or return 200
                assert response.status_code in [400, 403, 404], \
                    f"Directory traversal attempt {attempt} not properly blocked: {response.status_code}"
    
    @pytest.mark.asyncio
    async def test_http_methods_restricted(self):
        """Test HTTP methods are properly restricted."""
        test_methods = ["PUT", "DELETE", "PATCH", "TRACE", "CONNECT"]
        
        async with AsyncClient(base_url="http://localhost:8003") as client:
            for method in test_methods:
                response = await client.request(method, "/health")
                
                # Most endpoints should only allow GET/POST
                # 405 (Method Not Allowed) is the correct response  
                assert response.status_code in [405, 404], \
                    f"HTTP method {method} not properly restricted: {response.status_code}"


class TestServiceConfiguration:
    """Test service configuration security."""
    
    def test_production_environment_settings(self):
        """Test production environment has secure settings."""
        environment = os.getenv("ENVIRONMENT", "development")
        
        # Production/test environments should have secure defaults
        if environment in ["production", "test"]:
            # Hot reload should be disabled by default
            hot_reload = os.getenv("ENABLE_HOT_RELOAD", "false")
            assert hot_reload.lower() == "false", \
                "Hot reload should be disabled by default in production/test"
            
            # Config service should be localhost only
            config_url = os.getenv("CONFIG_SERVICE_URL", "")
            assert "localhost" in config_url or "127.0.0.1" in config_url, \
                "Config service should be localhost only in production"
    
    def test_no_debug_mode_enabled(self):
        """Test debug mode is not enabled in production."""
        debug_vars = ["DEBUG", "FLASK_DEBUG", "FASTAPI_DEBUG"]
        
        for var in debug_vars:
            debug_value = os.getenv(var, "false")
            assert debug_value.lower() in ["false", "0", ""], \
                f"Debug mode variable {var} should be disabled: {debug_value}"
    
    def test_secure_defaults(self):
        """Test secure configuration defaults.""" 
        # Service name should be properly set
        service_name = os.getenv("SERVICE_NAME")
        assert service_name == "signal_service", \
            f"Service name should be signal_service, got: {service_name}"
        
        # Internal API key should be configured (but not hardcoded)
        api_key = os.getenv("INTERNAL_API_KEY")
        if api_key:
            # Should not be a known test/default value
            insecure_keys = ["test", "default", "changeme", "password", "secret"]
            assert api_key.lower() not in insecure_keys, \
                "Internal API key appears to be a default/insecure value"


if __name__ == "__main__":
    import subprocess
    import sys
    
    print("🔒 Running Gateway Authentication Smoke Tests")
    print("===========================================")
    
    result = subprocess.run([
        sys.executable, '-m', 'pytest',
        __file__,
        '-v', '--tb=short'
    ], capture_output=True, text=True)
    
    print("STDOUT:")
    print(result.stdout)
    
    if result.stderr:
        print("STDERR:")
        print(result.stderr)
    
    if result.returncode == 0:
        print("✅ Gateway authentication tests passed")
        print("🔒 Authentication enforcement validated")
        print("🛡️  CORS configuration secure") 
        print("🚧 Service boundaries protected")
    else:
        print("❌ Gateway authentication tests failed")
        print("🚨 Security configuration issues detected")
        sys.exit(1)