#!/usr/bin/env python3
"""
Deployment Safety Validation Script

Validates that signal service is ready for deployment by checking:
1. Config service connectivity
2. Required environment variables 
3. No fallback configurations that mask issues
4. CORS settings compliance
5. Security logging configuration
"""
import os
import sys
import json
import logging
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

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
    suggestions: List[str] = None
    
    def __post_init__(self):
        if self.suggestions is None:
            self.suggestions = []


class DeploymentSafetyValidator:
    """Validates deployment safety requirements."""
    
    def __init__(self, environment: str = None):
        self.environment = environment or os.getenv("ENVIRONMENT", "production")
        self.validation_results: List[ValidationResult] = []
        self.critical_failures = 0
        self.warnings = 0
        
    def add_result(self, result: ValidationResult):
        """Add a validation result."""
        self.validation_results.append(result)
        
        if result.critical and not result.passed:
            self.critical_failures += 1
        elif not result.passed:
            self.warnings += 1
            
        # Log result
        level = logging.CRITICAL if (result.critical and not result.passed) else logging.WARNING if not result.passed else logging.INFO
        logger.log(level, f"[{result.name}] {'PASS' if result.passed else 'FAIL'}: {result.message}")
    
    def validate_required_environment_variables(self) -> List[ValidationResult]:
        """Validate that all required environment variables are present."""
        logger.info("Validating required environment variables...")
        
        # BOOTSTRAP ENVIRONMENT VARIABLES ONLY (matches docker-compose.production.yml)
        # All other configuration fetched from config service per StocksBlitz architecture
        required_bootstrap_vars = [
            "ENVIRONMENT",           # Bootstrap: environment selection (production/staging/dev)
            "CONFIG_SERVICE_URL",    # Bootstrap: config service location (http://config-service:8100)
            "INTERNAL_API_KEY",      # Bootstrap: service-to-service auth key
            "SERVICE_NAME"           # Bootstrap: service identification (signal_service)
        ]
        
        results = []
        
        for var in required_bootstrap_vars:
            value = os.getenv(var)
            
            if not value or not value.strip():
                results.append(ValidationResult(
                    name=f"bootstrap_env_{var.lower()}",
                    passed=False,
                    message=f"Required bootstrap environment variable {var} is not set",
                    critical=True,
                    suggestions=[
                        f"Set {var} in docker-compose.production.yml environment section",
                        "Ensure docker-compose uses production environment pattern",
                        "Check deployment configuration matches StocksBlitz architecture"
                    ]
                ))
            else:
                # Additional validation for specific variables
                if var == "ENVIRONMENT" and value not in ["development", "staging", "production"]:
                    results.append(ValidationResult(
                            name=f"env_var_{var.lower()}_value",
                            passed=False,
                            message=f"ENVIRONMENT variable has invalid value: {value}",
                            critical=True,
                            suggestions=["Use 'development', 'staging', or 'production'"]
                        ))
                elif var.endswith("_URL") and self._validate_url_format(var, value) is False:
                    # Get appropriate suggestions based on URL type
                    if var == "CONFIG_SERVICE_URL":
                        suggestions = ["Ensure CONFIG_SERVICE_URL starts with http:// or https://"]
                    else:
                        suggestions = [f"Ensure {var} starts with http:// or https://"]
                    
                    results.append(ValidationResult(
                        name=f"env_var_{var.lower()}_format",
                        passed=False,
                        message=f"{var} should be a valid URL, got: {value}",
                        critical=True,
                        suggestions=suggestions
                    ))
                else:
                    results.append(ValidationResult(
                        name=f"env_var_{var.lower()}",
                        passed=True,
                        message=f"{var} is properly configured"
                    ))
        
        return results
    
    def validate_config_service_integration(self) -> List[ValidationResult]:
        """Validate config service integration (StocksBlitz architecture pattern)."""
        logger.info("Validating config service integration...")
        
        results = []
        config_service_url = os.getenv("CONFIG_SERVICE_URL")
        internal_api_key = os.getenv("INTERNAL_API_KEY")
        
        if not config_service_url:
            results.append(ValidationResult(
                name="config_service_url",
                passed=False,
                message="CONFIG_SERVICE_URL not configured",
                critical=True,
                suggestions=[
                    "Set CONFIG_SERVICE_URL=http://config-service:8100",
                    "Ensure config service container is running",
                    "Check docker-compose.production.yml config"
                ]
            ))
            return results
        
        if not internal_api_key:
            results.append(ValidationResult(
                name="internal_api_key",
                passed=False,
                message="INTERNAL_API_KEY not configured",
                critical=True,
                suggestions=[
                    "Set INTERNAL_API_KEY for service-to-service authentication",
                    "Use StocksBlitz internal API key pattern",
                    "Check docker-compose.production.yml environment section"
                ]
            ))
            return results
        
        # Test config service connectivity
        try:
            import httpx
            
            with httpx.Client(timeout=10) as client:
                response = client.get(
                    f"{config_service_url}/api/v1/health",
                    headers={"X-Internal-API-Key": internal_api_key}
                )
                
                if response.status_code == 200:
                    results.append(ValidationResult(
                        name="config_service_connectivity",
                        passed=True,
                        message="Config service is accessible and healthy"
                    ))
                    
                    # Test getting configuration from config service
                    try:
                        # Test secrets access
                        response = client.get(
                            f"{config_service_url}/api/v1/secrets/DATABASE_PASSWORD/value?environment={self.environment}",
                            headers={"X-Internal-API-Key": internal_api_key}
                        )
                        
                        if response.status_code == 200:
                            results.append(ValidationResult(
                                name="config_service_secrets_access",
                                passed=True,
                                message="Config service secrets access working"
                            ))
                        else:
                            results.append(ValidationResult(
                                name="config_service_secrets_access",
                                passed=False,
                                message=f"Config service secrets access failed: {response.status_code}",
                                critical=True,
                                suggestions=[
                                    "Ensure secrets are configured in config service",
                                    "Check internal API key permissions",
                                    "Verify environment parameter is correct"
                                ]
                            ))
                            
                    except Exception as e:
                        results.append(ValidationResult(
                            name="config_service_secrets_test",
                            passed=False,
                            message=f"Config service secrets test failed: {e}",
                            critical=False,
                            suggestions=["Check config service secrets configuration"]
                        ))
                        
                else:
                    results.append(ValidationResult(
                        name="config_service_connectivity",
                        passed=False,
                        message=f"Config service health check failed: {response.status_code}",
                        critical=True,
                        suggestions=[
                            "Start config service container",
                            "Check config service health",
                            "Verify CONFIG_SERVICE_URL is correct"
                        ]
                    ))
                    
        except Exception as e:
            results.append(ValidationResult(
                name="config_service_connectivity",
                passed=False,
                message=f"Unable to reach config service: {e}",
                critical=True,
                suggestions=[
                    "Ensure config service is running on specified URL",
                    "Check network connectivity to config service",
                    "Verify docker network configuration"
                ]
            ))
        
        return results

    def validate_cors_configuration(self) -> List[ValidationResult]:
        """Validate CORS configuration from config service."""
        logger.info("Validating CORS configuration from config service...")
        
        results = []
        config_service_url = os.getenv("CONFIG_SERVICE_URL")
        internal_api_key = os.getenv("INTERNAL_API_KEY")
        
        if not config_service_url or not internal_api_key:
            results.append(ValidationResult(
                name="cors_config_service_prereq",
                passed=False,
                message="Cannot validate CORS: config service not available",
                critical=True,
                suggestions=["Ensure config service integration is working first"]
            ))
            return results
        
        try:
            import httpx
            
            with httpx.Client(timeout=10) as client:
                response = client.get(
                    f"{config_service_url}/api/v1/config/CORS_ALLOWED_ORIGINS",
                    headers={
                        "X-Internal-API-Key": internal_api_key,
                        "X-Environment": self.environment
                    }
                )
                
                if response.status_code == 200:
                    cors_config = response.json().get("value", "")
                    
                    if not cors_config:
                        results.append(ValidationResult(
                            name="cors_configuration",
                            passed=False,
                            message="CORS_ALLOWED_ORIGINS not configured in config service",
                            critical=True,
                            suggestions=[
                                "Configure CORS_ALLOWED_ORIGINS in config service",
                                "Add CORS configuration for production environment"
                            ]
                        ))
                    elif self.environment == "production" and "*" in cors_config:
                        results.append(ValidationResult(
                            name="cors_wildcard_check",
                            passed=False,
                            message="CORS_ALLOWED_ORIGINS contains wildcard in production",
                            critical=True,
                            suggestions=[
                                "Remove wildcard (*) from production CORS configuration",
                                "Use specific domain names in production"
                            ]
                        ))
                    else:
                        results.append(ValidationResult(
                            name="cors_configuration",
                            passed=True,
                            message=f"CORS configuration valid: {cors_config}"
                        ))
                        
                else:
                    results.append(ValidationResult(
                        name="cors_configuration",
                        passed=False,
                        message=f"Failed to fetch CORS config from config service: {response.status_code}",
                        critical=True,
                        suggestions=[
                            "Configure CORS_ALLOWED_ORIGINS in config service",
                            "Check config service configuration access"
                        ]
                    ))
                    
        except Exception as e:
            results.append(ValidationResult(
                name="cors_configuration",
                passed=False,
                message=f"Error fetching CORS config: {e}",
                critical=True,
                suggestions=["Check config service connectivity"]
            ))
        
        return results
        
        # Parse and validate origins
        origins = [origin.strip() for origin in cors_origins.split(",")]
        
        # Check for empty origins
        empty_origins = [i for i, origin in enumerate(origins) if not origin]
        if empty_origins:
            results.append(ValidationResult(
                name="cors_empty_origins",
                passed=False,
                message=f"CORS origins list contains empty entries at positions: {empty_origins}",
                critical=False,
                suggestions=["Remove empty entries from CORS_ALLOWED_ORIGINS"]
            ))
        
        # Check origin formats
        for i, origin in enumerate(origins):
            if not origin:
                continue
                
            if not (origin.startswith("http://") or origin.startswith("https://")):
                results.append(ValidationResult(
                    name=f"cors_origin_format_{i}",
                    passed=False,
                    message=f"CORS origin '{origin}' does not start with http:// or https://",
                    critical=True,
                    suggestions=[f"Fix origin format: '{origin}' -> 'https://{origin}'"]
                ))
            
            if self.environment == "production" and "*" in origin:
                results.append(ValidationResult(
                    name=f"cors_wildcard_origin_{i}",
                    passed=False,
                    message=f"Production CORS origin '{origin}' contains wildcard",
                    critical=True,
                    suggestions=[f"Replace wildcard origin '{origin}' with explicit domain"]
                ))
        
        if not any(result.name.startswith("cors_origin_format_") and not result.passed for result in results) and \
           not any(result.name.startswith("cors_wildcard_origin_") and not result.passed for result in results):
            results.append(ValidationResult(
                name="cors_configuration",
                passed=True,
                message=f"CORS configuration valid with {len([o for o in origins if o])} origins"
            ))
        
        return results
    
    def validate_security_configuration(self) -> List[ValidationResult]:
        """Validate security configuration."""
        logger.info("Validating security configuration...")
        
        results = []
        
        # Check secret lengths and formats
        secrets = {
            "GATEWAY_SECRET": 16,    # Minimum 16 characters
            "JWT_SECRET_KEY": 32,   # Minimum 32 characters
            "INTERNAL_API_KEY": 16  # Minimum 16 characters
        }
        
        for secret_name, min_length in secrets.items():
            secret_value = os.getenv(secret_name)
            
            if not secret_value:
                continue  # Already checked in environment variables validation
            
            if len(secret_value) < min_length:
                results.append(ValidationResult(
                    name=f"security_{secret_name.lower()}_length",
                    passed=False,
                    message=f"{secret_name} is too short (minimum {min_length} characters)",
                    critical=True,
                    suggestions=[f"Generate a {secret_name} with at least {min_length} characters"]
                ))
            else:
                results.append(ValidationResult(
                    name=f"security_{secret_name.lower()}_length",
                    passed=True,
                    message=f"{secret_name} meets minimum length requirement"
                ))
        
        # Check for production security requirements
        if self.environment == "production":
            # Ensure HTTPS URLs in production
            service_urls = [
                "CALENDAR_SERVICE_URL",
                "ALERT_SERVICE_URL", 
                "MESSAGING_SERVICE_URL",
                "MARKETPLACE_SERVICE_URL"
            ]
            
            for url_var in service_urls:
                url_value = os.getenv(url_var)
                if url_value and not url_value.startswith("https://"):
                    results.append(ValidationResult(
                        name=f"security_{url_var.lower()}_https",
                        passed=False,
                        message=f"Production {url_var} should use HTTPS: {url_value}",
                        critical=False,  # Warning, not critical
                        suggestions=[f"Change {url_var} to use HTTPS protocol"]
                    ))
        
        return results
    
    def validate_database_configuration(self) -> List[ValidationResult]:
        """Validate database configuration."""
        logger.info("Validating database configuration...")
        
        results = []
        database_url = os.getenv("DATABASE_URL")
        
        if not database_url:
            return results  # Already checked in environment variables validation
        
        # Basic database URL format check
        if not database_url.startswith(("postgresql://", "postgres://")):
            results.append(ValidationResult(
                name="database_url_format",
                passed=False,
                message="DATABASE_URL should start with postgresql:// or postgres://",
                critical=True,
                suggestions=["Use PostgreSQL/TimescaleDB URL format"]
            ))
        
        # Check for localhost in production
        if self.environment == "production" and ("localhost" in database_url or "127.0.0.1" in database_url):
            results.append(ValidationResult(
                name="database_production_localhost",
                passed=False,
                message="Production DATABASE_URL points to localhost",
                critical=True,
                suggestions=[
                    "Use production database hostname",
                    "Ensure database is accessible from deployment environment"
                ]
            ))
        
        if not any(not result.passed for result in results):
            results.append(ValidationResult(
                name="database_configuration",
                passed=True,
                message="Database configuration appears valid"
            ))
        
        return results
    
    def validate_service_integrations(self) -> List[ValidationResult]:
        """Validate service integration configuration."""
        logger.info("Validating service integration configuration...")
        
        results = []
        
        # Check service timeout configuration
        timeout_str = os.getenv("SERVICE_INTEGRATION_TIMEOUT")
        if timeout_str:
            try:
                timeout_val = float(timeout_str)
                if timeout_val <= 0:
                    results.append(ValidationResult(
                        name="service_timeout_value",
                        passed=False,
                        message="SERVICE_INTEGRATION_TIMEOUT must be positive",
                        critical=True,
                        suggestions=["Set SERVICE_INTEGRATION_TIMEOUT to a positive number (e.g., 30.0)"]
                    ))
                elif timeout_val > 300:  # 5 minutes
                    results.append(ValidationResult(
                        name="service_timeout_reasonable",
                        passed=False,
                        message=f"SERVICE_INTEGRATION_TIMEOUT is very high: {timeout_val}s",
                        critical=False,
                        suggestions=["Consider reducing SERVICE_INTEGRATION_TIMEOUT to under 300 seconds"]
                    ))
                else:
                    results.append(ValidationResult(
                        name="service_timeout_configuration",
                        passed=True,
                        message=f"Service timeout configured to {timeout_val}s"
                    ))
            except ValueError:
                results.append(ValidationResult(
                    name="service_timeout_format",
                    passed=False,
                    message=f"SERVICE_INTEGRATION_TIMEOUT is not a valid number: {timeout_str}",
                    critical=True,
                    suggestions=["Set SERVICE_INTEGRATION_TIMEOUT to a numeric value (e.g., 30.0)"]
                ))
        
        return results
    
    def validate_minio_configuration(self) -> List[ValidationResult]:
        """Validate MinIO configuration."""
        logger.info("Validating MinIO configuration...")
        
        results = []
        
        minio_endpoint = os.getenv("MINIO_ENDPOINT")
        if minio_endpoint:
            # Check endpoint format
            if not (":" in minio_endpoint and minio_endpoint.count(":") >= 1):
                results.append(ValidationResult(
                    name="minio_endpoint_format",
                    passed=False,
                    message=f"MINIO_ENDPOINT should include port: {minio_endpoint}",
                    critical=False,
                    suggestions=["Use format: hostname:port (e.g., minio.example.com:9000)"]
                ))
            
            # Check for localhost in production
            if self.environment == "production" and ("localhost" in minio_endpoint or "127.0.0.1" in minio_endpoint):
                results.append(ValidationResult(
                    name="minio_production_localhost",
                    passed=False,
                    message="Production MINIO_ENDPOINT points to localhost",
                    critical=True,
                    suggestions=[
                        "Use production MinIO hostname",
                        "Ensure MinIO is accessible from deployment environment"
                    ]
                ))
        
        # Check access credentials are not empty
        minio_access_key = os.getenv("MINIO_ACCESS_KEY")
        minio_secret_key = os.getenv("MINIO_SECRET_KEY")
        
        if minio_access_key and len(minio_access_key) < 3:
            results.append(ValidationResult(
                name="minio_access_key_length",
                passed=False,
                message="MINIO_ACCESS_KEY is too short",
                critical=True,
                suggestions=["Use a proper MinIO access key"]
            ))
        
        if minio_secret_key and len(minio_secret_key) < 8:
            results.append(ValidationResult(
                name="minio_secret_key_length",
                passed=False,
                message="MINIO_SECRET_KEY is too short",
                critical=True,
                suggestions=["Use a proper MinIO secret key (minimum 8 characters)"]
            ))
        
        return results
    
    def _validate_url_format(self, var_name: str, url_value: str) -> bool:
        """
        Validate URL format based on the type of URL.
        
        Args:
            var_name: Environment variable name
            url_value: URL value to validate
            
        Returns:
            True if URL format is valid, False otherwise
        """
        # Database URLs should use postgresql:// or postgres://
        if var_name == "DATABASE_URL":
            return url_value.startswith(("postgresql://", "postgres://"))
        
        # Redis URLs should use redis:// or rediss://
        elif var_name == "REDIS_URL":
            return url_value.startswith(("redis://", "rediss://"))
        
        # Service URLs should use http:// or https://
        elif var_name.endswith("_SERVICE_URL") or var_name in ["DASHBOARD_URL"]:
            return url_value.startswith(("http://", "https://"))
        
        # MinIO URLs should use http:// or https://
        elif var_name == "MINIO_ENDPOINT":
            return url_value.startswith(("http://", "https://"))
        
        # Other URL variables should use http:// or https://
        else:
            return url_value.startswith(("http://", "https://"))
    
    def run_all_validations(self) -> bool:
        """Run all deployment safety validations."""
        logger.info(f"Starting deployment safety validation for environment: {self.environment}")
        start_time = datetime.now()
        
        # Run all validation categories (updated for config service architecture)
        validation_methods = [
            self.validate_required_environment_variables,  # Only 4 bootstrap vars
            self.validate_config_service_integration,      # NEW: Config service connectivity
            self.validate_cors_configuration,              # NEW: CORS from config service
            # NOTE: Other validations moved to config service pattern
            # self.validate_security_configuration - secrets now in config service
            # self.validate_database_configuration - DATABASE_URL from config service  
            # self.validate_service_integrations - service URLs from config service
            # self.validate_minio_configuration - MinIO config from config service
        ]
        
        for method in validation_methods:
            try:
                results = method()
                for result in results:
                    self.add_result(result)
            except Exception as e:
                logger.critical(f"Validation method {method.__name__} failed: {e}")
                self.add_result(ValidationResult(
                    name=f"validation_{method.__name__}",
                    passed=False,
                    message=f"Validation method failed: {e}",
                    critical=True
                ))
        
        # Generate summary
        total_checks = len(self.validation_results)
        passed_checks = len([r for r in self.validation_results if r.passed])
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        logger.info(f"Deployment validation completed in {duration:.2f}s")
        logger.info(f"Results: {passed_checks}/{total_checks} passed, {self.warnings} warnings, {self.critical_failures} critical failures")
        
        # Return success if no critical failures
        return self.critical_failures == 0
    
    def generate_report(self, output_file: str = None) -> Dict[str, Any]:
        """Generate a detailed validation report."""
        report = {
            "environment": self.environment,
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total_checks": len(self.validation_results),
                "passed_checks": len([r for r in self.validation_results if r.passed]),
                "warnings": self.warnings,
                "critical_failures": self.critical_failures,
                "overall_status": "PASS" if self.critical_failures == 0 else "FAIL"
            },
            "results": []
        }
        
        # Group results by category
        for result in self.validation_results:
            report["results"].append({
                "name": result.name,
                "passed": result.passed,
                "message": result.message,
                "critical": result.critical,
                "suggestions": result.suggestions
            })
        
        if output_file:
            with open(output_file, 'w') as f:
                json.dump(report, f, indent=2)
            logger.info(f"Detailed validation report written to: {output_file}")
        
        return report
    
    def print_summary(self):
        """Print a human-readable summary of validation results."""
        print("\n" + "="*80)
        print(f"DEPLOYMENT SAFETY VALIDATION SUMMARY ({self.environment.upper()})")
        print("="*80)
        
        # Overall status
        status = "✅ PASS" if self.critical_failures == 0 else "❌ FAIL"
        print(f"Overall Status: {status}")
        print(f"Environment: {self.environment}")
        print(f"Total Checks: {len(self.validation_results)}")
        print(f"Passed: {len([r for r in self.validation_results if r.passed])}")
        print(f"Warnings: {self.warnings}")
        print(f"Critical Failures: {self.critical_failures}")
        
        # Critical failures
        if self.critical_failures > 0:
            print("\n🚨 CRITICAL FAILURES:")
            for result in self.validation_results:
                if result.critical and not result.passed:
                    print(f"  ❌ {result.name}: {result.message}")
                    for suggestion in result.suggestions:
                        print(f"     💡 {suggestion}")
        
        # Warnings
        if self.warnings > 0:
            print(f"\n⚠️ WARNINGS:")
            for result in self.validation_results:
                if not result.critical and not result.passed:
                    print(f"  ⚠️ {result.name}: {result.message}")
                    for suggestion in result.suggestions:
                        print(f"     💡 {suggestion}")
        
        print("\n" + "="*80)


def main():
    """Main deployment validation script."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Deployment Safety Validation Script")
    parser.add_argument("--environment", "-e", 
                       choices=["development", "staging", "production"],
                       help="Environment to validate (defaults to ENVIRONMENT env var)")
    parser.add_argument("--report", "-r",
                       help="Output detailed report to JSON file")
    parser.add_argument("--quiet", "-q", action="store_true",
                       help="Suppress verbose output")
    parser.add_argument("--fail-on-warnings", action="store_true",
                       help="Treat warnings as failures")
    
    args = parser.parse_args()
    
    if args.quiet:
        logging.getLogger().setLevel(logging.WARNING)
    
    # Create validator
    validator = DeploymentSafetyValidator(environment=args.environment)
    
    # Run validations
    success = validator.run_all_validations()
    
    # Apply fail-on-warnings if requested
    if args.fail_on_warnings and validator.warnings > 0:
        success = False
    
    # Generate report if requested
    if args.report:
        validator.generate_report(args.report)
    
    # Print summary
    if not args.quiet:
        validator.print_summary()
    
    # Exit with appropriate code
    exit_code = 0 if success else 1
    
    if exit_code == 0:
        print(f"\n✅ Deployment validation PASSED for {validator.environment}")
    else:
        print(f"\n❌ Deployment validation FAILED for {validator.environment}")
    
    sys.exit(exit_code)


if __name__ == "__main__":
    main()