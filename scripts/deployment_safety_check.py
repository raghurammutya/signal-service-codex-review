#!/usr/bin/env python3
"""
Deployment Safety Check

Validates that all required environment variables and configurations are present
before allowing Signal Service deployment. Addresses functionality_issues.txt
requirement for automated configuration validation.
"""
import json
import os
import sys
import time
from datetime import datetime
from typing import Any, Dict, List


class DeploymentSafetyChecker:
    """Comprehensive deployment safety validation."""

    def __init__(self):
        self.required_env_vars = [
            'ENVIRONMENT',
            'CONFIG_SERVICE_URL',
            'CONFIG_SERVICE_API_KEY'
        ]
        self.optional_env_vars = [
            'SERVICE_HOST',
            'SERVICE_PORT',
            'LOG_LEVEL'
        ]
        self.validation_results = {
            'timestamp': datetime.now().isoformat(),
            'safe_to_deploy': False,
            'checks': {},
            'warnings': [],
            'errors': []
        }

    def check_environment_variables(self) -> bool:
        """Check all required environment variables."""
        print("🔍 Checking environment variables...")

        missing_vars = []
        present_vars = []

        for var in self.required_env_vars:
            value = os.environ.get(var)
            if not value:
                missing_vars.append(var)
                self.validation_results['errors'].append(f"Missing required environment variable: {var}")
            else:
                present_vars.append(var)
                print(f"  ✅ {var}: {'*' * min(len(value), 8)}")  # Mask values for security

        for var in self.optional_env_vars:
            value = os.environ.get(var)
            if value:
                present_vars.append(var)
                print(f"  ℹ️  {var}: {value}")
            else:
                self.validation_results['warnings'].append(f"Optional environment variable not set: {var}")

        if missing_vars:
            print(f"  ❌ Missing required variables: {', '.join(missing_vars)}")
            self.validation_results['checks']['environment_variables'] = {
                'status': 'FAIL',
                'missing': missing_vars,
                'present': present_vars
            }
            return False
        print("  ✅ All required environment variables present")
        self.validation_results['checks']['environment_variables'] = {
            'status': 'PASS',
            'present': present_vars
        }
        return True

    def check_config_service_connectivity(self) -> bool:
        """Test config service connectivity and health."""
        print("\n🔍 Checking config service connectivity...")

        try:
            # Add project root to path for imports
            sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

            from common.config_service.client import ConfigServiceClient, ConfigServiceError

            # Create client and test health
            client = ConfigServiceClient()

            print(f"  🔗 Testing connection to {client.base_url}")

            # Test health check with timeout
            start_time = time.time()
            is_healthy = client.health_check()
            response_time = (time.time() - start_time) * 1000

            if is_healthy:
                print(f"  ✅ Config service healthy (response time: {response_time:.1f}ms)")
                self.validation_results['checks']['config_service'] = {
                    'status': 'PASS',
                    'response_time_ms': round(response_time, 1),
                    'url': client.base_url
                }
                return True
            print(f"  ❌ Config service unhealthy (response time: {response_time:.1f}ms)")
            self.validation_results['errors'].append("Config service health check failed")
            self.validation_results['checks']['config_service'] = {
                'status': 'FAIL',
                'response_time_ms': round(response_time, 1),
                'url': client.base_url,
                'error': 'Health check returned False'
            }
            return False

        except ConfigServiceError as e:
            print(f"  ❌ Config service error: {e}")
            self.validation_results['errors'].append(f"Config service error: {e}")
            self.validation_results['checks']['config_service'] = {
                'status': 'FAIL',
                'error': str(e),
                'error_type': 'ConfigServiceError'
            }
            return False
        except Exception as e:
            print(f"  ❌ Unexpected error testing config service: {e}")
            self.validation_results['errors'].append(f"Config service connection failed: {e}")
            self.validation_results['checks']['config_service'] = {
                'status': 'FAIL',
                'error': str(e),
                'error_type': type(e).__name__
            }
            return False

    def check_config_service_secrets(self) -> bool:
        """Test that required secrets can be retrieved from config service."""
        print("\n🔍 Checking config service secrets...")

        try:
            sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            from common.config_service.client import ConfigServiceClient

            client = ConfigServiceClient()

            # Test required secrets
            required_secrets = ['DATABASE_URL', 'REDIS_URL', 'GATEWAY_SECRET']
            secret_status = {}

            for secret_key in required_secrets:
                try:
                    secret_value = client.get_secret(secret_key, required=False)
                    if secret_value:
                        print(f"  ✅ {secret_key}: Available")
                        secret_status[secret_key] = 'available'
                    else:
                        print(f"  ⚠️  {secret_key}: Not found")
                        secret_status[secret_key] = 'missing'
                        self.validation_results['warnings'].append(f"Secret {secret_key} not found in config service")
                except Exception as e:
                    print(f"  ❌ {secret_key}: Error - {e}")
                    secret_status[secret_key] = 'error'
                    self.validation_results['errors'].append(f"Failed to retrieve secret {secret_key}: {e}")

            # Determine overall status
            missing_secrets = [k for k, v in secret_status.items() if v in ['missing', 'error']]
            if missing_secrets:
                self.validation_results['checks']['config_secrets'] = {
                    'status': 'FAIL',
                    'secrets': secret_status,
                    'missing': missing_secrets
                }
                return False
            self.validation_results['checks']['config_secrets'] = {
                'status': 'PASS',
                'secrets': secret_status
            }
            return True

        except Exception as e:
            print(f"  ❌ Error checking secrets: {e}")
            self.validation_results['errors'].append(f"Secret validation failed: {e}")
            self.validation_results['checks']['config_secrets'] = {
                'status': 'FAIL',
                'error': str(e)
            }
            return False

    def check_config_service_settings(self) -> bool:
        """Test that required configuration settings can be retrieved."""
        print("\n🔍 Checking config service settings...")

        try:
            sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            from common.config_service.client import ConfigServiceClient

            client = ConfigServiceClient()

            # Test a few critical settings
            required_settings = [
                'signal_service.service_name',
                'signal_service.environment',
                'signal_service.service_host',
                'signal_service.service_port'
            ]

            setting_status = {}

            for setting_key in required_settings:
                try:
                    setting_value = client.get_config(setting_key, required=False)
                    if setting_value:
                        print(f"  ✅ {setting_key}: {setting_value}")
                        setting_status[setting_key] = 'available'
                    else:
                        print(f"  ⚠️  {setting_key}: Not found")
                        setting_status[setting_key] = 'missing'
                        self.validation_results['warnings'].append(f"Setting {setting_key} not found in config service")
                except Exception as e:
                    print(f"  ❌ {setting_key}: Error - {e}")
                    setting_status[setting_key] = 'error'
                    self.validation_results['errors'].append(f"Failed to retrieve setting {setting_key}: {e}")

            # Determine overall status
            missing_settings = [k for k, v in setting_status.items() if v in ['missing', 'error']]
            if missing_settings:
                self.validation_results['checks']['config_settings'] = {
                    'status': 'FAIL',
                    'settings': setting_status,
                    'missing': missing_settings
                }
                return False
            self.validation_results['checks']['config_settings'] = {
                'status': 'PASS',
                'settings': setting_status
            }
            return True

        except Exception as e:
            print(f"  ❌ Error checking settings: {e}")
            self.validation_results['errors'].append(f"Settings validation failed: {e}")
            self.validation_results['checks']['config_settings'] = {
                'status': 'FAIL',
                'error': str(e)
            }
            return False

    def check_deployment_documentation(self) -> bool:
        """Verify deployment documentation is complete."""
        print("\n🔍 Checking deployment documentation...")

        try:
            # Check README.md exists and has required sections
            readme_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'README.md')

            if not os.path.exists(readme_path):
                print("  ❌ README.md not found")
                self.validation_results['errors'].append("README.md not found")
                return False

            with open(readme_path) as f:
                readme_content = f.read()

            required_sections = [
                'Required Environment Variables',
                'Bootstrap Variables',
                'Deployment Checklist',
                'Config Service Setup'
            ]

            missing_sections = []
            for section in required_sections:
                if section not in readme_content:
                    missing_sections.append(section)
                else:
                    print(f"  ✅ Documentation section: {section}")

            if missing_sections:
                print(f"  ⚠️  Missing documentation sections: {', '.join(missing_sections)}")
                self.validation_results['warnings'].extend([f"Missing documentation section: {section}" for section in missing_sections])
                self.validation_results['checks']['documentation'] = {
                    'status': 'WARN',
                    'missing_sections': missing_sections
                }
                return True  # Warning, not error
            print("  ✅ All required documentation sections present")
            self.validation_results['checks']['documentation'] = {
                'status': 'PASS'
            }
            return True

        except Exception as e:
            print(f"  ❌ Error checking documentation: {e}")
            self.validation_results['warnings'].append(f"Documentation check failed: {e}")
            self.validation_results['checks']['documentation'] = {
                'status': 'WARN',
                'error': str(e)
            }
            return True  # Warning, not error

    def run_all_checks(self) -> bool:
        """Run all deployment safety checks."""
        print("🚀 Signal Service Deployment Safety Check")
        print("=" * 50)

        checks = [
            self.check_environment_variables,
            self.check_config_service_connectivity,
            self.check_config_service_secrets,
            self.check_config_service_settings,
            self.check_deployment_documentation
        ]

        passed_checks = 0
        total_checks = len(checks)

        for check in checks:
            try:
                if check():
                    passed_checks += 1
            except Exception as e:
                print(f"  ❌ Check failed with exception: {e}")
                self.validation_results['errors'].append(f"Check failed: {e}")

        # Overall result
        print("\n" + "=" * 50)
        self.validation_results['passed_checks'] = passed_checks
        self.validation_results['total_checks'] = total_checks

        if passed_checks == total_checks and len(self.validation_results['errors']) == 0:
            print("✅ DEPLOYMENT SAFETY CHECK PASSED")
            print("🚀 Safe to deploy Signal Service")
            self.validation_results['safe_to_deploy'] = True
            return True
        print("❌ DEPLOYMENT SAFETY CHECK FAILED")
        print(f"📊 Passed: {passed_checks}/{total_checks} checks")
        print(f"🚫 Errors: {len(self.validation_results['errors'])}")
        print(f"⚠️  Warnings: {len(self.validation_results['warnings'])}")

        if self.validation_results['errors']:
            print("\n🚫 ERRORS:")
            for error in self.validation_results['errors']:
                print(f"  - {error}")

        if self.validation_results['warnings']:
            print("\n⚠️  WARNINGS:")
            for warning in self.validation_results['warnings']:
                print(f"  - {warning}")

        print("\n❌ NOT SAFE TO DEPLOY")
        self.validation_results['safe_to_deploy'] = False
        return False

    def save_report(self, filename: str = 'deployment_safety_report.json'):
        """Save detailed validation report."""
        report_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)

        with open(report_path, 'w') as f:
            json.dump(self.validation_results, f, indent=2)

        print(f"\n📋 Detailed report saved to: {report_path}")


def main():
    """Run deployment safety check."""
    checker = DeploymentSafetyChecker()

    success = checker.run_all_checks()
    checker.save_report()

    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
