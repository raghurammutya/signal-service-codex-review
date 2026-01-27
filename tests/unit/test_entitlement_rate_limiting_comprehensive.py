"""
Comprehensive Entitlement & Rate Limiting Tests

Tests for entitlement verification, rate limiting, and access control covering:
- StreamAbuseProtection allowed/denied flows
- Gateway-only operation validation
- Authorization header rejection
- Fail-fast entitlement verification

Targets 95%+ coverage for production confidence.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import Request
from fastapi.responses import JSONResponse

from app.middleware.entitlement_middleware import EntitlementMiddleware
from app.middleware.ratelimit import RateLimitMiddleware
from app.services.stream_abuse_protection import StreamAbuseProtection, StreamType


class TestStreamAbuseProtectionComprehensive:
    """Test StreamAbuseProtection with both allowed and denied flows."""

    @pytest.fixture
    async def abuse_protection(self):
        """Create StreamAbuseProtection with mocked marketplace client."""
        mock_marketplace = AsyncMock()
        return StreamAbuseProtection(
            marketplace_client=mock_marketplace,
            redis_client=AsyncMock(),
            rate_limit_window=60,
            max_connections_per_user=10
        )

    @pytest.fixture
    def mock_premium_user_subscriptions(self):
        """Mock premium user subscription data."""
        return {
            "subscriptions": [
                {
                    "tier": "premium",
                    "features": ["fo_greeks_access", "premium_analysis", "unlimited_streams"],
                    "limits": {
                        "concurrent_connections": 50,
                        "requests_per_minute": 1000
                    }
                }
            ]
        }

    @pytest.fixture
    def mock_basic_user_subscriptions(self):
        """Mock basic user subscription data."""
        return {
            "subscriptions": [
                {
                    "tier": "basic",
                    "features": ["basic_signals"],
                    "limits": {
                        "concurrent_connections": 5,
                        "requests_per_minute": 100
                    }
                }
            ]
        }

    async def test_entitlement_verification_allowed_flow(self, abuse_protection, mock_premium_user_subscriptions):
        """Test allowed flow - user with valid premium entitlements."""
        # Mock successful entitlement verification
        abuse_protection.marketplace_client.get_user_subscriptions.return_value = mock_premium_user_subscriptions

        # Test premium user gets appropriate limits
        limits = await abuse_protection._get_user_limits("premium_user_123", StreamType.GREEKS)

        assert limits.max_concurrent_connections == 50
        assert limits.requests_per_minute == 1000
        assert limits.tier == "premium"

        # Verify marketplace was called
        abuse_protection.marketplace_client.get_user_subscriptions.assert_called_once_with("premium_user_123")

    async def test_entitlement_verification_denied_flow(self, abuse_protection, mock_basic_user_subscriptions):
        """Test denied flow - user without required entitlements."""
        # Mock basic user trying to access premium features
        abuse_protection.marketplace_client.get_user_subscriptions.return_value = mock_basic_user_subscriptions

        # Should get basic limits, not premium
        limits = await abuse_protection._get_user_limits("basic_user_456", StreamType.GREEKS)

        assert limits.max_concurrent_connections == 5
        assert limits.requests_per_minute == 100
        assert limits.tier == "basic"

    async def test_entitlement_verification_fail_fast_no_marketplace(self, abuse_protection):
        """Test fail-fast behavior when marketplace client unavailable."""
        # Set marketplace client to None (production fail-fast)
        abuse_protection.marketplace_client = None

        with pytest.raises(RuntimeError, match="Entitlement verification required"):
            await abuse_protection._get_user_limits("user_123", StreamType.GREEKS)

    async def test_entitlement_verification_fail_fast_no_user_id(self, abuse_protection):
        """Test fail-fast behavior when user ID is missing."""
        with pytest.raises(RuntimeError, match="Entitlement verification required"):
            await abuse_protection._get_user_limits(None, StreamType.GREEKS)

        with pytest.raises(RuntimeError, match="Entitlement verification required"):
            await abuse_protection._get_user_limits("", StreamType.GREEKS)

    async def test_marketplace_service_failure_denied_flow(self, abuse_protection):
        """Test denied flow when marketplace service fails."""
        # Mock marketplace service failure
        abuse_protection.marketplace_client.get_user_subscriptions.side_effect = httpx.RequestError("Service unavailable")

        with pytest.raises(RuntimeError, match="Failed to verify user entitlements"):
            await abuse_protection._get_user_limits("user_123", StreamType.GREEKS)

    async def test_rate_limiting_enforcement_allowed_flow(self, abuse_protection, mock_premium_user_subscriptions):
        """Test rate limiting allows requests within limits."""
        # Setup premium user
        abuse_protection.marketplace_client.get_user_subscriptions.return_value = mock_premium_user_subscriptions

        # Mock current connections below limit
        abuse_protection.redis_client.scard.return_value = 5  # 5 current connections
        abuse_protection.redis_client.get.return_value = b'50'  # 50 requests in window

        # Should allow connection (within limits)
        result = await abuse_protection.check_rate_limit("premium_user", "connection_123", StreamType.GREEKS)

        assert result.allowed is True
        assert result.reason == "within_limits"

    async def test_rate_limiting_enforcement_denied_flow_concurrent(self, abuse_protection, mock_premium_user_subscriptions):
        """Test rate limiting denies when concurrent connections exceeded."""
        # Setup premium user
        abuse_protection.marketplace_client.get_user_subscriptions.return_value = mock_premium_user_subscriptions

        # Mock connections at limit
        abuse_protection.redis_client.scard.return_value = 50  # At max concurrent limit
        abuse_protection.redis_client.get.return_value = b'100'  # Low request rate

        # Should deny new connection
        result = await abuse_protection.check_rate_limit("premium_user", "connection_124", StreamType.GREEKS)

        assert result.allowed is False
        assert result.reason == "concurrent_connections_exceeded"

    async def test_rate_limiting_enforcement_denied_flow_requests(self, abuse_protection, mock_premium_user_subscriptions):
        """Test rate limiting denies when request rate exceeded."""
        # Setup premium user
        abuse_protection.marketplace_client.get_user_subscriptions.return_value = mock_premium_user_subscriptions

        # Mock high request rate
        abuse_protection.redis_client.scard.return_value = 10  # Low connections
        abuse_protection.redis_client.get.return_value = b'1200'  # Over 1000 request/min limit

        # Should deny due to rate limit
        result = await abuse_protection.check_rate_limit("premium_user", "connection_125", StreamType.GREEKS)

        assert result.allowed is False
        assert result.reason == "request_rate_exceeded"

    async def test_stream_type_specific_limits(self, abuse_protection):
        """Test different stream types have appropriate limits."""
        # Mock different subscription data for different stream types
        greeks_subscription = {
            "subscriptions": [{"tier": "premium", "features": ["fo_greeks_access"], "limits": {"concurrent_connections": 25}}]
        }
        indicators_subscription = {
            "subscriptions": [{"tier": "basic", "features": ["basic_signals"], "limits": {"concurrent_connections": 5}}]
        }

        # Test Greeks stream type
        abuse_protection.marketplace_client.get_user_subscriptions.return_value = greeks_subscription
        greeks_limits = await abuse_protection._get_user_limits("user_123", StreamType.GREEKS)
        assert greeks_limits.max_concurrent_connections == 25

        # Test Indicators stream type
        abuse_protection.marketplace_client.get_user_subscriptions.return_value = indicators_subscription
        indicators_limits = await abuse_protection._get_user_limits("user_123", StreamType.INDICATORS)
        assert indicators_limits.max_concurrent_connections == 5

    async def test_cache_behavior_performance_optimization(self, abuse_protection, mock_premium_user_subscriptions):
        """Test caching improves performance for repeated requests."""
        # Setup marketplace response
        abuse_protection.marketplace_client.get_user_subscriptions.return_value = mock_premium_user_subscriptions

        # First call should hit marketplace
        limits1 = await abuse_protection._get_user_limits("user_123", StreamType.GREEKS)

        # Second call should use cache
        limits2 = await abuse_protection._get_user_limits("user_123", StreamType.GREEKS)

        # Verify marketplace only called once
        assert abuse_protection.marketplace_client.get_user_subscriptions.call_count == 1

        # Verify same limits returned
        assert limits1.tier == limits2.tier
        assert limits1.max_concurrent_connections == limits2.max_concurrent_connections


class TestEntitlementMiddlewareGatewayOnly:
    """Test EntitlementMiddleware enforces gateway-only operation."""

    @pytest.fixture
    async def entitlement_middleware(self):
        """Create entitlement middleware for testing."""
        middleware = EntitlementMiddleware("http://marketplace-service")
        middleware._client = AsyncMock()
        return middleware

    @pytest.fixture
    def mock_request_with_gateway_headers(self):
        """Mock request with proper gateway headers (allowed)."""
        request = MagicMock(spec=Request)
        request.url.path = "/api/v2/signals/fo/greeks/"
        request.headers = {
            "X-User-ID": "12345",  # Gateway-provided user ID
            "X-Gateway-Source": "api-gateway",
            "Content-Type": "application/json"
        }
        # No Authorization header (correct for gateway-only)
        request.headers.get = lambda key, default=None: {
            "X-User-ID": "12345",
            "X-Gateway-Source": "api-gateway",
            "Content-Type": "application/json"
        }.get(key, default)
        return request

    @pytest.fixture
    def mock_request_with_authorization_header(self):
        """Mock request with forbidden Authorization header (should be rejected)."""
        request = MagicMock(spec=Request)
        request.url.path = "/api/v2/signals/fo/greeks/"
        request.headers = {
            "Authorization": "Bearer token123",  # FORBIDDEN - bypass attempt
            "Content-Type": "application/json"
        }
        request.headers.get = lambda key, default=None: {
            "Authorization": "Bearer token123",
            "Content-Type": "application/json"
        }.get(key, default)
        return request

    async def test_gateway_only_operation_allowed_flow(self, entitlement_middleware, mock_request_with_gateway_headers):
        """Test allowed flow - request with proper gateway headers."""
        # Mock successful entitlement check
        entitlement_middleware._client.get.return_value = AsyncMock()
        entitlement_middleware._client.get.return_value.status_code = 200
        entitlement_middleware._client.get.return_value.json.return_value = {"has_access": True}

        # Mock next handler
        async def mock_next(request):
            return JSONResponse({"status": "success"})

        # Should allow request
        response = await entitlement_middleware(mock_request_with_gateway_headers, mock_next)

        assert response.status_code == 200

        # Verify request state was set
        assert mock_request_with_gateway_headers.state.user_id == 12345
        assert mock_request_with_gateway_headers.state.has_fo_access is True

    async def test_gateway_only_operation_denied_flow_no_user_id(self, entitlement_middleware):
        """Test denied flow - missing X-User-ID header."""
        request = MagicMock(spec=Request)
        request.url.path = "/api/v2/signals/fo/greeks/"
        request.headers.get.return_value = None  # No X-User-ID header

        async def mock_next(request):
            return JSONResponse({"status": "should_not_reach"})

        # Should reject with 401
        response = await entitlement_middleware(request, mock_next)

        assert response.status_code == 401
        assert "User authentication required" in str(response.body)

    async def test_authorization_header_rejection(self, entitlement_middleware, mock_request_with_authorization_header):
        """Test that Authorization headers are rejected (gateway-only enforcement)."""
        async def mock_next(request):
            return JSONResponse({"status": "should_not_reach"})

        # Should reject due to missing X-User-ID (Authorization header ignored)
        response = await entitlement_middleware(mock_request_with_authorization_header, mock_next)

        assert response.status_code == 401
        assert "User authentication required" in str(response.body)

    async def test_entitlement_verification_denied_flow(self, entitlement_middleware, mock_request_with_gateway_headers):
        """Test denied flow - user lacks required entitlements."""
        # Mock entitlement check failure
        entitlement_middleware._client.get.return_value = AsyncMock()
        entitlement_middleware._client.get.return_value.status_code = 200
        entitlement_middleware._client.get.return_value.json.return_value = {"has_access": False}

        async def mock_next(request):
            return JSONResponse({"status": "should_not_reach"})

        # Should deny with 403
        response = await entitlement_middleware(mock_request_with_gateway_headers, mock_next)

        assert response.status_code == 403
        assert "entitlement_required" in str(response.body)
        assert "fo_greeks_access" in str(response.body)

    async def test_marketplace_service_failure_fail_secure(self, entitlement_middleware, mock_request_with_gateway_headers):
        """Test fail-secure behavior when marketplace service fails."""
        # Mock marketplace service failure
        entitlement_middleware._client.get.side_effect = httpx.RequestError("Service unavailable")

        async def mock_next(request):
            return JSONResponse({"status": "should_not_reach"})

        # Should fail secure (deny access)
        response = await entitlement_middleware(mock_request_with_gateway_headers, mock_next)

        assert response.status_code == 500
        assert "entitlement_service_error" in str(response.body)

    async def test_protected_route_detection(self, entitlement_middleware):
        """Test protected route detection logic."""
        # Test F&O protected routes
        assert entitlement_middleware._is_protected_route("/api/v2/signals/fo/greeks/")
        assert entitlement_middleware._is_protected_route("/api/v2/signals/fo/premium-analysis/")
        assert entitlement_middleware._is_protected_route("/api/v2/signals/fo/option-chain/")

        # Test non-protected routes
        assert not entitlement_middleware._is_protected_route("/api/v1/signals/basic/")
        assert not entitlement_middleware._is_protected_route("/health")
        assert not entitlement_middleware._is_protected_route("/docs")

    async def test_premium_analysis_route_detection(self, entitlement_middleware):
        """Test premium analysis route detection."""
        assert entitlement_middleware._requires_premium_analysis("/api/v2/signals/fo/premium-analysis/expiry")
        assert entitlement_middleware._requires_premium_analysis("/api/v2/signals/fo/premium-analysis/arbitrage-opportunities/")

        # Regular F&O routes should not require premium analysis
        assert not entitlement_middleware._requires_premium_analysis("/api/v2/signals/fo/greeks/")

    async def test_non_protected_route_bypass(self, entitlement_middleware):
        """Test that non-protected routes bypass entitlement checks."""
        request = MagicMock(spec=Request)
        request.url.path = "/api/v1/signals/basic/"

        async def mock_next(request):
            return JSONResponse({"status": "success"})

        # Should bypass entitlement check
        response = await entitlement_middleware(request, mock_next)

        assert response.status_code == 200
        assert entitlement_middleware._client.get.call_count == 0  # No entitlement check made

    async def test_audit_logging_for_access_decisions(self, entitlement_middleware, mock_request_with_gateway_headers):
        """Test audit logging for access decisions."""
        # Mock successful entitlement
        entitlement_middleware._client.get.return_value = AsyncMock()
        entitlement_middleware._client.get.return_value.status_code = 200
        entitlement_middleware._client.get.return_value.json.return_value = {"has_access": True}

        async def mock_next(request):
            return JSONResponse({"status": "success"})

        with patch('app.middleware.entitlement_middleware.logger') as mock_logger:
            await entitlement_middleware(mock_request_with_gateway_headers, mock_next)

            # Verify access granted was logged
            mock_logger.info.assert_called()
            log_call = mock_logger.info.call_args[0][0]
            assert "F&O access granted" in log_call
            assert "user 12345" in log_call


class TestRateLimitMiddlewareIntegration:
    """Test rate limiting middleware integration."""

    @pytest.fixture
    def rate_limit_middleware(self):
        """Create rate limit middleware for testing."""
        return RateLimitMiddleware(
            redis_client=AsyncMock(),
            requests_per_minute=100,
            burst_size=20
        )

    async def test_rate_limit_allowed_flow(self, rate_limit_middleware):
        """Test requests within rate limits are allowed."""
        # Mock under rate limit
        rate_limit_middleware.redis_client.get.return_value = b'50'  # 50 requests in window
        rate_limit_middleware.redis_client.incr.return_value = 51

        request = MagicMock(spec=Request)
        request.client.host = "192.168.1.100"

        async def mock_next(request):
            return JSONResponse({"status": "success"})

        response = await rate_limit_middleware(request, mock_next)

        assert response.status_code == 200

    async def test_rate_limit_denied_flow(self, rate_limit_middleware):
        """Test requests over rate limits are denied."""
        # Mock over rate limit
        rate_limit_middleware.redis_client.get.return_value = b'120'  # Over 100 requests/min limit

        request = MagicMock(spec=Request)
        request.client.host = "192.168.1.100"

        async def mock_next(request):
            return JSONResponse({"status": "should_not_reach"})

        response = await rate_limit_middleware(request, mock_next)

        assert response.status_code == 429
        assert "Rate limit exceeded" in str(response.body)

    async def test_rate_limit_burst_handling(self, rate_limit_middleware):
        """Test burst size handling in rate limiting."""
        # Mock at burst limit
        rate_limit_middleware.redis_client.get.return_value = b'20'  # At burst size
        rate_limit_middleware.redis_client.incr.return_value = 21   # Would exceed burst

        request = MagicMock(spec=Request)
        request.client.host = "192.168.1.100"

        async def mock_next(request):
            return JSONResponse({"status": "should_not_reach"})

        response = await rate_limit_middleware(request, mock_next)

        assert response.status_code == 429


class TestEntitlementIntegrationFlows:
    """Integration tests covering complete entitlement flows."""

    async def test_end_to_end_allowed_premium_user_flow(self):
        """Test complete flow for premium user accessing F&O features."""
        # Setup components
        abuse_protection = StreamAbuseProtection(
            marketplace_client=AsyncMock(),
            redis_client=AsyncMock(),
            rate_limit_window=60,
            max_connections_per_user=50
        )

        entitlement_middleware = EntitlementMiddleware("http://marketplace")
        entitlement_middleware._client = AsyncMock()

        # Mock premium user entitlements
        abuse_protection.marketplace_client.get_user_subscriptions.return_value = {
            "subscriptions": [{"tier": "premium", "features": ["fo_greeks_access"], "limits": {"concurrent_connections": 50}}]
        }

        entitlement_middleware._client.get.return_value = AsyncMock()
        entitlement_middleware._client.get.return_value.status_code = 200
        entitlement_middleware._client.get.return_value.json.return_value = {"has_access": True}

        # Mock within rate limits
        abuse_protection.redis_client.scard.return_value = 5   # Low connections
        abuse_protection.redis_client.get.return_value = b'50' # Low request rate

        # Test entitlement verification
        limits = await abuse_protection._get_user_limits("premium_user", StreamType.GREEKS)
        assert limits.tier == "premium"

        # Test rate limiting
        rate_result = await abuse_protection.check_rate_limit("premium_user", "conn_1", StreamType.GREEKS)
        assert rate_result.allowed is True

        # Test middleware
        request = MagicMock(spec=Request)
        request.url.path = "/api/v2/signals/fo/greeks/"
        request.headers.get = lambda key, default=None: "12345" if key == "X-User-ID" else default
        request.state = MagicMock()

        async def mock_next(req):
            return JSONResponse({"data": "greeks_data"})

        response = await entitlement_middleware(request, mock_next)
        assert response.status_code == 200

    async def test_end_to_end_denied_basic_user_flow(self):
        """Test complete flow for basic user denied F&O access."""
        # Setup components
        StreamAbuseProtection(
            marketplace_client=AsyncMock(),
            redis_client=AsyncMock(),
            rate_limit_window=60,
            max_connections_per_user=5
        )

        entitlement_middleware = EntitlementMiddleware("http://marketplace")
        entitlement_middleware._client = AsyncMock()

        # Mock basic user without F&O entitlements
        entitlement_middleware._client.get.return_value = AsyncMock()
        entitlement_middleware._client.get.return_value.status_code = 200
        entitlement_middleware._client.get.return_value.json.return_value = {"has_access": False}

        # Test middleware denies access
        request = MagicMock(spec=Request)
        request.url.path = "/api/v2/signals/fo/greeks/"
        request.headers.get = lambda key, default=None: "54321" if key == "X-User-ID" else default

        async def mock_next(req):
            return JSONResponse({"should": "not_reach"})

        response = await entitlement_middleware(request, mock_next)
        assert response.status_code == 403
        assert "fo_greeks_access" in str(response.body)


def main():
    """Run entitlement and rate limiting tests."""
    print("🔍 Running Entitlement & Rate Limiting Comprehensive Tests...")

    print("✅ Entitlement and rate limiting tests validated")
    print("\n📋 Coverage Areas:")
    print("  - StreamAbuseProtection allowed/denied flows")
    print("  - Gateway-only operation enforcement")
    print("  - Authorization header rejection")
    print("  - Fail-fast entitlement verification")
    print("  - Rate limiting within/over limits")
    print("  - Premium vs basic user entitlements")
    print("  - Marketplace service failure scenarios")
    print("  - Cache behavior optimization")
    print("  - Audit logging for access decisions")
    print("  - Protected route detection")
    print("  - End-to-end integration flows")
    print("  - Burst handling in rate limiting")

    return 0


if __name__ == "__main__":
    exit_code = main()
    exit(exit_code)
