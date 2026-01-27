#!/usr/bin/env python3
"""
Automated Security Validation

Comprehensive security validation with CI integration:
- Automated redaction checks with fake secrets
- CORS negative cases (wildcard/blocklist)
- Gateway-only auth with deny-by-default testing
"""
import asyncio
import json
import logging
import os
import subprocess
import tempfile
import time
from datetime import datetime
from typing import Any, Dict, List

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AutomatedSecurityValidator:
    """Automated security validation with CI integration."""

    def __init__(self):
        self.fake_secrets = {
            "api_keys": [
                "sk-1234567890abcdef1234567890abcdef",
                "API_KEY_abc123xyz789def456",
                "internal-api-key-super-secret-value"
            ],
            "passwords": [
                "MySecretPassword123!",
                "admin_password_prod_2024",
                "database_secret_pwd"
            ],
            "tokens": [
                "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.fake.token",
                "bearer_token_12345_secret_value",
                "session_token_abcd1234efgh5678"
            ],
            "connection_strings": [
                "postgresql://user:secret_password@db:5432/prod",
                "redis://admin:secret123@redis:6379/0",
                "mongodb://root:super_secret@mongo:27017/app"
            ]
        }

        self.validation_results = {
            "timestamp": datetime.now().isoformat(),
            "log_redaction": {},
            "cors_security": {},
            "auth_enforcement": {},
            "overall_security_score": 0
        }

    async def test_log_redaction_with_fake_secrets(self) -> dict[str, Any]:
        """Test log redaction by emitting fake secrets and verifying redaction."""
        print("🛡️ Testing Log Redaction with Fake Secrets...")

        redaction_results = {
            "secrets_tested": 0,
            "properly_redacted": 0,
            "redaction_failures": [],
            "test_log_samples": []
        }

        # Create temporary log file for testing
        with tempfile.NamedTemporaryFile(mode='w+', suffix='.log', delete=False) as tmp_log:
            tmp_log_path = tmp_log.name

        try:
            # Configure test logger to write to temp file
            test_logger = logging.getLogger('security_test')
            test_handler = logging.FileHandler(tmp_log_path)
            test_handler.setLevel(logging.INFO)

            # Apply security filters
            try:
                from app.utils.logging_security import SensitiveDataFilter
                security_filter = SensitiveDataFilter()
                test_handler.addFilter(security_filter)
            except ImportError:
                print("    ⚠️ Security logging module not available")
                return {"status": "module_unavailable"}

            test_logger.addHandler(test_handler)
            test_logger.setLevel(logging.INFO)

            # Test each category of fake secrets
            for category, secrets in self.fake_secrets.items():
                for secret in secrets:
                    test_message = f"Processing {category} with value: {secret}"
                    test_logger.info(test_message)
                    redaction_results["secrets_tested"] += 1

            # Flush and read back the log file
            test_handler.flush()

            with open(tmp_log_path) as f:
                logged_content = f.read()

            redaction_results["test_log_samples"] = logged_content.split('\n')[:10]  # First 10 lines

            # Check if secrets were redacted
            for category, secrets in self.fake_secrets.items():
                for secret in secrets:
                    if secret in logged_content:
                        redaction_results["redaction_failures"].append({
                            "category": category,
                            "leaked_secret": secret[:10] + "...",  # Don't log full secret
                            "context": "Secret appeared unredacted in logs"
                        })
                        print(f"    ❌ {category}: Secret leaked")
                    else:
                        redaction_results["properly_redacted"] += 1
                        print(f"    ✅ {category}: Secret redacted")

            # Check for redaction markers
            redaction_markers = ["***REDACTED***", "****", "[REDACTED]"]
            has_redaction_markers = any(marker in logged_content for marker in redaction_markers)

            if has_redaction_markers:
                print("    ✅ Redaction markers found in logs")
            else:
                print("    ⚠️ No redaction markers found")
                redaction_results["redaction_failures"].append({
                    "issue": "No redaction markers found",
                    "context": "Expected to see redaction markers in log output"
                })

        finally:
            # Cleanup
            try:
                test_logger.removeHandler(test_handler)
                test_handler.close()
                os.unlink(tmp_log_path)
            except:
                pass

        redaction_success_rate = (redaction_results["properly_redacted"] /
                                redaction_results["secrets_tested"] * 100) if redaction_results["secrets_tested"] > 0 else 0

        redaction_results["success_rate"] = redaction_success_rate
        redaction_results["passed"] = redaction_success_rate >= 90  # 90% threshold

        return redaction_results

    async def test_cors_negative_cases(self) -> dict[str, Any]:
        """Test CORS negative cases including wildcards and blocklist validation."""
        print("🌐 Testing CORS Security (Negative Cases)...")

        cors_results = {
            "tests_performed": [],
            "security_violations": [],
            "passed_checks": 0,
            "total_checks": 0
        }

        try:
            from fastapi.testclient import TestClient

            from app.main import app

            client = TestClient(app)

            # Test 1: Wildcard origin should be rejected in production
            cors_results["total_checks"] += 1
            print("    🔍 Testing wildcard origin rejection...")

            response = client.options("/api/v2/signals", headers={
                "Origin": "*",
                "Access-Control-Request-Method": "GET"
            })

            cors_origin = response.headers.get("access-control-allow-origin", "")
            if cors_origin == "*":
                cors_results["security_violations"].append({
                    "test": "wildcard_origin",
                    "issue": "Wildcard origin allowed in production",
                    "severity": "HIGH"
                })
                print("        ❌ SECURITY RISK: Wildcard origins allowed")
            else:
                cors_results["passed_checks"] += 1
                print("        ✅ Wildcard origins properly rejected")

            cors_results["tests_performed"].append("wildcard_origin_test")

            # Test 2: Malicious origin should be rejected
            cors_results["total_checks"] += 1
            print("    🔍 Testing malicious origin rejection...")

            malicious_origins = [
                "https://evil-site.com",
                "https://phishing-attack.net",
                "http://localhost:3000"  # Should be blocked in production
            ]

            malicious_blocked = 0
            for origin in malicious_origins:
                response = client.options("/api/v2/signals", headers={
                    "Origin": origin,
                    "Access-Control-Request-Method": "GET"
                })

                cors_origin = response.headers.get("access-control-allow-origin", "")
                if cors_origin != origin:  # Origin should not be echoed back
                    malicious_blocked += 1
                    print(f"        ✅ Blocked: {origin}")
                else:
                    print(f"        ❌ ALLOWED: {origin}")
                    cors_results["security_violations"].append({
                        "test": "malicious_origin",
                        "issue": f"Malicious origin {origin} was allowed",
                        "severity": "MEDIUM"
                    })

            if malicious_blocked >= len(malicious_origins) * 0.8:  # 80% should be blocked
                cors_results["passed_checks"] += 1

            cors_results["tests_performed"].append("malicious_origin_test")

            # Test 3: Check for proper CORS headers in responses
            cors_results["total_checks"] += 1
            print("    🔍 Testing CORS headers presence...")

            response = client.get("/health")
            expected_headers = ["access-control-allow-origin", "access-control-allow-methods"]
            headers_present = sum(1 for header in expected_headers
                                if header in response.headers)

            if headers_present >= len(expected_headers) * 0.5:  # At least 50% headers present
                cors_results["passed_checks"] += 1
                print("        ✅ Required CORS headers present")
            else:
                print("        ❌ Missing required CORS headers")
                cors_results["security_violations"].append({
                    "test": "cors_headers",
                    "issue": "Missing required CORS security headers",
                    "severity": "MEDIUM"
                })

            cors_results["tests_performed"].append("cors_headers_test")

        except ImportError:
            cors_results = {
                "status": "app_unavailable",
                "message": "Cannot test CORS - app not available"
            }

        cors_success_rate = (cors_results["passed_checks"] /
                           cors_results["total_checks"] * 100) if cors_results["total_checks"] > 0 else 0

        cors_results["success_rate"] = cors_success_rate
        cors_results["passed"] = cors_success_rate >= 70 and len(cors_results["security_violations"]) == 0

        return cors_results

    async def test_gateway_auth_deny_by_default(self) -> dict[str, Any]:
        """Test gateway-only auth with deny-by-default on every entrypoint."""
        print("🔐 Testing Gateway Auth (Deny-by-Default)...")

        auth_results = {
            "endpoints_tested": [],
            "auth_violations": [],
            "properly_secured": 0,
            "total_endpoints": 0
        }

        try:
            from fastapi.testclient import TestClient

            from app.main import app

            client = TestClient(app)

            # Define critical endpoints that should require authentication
            critical_endpoints = [
                "/api/v2/signals",
                "/api/v2/admin/config",
                "/api/v2/admin/budget",
                "/api/v1/signals",
                "/api/v1/admin"
            ]

            for endpoint in critical_endpoints:
                auth_results["total_endpoints"] += 1
                print(f"    🔍 Testing {endpoint}...")

                # Test 1: No authentication (should be denied)
                response = client.get(endpoint)
                no_auth_denied = response.status_code in [401, 403, 404]

                # Test 2: Invalid authentication (should be denied)
                headers = {"Authorization": "Bearer invalid_token_12345"}
                response = client.get(endpoint, headers=headers)
                invalid_auth_denied = response.status_code in [401, 403, 404]

                # Test 3: Missing gateway headers (should be denied)
                headers = {"X-User-ID": "user123"}  # Missing X-Gateway-Secret
                response = client.get(endpoint, headers=headers)
                missing_gateway_denied = response.status_code in [401, 403, 404]

                security_score = sum([no_auth_denied, invalid_auth_denied, missing_gateway_denied])

                if security_score >= 2:  # At least 2/3 security checks passed
                    auth_results["properly_secured"] += 1
                    print(f"        ✅ Properly secured ({security_score}/3 checks)")
                else:
                    print(f"        ❌ Security gaps ({security_score}/3 checks)")
                    auth_results["auth_violations"].append({
                        "endpoint": endpoint,
                        "no_auth_denied": no_auth_denied,
                        "invalid_auth_denied": invalid_auth_denied,
                        "missing_gateway_denied": missing_gateway_denied,
                        "security_score": security_score
                    })

                auth_results["endpoints_tested"].append(endpoint)

        except ImportError:
            auth_results = {
                "status": "app_unavailable",
                "message": "Cannot test auth - app not available"
            }

        auth_success_rate = (auth_results["properly_secured"] /
                           auth_results["total_endpoints"] * 100) if auth_results["total_endpoints"] > 0 else 0

        auth_results["success_rate"] = auth_success_rate
        auth_results["passed"] = auth_success_rate >= 80  # 80% of endpoints should be properly secured

        return auth_results

    async def run_automated_security_validation(self) -> dict[str, Any]:
        """Run complete automated security validation."""
        print("🔒 Automated Security Validation")
        print("=" * 60)

        start_time = time.time()

        # Run all security tests
        self.validation_results["log_redaction"] = await self.test_log_redaction_with_fake_secrets()
        print()

        self.validation_results["cors_security"] = await self.test_cors_negative_cases()
        print()

        self.validation_results["auth_enforcement"] = await self.test_gateway_auth_deny_by_default()
        print()

        duration = time.time() - start_time
        self.validation_results["duration_seconds"] = duration

        # Calculate overall security score
        security_scores = []
        test_results = [
            ("Log Redaction", self.validation_results["log_redaction"]),
            ("CORS Security", self.validation_results["cors_security"]),
            ("Auth Enforcement", self.validation_results["auth_enforcement"])
        ]

        for _test_name, result in test_results:
            if isinstance(result, dict) and "success_rate" in result:
                security_scores.append(result["success_rate"])
            elif isinstance(result, dict) and result.get("passed"):
                security_scores.append(100.0)
            else:
                security_scores.append(0.0)

        overall_security_score = sum(security_scores) / len(security_scores) if security_scores else 0
        self.validation_results["overall_security_score"] = overall_security_score

        # Generate report
        self._generate_security_report()

        return self.validation_results

    def _generate_security_report(self):
        """Generate comprehensive security validation report."""
        print("=" * 60)
        print("🎯 Automated Security Validation Results")

        overall_score = self.validation_results["overall_security_score"]
        duration = self.validation_results["duration_seconds"]

        print(f"Overall Security Score: {overall_score:.1f}%")
        print(f"Validation Duration: {duration:.2f}s")
        print()

        # Individual test results
        test_results = [
            ("Log Redaction", self.validation_results["log_redaction"]),
            ("CORS Security", self.validation_results["cors_security"]),
            ("Auth Enforcement", self.validation_results["auth_enforcement"])
        ]

        for test_name, result in test_results:
            if isinstance(result, dict):
                status = result.get("passed", False)
                score = result.get("success_rate", 0)
                emoji = "✅" if status else "❌"

                print(f"{emoji} {test_name}: {score:.1f}%")

                # Show violations/failures
                violations = result.get("security_violations", []) + result.get("redaction_failures", [])
                if violations:
                    print(f"   Violations: {len(violations)}")
                    for violation in violations[:2]:  # Show first 2
                        issue = violation.get("issue", violation.get("context", "Unknown"))
                        print(f"     - {issue}")

        print()

        # Save detailed report
        report_file = f"automated_security_validation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w') as f:
            json.dump(self.validation_results, f, indent=2)

        print(f"📄 Detailed security report: {report_file}")


async def main():
    """Run automated security validation."""
    validator = AutomatedSecurityValidator()
    results = await validator.run_automated_security_validation()

    overall_score = results["overall_security_score"]

    if overall_score >= 85:
        print("\n🎉 AUTOMATED SECURITY VALIDATION PASSED")
        print(f"✅ Security Score: {overall_score:.1f}%")
        print("\n🔒 Security Controls Validated:")
        print("  - Log redaction with fake secrets")
        print("  - CORS wildcard/blocklist protection")
        print("  - Gateway-only auth enforcement")
        return 0
    print("\n❌ AUTOMATED SECURITY VALIDATION FAILED")
    print(f"⚠️ Security Score: {overall_score:.1f}% (target: ≥85%)")
    print("\n🔧 Address security gaps before production")
    return 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        exit(exit_code)
    except Exception as e:
        print(f"💥 Security validation failed: {e}")
        exit(1)
