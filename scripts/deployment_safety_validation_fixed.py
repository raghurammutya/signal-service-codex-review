#!/usr/bin/env python3
"""
Deployment Safety Validation Script - Config Service Architecture

Validates signal_service deployment readiness using StocksBlitz config service pattern.
Only validates bootstrap environment variables; all other config from config service.
"""
import json
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('deployment_validation.log')
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of a validation check."""
    name: str
    passed: bool
    message: str
    critical: bool = False
    suggestions: list[str] = None

    def __post_init__(self):
        if self.suggestions is None:
            self.suggestions = []


class ConfigServiceDeploymentValidator:
    """Validates deployment using StocksBlitz config service architecture."""

    def __init__(self, environment: str = None):
        self.environment = environment or os.getenv("ENVIRONMENT", "production")
        self.validation_results: list[ValidationResult] = []
        self.critical_failures = 0
        self.warnings = 0

    def add_result(self, result: ValidationResult):
        """Add a validation result."""
        self.validation_results.append(result)
        if not result.passed:
            if result.critical:
                self.critical_failures += 1
            else:
                self.warnings += 1

    def validate_bootstrap_environment_variables(self) -> list[ValidationResult]:
        """Validate only the 4 required bootstrap environment variables."""
        logger.info("Validating bootstrap environment variables...")

        # ONLY 4 BOOTSTRAP VARIABLES (per docker-compose.production.yml pattern)
        required_bootstrap_vars = {
            "ENVIRONMENT": "Environment selection (production/staging/development)",
            "CONFIG_SERVICE_URL": "Config service location (http://config-service:8100)",
            "INTERNAL_API_KEY": "StocksBlitz service-to-service authentication key",
            "SERVICE_NAME": "Service identification (signal_service)"
        }

        results = []

        for var, description in required_bootstrap_vars.items():
            value = os.getenv(var)

            if not value or not value.strip():
                results.append(ValidationResult(
                    name=f"bootstrap_{var.lower()}",
                    passed=False,
                    message=f"Bootstrap variable {var} not set: {description}",
                    critical=True,
                    suggestions=[
                        f"set {var} in docker-compose.production.yml environment section",
                        f"Value should be: {description}",
                        "Follow StocksBlitz docker-compose production pattern"
                    ]
                ))
            else:
                # Validate specific bootstrap variables
                if var == "ENVIRONMENT":
                    if value not in ["development", "staging", "production"]:
                        results.append(ValidationResult(
                            name="bootstrap_environment_value",
                            passed=False,
                            message=f"ENVIRONMENT has invalid value: {value}",
                            critical=True,
                            suggestions=["Use 'development', 'staging', or 'production'"]
                        ))
                    else:
                        results.append(ValidationResult(
                            name="bootstrap_environment_valid",
                            passed=True,
                            message=f"ENVIRONMENT properly set to: {value}"
                        ))

                elif var == "CONFIG_SERVICE_URL":
                    if not (value.startswith(('http://', 'https://'))):
                        results.append(ValidationResult(
                            name="bootstrap_config_url_format",
                            passed=False,
                            message=f"CONFIG_SERVICE_URL invalid format: {value}",
                            critical=True,
                            suggestions=["Use format: http://config-service:8100"]
                        ))
                    else:
                        results.append(ValidationResult(
                            name="bootstrap_config_url_valid",
                            passed=True,
                            message=f"CONFIG_SERVICE_URL properly formatted: {value}"
                        ))

                elif var == "SERVICE_NAME":
                    if value != "signal_service":
                        results.append(ValidationResult(
                            name="bootstrap_service_name_value",
                            passed=False,
                            message=f"SERVICE_NAME should be 'signal_service', got: {value}",
                            critical=False,
                            suggestions=["set SERVICE_NAME=signal_service"]
                        ))
                    else:
                        results.append(ValidationResult(
                            name="bootstrap_service_name_valid",
                            passed=True,
                            message="SERVICE_NAME correctly set to signal_service"
                        ))

                elif var == "INTERNAL_API_KEY":
                    if len(value) < 32:
                        results.append(ValidationResult(
                            name="bootstrap_api_key_strength",
                            passed=False,
                            message="INTERNAL_API_KEY appears too short for security",
                            critical=False,
                            suggestions=["Use StocksBlitz standard internal API key"]
                        ))
                    else:
                        results.append(ValidationResult(
                            name="bootstrap_api_key_valid",
                            passed=True,
                            message="INTERNAL_API_KEY properly configured"
                        ))

        return results

    def validate_config_service_connectivity(self) -> list[ValidationResult]:
        """Test connection to config service."""
        logger.info("Validating config service connectivity...")

        results = []
        config_service_url = os.getenv("CONFIG_SERVICE_URL")
        internal_api_key = os.getenv("INTERNAL_API_KEY")

        if not config_service_url or not internal_api_key:
            results.append(ValidationResult(
                name="config_service_prerequisites",
                passed=False,
                message="Cannot test config service: missing bootstrap variables",
                critical=True,
                suggestions=["Ensure CONFIG_SERVICE_URL and INTERNAL_API_KEY are set"]
            ))
            return results

        try:
            import httpx

            with httpx.Client(timeout=10) as client:
                # Test health endpoint
                health_response = client.get(
                    f"{config_service_url}/api/v1/health",
                    headers={"X-Internal-API-Key": internal_api_key}
                )

                if health_response.status_code == 200:
                    results.append(ValidationResult(
                        name="config_service_health",
                        passed=True,
                        message="Config service health check passed"
                    ))

                    # Test configuration access
                    try:
                        config_response = client.get(
                            f"{config_service_url}/api/v1/config/DATABASE_URL",
                            headers={
                                "X-Internal-API-Key": internal_api_key,
                                "X-Environment": self.environment
                            }
                        )

                        if config_response.status_code == 200:
                            results.append(ValidationResult(
                                name="config_service_access",
                                passed=True,
                                message="Config service configuration access working"
                            ))
                        else:
                            results.append(ValidationResult(
                                name="config_service_access",
                                passed=False,
                                message=f"Config access failed: {config_response.status_code}",
                                critical=True,
                                suggestions=[
                                    "Ensure configuration is populated in config service",
                                    "Check internal API key permissions"
                                ]
                            ))

                    except Exception as e:
                        results.append(ValidationResult(
                            name="config_service_access_test",
                            passed=False,
                            message=f"Config access test failed: {e}",
                            critical=False,
                            suggestions=["Check config service configuration"]
                        ))

                else:
                    results.append(ValidationResult(
                        name="config_service_health",
                        passed=False,
                        message=f"Config service unhealthy: {health_response.status_code}",
                        critical=True,
                        suggestions=[
                            "Start config service container",
                            "Check config service logs",
                            "Verify config service URL"
                        ]
                    ))

        except Exception as e:
            results.append(ValidationResult(
                name="config_service_connectivity",
                passed=False,
                message=f"Cannot reach config service: {e}",
                critical=True,
                suggestions=[
                    "Ensure config service is running",
                    "Check docker network connectivity",
                    "Verify CONFIG_SERVICE_URL is correct"
                ]
            ))

        return results

    def validate_architecture_compliance(self) -> list[ValidationResult]:
        """Validate compliance with StocksBlitz config service architecture."""
        logger.info("Validating architecture compliance...")

        results = []

        # Check for old environment variables that should NOT be present
        deprecated_env_vars = [
            "DATABASE_URL", "REDIS_URL", "CORS_ALLOWED_ORIGINS",
            "ALERT_SERVICE_URL", "COMMS_SERVICE_URL", "MARKETPLACE_SERVICE_URL",
            "JWT_SECRET_KEY", "GATEWAY_SECRET", "MINIO_ACCESS_KEY", "MINIO_SECRET_KEY"
        ]

        found_deprecated = []
        for var in deprecated_env_vars:
            if os.getenv(var):
                found_deprecated.append(var)

        if found_deprecated:
            results.append(ValidationResult(
                name="architecture_deprecated_env_vars",
                passed=False,
                message=f"Found deprecated environment variables: {', '.join(found_deprecated)}",
                critical=False,
                suggestions=[
                    "Remove deprecated environment variables from docker-compose",
                    "These should come from config service instead",
                    "Follow StocksBlitz config service architecture pattern"
                ]
            ))
        else:
            results.append(ValidationResult(
                name="architecture_compliance",
                passed=True,
                message="No deprecated environment variables found - architecture compliant"
            ))

        return results

    def run_all_validations(self) -> bool:
        """Run all config service architecture validations."""
        logger.info(f"Starting config service deployment validation for environment: {self.environment}")
        start_time = datetime.now()

        # Updated validation methods for config service architecture
        validation_methods = [
            self.validate_bootstrap_environment_variables,
            self.validate_config_service_connectivity,
            self.validate_architecture_compliance
        ]

        for method in validation_methods:
            try:
                results = method()
                for result in results:
                    self.add_result(result)
            except Exception as e:
                logger.error(f"Validation method {method.__name__} failed: {e}")
                self.add_result(ValidationResult(
                    name=f"{method.__name__}_error",
                    passed=False,
                    message=f"Validation method failed: {e}",
                    critical=True,
                    suggestions=["Check validation method implementation"]
                ))

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        logger.info(f"Deployment validation completed in {duration:.2f}s")

        # Print results
        self.print_summary()

        # Return success/failure
        return self.critical_failures == 0

    def print_summary(self):
        """Print validation summary."""
        passed = len([r for r in self.validation_results if r.passed])
        total = len(self.validation_results)

        print("\n" + "="*80)
        print(f"CONFIG SERVICE DEPLOYMENT VALIDATION SUMMARY ({self.environment.upper()})")
        print("="*80)

        if self.critical_failures == 0:
            print("Overall Status: ✅ PASS")
        else:
            print("Overall Status: ❌ FAIL")

        print(f"Environment: {self.environment}")
        print(f"Total Checks: {total}")
        print(f"Passed: {passed}")
        print(f"Warnings: {self.warnings}")
        print(f"Critical Failures: {self.critical_failures}")

        if self.critical_failures > 0:
            print("\n🚨 CRITICAL FAILURES:")
            for result in self.validation_results:
                if not result.passed and result.critical:
                    print(f"  ❌ {result.name}: {result.message}")
                    for suggestion in result.suggestions:
                        print(f"     💡 {suggestion}")

        if self.warnings > 0:
            print("\n⚠️  WARNINGS:")
            for result in self.validation_results:
                if not result.passed and not result.critical:
                    print(f"  ⚠️  {result.name}: {result.message}")
                    for suggestion in result.suggestions:
                        print(f"     💡 {suggestion}")

        print("\n" + "="*80)

        if self.critical_failures == 0:
            print("✅ Deployment validation PASSED for", self.environment)
            print("🎯 Config service architecture compliance verified")
        else:
            print("❌ Deployment validation FAILED for", self.environment)
            print("🚨 Fix critical failures before deployment")


def main():
    """Main execution function."""
    import argparse

    parser = argparse.ArgumentParser(description="StocksBlitz Config Service Deployment Validation")
    parser.add_argument("--environment", default=None, help="Environment (development/staging/production)")

    args = parser.parse_args()

    validator = ConfigServiceDeploymentValidator(environment=args.environment)
    success = validator.run_all_validations()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
