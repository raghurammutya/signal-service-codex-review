"""
Test SDK Signal Listing (Real Implementation)

Sprint 5A: Tests for real SDK signal listing with marketplace/personal integration.
"""
from unittest.mock import patch

import pytest
from httpx import AsyncClient

from app.services.signal_stream_contract import StreamKeyFormat


class TestSDKSignalListing:
    """Test real SDK signal listing functionality."""

    @pytest.fixture
    def mock_marketplace_subscriptions(self):
        """Mock marketplace subscriptions response."""
        return [
            {
                "subscription_id": "sub-123",
                "product_id": "prod-momentum",
                "product_name": "Advanced Momentum Signals",
                "status": "active",
                "execution_token": "exec-token-123",
                "expires_at": "2024-12-31T23:59:59Z",
                "signals": [
                    {
                        "name": "momentum_surge",
                        "description": "Momentum surge detector",
                        "default_params": {"threshold": 2.5, "period": 14}
                    },
                    {
                        "name": "volume_breakout",
                        "description": "Volume breakout signal",
                        "default_params": {"multiplier": 1.5}
                    }
                ]
            },
            {
                "subscription_id": "sub-456",
                "product_id": "prod-options",
                "product_name": "Options Flow Analysis",
                "status": "active",
                "execution_token": "exec-token-456",
                "expires_at": "2024-12-31T23:59:59Z",
                "signals": [
                    {
                        "name": "options_flow",
                        "description": "Unusual options activity",
                        "default_params": {"min_premium": 100000}
                    }
                ]
            }
        ]

    @pytest.fixture
    def mock_personal_signals(self):
        """Mock personal signals response."""
        return [
            {
                "script_id": "signal-001",
                "name": "My RSI Divergence",
                "script_type": "signal",
                "owner_id": "user-123",
                "created_at": "2024-01-01T00:00:00Z"
            },
            {
                "script_id": "signal-002",
                "name": "Custom MACD Cross",
                "script_type": "signal",
                "owner_id": "user-123",
                "created_at": "2024-01-02T00:00:00Z"
            }
        ]

    @pytest.fixture
    async def client(self, app):
        """Test client."""
        async with AsyncClient(app=app, base_url="http://test") as ac:
            yield ac

    async def test_list_all_signal_streams(self, client, mock_marketplace_subscriptions, mock_personal_signals):
        """Test listing all available signal streams."""
        with patch('app.core.auth.get_current_user_from_gateway', return_value={"user_id": "user-123"}):
            with patch('app.services.marketplace_client.MarketplaceClient.get_user_subscriptions',
                      return_value=mock_marketplace_subscriptions):
                with patch('algo_engine.app.services.personal_script_service.PersonalScriptService.list_scripts',
                          return_value=mock_personal_signals):

                    response = await client.get(
                        "/api/v2/signals/sdk/signals/streams",
                        headers={
                            "X-User-ID": "user-123",
                            "X-Gateway-Secret": "test-secret"
                        },
                        params={
                            "instruments": ["NIFTY50", "BANKNIFTY"]
                        }
                    )

                    assert response.status_code == 200
                    data = response.json()

                    # Check structure
                    assert "streams" in data
                    assert "counts" in data
                    assert "total" in data

                    streams = data["streams"]

                    # Check public streams
                    assert len(streams["public"]) > 0
                    assert any("public:NIFTY50:price:realtime" in s for s in streams["public"])

                    # Check common streams
                    assert len(streams["common"]) > 0
                    assert any("common:NIFTY50:rsi:period-14" in s for s in streams["common"])

                    # Check marketplace streams
                    assert len(streams["marketplace"]) == 6  # 3 signals x 2 instruments
                    marketplace_stream = streams["marketplace"][0]
                    assert "stream_key" in marketplace_stream
                    assert "product_id" in marketplace_stream
                    assert "product_name" in marketplace_stream
                    assert "signal_name" in marketplace_stream
                    assert "execution_token" in marketplace_stream
                    assert "subscription_id" in marketplace_stream

                    # Verify stream key format
                    key = marketplace_stream["stream_key"]
                    assert key.startswith("marketplace:prod-momentum:")

                    # Check personal streams
                    assert len(streams["personal"]) == 4  # 2 signals x 2 instruments
                    personal_stream = streams["personal"][0]
                    assert "stream_key" in personal_stream
                    assert "script_id" in personal_stream
                    assert "script_name" in personal_stream
                    assert personal_stream["owner_id"] == "user-123"

                    # Verify counts
                    assert data["counts"]["marketplace"] == 6
                    assert data["counts"]["personal"] == 4
                    assert data["total"] > 10

    async def test_list_filtered_by_type(self, client):
        """Test listing streams filtered by signal type."""
        with patch('app.core.auth.get_current_user_from_gateway', return_value={"user_id": "user-123"}):
            # Test filtering by common signals
            response = await client.get(
                "/api/v2/signals/sdk/signals/streams",
                headers={
                    "X-User-ID": "user-123",
                    "X-Gateway-Secret": "test-secret"
                },
                params={
                    "signal_type": "common",
                    "instruments": ["NIFTY50"]
                }
            )

            assert response.status_code == 200
            data = response.json()

            assert data["signal_type"] == "common"
            assert len(data["streams"]) > 0
            assert all("common:NIFTY50:" in s for s in data["streams"])
            assert data["count"] == len(data["streams"])

    async def test_default_instruments(self, client):
        """Test that default instruments are used when none specified."""
        with patch('app.core.auth.get_current_user_from_gateway', return_value={"user_id": "user-123"}):
            response = await client.get(
                "/api/v2/signals/sdk/signals/streams",
                headers={
                    "X-User-ID": "user-123",
                    "X-Gateway-Secret": "test-secret"
                }
            )

            assert response.status_code == 200
            data = response.json()

            # Should have signals for default instruments
            public_streams = data["streams"]["public"]
            instruments_found = set()

            for stream in public_streams:
                if ":price:" in stream:
                    # Extract instrument from stream key
                    parts = stream.split(":")
                    instruments_found.add(parts[1])

            # Check default instruments are present
            assert "NIFTY50" in instruments_found
            assert "BANKNIFTY" in instruments_found

    async def test_marketplace_integration_failure(self, client):
        """Test graceful handling when marketplace service fails."""
        with patch('app.core.auth.get_current_user_from_gateway', return_value={"user_id": "user-123"}):
            with patch('app.services.marketplace_client.MarketplaceClient.get_user_subscriptions',
                      side_effect=Exception("Marketplace service unavailable")):

                response = await client.get(
                    "/api/v2/signals/sdk/signals/streams",
                    headers={
                        "X-User-ID": "user-123",
                        "X-Gateway-Secret": "test-secret"
                    }
                )

                assert response.status_code == 200
                data = response.json()

                # Should still return public and common streams
                assert len(data["streams"]["public"]) > 0
                assert len(data["streams"]["common"]) > 0

                # But marketplace streams should be empty
                assert len(data["streams"]["marketplace"]) == 0

    async def test_personal_signals_integration_failure(self, client):
        """Test graceful handling when personal script service fails."""
        with patch('app.core.auth.get_current_user_from_gateway', return_value={"user_id": "user-123"}):
            with patch('algo_engine.app.services.personal_script_service.PersonalScriptService.list_scripts',
                      side_effect=Exception("MinIO unavailable")):

                response = await client.get(
                    "/api/v2/signals/sdk/signals/streams",
                    headers={
                        "X-User-ID": "user-123",
                        "X-Gateway-Secret": "test-secret"
                    }
                )

                assert response.status_code == 200
                data = response.json()

                # Should still return public and common streams
                assert len(data["streams"]["public"]) > 0
                assert len(data["streams"]["common"]) > 0

                # But personal streams should be empty
                assert len(data["streams"]["personal"]) == 0


class TestTokenValidation:
    """Test marketplace token validation endpoint."""

    @pytest.fixture
    async def client(self, app):
        """Test client."""
        async with AsyncClient(app=app, base_url="http://test") as ac:
            yield ac

    async def test_validate_valid_token(self, client):
        """Test validating a valid execution token."""
        with patch('app.core.auth.get_current_user_from_gateway', return_value={"user_id": "user-123"}):
            with patch('app.services.marketplace_client.MarketplaceClient.verify_execution_token',
                      return_value={
                          "is_valid": True,
                          "subscription_id": "sub-123",
                          "expires_at": "2024-12-31T23:59:59Z"
                      }):

                response = await client.post(
                    "/api/v2/signals/sdk/signals/validate-token",
                    headers={
                        "X-User-ID": "user-123",
                        "X-Gateway-Secret": "test-secret"
                    },
                    params={
                        "execution_token": "valid-token-123",
                        "product_id": "prod-momentum"
                    }
                )

                assert response.status_code == 200
                data = response.json()

                assert data["is_valid"] is True
                assert data["user_id"] == "user-123"
                assert data["product_id"] == "prod-momentum"
                assert data["subscription_id"] == "sub-123"
                assert data["expires_at"] == "2024-12-31T23:59:59Z"

    async def test_validate_invalid_token(self, client):
        """Test validating an invalid execution token."""
        with patch('app.core.auth.get_current_user_from_gateway', return_value={"user_id": "user-123"}):
            with patch('app.services.marketplace_client.MarketplaceClient.verify_execution_token',
                      return_value={"is_valid": False}):

                response = await client.post(
                    "/api/v2/signals/sdk/signals/validate-token",
                    headers={
                        "X-User-ID": "user-123",
                        "X-Gateway-Secret": "test-secret"
                    },
                    params={
                        "execution_token": "invalid-token",
                        "product_id": "prod-momentum"
                    }
                )

                assert response.status_code == 200
                data = response.json()

                assert data["is_valid"] is False
                assert data["user_id"] == "user-123"
                assert data["product_id"] == "prod-momentum"
                assert data.get("subscription_id") is None


class TestStreamKeyParsing:
    """Test stream key generation and parsing."""

    def test_marketplace_stream_keys_in_listing(self):
        """Test that marketplace stream keys are correctly formatted."""
        key = StreamKeyFormat.create_marketplace_key(
            product_id="prod-123",
            instrument="NIFTY50",
            signal="momentum",
            params={"threshold": 2.5, "period": 14}
        )

        assert key == "marketplace:prod-123:NIFTY50:momentum:period-14_threshold-2.5"

        # Parse it back
        parsed = StreamKeyFormat.parse_key(key)
        assert parsed["type"] == "marketplace"
        assert parsed["product_id"] == "prod-123"
        assert parsed["instrument"] == "NIFTY50"
        assert parsed["signal"] == "momentum"
        assert parsed["params"]["period"] == 14
        assert parsed["params"]["threshold"] == 2.5

    def test_personal_stream_keys_in_listing(self):
        """Test that personal stream keys are correctly formatted."""
        key = StreamKeyFormat.create_personal_key(
            user_id="user-456",
            signal_id="signal-789",
            instrument="BANKNIFTY",
            params=None
        )

        assert key == "personal:user-456:signal-789:BANKNIFTY:default"

        # Parse it back
        parsed = StreamKeyFormat.parse_key(key)
        assert parsed["type"] == "personal"
        assert parsed["user_id"] == "user-456"
        assert parsed["signal_id"] == "signal-789"
        assert parsed["instrument"] == "BANKNIFTY"
        assert parsed["params"] is None
