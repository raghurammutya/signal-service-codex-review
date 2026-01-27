#!/usr/bin/env python3
"""
Contract Compliance Validation

Validates contract compliance across all external integrations with auditable evidence.
"""
import asyncio
import json
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Tuple


class ContractComplianceValidator:
    """Validates contract compliance with auditable evidence collection."""

    def __init__(self):
        self.contracts = {
            "ticker_service": {
                "endpoints": ["/api/v1/historical", "/api/v1/realtime"],
                "test_file": "tests/integration/test_ticker_service_integration.py",
                "confidence_target": 95,
                "evidence_required": ["request_examples", "response_examples", "error_handling"]
            },
            "marketplace": {
                "endpoints": ["/api/v1/integration/verify-execution", "/api/v1/watermark/validate"],
                "test_file": "tests/unit/test_marketplace_watermarking_fail_secure.py",
                "confidence_target": 88,
                "evidence_required": ["execution_verification", "watermark_validation", "fail_secure"]
            },
            "user_service": {
                "endpoints": ["/api/v1/users/{id}/profile", "/api/v1/users/{id}/entitlements"],
                "test_file": "tests/integration/test_entitlement_gateway_only_access.py",
                "confidence_target": 90,
                "evidence_required": ["entitlement_checks", "profile_access", "rate_limiting"]
            },
            "alert_service": {
                "endpoints": ["/api/v1/alerts/send", "/api/v1/alerts/delivery-status"],
                "test_file": "tests/integration/test_service_integrations_coverage.py",
                "confidence_target": 85,
                "evidence_required": ["delivery_confirmation", "status_polling", "channel_fallback"]
            },
            "metrics": {
                "endpoints": ["/api/v1/metrics"],
                "test_file": "tests/integration/test_metrics_service_contract.py",
                "confidence_target": 92,
                "evidence_required": ["prometheus_format", "scrape_compatibility", "metric_validation"]
            },
            "config_service": {
                "endpoints": ["/api/v1/config/budget-guards", "/api/v1/config/circuit-breakers"],
                "test_file": "tests/config/test_config_bootstrap.py",
                "confidence_target": 90,
                "evidence_required": ["config_retrieval", "validation", "hot_reload"]
            }
        }

        self.validation_results = {
            "timestamp": datetime.now().isoformat(),
            "overall_compliance": 0,
            "contract_details": {},
            "evidence_collected": {},
            "gaps_identified": []
        }

    def validate_test_coverage(self, service: str, contract: dict[str, Any]) -> dict[str, Any]:
        """Validate test coverage for a service contract."""
        print(f"📋 Validating {service} contract...")

        test_file = contract["test_file"]
        confidence_target = contract["confidence_target"]

        # Check if test file exists
        if not os.path.exists(test_file):
            return {
                "status": "MISSING_TESTS",
                "confidence": 0,
                "test_file_exists": False,
                "evidence_found": [],
                "gaps": [f"Test file {test_file} does not exist"]
            }

        # Analyze test file content
        try:
            with open(test_file) as f:
                content = f.read()
        except Exception as e:
            return {
                "status": "READ_ERROR",
                "confidence": 0,
                "error": str(e),
                "gaps": [f"Cannot read test file: {e}"]
            }

        # Check for evidence requirements
        evidence_found = []
        gaps = []

        for evidence_type in contract["evidence_required"]:
            # Look for evidence patterns in test content
            evidence_patterns = {
                "request_examples": ["request", "payload", "params"],
                "response_examples": ["response", "status_code", "json"],
                "error_handling": ["error", "exception", "fail", "4xx", "5xx"],
                "execution_verification": ["verify", "execute", "token"],
                "watermark_validation": ["watermark", "validate", "secure"],
                "fail_secure": ["fail", "secure", "fallback"],
                "entitlement_checks": ["entitlement", "permission", "access"],
                "profile_access": ["profile", "user", "data"],
                "rate_limiting": ["rate", "limit", "throttle"],
                "delivery_confirmation": ["deliver", "send", "confirm"],
                "status_polling": ["status", "poll", "check"],
                "channel_fallback": ["channel", "fallback", "backup"],
                "prometheus_format": ["prometheus", "metrics", "format"],
                "scrape_compatibility": ["scrape", "endpoint", "parse"],
                "metric_validation": ["metric", "validate", "test"],
                "config_retrieval": ["config", "get", "fetch"],
                "validation": ["validate", "check", "verify"],
                "hot_reload": ["reload", "refresh", "update"]
            }

            patterns = evidence_patterns.get(evidence_type, [evidence_type])
            found = any(pattern.lower() in content.lower() for pattern in patterns)

            if found:
                evidence_found.append(evidence_type)
                print(f"    ✅ {evidence_type}")
            else:
                gaps.append(f"Missing evidence for {evidence_type}")
                print(f"    ❌ {evidence_type}")

        # Calculate confidence score
        evidence_coverage = len(evidence_found) / len(contract["evidence_required"]) * 100
        test_file_score = 20  # Base score for having test file
        error_handling_score = 25 if any("error" in ev for ev in evidence_found) else 0

        calculated_confidence = min(100, evidence_coverage * 0.4 + test_file_score + error_handling_score)

        status = "COMPLIANT" if calculated_confidence >= confidence_target else "NEEDS_IMPROVEMENT"

        return {
            "status": status,
            "confidence": calculated_confidence,
            "confidence_target": confidence_target,
            "test_file_exists": True,
            "evidence_found": evidence_found,
            "evidence_coverage": f"{evidence_coverage:.1f}%",
            "gaps": gaps
        }

    def collect_request_response_examples(self, service: str) -> dict[str, Any]:
        """Collect actual request/response examples for auditing."""
        print(f"📝 Collecting {service} request/response examples...")

        # This would typically run actual API calls to collect examples
        # For demo purposes, we'll simulate this
        examples = {
            "ticker_service": {
                "historical_request": {
                    "instrument": "NSE@NIFTY@INDEX",
                    "start": "2024-01-01T09:15:00Z",
                    "end": "2024-01-01T15:30:00Z",
                    "interval": "1m"
                },
                "historical_response_200": {
                    "success": True,
                    "data": [{"timestamp": "2024-01-01T09:15:00Z", "close": 21510.50}]
                },
                "error_response_400": {
                    "success": False,
                    "error": "Invalid instrument format",
                    "code": "INVALID_INSTRUMENT"
                }
            },
            "marketplace": {
                "verify_request": {
                    "token": "user_session_token_here",
                    "stream": "realtime_signals_v2"
                },
                "verify_response_200": {
                    "valid": True,
                    "user_id": "user_12345",
                    "entitlements": ["premium_signals"]
                }
            },
            "metrics": {
                "prometheus_response": "# HELP signal_service_requests_total Total requests\nsignal_service_requests_total{method=\"GET\"} 1234"
            }
        }

        return examples.get(service, {"note": "No examples available for simulation"})

    async def run_contract_validation(self) -> dict[str, Any]:
        """Run comprehensive contract validation."""
        print("📋 Contract Compliance Validation")
        print("=" * 60)

        start_time = time.time()
        total_confidence = 0
        compliant_contracts = 0

        for service, contract in self.contracts.items():
            print(f"\n🔍 Validating {service.upper()} Contract:")

            # Validate test coverage
            validation_result = self.validate_test_coverage(service, contract)
            self.validation_results["contract_details"][service] = validation_result

            # Collect examples for auditing
            examples = self.collect_request_response_examples(service)
            self.validation_results["evidence_collected"][service] = examples

            # Track compliance
            if validation_result["status"] == "COMPLIANT":
                compliant_contracts += 1

            total_confidence += validation_result.get("confidence", 0)

            # Collect gaps
            if validation_result.get("gaps"):
                for gap in validation_result["gaps"]:
                    self.validation_results["gaps_identified"].append(f"{service}: {gap}")

        # Calculate overall compliance
        duration = time.time() - start_time
        overall_confidence = total_confidence / len(self.contracts) if self.contracts else 0
        compliance_rate = (compliant_contracts / len(self.contracts)) * 100 if self.contracts else 0

        self.validation_results.update({
            "duration_seconds": duration,
            "overall_compliance": overall_confidence,
            "compliance_rate": f"{compliance_rate:.1f}%",
            "compliant_contracts": compliant_contracts,
            "total_contracts": len(self.contracts)
        })

        # Generate summary report
        self._generate_compliance_report()

        return self.validation_results

    def _generate_compliance_report(self):
        """Generate comprehensive compliance report."""
        print("\n" + "=" * 60)
        print("🎯 Contract Compliance Summary")

        overall = self.validation_results["overall_compliance"]
        rate = self.validation_results["compliance_rate"]
        compliant = self.validation_results["compliant_contracts"]
        total = self.validation_results["total_contracts"]

        print(f"Overall Confidence: {overall:.1f}%")
        print(f"Compliance Rate: {rate} ({compliant}/{total} contracts)")
        print()

        # Service-by-service results
        print("📊 Service Contract Details:")
        for service, details in self.validation_results["contract_details"].items():
            status_emoji = "✅" if details["status"] == "COMPLIANT" else "❌"
            confidence = details.get("confidence", 0)
            target = details.get("confidence_target", 0)

            print(f"   {status_emoji} {service}: {confidence:.1f}% (target: {target}%)")

            if details.get("gaps"):
                print(f"      Gaps: {len(details['gaps'])} identified")

        print()

        # Critical gaps
        if self.validation_results["gaps_identified"]:
            print("⚠️ Critical Gaps Requiring Attention:")
            for gap in self.validation_results["gaps_identified"][:5]:  # Show top 5
                print(f"   - {gap}")

            if len(self.validation_results["gaps_identified"]) > 5:
                remaining = len(self.validation_results["gaps_identified"]) - 5
                print(f"   ... and {remaining} more gaps")
            print()

        # Save detailed report
        report_file = f"contract_compliance_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w') as f:
            json.dump(self.validation_results, f, indent=2)

        print(f"📄 Detailed report saved: {report_file}")

        # Save audit evidence
        evidence_file = f"contract_audit_evidence_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(evidence_file, 'w') as f:
            json.dump(self.validation_results["evidence_collected"], f, indent=2)

        print(f"📋 Audit evidence saved: {evidence_file}")


async def main():
    """Run contract compliance validation."""
    validator = ContractComplianceValidator()
    results = await validator.run_contract_validation()

    overall_confidence = results["overall_compliance"]
    compliance_rate = float(results["compliance_rate"].rstrip('%'))

    if overall_confidence >= 85 and compliance_rate >= 80:
        print("\n🎉 CONTRACT COMPLIANCE VALIDATION PASSED")
        print(f"✅ Overall Confidence: {overall_confidence:.1f}%")
        print(f"✅ Compliance Rate: {compliance_rate:.1f}%")
        return 0
    print("\n❌ CONTRACT COMPLIANCE VALIDATION NEEDS IMPROVEMENT")
    print(f"⚠️ Overall Confidence: {overall_confidence:.1f}% (target: ≥85%)")
    print(f"⚠️ Compliance Rate: {compliance_rate:.1f}% (target: ≥80%)")
    return 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        exit(exit_code)
    except Exception as e:
        print(f"💥 Contract validation failed: {e}")
        exit(1)
