"""
Test Signal Version Policy API

Sprint 5A: Tests for author-controlled version policy.
"""
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient

from app.api.v2.signal_version_policy import (
    VersionPolicyRequest,
    VersionPolicyResponse,
    SignalVersionInfo
)


class TestSignalVersionPolicy:
    """Test signal version policy functionality."""
    
    @pytest.fixture
    def mock_signal_product(self):
        """Mock signal product from marketplace."""
        return {
            "product_id": "signal-123",
            "creator_id": "user-456",
            "product_type": "signal",
            "risk_level": "medium",
            "subscriber_count": 25,
            "version_info": {
                "policy": "auto",
                "current_version": "1.2.0",
                "effective_version": "1.2.0",
                "last_updated": "2024-01-01T00:00:00Z"
            }
        }
    
    @pytest.fixture
    def mock_signal_versions(self):
        """Mock version history."""
        return {
            "versions": [
                {
                    "version": "1.0.0",
                    "status": "published",
                    "created_at": "2023-01-01T00:00:00Z",
                    "description": "Initial release",
                    "breaking_changes": False
                },
                {
                    "version": "1.1.0",
                    "status": "published",
                    "created_at": "2023-06-01T00:00:00Z",
                    "description": "Added new features",
                    "breaking_changes": False
                },
                {
                    "version": "1.2.0",
                    "status": "published",
                    "created_at": "2024-01-01T00:00:00Z",
                    "description": "Performance improvements",
                    "breaking_changes": False
                },
                {
                    "version": "2.0.0",
                    "status": "draft",
                    "created_at": "2024-03-01T00:00:00Z",
                    "description": "Major rewrite",
                    "breaking_changes": True,
                    "min_compatible_version": "2.0.0"
                }
            ]
        }
    
    @pytest.fixture
    async def client(self, app):
        """Test client."""
        async with AsyncClient(app=app, base_url="http://test") as ac:
            yield ac
    
    async def test_get_version_policy(self, client, mock_signal_product):
        """Test getting current version policy."""
        with patch('app.core.auth.get_current_user_from_gateway', 
                  return_value={"user_id": "user-456"}):
            with patch('app.services.marketplace_client.MarketplaceClient.get_product_definition',
                      return_value=mock_signal_product):
                
                response = await client.get(
                    "/api/v2/signals/version-policy/signal-123",
                    headers={
                        "X-User-ID": "user-456",
                        "X-Gateway-Secret": "test-secret"
                    }
                )
                
                assert response.status_code == 200
                data = response.json()
                
                assert data["signal_id"] == "signal-123"
                assert data["policy"] == "auto"
                assert data["current_version"] == "1.2.0"
                assert data["effective_version"] == "1.2.0"
                assert data["auto_upgrade_enabled"] is True
    
    async def test_get_version_policy_unauthorized(self, client, mock_signal_product):
        """Test that non-owners cannot view version policy."""
        with patch('app.core.auth.get_current_user_from_gateway', 
                  return_value={"user_id": "other-user"}):
            with patch('app.services.marketplace_client.MarketplaceClient.get_product_definition',
                      return_value=mock_signal_product):
                
                response = await client.get(
                    "/api/v2/signals/version-policy/signal-123",
                    headers={
                        "X-User-ID": "other-user",
                        "X-Gateway-Secret": "test-secret"
                    }
                )
                
                assert response.status_code == 403
                assert "Not authorized" in response.json()["detail"]
    
    async def test_update_to_locked_policy(self, client, mock_signal_product):
        """Test updating to locked version policy."""
        with patch('app.core.auth.get_current_user_from_gateway', 
                  return_value={"user_id": "user-456"}):
            with patch('app.services.marketplace_client.MarketplaceClient.get_product_definition',
                      return_value=mock_signal_product):
                
                # Mock the update response
                mock_client = MagicMock()
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    "policy": "locked",
                    "current_version": "1.2.0",
                    "effective_version": "1.2.0",
                    "pinned_version": "1.2.0",
                    "last_updated": "2024-01-15T00:00:00Z"
                }
                
                mock_client.__aenter__.return_value.put.return_value = mock_response
                
                with patch('app.services.marketplace_client.MarketplaceClient._get_client',
                          return_value=mock_client):
                    
                    request = VersionPolicyRequest(
                        signal_id="signal-123",
                        policy="locked",
                        pinned_version="1.2.0"
                    )
                    
                    response = await client.put(
                        "/api/v2/signals/version-policy/signal-123",
                        json=request.dict(),
                        headers={
                            "X-User-ID": "user-456",
                            "X-Gateway-Secret": "test-secret"
                        }
                    )
                    
                    assert response.status_code == 200
                    data = response.json()
                    
                    assert data["policy"] == "locked"
                    assert data["pinned_version"] == "1.2.0"
                    assert data["auto_upgrade_enabled"] is False
    
    async def test_update_to_range_policy(self, client, mock_signal_product):
        """Test updating to range version policy."""
        with patch('app.core.auth.get_current_user_from_gateway', 
                  return_value={"user_id": "user-456"}):
            with patch('app.services.marketplace_client.MarketplaceClient.get_product_definition',
                      return_value=mock_signal_product):
                
                # Mock the update response
                mock_client = MagicMock()
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    "policy": "range",
                    "current_version": "1.2.0",
                    "effective_version": "1.2.0",
                    "min_version": "1.0.0",
                    "max_version": "2.0.0"
                }
                
                mock_client.__aenter__.return_value.put.return_value = mock_response
                
                with patch('app.services.marketplace_client.MarketplaceClient._get_client',
                          return_value=mock_client):
                    
                    request = VersionPolicyRequest(
                        signal_id="signal-123",
                        policy="range",
                        min_version="1.0.0",
                        max_version="2.0.0"
                    )
                    
                    response = await client.put(
                        "/api/v2/signals/version-policy/signal-123",
                        json=request.dict(),
                        headers={
                            "X-User-ID": "user-456",
                            "X-Gateway-Secret": "test-secret"
                        }
                    )
                    
                    assert response.status_code == 200
                    data = response.json()
                    
                    assert data["policy"] == "range"
                    assert data["min_version"] == "1.0.0"
                    assert data["max_version"] == "2.0.0"
    
    async def test_invalid_policy_request(self, client):
        """Test validation of invalid policy requests."""
        with patch('app.core.auth.get_current_user_from_gateway', 
                  return_value={"user_id": "user-456"}):
            
            # Invalid policy type
            response = await client.put(
                "/api/v2/signals/version-policy/signal-123",
                json={
                    "signal_id": "signal-123",
                    "policy": "invalid-policy"
                },
                headers={
                    "X-User-ID": "user-456",
                    "X-Gateway-Secret": "test-secret"
                }
            )
            
            assert response.status_code == 400
            assert "Invalid policy" in response.json()["detail"]
            
            # Locked without pinned version
            response = await client.put(
                "/api/v2/signals/version-policy/signal-123",
                json={
                    "signal_id": "signal-123",
                    "policy": "locked"
                },
                headers={
                    "X-User-ID": "user-456",
                    "X-Gateway-Secret": "test-secret"
                }
            )
            
            assert response.status_code == 400
            assert "pinned_version" in response.json()["detail"]
    
    async def test_list_signal_versions(self, client, mock_signal_versions):
        """Test listing signal versions."""
        with patch('app.core.auth.get_current_user_from_gateway', 
                  return_value={"user_id": "user-456"}):
            
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_signal_versions
            
            mock_client.__aenter__.return_value.get.return_value = mock_response
            
            with patch('app.services.marketplace_client.MarketplaceClient._get_client',
                      return_value=mock_client):
                
                response = await client.get(
                    "/api/v2/signals/version-policy/signal-123/versions",
                    headers={
                        "X-User-ID": "user-456",
                        "X-Gateway-Secret": "test-secret"
                    }
                )
                
                assert response.status_code == 200
                versions = response.json()
                
                assert len(versions) == 4
                assert versions[0]["version"] == "1.0.0"
                assert versions[0]["status"] == "published"
                assert versions[3]["version"] == "2.0.0"
                assert versions[3]["status"] == "draft"
                assert versions[3]["breaking_changes"] is True
    
    async def test_publish_version(self, client):
        """Test publishing a signal version."""
        with patch('app.core.auth.get_current_user_from_gateway', 
                  return_value={"user_id": "user-456"}):
            
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "version": "2.0.0",
                "status": "published",
                "created_at": "2024-03-01T00:00:00Z",
                "description": "Major rewrite",
                "breaking_changes": True,
                "min_compatible_version": "2.0.0"
            }
            
            mock_client.__aenter__.return_value.post.return_value = mock_response
            
            with patch('app.services.marketplace_client.MarketplaceClient._get_client',
                      return_value=mock_client):
                
                response = await client.post(
                    "/api/v2/signals/version-policy/signal-123/versions/2.0.0/publish",
                    params={"breaking_changes": True},
                    headers={
                        "X-User-ID": "user-456",
                        "X-Gateway-Secret": "test-secret"
                    }
                )
                
                assert response.status_code == 200
                data = response.json()
                
                assert data["version"] == "2.0.0"
                assert data["status"] == "published"
                assert data["breaking_changes"] is True
    
    async def test_get_policy_recommendations(self, client, mock_signal_product):
        """Test getting version policy recommendations."""
        with patch('app.core.auth.get_current_user_from_gateway', 
                  return_value={"user_id": "user-456"}):
            with patch('app.services.marketplace_client.MarketplaceClient.get_product_definition',
                      return_value=mock_signal_product):
                
                # Test with moderate subscribers
                response = await client.get(
                    "/api/v2/signals/version-policy/recommendations/signal-123",
                    headers={
                        "X-User-ID": "user-456",
                        "X-Gateway-Secret": "test-secret"
                    }
                )
                
                assert response.status_code == 200
                data = response.json()
                
                assert data["signal_id"] == "signal-123"
                assert data["recommended_policy"] == "range"
                assert "Moderate subscribers" in data["reason"]
                assert data["factors_considered"]["subscriber_count"] == 25
                
                # Test with high subscribers
                mock_signal_product["subscriber_count"] = 150
                
                response = await client.get(
                    "/api/v2/signals/version-policy/recommendations/signal-123",
                    headers={
                        "X-User-ID": "user-456",
                        "X-Gateway-Secret": "test-secret"
                    }
                )
                
                assert response.status_code == 200
                data = response.json()
                
                assert data["recommended_policy"] == "range"
                assert "High subscriber count" in data["reason"]
    
    async def test_recommendations_based_on_risk(self, client):
        """Test policy recommendations based on risk level."""
        with patch('app.core.auth.get_current_user_from_gateway', 
                  return_value={"user_id": "user-456"}):
            
            # High risk signal
            high_risk_signal = {
                "product_id": "signal-high",
                "risk_level": "high",
                "subscriber_count": 5
            }
            
            with patch('app.services.marketplace_client.MarketplaceClient.get_product_definition',
                      return_value=high_risk_signal):
                
                response = await client.get(
                    "/api/v2/signals/version-policy/recommendations/signal-high",
                    headers={
                        "X-User-ID": "user-456",
                        "X-Gateway-Secret": "test-secret"
                    }
                )
                
                assert response.status_code == 200
                data = response.json()
                assert data["recommended_policy"] == "locked"
                assert "High risk" in data["reason"]
            
            # Low risk signal
            low_risk_signal = {
                "product_id": "signal-low",
                "risk_level": "low",
                "subscriber_count": 5
            }
            
            with patch('app.services.marketplace_client.MarketplaceClient.get_product_definition',
                      return_value=low_risk_signal):
                
                response = await client.get(
                    "/api/v2/signals/version-policy/recommendations/signal-low",
                    headers={
                        "X-User-ID": "user-456",
                        "X-Gateway-Secret": "test-secret"
                    }
                )
                
                assert response.status_code == 200
                data = response.json()
                assert data["recommended_policy"] == "auto"
                assert "Low risk" in data["reason"]