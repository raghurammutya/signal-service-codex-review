#!/usr/bin/env python3
"""
Integration Assessment Validation Script

Comprehensive validation of all external service interactions to achieve
≥95% integration coverage for production readiness certification.
"""
import asyncio
import json
import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class IntegrationAssessmentValidator:
    """Validates all service integrations for production readiness."""

    def __init__(self, project_root: str = "."):
        self.project_root = Path(project_root)
        self.results = {
            "timestamp": datetime.now().isoformat(),
            "overall_confidence": 0.0,
            "target_confidence": 95.0,
            "service_interactions": {},
            "critical_gaps": [],
            "coverage_reports": {},
            "production_ready": False
        }

        # Define critical integration test suites
        self.integration_test_suites = {
            # Critical Service Integrations
            "metrics_service": {
                "test_file": "tests/integration/test_metrics_service.py",
                "coverage_modules": ["app.services.metrics_service"],
                "confidence_weight": 10
            },
            "watermark_fail_secure": {
                "test_file": "tests/integration/test_watermark_fail_secure.py",
                "coverage_modules": ["app.services.enhanced_watermark_integration", "app.services.signal_delivery_service"],
                "confidence_weight": 10
            },
            "gateway_acl": {
                "test_file": "tests/integration/test_gateway_acl_integration.py",
                "coverage_modules": ["app.middleware.entitlement_middleware", "app.middleware.ratelimit"],
                "confidence_weight": 9
            },

            # Core Engine Integrations
            "pandas_ta_real_data": {
                "test_file": "tests/unit/test_pandas_ta_coverage_with_real_data.py",
                "coverage_modules": ["app.services.pandas_ta_executor"],
                "confidence_weight": 10
            },
            "pyvollib_vectorized": {
                "test_file": "tests/unit/test_pyvollib_vectorized_engine_fallback.py",
                "coverage_modules": ["app.services.vectorized_pyvollib_engine"],
                "confidence_weight": 10
            },
            "optional_dependencies": {
                "test_file": "tests/unit/test_optional_dependencies_computation_errors.py",
                "coverage_modules": ["app.services"],
                "confidence_weight": 8
            },

            # Service Client Integrations
            "ticker_service": {
                "test_file": "tests/integration/test_ticker_service_integration.py",
                "coverage_modules": ["app.clients.ticker_service_client", "app.services.historical_data_manager"],
                "confidence_weight": 9
            },
            "config_bootstrap": {
                "test_file": "tests/config/test_config_bootstrap.py",
                "coverage_modules": ["common.config_service"],
                "confidence_weight": 8
            },
            "signal_delivery": {
                "test_file": "tests/unit/test_signal_delivery_service.py",
                "coverage_modules": ["app.services.signal_delivery_service"],
                "confidence_weight": 9
            },

            # Infrastructure Integrations
            "cors_validation": {
                "test_file": "tests/unit/test_cors_validation_coverage.py",
                "coverage_modules": ["common.cors_config"],
                "confidence_weight": 7
            },
            "database_session": {
                "test_file": "tests/unit/test_database_session_coverage.py",
                "coverage_modules": ["common.storage.database"],
                "confidence_weight": 8
            },
            "health_metrics": {
                "test_file": "tests/unit/test_health_metrics_positive_coverage.py",
                "coverage_modules": ["app.core.health_checker", "app.core.distributed_health_manager"],
                "confidence_weight": 8
            }
        }

    async def validate_all_integrations(self) -> dict[str, Any]:
        """Run comprehensive integration validation."""
        logger.info("🔍 Starting Comprehensive Integration Assessment")
        logger.info("="*60)

        total_weight = 0
        weighted_confidence = 0

        for suite_name, suite_config in self.integration_test_suites.items():
            logger.info(f"Validating integration: {suite_name}")

            result = await self.validate_integration_suite(suite_name, suite_config)
            self.results["service_interactions"][suite_name] = result

            # Calculate weighted confidence
            weight = suite_config["confidence_weight"]
            confidence = result["confidence_percentage"]

            total_weight += weight
            weighted_confidence += confidence * weight

            if confidence < 95.0:
                self.results["critical_gaps"].append({
                    "integration": suite_name,
                    "confidence": confidence,
                    "gap": 95.0 - confidence,
                    "issues": result.get("issues", [])
                })

        # Calculate overall confidence
        self.results["overall_confidence"] = weighted_confidence / total_weight if total_weight > 0 else 0
        self.results["production_ready"] = (
            self.results["overall_confidence"] >= 95.0 and
            len(self.results["critical_gaps"]) == 0
        )

        return self.results

    async def validate_integration_suite(self, suite_name: str, suite_config: dict[str, Any]) -> dict[str, Any]:
        """Validate a specific integration test suite."""
        test_file = self.project_root / suite_config["test_file"]
        coverage_modules = suite_config["coverage_modules"]

        result = {
            "suite_name": suite_name,
            "test_file": str(test_file),
            "coverage_modules": coverage_modules,
            "confidence_percentage": 0.0,
            "coverage_data": {},
            "test_results": {},
            "issues": []
        }

        try:
            # Check if test file exists
            if not test_file.exists():
                result["issues"].append(f"Test file not found: {test_file}")
                return result

            # Run tests with coverage
            coverage_result = await self.run_coverage_test(test_file, coverage_modules)
            result["coverage_data"] = coverage_result["coverage"]
            result["test_results"] = coverage_result["test_output"]

            # Calculate confidence based on coverage
            line_coverage = coverage_result["coverage"].get("line_coverage", 0)
            branch_coverage = coverage_result["coverage"].get("branch_coverage", 0)
            test_success = coverage_result["test_success"]

            # Confidence formula: weighted average of coverage metrics + test success bonus
            base_confidence = (line_coverage * 0.6 + branch_coverage * 0.4)
            test_bonus = 10 if test_success else -20

            result["confidence_percentage"] = min(100, max(0, base_confidence + test_bonus))

            # Identify specific issues
            if line_coverage < 95:
                result["issues"].append(f"Line coverage ({line_coverage:.1f}%) below 95%")
            if branch_coverage < 95:
                result["issues"].append(f"Branch coverage ({branch_coverage:.1f}%) below 95%")
            if not test_success:
                result["issues"].append("Test execution failed")

        except Exception as e:
            result["issues"].append(f"Validation failed: {str(e)}")
            logger.error(f"Error validating {suite_name}: {str(e)}")

        return result

    async def run_coverage_test(self, test_file: Path, coverage_modules: list[str]) -> dict[str, Any]:
        """Run coverage test for specific modules."""
        # Build coverage command
        coverage_args = []
        for module in coverage_modules:
            coverage_args.extend(["--cov", module])

        # Create coverage report directory
        coverage_dir = self.project_root / "coverage_reports"
        coverage_dir.mkdir(exist_ok=True)

        suite_name = test_file.stem.replace("test_", "")
        json_report = coverage_dir / f"coverage_{suite_name}.json"
        html_report = coverage_dir / f"html_{suite_name}"

        cmd = [
            sys.executable, "-m", "pytest",
            str(test_file),
            *coverage_args,
            "--cov-report=term-missing",
            f"--cov-report=json:{json_report}",
            f"--cov-report=html:{html_report}",
            "--tb=short",
            "-v"
        ]

        # Run test with timeout
        try:
            result = await asyncio.wait_for(
                asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=self.project_root
                ),
                timeout=300  # 5 minute timeout
            )

            stdout, stderr = await result.communicate()
            test_success = result.returncode == 0

            # Parse coverage data
            coverage_data = {"line_coverage": 0, "branch_coverage": 0}
            if json_report.exists() and test_success:
                try:
                    with open(json_report) as f:
                        coverage_json = json.load(f)

                    totals = coverage_json.get("totals", {})
                    coverage_data["line_coverage"] = totals.get("percent_covered", 0)
                    coverage_data["branch_coverage"] = totals.get("percent_covered_display", 0)

                    # Try to extract branch coverage from summary
                    summary = coverage_json.get("files", {})
                    if summary:
                        total_branches = sum(file_data.get("summary", {}).get("num_branches", 0) for file_data in summary.values())
                        covered_branches = sum(file_data.get("summary", {}).get("covered_branches", 0) for file_data in summary.values())

                        if total_branches > 0:
                            coverage_data["branch_coverage"] = (covered_branches / total_branches) * 100

                except Exception as e:
                    logger.warning(f"Failed to parse coverage data: {e}")

            return {
                "test_success": test_success,
                "coverage": coverage_data,
                "test_output": {
                    "stdout": stdout.decode() if stdout else "",
                    "stderr": stderr.decode() if stderr else "",
                    "exit_code": result.returncode
                }
            }

        except TimeoutError:
            return {
                "test_success": False,
                "coverage": {"line_coverage": 0, "branch_coverage": 0},
                "test_output": {"error": "Test execution timed out"}
            }
        except Exception as e:
            return {
                "test_success": False,
                "coverage": {"line_coverage": 0, "branch_coverage": 0},
                "test_output": {"error": f"Test execution failed: {str(e)}"}
            }

    def generate_assessment_report(self) -> str:
        """Generate comprehensive integration assessment report."""
        results = self.results

        report_lines = [
            "# Integration Assessment Validation Report",
            f"Generated: {results['timestamp']}",
            "",
            "## Executive Summary",
            f"- Overall Integration Confidence: **{results['overall_confidence']:.1f}%**",
            f"- Target Confidence: **{results['target_confidence']:.1f}%**",
            f"- Production Ready: **{'YES' if results['production_ready'] else 'NO'}**",
            f"- Critical Gaps: **{len(results['critical_gaps'])}**",
            f"- Service Interactions Tested: **{len(results['service_interactions'])}**",
            ""
        ]

        if results["production_ready"]:
            report_lines.extend([
                "## 🎉 INTEGRATION ASSESSMENT PASSED",
                "",
                "All service integrations meet the ≥95% confidence threshold.",
                "The Signal Service is certified for production deployment.",
                ""
            ])
        else:
            report_lines.extend([
                "## 🚨 INTEGRATION ASSESSMENT FAILED",
                "",
                "Critical gaps must be resolved before production deployment:",
                ""
            ])

            for gap in results["critical_gaps"]:
                report_lines.extend([
                    f"### {gap['integration']} - {gap['confidence']:.1f}% Confidence",
                    f"**Gap**: {gap['gap']:.1f}% below target",
                    "**Issues**:"
                ])

                for issue in gap["issues"]:
                    report_lines.append(f"  - {issue}")

                report_lines.append("")

        # Detailed results
        report_lines.extend([
            "## Detailed Integration Results",
            ""
        ])

        for suite_name, result in results["service_interactions"].items():
            status_emoji = "✅" if result["confidence_percentage"] >= 95 else "❌"
            report_lines.extend([
                f"{status_emoji} **{suite_name}** - {result['confidence_percentage']:.1f}%",
                f"  - Test File: `{result['test_file']}`",
                f"  - Modules: `{', '.join(result['coverage_modules'])}`"
            ])

            if result["coverage_data"]:
                coverage = result["coverage_data"]
                report_lines.extend([
                    f"  - Line Coverage: {coverage.get('line_coverage', 0):.1f}%",
                    f"  - Branch Coverage: {coverage.get('branch_coverage', 0):.1f}%"
                ])

            if result["issues"]:
                report_lines.append("  - Issues:")
                for issue in result["issues"]:
                    report_lines.append(f"    * {issue}")

            report_lines.append("")

        return "\n".join(report_lines)

    def save_assessment_report(self, filename: str = "integration_assessment_report.md"):
        """Save integration assessment report."""
        report = self.generate_assessment_report()
        reports_dir = self.project_root / "coverage_reports"
        reports_dir.mkdir(exist_ok=True)

        report_file = reports_dir / filename
        with open(report_file, 'w') as f:
            f.write(report)

        logger.info(f"📝 Integration assessment report saved to: {report_file}")
        return report_file


async def main():
    """Main function to run integration assessment validation."""
    import argparse

    parser = argparse.ArgumentParser(description="Integration Assessment Validation")
    parser.add_argument("--project-root", default=".", help="Project root directory")
    parser.add_argument("--comprehensive", action="store_true",
                       help="Run comprehensive validation of all integrations")
    parser.add_argument("--integration-focus", action="store_true",
                       help="Focus on integration test suites only")
    parser.add_argument("--fail-under-95", action="store_true",
                       help="Exit with error if overall confidence < 95%")

    args = parser.parse_args()

    validator = IntegrationAssessmentValidator(args.project_root)

    try:
        results = await validator.validate_all_integrations()

        # Print summary
        print("\n" + "="*60)
        print("INTEGRATION ASSESSMENT VALIDATION SUMMARY")
        print("="*60)
        print(f"Overall Confidence: {results['overall_confidence']:.1f}%")
        print(f"Target: {results['target_confidence']:.1f}%")
        print(f"Production Ready: {'YES' if results['production_ready'] else 'NO'}")
        print(f"Critical Gaps: {len(results['critical_gaps'])}")

        # Save detailed report
        validator.save_assessment_report()

        if results["production_ready"]:
            print("\n🎉 INTEGRATION ASSESSMENT PASSED!")
            print("All service integrations meet ≥95% confidence threshold.")
            sys.exit(0)
        else:
            print("\n❌ INTEGRATION ASSESSMENT FAILED")
            print("Critical integration gaps must be resolved:")

            for gap in results["critical_gaps"][:3]:
                print(f"  - {gap['integration']}: {gap['confidence']:.1f}%")

            if len(results["critical_gaps"]) > 3:
                print(f"  ... and {len(results['critical_gaps']) - 3} more")

            if args.fail_under_95:
                sys.exit(1)

    except Exception as e:
        logger.error(f"Integration assessment failed: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
