"""
Test Signal Script Execution from MinIO

Sprint 5A: Tests for marketplace and personal signal script execution.
"""
import json
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient

from app.services.signal_executor import SignalExecutor
from app.services.signal_stream_contract import StreamKeyFormat


class TestSignalExecutor:
    """Test signal script execution service."""
    
    @pytest.fixture
    def mock_minio_client(self):
        """Mock MinIO client."""
        client = MagicMock()
        client.bucket_exists.return_value = True
        return client
    
    @pytest.fixture
    def sample_script(self):
        """Sample signal script."""
        return """
# Simple momentum signal
def calculate_signal(context):
    instrument = context.get('instrument')
    params = context.get('params', {})
    
    # Emit a signal
    emit_signal({
        'name': 'momentum',
        'instrument': instrument,
        'value': 1.5,
        'direction': 'BUY',
        'params': params
    })

# Execute
calculate_signal(context)
"""
    
    async def test_fetch_marketplace_script(self, sample_script):
        """Test fetching marketplace script via execution token."""
        # Mock marketplace service response
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            # Mock access response
            mock_client.post.return_value.status_code = 200
            mock_client.post.return_value.json.return_value = {
                "presigned_url": "http://minio/presigned",
                "metadata": {"version": "1.0.0"},
                "version": "latest"
            }
            
            # Mock script fetch
            mock_client.get.return_value.status_code = 200
            mock_client.get.return_value.text = sample_script
            
            result = await SignalExecutor.fetch_marketplace_script(
                execution_token="test-token",
                product_id="prod-123"
            )
            
            assert result is not None
            assert result["content"] == sample_script
            assert result["metadata"]["version"] == "1.0.0"
            assert result["product_id"] == "prod-123"
    
    async def test_fetch_personal_script(self, mock_minio_client, sample_script):
        """Test fetching personal script with ACL check."""
        with patch.object(SignalExecutor, '_get_client', return_value=mock_minio_client):
            # Mock script content
            mock_response = MagicMock()
            mock_response.read.return_value = sample_script.encode('utf-8')
            mock_minio_client.get_object.return_value = mock_response
            
            # Mock metadata
            metadata = {
                "script_id": "signal-123",
                "owner_id": "user-456",
                "name": "My Signal"
            }
            mock_meta_response = MagicMock()
            mock_meta_response.read.return_value = json.dumps(metadata).encode('utf-8')
            mock_minio_client.get_object.side_effect = [mock_meta_response, mock_response]
            
            # Test owner access (allowed)
            result = await SignalExecutor.fetch_personal_script(
                user_id="user-456",
                script_id="signal-123",
                requesting_user_id="user-456"
            )
            
            assert result is not None
            assert result["content"] == sample_script
            assert result["script_id"] == "signal-123"
            assert result["owner_id"] == "user-456"
            
            # Test non-owner access (denied)
            mock_minio_client.get_object.side_effect = [mock_meta_response, mock_response]
            result = await SignalExecutor.fetch_personal_script(
                user_id="user-456",
                script_id="signal-123",
                requesting_user_id="other-user"
            )
            
            assert result is None  # Access denied
    
    async def test_execute_signal_script(self):
        """Test signal script execution in sandbox."""
        script = """
# Generate multiple signals
signals = [
    {'name': 'rsi', 'value': 75, 'overbought': True},
    {'name': 'macd', 'value': 0.5, 'bullish': True}
]

for signal in signals:
    signal['instrument'] = context.get('instrument')
    signal['timestamp'] = get_timestamp()
    emit_signal(signal)
"""
        
        context = {
            "instrument": "NIFTY50",
            "params": {"period": 14}
        }
        
        result = await SignalExecutor.execute_signal_script(
            script_content=script,
            context=context,
            timeout=10.0
        )
        
        assert result["success"] is True
        assert len(result["signals"]) == 2
        assert result["signals"][0]["name"] == "rsi"
        assert result["signals"][0]["value"] == 75
        assert result["signals"][0]["instrument"] == "NIFTY50"
        assert result["signals"][1]["name"] == "macd"
        assert result["execution_time"] < 10.0
    
    async def test_script_timeout(self):
        """Test script execution timeout."""
        script = """
# Infinite loop
while True:
    pass
"""
        
        result = await SignalExecutor.execute_signal_script(
            script_content=script,
            context={},
            timeout=0.5
        )
        
        assert result["success"] is False
        assert result["error"] == "Execution timeout"
        assert result["timeout"] == 0.5
    
    async def test_script_error_handling(self):
        """Test script error handling."""
        script = """
# Error in script
result = 1 / 0
"""
        
        result = await SignalExecutor.execute_signal_script(
            script_content=script,
            context={},
            timeout=5.0
        )
        
        assert result["success"] is False
        assert "division by zero" in result["error"]
        assert result["error_type"] == "ZeroDivisionError"
    
    async def test_sandbox_restrictions(self):
        """Test that sandbox blocks dangerous operations."""
        dangerous_scripts = [
            "import os; os.system('ls')",
            "open('/etc/passwd', 'r')",
            "__import__('subprocess').call(['ls'])",
            "exec('import sys')"
        ]
        
        for script in dangerous_scripts:
            result = await SignalExecutor.execute_signal_script(
                script_content=script,
                context={},
                timeout=5.0
            )
            
            assert result["success"] is False
            assert result.get("error") is not None
    
    async def test_publish_to_redis(self):
        """Test publishing signal to Redis stream."""
        mock_redis = AsyncMock()
        mock_redis.xadd = AsyncMock(return_value="1234567890-0")
        
        with patch('app.services.signal_executor.get_redis_client', return_value=mock_redis):
            signal_data = {
                "name": "momentum",
                "value": 2.5,
                "direction": "BUY"
            }
            
            result = await SignalExecutor.publish_to_redis(
                stream_key="marketplace:prod-123:NIFTY50:momentum:default",
                signal_data=signal_data
            )
            
            assert result is True
            
            # Verify Redis XADD was called
            mock_redis.xadd.assert_called_once()
            call_args = mock_redis.xadd.call_args
            
            assert call_args[0][0] == "marketplace:prod-123:NIFTY50:momentum:default"
            assert "name" in call_args[0][1]
            assert call_args[0][1]["name"] == "momentum"
            assert call_args[0][1]["value"] == "2.5"
            assert call_args[0][1]["direction"] == "BUY"
            assert "_published_at" in call_args[0][1]
    
    async def test_execute_marketplace_signal(self, sample_script):
        """Test end-to-end marketplace signal execution."""
        # Mock script fetch
        with patch.object(
            SignalExecutor, 
            'fetch_marketplace_script',
            return_value={
                "content": sample_script,
                "metadata": {},
                "product_id": "prod-123"
            }
        ):
            # Mock Redis publish
            with patch.object(SignalExecutor, 'publish_to_redis', return_value=True):
                result = await SignalExecutor.execute_marketplace_signal(
                    execution_token="test-token",
                    product_id="prod-123",
                    instrument="NIFTY50",
                    params={"period": 14},
                    user_id="user-456",
                    subscription_id="sub-789"
                )
                
                assert result["success"] is True
                assert len(result["signals"]) == 1
                assert result["signals"][0]["name"] == "momentum"
                assert result["signals"][0]["_subscription_id"] == "sub-789"


class TestSignalExecutionAPI:
    """Test signal execution API endpoints."""
    
    @pytest.fixture
    async def client(self, app):
        """Test client."""
        async with AsyncClient(app=app, base_url="http://test") as ac:
            yield ac
    
    async def test_execute_marketplace_signal_endpoint(self, client):
        """Test marketplace signal execution endpoint."""
        # Mock authentication
        with patch('app.core.auth.get_current_user_from_gateway', return_value={"user_id": "123"}):
            # Mock background task
            with patch('app.services.signal_executor.SignalExecutor.execute_marketplace_signal'):
                response = await client.post(
                    "/api/v2/signals/execute/marketplace",
                    json={
                        "execution_token": "test-token",
                        "product_id": "prod-123",
                        "instrument": "NIFTY50",
                        "params": {"period": 14},
                        "subscription_id": "sub-789"
                    },
                    headers={
                        "X-User-ID": "123",
                        "X-Gateway-Secret": "test-secret"
                    }
                )
                
                assert response.status_code == 200
                data = response.json()
                
                assert data["success"] is True
                assert data["message"] == "Signal execution initiated"
                assert data["execution_id"] == "exec_prod-123_NIFTY50"
                assert len(data["stream_keys"]) > 0
    
    async def test_execute_personal_signal_endpoint(self, client):
        """Test personal signal execution endpoint."""
        # Mock authentication
        with patch('app.core.auth.get_current_user_from_gateway', return_value={"user_id": "123"}):
            # Mock background task
            with patch('app.services.signal_executor.SignalExecutor.execute_personal_signal'):
                response = await client.post(
                    "/api/v2/signals/execute/personal",
                    json={
                        "script_id": "signal-456",
                        "instrument": "BANKNIFTY",
                        "params": {"threshold": 0.5}
                    },
                    headers={
                        "X-User-ID": "123",
                        "X-Gateway-Secret": "test-secret"
                    }
                )
                
                assert response.status_code == 200
                data = response.json()
                
                assert data["success"] is True
                assert data["message"] == "Personal signal execution initiated"
                assert data["execution_id"] == "exec_personal_123_signal-456"
                assert len(data["stream_keys"]) > 0


class TestStreamKeyGeneration:
    """Test stream key generation for signal routing."""
    
    def test_marketplace_stream_key(self):
        """Test marketplace signal stream key generation."""
        key = StreamKeyFormat.create_marketplace_key(
            product_id="prod-123",
            instrument="NIFTY50",
            signal="momentum",
            params={"period": 14, "threshold": 0.5}
        )
        
        assert key == "marketplace:prod-123:NIFTY50:momentum:period-14_threshold-0.5"
        
        # Parse it back
        parsed = StreamKeyFormat.parse_key(key)
        assert parsed["type"] == "marketplace"
        assert parsed["product_id"] == "prod-123"
        assert parsed["instrument"] == "NIFTY50"
        assert parsed["signal"] == "momentum"
        assert parsed["params"]["period"] == 14
        assert parsed["params"]["threshold"] == 0.5
    
    def test_personal_stream_key(self):
        """Test personal signal stream key generation."""
        key = StreamKeyFormat.create_personal_key(
            user_id="user-456",
            signal_id="signal-789",
            instrument="BANKNIFTY",
            params={"fast": 12, "slow": 26}
        )
        
        assert key == "personal:user-456:signal-789:BANKNIFTY:fast-12_slow-26"
        
        # Parse it back
        parsed = StreamKeyFormat.parse_key(key)
        assert parsed["type"] == "personal"
        assert parsed["user_id"] == "user-456"
        assert parsed["signal_id"] == "signal-789"
        assert parsed["instrument"] == "BANKNIFTY"
        assert parsed["params"]["fast"] == 12
        assert parsed["params"]["slow"] == 26