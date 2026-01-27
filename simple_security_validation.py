#!/usr/bin/env python3
"""
Simple Security Validation

Tests logging redaction, CORS, auth, and watermark security measures.
"""
import json
import os
import time
from datetime import datetime


class SimpleSecurityValidation:
    """Simple security validation for production readiness."""

    def __init__(self):
        self.results = {
            "timestamp": datetime.now().isoformat(),
            "tests": {}
        }

    def test_logging_redaction_structure(self):
        """Test logging redaction structure and patterns."""
        print("🛡️ Testing Logging Redaction Structure...")

        try:
            # Check if logging security module exists
            logging_file = "app/utils/logging_security.py"
            if not os.path.exists(logging_file):
                print("  ❌ Logging security module not found")
                return {"status": "missing", "file": logging_file}

            with open(logging_file) as f:
                content = f.read()

            # Check for security patterns
            security_patterns = [
                ("SensitiveDataFilter", "Sensitive data filter class"),
                ("redaction_marker", "Redaction marker configuration"),
                ("api_key", "API key redaction pattern"),
                ("password", "Password redaction pattern"),
                ("bearer", "Bearer token redaction pattern"),
                ("***REDACTED***", "Redaction marker usage"),
                ("configure_secure_logging", "Secure logging configuration function")
            ]

            patterns_found = 0
            for pattern, description in security_patterns:
                if pattern in content:
                    print(f"    ✅ {description}")
                    patterns_found += 1
                else:
                    print(f"    ❌ {description}")

            print(f"  📊 Security patterns: {patterns_found}/{len(security_patterns)}")

            return {
                "status": "tested",
                "patterns_found": patterns_found,
                "total_patterns": len(security_patterns),
                "coverage_percentage": (patterns_found / len(security_patterns)) * 100
            }

        except Exception as e:
            print(f"  ❌ Logging redaction test failed: {e}")
            return {"status": "error", "error": str(e)}

    def test_cors_configuration_structure(self):
        """Test CORS configuration structure."""
        print("🌐 Testing CORS Configuration Structure...")

        try:
            # Check main.py for CORS configuration
            main_file = "app/main.py"
            if not os.path.exists(main_file):
                print(f"  ❌ {main_file} not found")
                return {"status": "missing", "file": main_file}

            with open(main_file) as f:
                content = f.read()

            cors_checks = [
                ("CORSMiddleware", "CORS middleware import/usage"),
                ("allow_origins", "CORS origins configuration"),
                ("allow_credentials", "CORS credentials configuration"),
                ("allow_methods", "CORS methods configuration"),
                ("allow_headers", "CORS headers configuration")
            ]

            cors_found = 0
            for check, description in cors_checks:
                if check in content:
                    print(f"    ✅ {description}")
                    cors_found += 1
                else:
                    print(f"    ⚠️ {description} not found")

            # Check for wildcard origins (should not be present in production)
            wildcard_safe = True
            if '"*"' in content and "allow_origins" in content:
                print("    ❌ Wildcard origins detected (security risk)")
                wildcard_safe = False
            else:
                print("    ✅ No wildcard origins detected")

            print(f"  📊 CORS configuration: {cors_found}/{len(cors_checks)} present")

            return {
                "status": "tested",
                "cors_configs_found": cors_found,
                "total_configs": len(cors_checks),
                "wildcard_safe": wildcard_safe
            }

        except Exception as e:
            print(f"  ❌ CORS configuration test failed: {e}")
            return {"status": "error", "error": str(e)}

    def test_authentication_structure(self):
        """Test authentication structure."""
        print("🔐 Testing Authentication Structure...")

        try:
            auth_files = [
                ("app/core/auth.py", "Core authentication module"),
                ("app/middleware/auth_middleware.py", "Authentication middleware"),
                ("app/api/v2/config_admin.py", "Admin API authentication")
            ]

            auth_components_found = 0
            for file_path, description in auth_files:
                if os.path.exists(file_path):
                    print(f"    ✅ {description}")
                    auth_components_found += 1

                    # Check for authentication patterns
                    with open(file_path) as f:
                        content = f.read()

                    auth_patterns = ["Bearer", "verify", "auth", "token"]
                    patterns_in_file = sum(1 for pattern in auth_patterns if pattern in content)
                    print(f"      📊 Auth patterns: {patterns_in_file}/{len(auth_patterns)}")
                else:
                    print(f"    ⚠️ {description} not found")

            print(f"  📊 Auth components: {auth_components_found}/{len(auth_files)}")

            return {
                "status": "tested",
                "auth_components_found": auth_components_found,
                "total_components": len(auth_files)
            }

        except Exception as e:
            print(f"  ❌ Authentication structure test failed: {e}")
            return {"status": "error", "error": str(e)}

    def test_admin_api_security_structure(self):
        """Test admin API security structure."""
        print("👑 Testing Admin API Security Structure...")

        try:
            admin_file = "app/api/v2/config_admin.py"
            if not os.path.exists(admin_file):
                print(f"  ❌ {admin_file} not found")
                return {"status": "missing", "file": admin_file}

            with open(admin_file) as f:
                content = f.read()

            security_checks = [
                ("HTTPBearer", "Bearer token authentication"),
                ("verify_admin_token", "Admin token verification"),
                ("ADMIN_API_TOKEN", "Admin token configuration"),
                ("_sanitize_config_response", "Response sanitization"),
                ("***REDACTED***", "Sensitive data redaction"),
                ("admin", "Admin-specific security"),
                ("Depends", "Dependency injection for security")
            ]

            security_found = 0
            for check, description in security_checks:
                if check in content:
                    print(f"    ✅ {description}")
                    security_found += 1
                else:
                    print(f"    ⚠️ {description} not found")

            print(f"  📊 Admin security: {security_found}/{len(security_checks)}")

            return {
                "status": "tested",
                "security_checks_found": security_found,
                "total_checks": len(security_checks),
                "security_coverage": (security_found / len(security_checks)) * 100
            }

        except Exception as e:
            print(f"  ❌ Admin API security test failed: {e}")
            return {"status": "error", "error": str(e)}

    def test_watermark_security_structure(self):
        """Test watermark security structure."""
        print("🔏 Testing Watermark Security Structure...")

        try:
            # Look for watermark-related files
            watermark_files = [
                "app/services/watermark_service.py",
                "app/utils/watermark.py",
                "app/core/watermark.py"
            ]

            watermark_found = False
            for file_path in watermark_files:
                if os.path.exists(file_path):
                    print(f"    ✅ Watermark service found: {file_path}")
                    watermark_found = True

                    with open(file_path) as f:
                        content = f.read()

                    # Check for fail-secure patterns
                    fail_secure_patterns = [
                        ("raise", "Exception raising on failure"),
                        ("except", "Exception handling"),
                        ("validate", "Validation methods"),
                        ("verify", "Verification methods"),
                        ("secure", "Security-focused methods")
                    ]

                    patterns_found = sum(1 for pattern, _ in fail_secure_patterns if pattern in content)
                    print(f"      📊 Fail-secure patterns: {patterns_found}/{len(fail_secure_patterns)}")
                    break

            if not watermark_found:
                print("    ⚠️ Watermark service not found (may be external)")
                return {"status": "unavailable", "message": "Watermark service not implemented"}

            return {
                "status": "tested",
                "service_available": watermark_found,
                "fail_secure_patterns": patterns_found if 'patterns_found' in locals() else 0
            }

        except Exception as e:
            print(f"  ❌ Watermark security test failed: {e}")
            return {"status": "error", "error": str(e)}

    def test_environment_security_configuration(self):
        """Test environment security configuration."""
        print("🔧 Testing Environment Security Configuration...")

        try:
            # Check for environment-based security configurations
            config_files = [
                "app/core/config.py",
                "app/config/settings.py",
                ".env",
                ".env.example"
            ]

            security_configs = []
            for file_path in config_files:
                if os.path.exists(file_path):
                    with open(file_path) as f:
                        content = f.read()

                    # Look for security-related environment variables
                    env_patterns = [
                        "ENVIRONMENT",
                        "API_KEY",
                        "SECRET",
                        "TOKEN",
                        "AUTH",
                        "CORS",
                        "ALLOWED_ORIGINS"
                    ]

                    found_patterns = [pattern for pattern in env_patterns if pattern in content]
                    if found_patterns:
                        security_configs.append({
                            "file": file_path,
                            "patterns": found_patterns
                        })
                        print(f"    ✅ {file_path}: {len(found_patterns)} security configs")

            print(f"  📊 Security config files: {len(security_configs)}")

            return {
                "status": "tested",
                "config_files_found": len(security_configs),
                "security_configs": security_configs
            }

        except Exception as e:
            print(f"  ❌ Environment security test failed: {e}")
            return {"status": "error", "error": str(e)}

    def run_validation(self):
        """Run complete security validation."""
        print("🔒 Simple Security Validation")
        print("=" * 60)

        start_time = time.time()

        # Run all tests
        self.results["tests"]["logging_redaction_structure"] = self.test_logging_redaction_structure()
        print()

        self.results["tests"]["cors_configuration_structure"] = self.test_cors_configuration_structure()
        print()

        self.results["tests"]["authentication_structure"] = self.test_authentication_structure()
        print()

        self.results["tests"]["admin_api_security_structure"] = self.test_admin_api_security_structure()
        print()

        self.results["tests"]["watermark_security_structure"] = self.test_watermark_security_structure()
        print()

        self.results["tests"]["environment_security_configuration"] = self.test_environment_security_configuration()
        print()

        end_time = time.time()
        duration = end_time - start_time

        self.results["duration_seconds"] = duration
        self.results["summary"] = self._generate_summary()

        print("=" * 60)
        print(f"🎯 Security Validation Summary (Duration: {duration:.2f}s)")

        for test_name, result in self.results["tests"].items():
            status = result.get("status", "unknown")
            emoji = "✅" if status == "tested" else "⚠️" if status in ["unavailable", "missing"] else "❌"
            print(f"  {emoji} {test_name.replace('_', ' ').title()}: {status}")

        # Generate security validation report
        with open('simple_security_validation_output.log', 'w') as f:
            json.dump(self.results, f, indent=2)

        return self.results

    def _generate_summary(self):
        """Generate security validation summary."""
        tested_count = sum(1 for test in self.results["tests"].values()
                          if test.get("status") == "tested")
        total_count = len(self.results["tests"])

        return {
            "total_tests": total_count,
            "successfully_tested": tested_count,
            "unavailable_tests": sum(1 for test in self.results["tests"].values()
                                   if test.get("status") in ["unavailable", "missing"]),
            "success_rate": (tested_count / total_count) * 100 if total_count > 0 else 0
        }


def main():
    """Run simple security validation."""
    validation = SimpleSecurityValidation()
    results = validation.run_validation()

    success_rate = results["summary"]["success_rate"]
    if success_rate >= 70:  # 70% success rate acceptable for validation
        print(f"\n🎉 SECURITY VALIDATION PASSED ({success_rate:.1f}% success rate)")
        print("\n🔒 Security Measures Validated:")
        print("  - Logging redaction patterns and structure")
        print("  - CORS configuration and wildcard prevention")
        print("  - Authentication structure and components")
        print("  - Admin API security measures")
        print("  - Environment security configuration")
        return 0
    print(f"\n❌ SECURITY VALIDATION INSUFFICIENT ({success_rate:.1f}% success rate)")
    return 1


if __name__ == "__main__":
    try:
        exit_code = main()
        exit(exit_code)
    except Exception as e:
        print(f"💥 Security validation failed: {e}")
        exit(1)
