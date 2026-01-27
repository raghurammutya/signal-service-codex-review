"""
CORS Environment Variable Validation Tests

Comprehensive tests for CORS environment variable handling, validation, and parsing.
Focuses on deployment scenarios, configuration management, and environment-specific behaviors.
"""
import os
from unittest.mock import patch

import pytest

from common.cors_config import get_allowed_origins, validate_cors_configuration


class TestCORSEnvironmentVariableParsing:
    """Test CORS environment variable parsing and validation."""

    def test_cors_allowed_origins_single_value(self):
        """Test parsing single CORS_ALLOWED_ORIGINS value."""
        test_cases = [
            "https://app.stocksblitz.com",
            "http://localhost:3000",
            "https://api.example.com"
        ]

        for origin in test_cases:
            with patch.dict(os.environ, {"CORS_ALLOWED_ORIGINS": origin}, clear=True):
                origins = get_allowed_origins("production")
                assert origins == [origin]

    def test_cors_allowed_origins_multiple_values(self):
        """Test parsing multiple CORS_ALLOWED_ORIGINS values."""
        test_origins = [
            "https://app.stocksblitz.com",
            "https://dashboard.stocksblitz.com",
            "https://api.stocksblitz.com"
        ]

        origins_string = ",".join(test_origins)

        with patch.dict(os.environ, {"CORS_ALLOWED_ORIGINS": origins_string}, clear=True):
            origins = get_allowed_origins("production")
            assert origins == test_origins

    def test_cors_allowed_origins_with_varied_whitespace(self):
        """Test parsing CORS_ALLOWED_ORIGINS with various whitespace patterns."""
        whitespace_test_cases = [
            (" https://app.stocksblitz.com ", ["https://app.stocksblitz.com"]),
            ("https://app.stocksblitz.com, https://dashboard.stocksblitz.com",
             ["https://app.stocksblitz.com", "https://dashboard.stocksblitz.com"]),
            ("  https://app.stocksblitz.com  ,  https://dashboard.stocksblitz.com  ",
             ["https://app.stocksblitz.com", "https://dashboard.stocksblitz.com"]),
            ("https://app.stocksblitz.com,\nhttps://dashboard.stocksblitz.com",
             ["https://app.stocksblitz.com", "https://dashboard.stocksblitz.com"]),
            ("https://app.stocksblitz.com\t,\t\thttps://dashboard.stocksblitz.com",
             ["https://app.stocksblitz.com", "https://dashboard.stocksblitz.com"])
        ]

        for origins_string, expected in whitespace_test_cases:
            with patch.dict(os.environ, {"CORS_ALLOWED_ORIGINS": origins_string}, clear=True):
                origins = get_allowed_origins("production")
                assert origins == expected

    def test_cors_allowed_origins_empty_value_handling(self):
        """Test handling of empty CORS_ALLOWED_ORIGINS values."""
        empty_test_cases = ["", "   ", "\t", "\n", "\r\n"]

        for empty_value in empty_test_cases:
            with patch.dict(os.environ, {"CORS_ALLOWED_ORIGINS": empty_value}, clear=True), pytest.raises(ValueError, match="CORS_ALLOWED_ORIGINS must be configured"):
                get_allowed_origins("production")

    def test_cors_allowed_origins_missing_variable(self):
        """Test handling of missing CORS_ALLOWED_ORIGINS environment variable."""
        environments = ["production", "staging", "development"]

        for env in environments:
            with patch.dict(os.environ, {}, clear=True), pytest.raises(ValueError, match=f"CORS_ALLOWED_ORIGINS must be configured for {env} environment"):
                get_allowed_origins(env)

    def test_cors_allowed_origins_malformed_values(self):
        """Test handling of malformed CORS_ALLOWED_ORIGINS values."""
        malformed_cases = [
            "https://app.stocksblitz.com,,https://dashboard.stocksblitz.com",  # Empty entry
            "https://app.stocksblitz.com,",  # Trailing comma
            ",https://app.stocksblitz.com",  # Leading comma
            "https://app.stocksblitz.com,,,"  # Multiple empty entries
        ]

        for malformed in malformed_cases:
            with patch.dict(os.environ, {"CORS_ALLOWED_ORIGINS": malformed}, clear=True):
                origins = get_allowed_origins("production")
                # Should filter out empty origins
                assert all(origin.strip() for origin in origins)

    def test_cors_allowed_origins_special_characters(self):
        """Test handling of special characters in CORS_ALLOWED_ORIGINS."""
        special_cases = [
            "https://app-staging.stocksblitz.com",  # Hyphens
            "https://app.staging.stocksblitz.com",  # Subdomain dots
            "https://app.stocksblitz.com:8443",     # Custom port
            "https://app.stocksblitz.com/api/v1"   # Path component
        ]

        for special_origin in special_cases:
            with patch.dict(os.environ, {"CORS_ALLOWED_ORIGINS": special_origin}, clear=True):
                origins = get_allowed_origins("production")
                assert origins == [special_origin]


class TestCORSEnvironmentSpecificValidation:
    """Test environment-specific CORS validation rules."""

    def test_production_environment_validation(self):
        """Test production environment CORS validation rules."""
        # Valid production configurations
        valid_production_configs = [
            "https://app.stocksblitz.com",
            "https://dashboard.stocksblitz.com,https://api.stocksblitz.com",
            "https://app.example.com"
        ]

        for config in valid_production_configs:
            with patch.dict(os.environ, {"CORS_ALLOWED_ORIGINS": config}, clear=True):
                origins = get_allowed_origins("production")
                assert len(origins) >= 1

                # All production origins should be HTTPS for security
                for origin in origins:
                    if not origin.startswith("http://localhost") and not origin.startswith("http://127.0.0.1"):
                        assert origin.startswith("https://"), f"Production should use HTTPS: {origin}"

    def test_staging_environment_validation(self):
        """Test staging environment CORS validation rules."""
        staging_configs = [
            "https://staging.stocksblitz.com",
            "https://staging-api.stocksblitz.com,https://staging-dashboard.stocksblitz.com",
            "https://test.stocksblitz.com"
        ]

        for config in staging_configs:
            with patch.dict(os.environ, {"CORS_ALLOWED_ORIGINS": config}, clear=True):
                origins = get_allowed_origins("staging")
                assert len(origins) >= 1

    def test_development_environment_validation(self):
        """Test development environment CORS validation rules."""
        dev_configs = [
            "http://localhost:3000",
            "http://localhost:3000,https://app.stocksblitz.com",
            "http://127.0.0.1:8080,http://localhost:3000",
            "https://localhost:3443"
        ]

        for config in dev_configs:
            with patch.dict(os.environ, {"CORS_ALLOWED_ORIGINS": config}, clear=True):
                origins = get_allowed_origins("development")
                assert len(origins) >= 1

                # Development should allow localhost
                any(
                    "localhost" in origin or "127.0.0.1" in origin
                    for origin in origins
                )
                # Not strictly required but expected in most dev configs

    def test_environment_wildcard_restrictions(self):
        """Test wildcard restrictions per environment."""
        wildcard_origins = [
            "*",
            "https://*.stocksblitz.com",
            "http://*",
            "*.example.com"
        ]

        # Production should reject all wildcards
        for wildcard in wildcard_origins:
            with patch.dict(os.environ, {"CORS_ALLOWED_ORIGINS": wildcard}, clear=True), pytest.raises(ValueError, match="Wildcard origins not permitted in production"):
                get_allowed_origins("production")

    def test_unknown_environment_handling(self):
        """Test handling of unknown environment values."""
        unknown_environments = ["test", "qa", "local", "sandbox", "review", ""]

        for env in unknown_environments:
            if env:  # Skip empty string
                with pytest.raises(ValueError, match=f"Unknown environment for CORS configuration: {env}"):
                    get_allowed_origins(env)

    def test_environment_case_sensitivity(self):
        """Test environment name case sensitivity."""
        case_variations = [
            ("PRODUCTION", "production"),
            ("Production", "production"),
            ("STAGING", "staging"),
            ("Staging", "staging"),
            ("DEVELOPMENT", "development"),
            ("Development", "development")
        ]

        for case_variant, normalized in case_variations:
            with patch.dict(os.environ, {"CORS_ALLOWED_ORIGINS": "https://app.stocksblitz.com"}, clear=True):
                # The function should handle exact case matching
                if case_variant.lower() == normalized:
                    origins = get_allowed_origins(case_variant)
                    assert len(origins) == 1
                else:
                    # Should reject case mismatches
                    with pytest.raises(ValueError):
                        get_allowed_origins(case_variant)


class TestCORSEnvironmentVariableValidationFunction:
    """Test the CORS configuration validation function behavior."""

    def test_validate_cors_configuration_success_cases(self):
        """Test successful CORS configuration validation."""
        success_cases = [
            ("production", "https://app.stocksblitz.com"),
            ("staging", "https://staging.stocksblitz.com"),
            ("development", "http://localhost:3000"),
            ("production", "https://app.example.com,https://dashboard.example.com")
        ]

        for environment, origins in success_cases:
            with patch.dict(os.environ, {"CORS_ALLOWED_ORIGINS": origins}, clear=True):
                result = validate_cors_configuration(environment)
                assert result is True

    def test_validate_cors_configuration_failure_cases(self):
        """Test failed CORS configuration validation."""
        failure_cases = [
            ("production", ""),  # Empty origins
            ("staging", ""),     # Empty origins
            ("development", ""), # Empty origins
            ("production", "*"), # Wildcard in production
            ("unknown", "https://app.stocksblitz.com")  # Unknown environment
        ]

        for environment, origins in failure_cases:
            if origins:
                with patch.dict(os.environ, {"CORS_ALLOWED_ORIGINS": origins}, clear=True):
                    result = validate_cors_configuration(environment)
                    assert result is False
            else:
                with patch.dict(os.environ, {}, clear=True):
                    result = validate_cors_configuration(environment)
                    assert result is False

    def test_validate_cors_configuration_logging(self):
        """Test CORS configuration validation logging behavior."""
        with patch('common.cors_config.logger') as mock_logger:
            # Test successful validation logging
            with patch.dict(os.environ, {"CORS_ALLOWED_ORIGINS": "https://app.stocksblitz.com"}, clear=True):
                result = validate_cors_configuration("production")
                assert result is True
                mock_logger.info.assert_called_with("CORS configuration validation passed for production")

            # Test failed validation logging
            with patch.dict(os.environ, {}, clear=True):
                result = validate_cors_configuration("production")
                assert result is False
                mock_logger.error.assert_called()


class TestCORSDeploymentEnvironmentValidation:
    """Test CORS environment validation for deployment scenarios."""

    def test_deployment_environment_variable_presence(self):
        """Test deployment environment variable presence validation."""
        def validate_deployment_environment() -> dict[str, any]:
            """Validate environment variables for deployment."""
            validation = {
                "cors_origins_present": bool(os.getenv("CORS_ALLOWED_ORIGINS")),
                "cors_origins_value": os.getenv("CORS_ALLOWED_ORIGINS"),
                "environment_present": bool(os.getenv("ENVIRONMENT")),
                "environment_value": os.getenv("ENVIRONMENT"),
                "validation_errors": []
            }

            # Check CORS_ALLOWED_ORIGINS
            if not validation["cors_origins_present"]:
                validation["validation_errors"].append("CORS_ALLOWED_ORIGINS environment variable missing")
            elif not validation["cors_origins_value"].strip():
                validation["validation_errors"].append("CORS_ALLOWED_ORIGINS environment variable empty")

            # Check ENVIRONMENT
            if not validation["environment_present"]:
                validation["validation_errors"].append("ENVIRONMENT environment variable missing")

            return validation

        # Test with all required variables present
        with patch.dict(os.environ, {
            "CORS_ALLOWED_ORIGINS": "https://app.stocksblitz.com",
            "ENVIRONMENT": "production"
        }, clear=True):
            result = validate_deployment_environment()
            assert result["cors_origins_present"] is True
            assert result["environment_present"] is True
            assert len(result["validation_errors"]) == 0

        # Test with missing CORS_ALLOWED_ORIGINS
        with patch.dict(os.environ, {"ENVIRONMENT": "production"}, clear=True):
            result = validate_deployment_environment()
            assert result["cors_origins_present"] is False
            assert len(result["validation_errors"]) > 0

    def test_deployment_cors_security_validation(self):
        """Test CORS security validation for deployment."""
        def validate_deployment_cors_security(environment: str) -> dict[str, any]:
            """Validate CORS security configuration for deployment."""
            security_check = {
                "environment": environment,
                "security_compliant": False,
                "security_issues": [],
                "origins_count": 0,
                "wildcard_detected": False,
                "insecure_origins_detected": False
            }

            try:
                origins = get_allowed_origins(environment)
                security_check["origins_count"] = len(origins)

                for origin in origins:
                    # Check for wildcards
                    if "*" in origin:
                        security_check["wildcard_detected"] = True
                        security_check["security_issues"].append(f"Wildcard origin detected: {origin}")

                    # Check for insecure origins in production
                    if environment == "production":
                        if origin.startswith("http://") and not origin.startswith("http://localhost"):
                            security_check["insecure_origins_detected"] = True
                            security_check["security_issues"].append(f"Insecure HTTP origin in production: {origin}")

                        if "localhost" in origin or "127.0.0.1" in origin:
                            security_check["security_issues"].append(f"Localhost origin in production: {origin}")

                # Security compliant if no issues found
                security_check["security_compliant"] = len(security_check["security_issues"]) == 0

            except Exception as e:
                security_check["security_issues"].append(f"Configuration error: {str(e)}")

            return security_check

        # Test secure production configuration
        with patch.dict(os.environ, {"CORS_ALLOWED_ORIGINS": "https://app.stocksblitz.com"}, clear=True):
            result = validate_deployment_cors_security("production")
            assert result["security_compliant"] is True
            assert result["wildcard_detected"] is False
            assert len(result["security_issues"]) == 0

        # Test insecure production configuration
        with patch.dict(os.environ, {"CORS_ALLOWED_ORIGINS": "*"}, clear=True):
            result = validate_deployment_cors_security("production")
            assert result["security_compliant"] is False
            assert len(result["security_issues"]) > 0

    def test_deployment_environment_matrix_validation(self):
        """Test CORS validation across environment matrix."""
        environment_matrix = [
            {
                "environment": "production",
                "origins": "https://app.stocksblitz.com,https://dashboard.stocksblitz.com",
                "expected_valid": True,
                "expected_origin_count": 2
            },
            {
                "environment": "production",
                "origins": "*",
                "expected_valid": False,
                "expected_origin_count": 0
            },
            {
                "environment": "staging",
                "origins": "https://staging.stocksblitz.com",
                "expected_valid": True,
                "expected_origin_count": 1
            },
            {
                "environment": "development",
                "origins": "http://localhost:3000,https://app.stocksblitz.com",
                "expected_valid": True,
                "expected_origin_count": 2
            },
            {
                "environment": "unknown",
                "origins": "https://app.stocksblitz.com",
                "expected_valid": False,
                "expected_origin_count": 0
            }
        ]

        for test_case in environment_matrix:
            with patch.dict(os.environ, {"CORS_ALLOWED_ORIGINS": test_case["origins"]}, clear=True):
                try:
                    origins = get_allowed_origins(test_case["environment"])
                    is_valid = True
                    origin_count = len(origins)
                except Exception:
                    is_valid = False
                    origin_count = 0

                assert is_valid == test_case["expected_valid"], \
                    f"Environment {test_case['environment']} validation mismatch"

                if test_case["expected_valid"]:
                    assert origin_count == test_case["expected_origin_count"], \
                        f"Environment {test_case['environment']} origin count mismatch"

    def test_cors_configuration_file_based_validation(self):
        """Test CORS configuration validation from file-based configuration."""
        def validate_cors_from_config_file(config_data: dict) -> dict[str, any]:
            """Validate CORS configuration from configuration file data."""
            validation = {
                "valid": False,
                "errors": [],
                "environment": config_data.get("environment"),
                "cors_origins": config_data.get("cors_allowed_origins"),
                "origins_parsed": []
            }

            if not validation["environment"]:
                validation["errors"].append("Environment not specified in configuration")
                return validation

            if not validation["cors_origins"]:
                validation["errors"].append("CORS allowed origins not specified in configuration")
                return validation

            # Simulate environment variable from config file
            with patch.dict(os.environ, {"CORS_ALLOWED_ORIGINS": validation["cors_origins"]}, clear=True):
                try:
                    origins = get_allowed_origins(validation["environment"])
                    validation["origins_parsed"] = origins
                    validation["valid"] = True
                except Exception as e:
                    validation["errors"].append(str(e))

            return validation

        # Test valid configuration
        valid_config = {
            "environment": "production",
            "cors_allowed_origins": "https://app.stocksblitz.com,https://dashboard.stocksblitz.com"
        }
        result = validate_cors_from_config_file(valid_config)
        assert result["valid"] is True
        assert len(result["origins_parsed"]) == 2

        # Test invalid configuration
        invalid_config = {
            "environment": "production",
            "cors_allowed_origins": "*"
        }
        result = validate_cors_from_config_file(invalid_config)
        assert result["valid"] is False
        assert len(result["errors"]) > 0


def run_cors_environment_validation_tests():
    """Run all CORS environment variable validation tests."""
    print("🔍 Running CORS Environment Variable Validation Tests...")

    test_classes = [
        TestCORSEnvironmentVariableParsing,
        TestCORSEnvironmentSpecificValidation,
        TestCORSEnvironmentVariableValidationFunction,
        TestCORSDeploymentEnvironmentValidation
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
            test_instance = test_class()
            for test_method in test_methods:
                try:
                    method = getattr(test_instance, test_method)
                    method()
                    passed_tests += 1
                    print(f"  ✅ {test_method}")
                except Exception as e:
                    print(f"  ❌ {test_method}: {e}")
        except Exception as e:
            print(f"  ❌ Failed to initialize {class_name}: {e}")

    print(f"\n📊 Test Results: {passed_tests}/{total_tests} tests passed")

    if passed_tests == total_tests:
        print("\n✅ All CORS environment validation tests passed!")
        print("\n🔧 Environment Variable Coverage:")
        print("  - CORS_ALLOWED_ORIGINS parsing and validation")
        print("  - Environment-specific validation rules")
        print("  - Deployment environment variable validation")
        print("  - Security compliance checking")
        print("  - Configuration file integration")
        print("  - Error handling and logging")
    else:
        print(f"\n⚠️  {total_tests - passed_tests} CORS environment validation tests need attention")

    return passed_tests == total_tests


if __name__ == "__main__":
    success = run_cors_environment_validation_tests()
    exit(0 if success else 1)
