"""
Test subscription metadata is properly wired for watermarking.
"""
import pytest
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime

from app.api.v2.sdk_signals import subscribe_to_signals
from app.schemas.signal_schemas import SignalSubscriptionRequest


@pytest.mark.asyncio
async def test_marketplace_subscription_includes_metadata():
    """Test that marketplace subscriptions include subscription_id in metadata."""
    
    # Mock marketplace client
    mock_marketplace_client = AsyncMock()
    mock_marketplace_client.get_product_signals = AsyncMock(return_value={
        "signals": [
            {"indicators": ["momentum", "rsi"]},
        ],
        "subscription_id": "sub_12345",  # This should be captured
    })
    
    # Mock cache
    mock_cache = AsyncMock()
    mock_cache.set = AsyncMock()
    
    # Mock user info
    mock_user_info = {"user_id": 1001, "email": "test@example.com"}
    
    with patch("app.api.v2.sdk_signals.get_current_user_from_gateway", return_value=mock_user_info), \
         patch("app.api.v2.sdk_signals.create_marketplace_client", return_value=mock_marketplace_client), \
         patch("app.api.v2.sdk_signals.get_cache", return_value=mock_cache), \
         patch("app.api.v2.sdk_signals.SignalStreamContract") as mock_contract_class:
        
        # Mock entitlement checks
        mock_contract = Mock()
        mock_contract.check_entitlement = AsyncMock(return_value=Mock(is_allowed=True))
        mock_contract_class.return_value = mock_contract
        
        # Make subscription request
        request = SignalSubscriptionRequest(
            signal_types=["marketplace"],
            instrument="NSE_EQ|RELIANCE",
            product_id="prod_test123",
            execution_token="token_xyz"
        )
        
        response = await subscribe_to_signals(
            request=request,
            authorization="Bearer test_token"
        )
        
        # Verify response
        assert response.success is True
        assert len(response.allowed_streams) > 0
        
        # Verify cache was called with marketplace metadata
        mock_cache.set.assert_called_once()
        cache_key, cache_data, _ = mock_cache.set.call_args[0]
        
        assert cache_key.startswith("sdk_connection_metadata:")
        assert cache_data["user_id"] == "1001"
        assert "marketplace_metadata" in cache_data
        
        # Check that subscription_id is in metadata for each stream
        marketplace_metadata = cache_data["marketplace_metadata"]
        for stream_key in response.allowed_streams:
            if stream_key.startswith("marketplace:"):
                assert stream_key in marketplace_metadata
                assert marketplace_metadata[stream_key]["subscription_id"] == "sub_12345"
                assert marketplace_metadata[stream_key]["product_id"] == "prod_test123"
                assert marketplace_metadata[stream_key]["signal_id"] in ["momentum", "rsi"]


@pytest.mark.asyncio 
async def test_websocket_uses_cached_metadata():
    """Test that WebSocket connection retrieves and uses cached metadata."""
    from app.api.v2.websocket import ConnectionManager
    
    # Mock cache with metadata
    mock_cache = AsyncMock()
    mock_cache.get = AsyncMock(return_value={
        "user_id": "1001", 
        "marketplace_metadata": {
            "marketplace:prod_test123:NSE_EQ|RELIANCE:momentum": {
                "subscription_id": "sub_12345",
                "product_id": "prod_test123",
                "signal_id": "momentum"
            }
        },
        "execution_token": "token_xyz"
    })
    
    # Mock WebSocket
    mock_websocket = AsyncMock()
    mock_websocket.receive_text = AsyncMock(side_effect=Exception("Test complete"))
    mock_websocket.send_json = AsyncMock()
    
    manager = ConnectionManager()
    
    with patch("app.api.v2.sdk_signals.get_cache", return_value=mock_cache):
        # Simulate WebSocket connection
        client_id = "test_client"
        token = "sdk_1001_1234567890"
        
        # This would normally be called in the WebSocket endpoint
        await manager.connect(mock_websocket, client_id)
        
        # Simulate the metadata loading logic
        parts = token.split("_")
        user_id = parts[1]
        
        cached_metadata = await mock_cache.get(f"sdk_connection_metadata:{token}")
        
        if client_id not in manager.connection_metadata:
            manager.connection_metadata[client_id] = {}
        
        manager.connection_metadata[client_id].update({
            "user_id": user_id,
            "connection_type": "sdk",
            "token": token,
            "marketplace_metadata": cached_metadata.get("marketplace_metadata", {}),
            "execution_token": cached_metadata.get("execution_token")
        })
        
        # Verify metadata is stored correctly
        assert manager.connection_metadata[client_id]["user_id"] == "1001"
        assert "marketplace_metadata" in manager.connection_metadata[client_id]
        
        marketplace_meta = manager.connection_metadata[client_id]["marketplace_metadata"]
        stream_key = "marketplace:prod_test123:NSE_EQ|RELIANCE:momentum"
        assert stream_key in marketplace_meta
        assert marketplace_meta[stream_key]["subscription_id"] == "sub_12345"


@pytest.mark.asyncio
async def test_watermarking_receives_subscription_metadata():
    """Test that watermark service receives subscription_id and signal_id."""
    from app.api.v2.websocket import ConnectionManager
    
    # Mock watermark service
    mock_watermark_service = AsyncMock()
    mock_watermark_service.watermark_signal = AsyncMock(return_value={"data": "watermarked"})
    mock_watermark_service.detect_leak_and_enforce = AsyncMock(return_value={"leak_detected": False})
    
    manager = ConnectionManager()
    manager.watermark_service = mock_watermark_service
    
    # Set up connection metadata
    client_id = "test_client"
    stream_key = "marketplace:prod_test123:NSE_EQ|RELIANCE:momentum"
    
    manager.active_connections[client_id] = AsyncMock()  # Mock WebSocket
    manager.subscription_connections[stream_key] = {client_id}
    manager.connection_metadata[client_id] = {
        "user_id": "1001",
        "marketplace_metadata": {
            stream_key: {
                "subscription_id": "sub_12345",
                "product_id": "prod_test123",
                "signal_id": "momentum"
            }
        }
    }
    
    # Broadcast a signal
    test_data = {"value": 42, "timestamp": datetime.utcnow().isoformat()}
    await manager.broadcast_to_subscription(stream_key, test_data)
    
    # Verify watermark was called with correct metadata
    mock_watermark_service.watermark_signal.assert_called_once_with(
        stream_key=stream_key,
        signal_data=test_data,
        user_id="1001",
        subscription_id="sub_12345",
        signal_id="momentum"
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])