"""
Comprehensive configuration management testing
Tests configuration loading, validation, updates, and secret handling
"""

import asyncio
import json
import os
import tempfile
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.core.config import SignalServiceConfig
from app.core.config_update import ConfigUpdateManager
from app.errors import ConfigurationError
from app.services.config_handler import ConfigHandler


class TestSignalServiceConfig:
    """Test core configuration management"""

    @pytest.fixture
    def config_data(self):
        """Sample configuration data"""
        return {
            "database": {
                "host": "localhost",
                "port": 5432,
                "name": "signal_service_test",
                "user": "test_user"
            },
            "redis": {
                "host": "localhost",
                "port": 6379,
                "db": 0
            },
            "external_functions": {
                "enable": True,
                "max_memory_mb": 128,
                "timeout_seconds": 30,
                "storage_path": "/tmp/external_functions"
            },
            "security": {
                "jwt_secret": "test-jwt-secret",
                "gateway_secret": "test-gateway-secret",
                "enable_gateway_trust": True
            }
        }

    def test_config_initialization(self, config_data):
        """Test configuration initialization"""
        with patch.dict(os.environ, {
            "DATABASE_HOST": config_data["database"]["host"],
            "DATABASE_PORT": str(config_data["database"]["port"]),
            "REDIS_HOST": config_data["redis"]["host"],
            "ENVIRONMENT": "test"
        }):
            config = SignalServiceConfig()

            assert config.DATABASE_HOST == "localhost"
            assert config.DATABASE_PORT == 5432
            assert config.REDIS_HOST == "localhost"
            assert config.ENVIRONMENT == "test"

    def test_config_environment_override(self):
        """Test environment variable overrides"""
        with patch.dict(os.environ, {
            "DATABASE_HOST": "prod-db.example.com",
            "DATABASE_PORT": "5433",
            "EXTERNAL_FUNCTION_MAX_MEMORY_MB": "256",
            "ENABLE_EXTERNAL_FUNCTIONS": "false"
        }):
            config = SignalServiceConfig()

            assert config.DATABASE_HOST == "prod-db.example.com"
            assert config.DATABASE_PORT == 5433
            assert config.EXTERNAL_FUNCTION_MAX_MEMORY_MB == 256
            assert config.ENABLE_EXTERNAL_FUNCTIONS is False

    def test_config_validation_success(self, config_data):
        """Test successful configuration validation"""
        with patch.dict(os.environ, {
            "DATABASE_HOST": config_data["database"]["host"],
            "DATABASE_PASSWORD": "test-password",
            "JWT_SECRET": config_data["security"]["jwt_secret"],
            "GATEWAY_SECRET": config_data["security"]["gateway_secret"]
        }):
            config = SignalServiceConfig()

            # Should not raise any exceptions
            config.validate_config()

    def test_config_validation_missing_required(self):
        """Test configuration validation with missing required fields"""
        with patch.dict(os.environ, {
            "DATABASE_HOST": "localhost",
            # Missing required DATABASE_PASSWORD
        }, clear=True):
            config = SignalServiceConfig()

            with pytest.raises(ConfigurationError, match="DATABASE_PASSWORD is required"):
                config.validate_config()

    def test_config_validation_invalid_values(self):
        """Test configuration validation with invalid values"""
        with patch.dict(os.environ, {
            "DATABASE_HOST": "localhost",
            "DATABASE_PASSWORD": "password",
            "DATABASE_PORT": "invalid_port",  # Invalid port
            "EXTERNAL_FUNCTION_MAX_MEMORY_MB": "-10"  # Invalid memory limit
        }):
            config = SignalServiceConfig()

            with pytest.raises(ConfigurationError, match="Invalid configuration"):
                config.validate_config()

    def test_secret_redaction_in_logs(self, config_data):
        """Test that secrets are redacted in logs and string representations"""
        with patch.dict(os.environ, {
            "DATABASE_PASSWORD": "secret_password_123",
            "JWT_SECRET": "secret_jwt_key_456",
            "GATEWAY_SECRET": "secret_gateway_789"
        }):
            config = SignalServiceConfig()

            config_str = str(config)

            # Secrets should be redacted
            assert "secret_password_123" not in config_str
            assert "secret_jwt_key_456" not in config_str
            assert "secret_gateway_789" not in config_str
            assert "[REDACTED]" in config_str or "***" in config_str

    def test_config_get_method(self, config_data):
        """Test configuration get method with defaults"""
        with patch.dict(os.environ, {
            "DATABASE_HOST": "localhost",
            "DATABASE_PASSWORD": "password"
        }):
            config = SignalServiceConfig()

            # Test getting existing value
            assert config.get_config("DATABASE_HOST") == "localhost"

            # Test getting non-existent value with default
            assert config.get_config("NON_EXISTENT_KEY", "default_value") == "default_value"

            # Test getting non-existent value without default
            assert config.get_config("NON_EXISTENT_KEY") is None


class TestConfigHandler:
    """Test configuration handler for dynamic config management"""

    @pytest.fixture
    def config_handler(self):
        """Create config handler instance"""
        return ConfigHandler()

    @pytest.fixture
    def temp_config_file(self):
        """Create temporary config file"""
        config_data = {
            "signal_processing": {
                "batch_size": 1000,
                "timeout_seconds": 30,
                "enable_caching": True
            },
            "indicators": {
                "default_period": 14,
                "max_lookback": 100
            }
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            temp_file = f.name

        yield temp_file

        # Cleanup
        os.unlink(temp_file)

    def test_load_config_from_file(self, config_handler, temp_config_file):
        """Test loading configuration from file"""
        config = config_handler.load_config_from_file(temp_config_file)

        assert config["signal_processing"]["batch_size"] == 1000
        assert config["signal_processing"]["enable_caching"] is True
        assert config["indicators"]["default_period"] == 14

    def test_load_config_file_not_found(self, config_handler):
        """Test loading configuration from non-existent file"""
        with pytest.raises(ConfigurationError, match="Configuration file not found"):
            config_handler.load_config_from_file("/non/existent/file.json")

    def test_load_config_invalid_json(self, config_handler):
        """Test loading invalid JSON configuration"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("invalid json content {")
            temp_file = f.name

        try:
            with pytest.raises(ConfigurationError, match="Invalid JSON"):
                config_handler.load_config_from_file(temp_file)
        finally:
            os.unlink(temp_file)

    @patch('app.services.config_handler.ConfigServiceClient')
    def test_load_config_from_service(self, mock_client, config_handler):
        """Test loading configuration from config service"""
        mock_client_instance = Mock()
        mock_client.return_value = mock_client_instance
        mock_client_instance.get_config.return_value = {
            "key": "signal_service.batch_size",
            "value": "2000",
            "type": "integer"
        }

        result = config_handler.get_config_from_service("signal_service.batch_size")

        assert result == 2000  # Should be converted to integer
        mock_client_instance.get_config.assert_called_once_with("signal_service.batch_size")

    @patch('app.services.config_handler.ConfigServiceClient')
    def test_load_config_service_unavailable(self, mock_client, config_handler):
        """Test handling config service unavailability"""
        mock_client_instance = Mock()
        mock_client.return_value = mock_client_instance
        mock_client_instance.get_config.side_effect = Exception("Service unavailable")

        # Should fall back to default value
        result = config_handler.get_config_from_service(
            "signal_service.batch_size",
            default=1000
        )

        assert result == 1000

    def test_merge_configurations(self, config_handler):
        """Test merging multiple configuration sources"""
        base_config = {
            "database": {"host": "localhost", "port": 5432},
            "redis": {"host": "localhost"}
        }

        override_config = {
            "database": {"port": 5433},  # Override port
            "redis": {"db": 1},          # Add new field
            "cache": {"ttl": 3600}       # Add new section
        }

        merged = config_handler.merge_configs(base_config, override_config)

        assert merged["database"]["host"] == "localhost"  # Preserved
        assert merged["database"]["port"] == 5433         # Overridden
        assert merged["redis"]["host"] == "localhost"     # Preserved
        assert merged["redis"]["db"] == 1                 # Added
        assert merged["cache"]["ttl"] == 3600             # Added

    def test_config_type_conversion(self, config_handler):
        """Test automatic type conversion"""
        test_cases = [
            ("123", "integer", 123),
            ("45.67", "float", 45.67),
            ("true", "boolean", True),
            ("false", "boolean", False),
            ("[1,2,3]", "json", [1, 2, 3]),
            ('{"key": "value"}', "json", {"key": "value"}),
            ("plain_string", "string", "plain_string")
        ]

        for value, type_hint, expected in test_cases:
            result = config_handler.convert_config_value(value, type_hint)
            assert result == expected

    def test_config_validation_schema(self, config_handler):
        """Test configuration validation against schema"""
        config_data = {
            "database": {
                "host": "localhost",
                "port": 5432,
                "name": "signal_service"
            },
            "external_functions": {
                "max_memory_mb": 128,
                "timeout_seconds": 30
            }
        }

        schema = {
            "database": {
                "required": ["host", "port", "name"],
                "types": {"port": int, "host": str, "name": str}
            },
            "external_functions": {
                "required": ["max_memory_mb", "timeout_seconds"],
                "types": {"max_memory_mb": int, "timeout_seconds": int},
                "constraints": {
                    "max_memory_mb": {"min": 16, "max": 512},
                    "timeout_seconds": {"min": 1, "max": 300}
                }
            }
        }

        # Should pass validation
        is_valid, errors = config_handler.validate_config_schema(config_data, schema)
        assert is_valid is True
        assert len(errors) == 0

    def test_config_validation_schema_failures(self, config_handler):
        """Test configuration validation failures"""
        invalid_config = {
            "database": {
                "host": "localhost",
                # Missing required "port" and "name"
            },
            "external_functions": {
                "max_memory_mb": 1024,  # Exceeds max limit
                "timeout_seconds": -5   # Below min limit
            }
        }

        schema = {
            "database": {
                "required": ["host", "port", "name"],
                "types": {"port": int, "host": str, "name": str}
            },
            "external_functions": {
                "required": ["max_memory_mb", "timeout_seconds"],
                "types": {"max_memory_mb": int, "timeout_seconds": int},
                "constraints": {
                    "max_memory_mb": {"min": 16, "max": 512},
                    "timeout_seconds": {"min": 1, "max": 300}
                }
            }
        }

        is_valid, errors = config_handler.validate_config_schema(invalid_config, schema)
        assert is_valid is False
        assert len(errors) > 0
        assert any("missing required" in error.lower() for error in errors)
        assert any("exceeds maximum" in error.lower() for error in errors)


class TestConfigUpdateManager:
    """Test dynamic configuration update management"""

    @pytest.fixture
    def update_manager(self):
        """Create config update manager instance"""
        return ConfigUpdateManager()

    @pytest.fixture
    def mock_config_cache(self):
        """Mock configuration cache"""
        return {
            "signal_processing.batch_size": 1000,
            "indicators.default_period": 14,
            "external_functions.max_memory_mb": 128
        }

    def test_config_update_notification(self, update_manager, mock_config_cache):
        """Test configuration update notification handling"""
        with patch.object(update_manager, '_current_config', mock_config_cache):
            update_notification = {
                "key": "signal_processing.batch_size",
                "old_value": "1000",
                "new_value": "2000",
                "timestamp": datetime.now().isoformat(),
                "source": "config_service"
            }

            update_manager.process_config_update(update_notification)

            # Should update cached value
            assert update_manager._current_config["signal_processing.batch_size"] == 2000

    def test_config_update_validation(self, update_manager):
        """Test configuration update validation"""
        # Valid update
        valid_update = {
            "key": "external_functions.max_memory_mb",
            "new_value": "256",
            "type": "integer"
        }

        is_valid, error = update_manager.validate_config_update(valid_update)
        assert is_valid is True
        assert error is None

        # Invalid update - negative memory limit
        invalid_update = {
            "key": "external_functions.max_memory_mb",
            "new_value": "-10",
            "type": "integer"
        }

        is_valid, error = update_manager.validate_config_update(invalid_update)
        assert is_valid is False
        assert error is not None

    def test_config_rollback(self, update_manager, mock_config_cache):
        """Test configuration rollback functionality"""
        with patch.object(update_manager, '_current_config', mock_config_cache.copy()):
            with patch.object(update_manager, '_config_history', []):

                original_value = mock_config_cache["signal_processing.batch_size"]

                # Apply update
                update = {
                    "key": "signal_processing.batch_size",
                    "new_value": "2000"
                }
                update_manager.process_config_update(update)

                # Verify update applied
                assert update_manager._current_config["signal_processing.batch_size"] == 2000

                # Rollback
                update_manager.rollback_config_update("signal_processing.batch_size")

                # Verify rollback
                assert update_manager._current_config["signal_processing.batch_size"] == original_value

    def test_config_update_callbacks(self, update_manager):
        """Test configuration update callbacks"""
        callback_called = False
        callback_data = None

        def test_callback(key, old_value, new_value):
            nonlocal callback_called, callback_data
            callback_called = True
            callback_data = {"key": key, "old_value": old_value, "new_value": new_value}

        # Register callback
        update_manager.register_config_callback("signal_processing.*", test_callback)

        # Process update
        update = {
            "key": "signal_processing.batch_size",
            "old_value": "1000",
            "new_value": "2000"
        }
        update_manager.process_config_update(update)

        # Verify callback was called
        assert callback_called is True
        assert callback_data["key"] == "signal_processing.batch_size"
        assert callback_data["new_value"] == 2000

    def test_config_update_impact_analysis(self, update_manager):
        """Test configuration update impact analysis"""
        update = {
            "key": "external_functions.max_memory_mb",
            "old_value": "128",
            "new_value": "256"
        }

        impact = update_manager.analyze_update_impact(update)

        assert impact["affected_components"] is not None
        assert impact["restart_required"] is not None
        assert impact["risk_level"] in ["low", "medium", "high"]
        assert "description" in impact


class TestSecretManagement:
    """Test secure handling of secrets in configuration"""

    def test_secret_detection(self):
        """Test automatic secret detection"""
        config_handler = ConfigHandler()

        secret_keys = [
            "password", "secret", "key", "token", "credential",
            "DATABASE_PASSWORD", "JWT_SECRET", "API_KEY"
        ]

        regular_keys = [
            "database_host", "port", "timeout", "batch_size"
        ]

        for key in secret_keys:
            assert config_handler.is_secret_key(key) is True

        for key in regular_keys:
            assert config_handler.is_secret_key(key) is False

    def test_secret_encryption(self):
        """Test secret encryption/decryption"""
        config_handler = ConfigHandler()

        plain_secret = "my_secret_password_123"

        # Encrypt
        encrypted = config_handler.encrypt_secret(plain_secret)
        assert encrypted != plain_secret
        assert len(encrypted) > len(plain_secret)

        # Decrypt
        decrypted = config_handler.decrypt_secret(encrypted)
        assert decrypted == plain_secret

    def test_secret_environment_variable_handling(self):
        """Test handling of secrets from environment variables"""
        with patch.dict(os.environ, {
            "DATABASE_PASSWORD": "secret_db_password",
            "JWT_SECRET": "secret_jwt_key",
            "REGULAR_CONFIG": "not_a_secret"
        }):
            config = SignalServiceConfig()

            # Secrets should be accessible but redacted in logs
            assert hasattr(config, 'DATABASE_PASSWORD')
            assert hasattr(config, 'JWT_SECRET')

            # Test redaction
            config_dict = config.to_dict(redact_secrets=True)
            assert config_dict["DATABASE_PASSWORD"] == "[REDACTED]"
            assert config_dict["JWT_SECRET"] == "[REDACTED]"
            assert config_dict["REGULAR_CONFIG"] == "not_a_secret"


class TestConfigurationIntegration:
    """Test configuration integration with other components"""

    def test_config_service_integration(self):
        """Test integration with config service"""
        with patch('app.clients.config_service_client.ConfigServiceClient') as mock_client:
            mock_client_instance = Mock()
            mock_client.return_value = mock_client_instance

            # Mock config service responses
            mock_client_instance.get_config.side_effect = lambda key: {
                "signal_service.batch_size": {"value": "2000", "type": "integer"},
                "signal_service.enable_caching": {"value": "true", "type": "boolean"},
            }.get(key, {"value": None, "type": "string"})

            config_handler = ConfigHandler()

            batch_size = config_handler.get_config_from_service("signal_service.batch_size")
            enable_caching = config_handler.get_config_from_service("signal_service.enable_caching")

            assert batch_size == 2000
            assert enable_caching is True

    def test_config_hot_reload(self):
        """Test configuration hot reload functionality"""
        config_handler = ConfigHandler()

        # Mock file watcher
        with patch('app.services.config_handler.FileWatcher') as mock_watcher:
            mock_watcher_instance = Mock()
            mock_watcher.return_value = mock_watcher_instance

            config_handler.enable_hot_reload("/path/to/config.json")

            # Verify file watcher was setup
            mock_watcher.assert_called_once_with("/path/to/config.json")
            mock_watcher_instance.start.assert_called_once()

    def test_config_distributed_cache(self):
        """Test configuration distributed caching"""
        with patch('app.core.redis_manager.get_redis_client') as mock_redis:
            mock_redis_instance = AsyncMock()
            mock_redis.return_value = mock_redis_instance

            config_handler = ConfigHandler()

            # Test cache set
            asyncio.run(config_handler.set_cached_config("test_key", "test_value"))

            # Test cache get
            mock_redis_instance.get.return_value = '"test_value"'  # JSON encoded
            result = asyncio.run(config_handler.get_cached_config("test_key"))

            assert result == "test_value"
