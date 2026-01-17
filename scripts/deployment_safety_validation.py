#!/usr/bin/env python3
"""
Deployment Safety Validation Script

Automated checks for required environment variables and configuration validation
before deployment. Ensures all critical configuration is present and valid.
Addresses functionality_issues.txt requirement for deployment safety nets.
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
        
        # Define required environment variables by category
        required_vars = {
            # Core application configuration
            "core": [
                "ENVIRONMENT",
                "DATABASE_URL",
                "REDIS_URL",
                "LOG_LEVEL"
            ],
            # Service URLs (must be from config service)
            "services": [
                "CALENDAR_SERVICE_URL", 
                "ALERT_SERVICE_URL",
                "MESSAGING_SERVICE_URL",
                "MARKETPLACE_SERVICE_URL"
            ],
            # CORS configuration
            "cors": [
                "CORS_ALLOWED_ORIGINS"
            ],
            # Authentication and security
            "security": [
                "GATEWAY_SECRET",
                "INTERNAL_API_KEY",
                "JWT_SECRET_KEY"
            ],
            # External integrations
            "integrations": [
                "MINIO_ENDPOINT",
                "MINIO_ACCESS_KEY", 
                "MINIO_SECRET_KEY",
                "SERVICE_INTEGRATION_TIMEOUT"
            ]
        }
        
        results = []
        
        for category, vars_list in required_vars.items():
            for var in vars_list:
                value = os.getenv(var)
                
                if not value or not value.strip():
                    results.append(ValidationResult(
                        name=f"env_var_{var.lower()}",
                        passed=False,
                        message=f"Required environment variable {var} is not set or empty",
                        critical=True,
                        suggestions=[
                            f"Set {var} environment variable",
                            f"Ensure config service provides {var}",
                            "Check deployment configuration"
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
                    elif var.endswith("_URL") and not (value.startswith("http://") or value.startswith("https://")):
                        results.append(ValidationResult(
                            name=f"env_var_{var.lower()}_format",
                            passed=False,
                            message=f"{var} should be a valid URL, got: {value}",
                            critical=True,
                            suggestions=[f"Ensure {var} starts with http:// or https://"]
                        ))
                    elif var == "CORS_ALLOWED_ORIGINS" and self.environment == "production":
                        # Special validation for CORS in production
                        if "*" in value:
                            results.append(ValidationResult(
                                name="cors_wildcard_check",
                                passed=False,
                                message="CORS_ALLOWED_ORIGINS contains wildcard origins in production",
                                critical=True,
                                suggestions=[
                                    "Remove wildcard (*) origins from CORS_ALLOWED_ORIGINS",
                                    "Use explicit domain names only"
                                ]
                            ))
                        else:
                            results.append(ValidationResult(
                                name=f"env_var_{var.lower()}",
                                passed=True,
                                message=f"{var} is properly configured"
                            ))
                    else:
                        results.append(ValidationResult(
                            name=f"env_var_{var.lower()}",
                            passed=True,
                            message=f"{var} is properly configured"
                        ))
        
        return results
    
    def validate_cors_configuration(self) -> List[ValidationResult]:
        """Validate CORS configuration."""
        logger.info("Validating CORS configuration...")
        
        results = []
        cors_origins = os.getenv("CORS_ALLOWED_ORIGINS")
        
        if not cors_origins:
            results.append(ValidationResult(
                name="cors_configuration",
                passed=False,
                message="CORS_ALLOWED_ORIGINS not configured",
                critical=True,
                suggestions=["Configure CORS_ALLOWED_ORIGINS environment variable"]
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
    
    def run_all_validations(self) -> bool:
        """Run all deployment safety validations."""
        logger.info(f"Starting deployment safety validation for environment: {self.environment}")
        start_time = datetime.now()
        
        # Run all validation categories
        validation_methods = [
            self.validate_required_environment_variables,
            self.validate_cors_configuration,
            self.validate_security_configuration,
            self.validate_database_configuration,
            self.validate_service_integrations,
            self.validate_minio_configuration
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