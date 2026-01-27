"""
Test Dynamic Billing Tiers

Sprint 5A: Tests for dynamic connection limits based on marketplace subscriptions.
"""
import time
from unittest.mock import AsyncMock, patch

import pytest

from app.services.stream_abuse_protection import (
    StreamAbuseProtectionService,
    StreamType,
)


class TestDynamicBillingTiers:
    """Test dynamic billing tier implementation."""

    @pytest.fixture
    def mock_redis_client(self):
        """Mock Redis client."""
        client = AsyncMock()
        client.get.return_value = None
        client.setex.return_value = None
        client.incr.return_value = 1
        client.scard.return_value = 0
        client.sadd.return_value = None
        client.expire.return_value = None
        return client

    @pytest.fixture
    def mock_marketplace_response_free(self):
        """Mock marketplace response for free tier user."""
        return {
            "subscriptions": [],
            "total_count": 0
        }

    @pytest.fixture
    def mock_marketplace_response_premium(self):
        """Mock marketplace response for premium tier user."""
        return {
            "subscriptions": [
                {
                    "subscription_id": "sub-123",
                    "product_id": "prod-premium",
                    "product_name": "Premium Signals",
                    "status": "active",
                    "tier": "premium",
                    "expires_at": "2024-12-31T23:59:59Z"
                }
            ],
            "total_count": 1
        }

    @pytest.fixture
    def mock_marketplace_response_enterprise(self):
        """Mock marketplace response for enterprise tier user."""
        return {
            "subscriptions": [
                {
                    "subscription_id": "sub-456",
                    "product_id": "prod-enterprise",
                    "product_name": "Enterprise Suite",
                    "status": "active",
                    "tier": "enterprise",
                    "expires_at": "2024-12-31T23:59:59Z"
                }
            ],
            "total_count": 1
        }

    @pytest.fixture
    async def abuse_protection_service(self, mock_redis_client):
        """Create abuse protection service with mocked dependencies."""
        service = StreamAbuseProtectionService()
        service.redis_client = mock_redis_client
        return service

    async def test_free_tier_limits(
        self,
        abuse_protection_service,
        mock_marketplace_response_free
    ):
        """Test that free tier users get base limits."""
        with patch.object(
            abuse_protection_service.marketplace_client,
            'get_user_subscriptions',
            return_value=mock_marketplace_response_free
        ):
            limits = await abuse_protection_service._get_user_limits("user-free", StreamType.PUBLIC)

            # Free tier should match fallback limits
            assert limits.max_concurrent_connections == 50
            assert limits.max_subscriptions_per_connection == 10
            assert limits.max_subscription_requests == 30
            assert limits.max_messages_sent == 1000
            assert limits.rapid_subscription_threshold == 5
            assert limits.burst_message_threshold == 50

    async def test_premium_tier_limits(
        self,
        abuse_protection_service,
        mock_marketplace_response_premium
    ):
        """Test that premium tier users get higher limits."""
        # Create a real marketplace client mock
        mock_client = AsyncMock()
        mock_client.get_user_subscriptions = AsyncMock(return_value=mock_marketplace_response_premium)
        abuse_protection_service.marketplace_client = mock_client

        limits = await abuse_protection_service._get_user_limits("user-premium", StreamType.PUBLIC)

        # Premium tier should have 5x base limits
        assert limits.max_concurrent_connections == 250  # 50 * 5
        assert limits.max_subscriptions_per_connection == 50  # 10 * 5
        assert limits.max_subscription_requests == 150  # 30 * 5
        assert limits.max_messages_sent == 5000  # 1000 * 5
        assert limits.rapid_subscription_threshold == 25  # 5 * 5
        assert limits.burst_message_threshold == 250  # 50 * 5

    async def test_enterprise_tier_limits(
        self,
        abuse_protection_service,
        mock_marketplace_response_enterprise
    ):
        """Test that enterprise tier users get highest limits."""
        # Create a real marketplace client mock
        mock_client = AsyncMock()
        mock_client.get_user_subscriptions = AsyncMock(return_value=mock_marketplace_response_enterprise)
        abuse_protection_service.marketplace_client = mock_client

        limits = await abuse_protection_service._get_user_limits("user-enterprise", StreamType.PUBLIC)

        # Enterprise tier should have 10x base limits
        assert limits.max_concurrent_connections == 500  # 50 * 10
        assert limits.max_subscriptions_per_connection == 100  # 10 * 10
        assert limits.max_subscription_requests == 300  # 30 * 10
        assert limits.max_messages_sent == 10000  # 1000 * 10
        assert limits.rapid_subscription_threshold == 50  # 5 * 10
        assert limits.burst_message_threshold == 500  # 50 * 10

    async def test_multiple_subscriptions_best_tier(
        self,
        abuse_protection_service
    ):
        """Test that user with multiple subscriptions gets the best tier."""
        multi_subscription_response = {
            "subscriptions": [
                {
                    "subscription_id": "sub-1",
                    "status": "active",
                    "tier": "standard"
                },
                {
                    "subscription_id": "sub-2",
                    "status": "active",
                    "tier": "premium"
                },
                {
                    "subscription_id": "sub-3",
                    "status": "expired",
                    "tier": "enterprise"
                }
            ],
            "total_count": 3
        }

        mock_client = AsyncMock()
        mock_client.get_user_subscriptions = AsyncMock(return_value=multi_subscription_response)
        abuse_protection_service.marketplace_client = mock_client

        limits = await abuse_protection_service._get_user_limits("user-multi", StreamType.PUBLIC)

        # Should get premium tier (best active subscription)
        assert limits.max_concurrent_connections == 250  # Premium level

    async def test_limits_caching(
        self,
        abuse_protection_service,
        mock_marketplace_response_premium
    ):
        """Test that limits are cached to avoid repeated API calls."""
        mock_client = AsyncMock()
        mock_client.get_user_subscriptions = AsyncMock(return_value=mock_marketplace_response_premium)
        abuse_protection_service.marketplace_client = mock_client

        # First call should fetch from marketplace
        limits1 = await abuse_protection_service._get_user_limits("user-cached", StreamType.PUBLIC)
        assert mock_client.get_user_subscriptions.call_count == 1

        # Second call should use cache
        limits2 = await abuse_protection_service._get_user_limits("user-cached", StreamType.PUBLIC)
        assert mock_client.get_user_subscriptions.call_count == 1  # No additional call

        # Limits should be identical
        assert limits1.max_concurrent_connections == limits2.max_concurrent_connections

    async def test_cache_expiration(
        self,
        abuse_protection_service,
        mock_marketplace_response_premium
    ):
        """Test that cached limits expire after TTL."""
        mock_client = AsyncMock()
        mock_client.get_user_subscriptions = AsyncMock(return_value=mock_marketplace_response_premium)
        abuse_protection_service.marketplace_client = mock_client

        # Set short TTL for test
        abuse_protection_service._limits_cache_ttl = 0.1  # 100ms

        # First call
        await abuse_protection_service._get_user_limits("user-ttl", StreamType.PUBLIC)
        assert mock_client.get_user_subscriptions.call_count == 1

        # Wait for cache to expire
        time.sleep(0.2)

        # Second call should fetch again
        await abuse_protection_service._get_user_limits("user-ttl", StreamType.PUBLIC)
        assert mock_client.get_user_subscriptions.call_count == 2

    async def test_marketplace_failure_fallback(
        self,
        abuse_protection_service
    ):
        """Test fallback to default limits when marketplace fails."""
        mock_client = AsyncMock()
        mock_client.get_user_subscriptions = AsyncMock(side_effect=Exception("Marketplace error"))
        abuse_protection_service.marketplace_client = mock_client

        # Should fall back to default limits without error
        limits = await abuse_protection_service._get_user_limits("user-error", StreamType.PUBLIC)

        # Should get base fallback limits
        assert limits.max_concurrent_connections == 50
        assert limits.max_subscriptions_per_connection == 10

    async def test_different_stream_types(
        self,
        abuse_protection_service,
        mock_marketplace_response_premium
    ):
        """Test that different stream types have different base limits."""
        mock_client = AsyncMock()
        mock_client.get_user_subscriptions = AsyncMock(return_value=mock_marketplace_response_premium)
        abuse_protection_service.marketplace_client = mock_client

        # Test PUBLIC stream
        public_limits = await abuse_protection_service._get_user_limits("user-types", StreamType.PUBLIC)

        # Test COMMON stream (should have higher base)
        common_limits = await abuse_protection_service._get_user_limits("user-types", StreamType.COMMON)

        # Common should have higher base limits than public
        assert common_limits.max_concurrent_connections > public_limits.max_concurrent_connections
        assert common_limits.max_subscriptions_per_connection > public_limits.max_subscriptions_per_connection

    async def test_connection_check_with_dynamic_limits(
        self,
        abuse_protection_service,
        mock_marketplace_response_enterprise,
        mock_redis_client
    ):
        """Test that connection checks use dynamic limits."""
        mock_client = AsyncMock()
        mock_client.get_user_subscriptions = AsyncMock(return_value=mock_marketplace_response_enterprise)
        abuse_protection_service.marketplace_client = mock_client

        # Mock connection count at enterprise limit
        mock_redis_client.scard.return_value = 499  # Just under enterprise limit of 500

        # Should be allowed
        allowed, reason = await abuse_protection_service.check_connection_allowed(
            client_id="client-123",
            user_id="user-enterprise",
            stream_type=StreamType.PUBLIC
        )

        assert allowed is True
        assert reason is None

        # Mock connection count at enterprise limit
        mock_redis_client.scard.return_value = 500

        # Should be denied
        allowed, reason = await abuse_protection_service.check_connection_allowed(
            client_id="client-124",
            user_id="user-enterprise",
            stream_type=StreamType.PUBLIC
        )

        assert allowed is False
        assert "Maximum concurrent connections exceeded" in reason
        assert "500/500" in reason  # Should show enterprise limit
