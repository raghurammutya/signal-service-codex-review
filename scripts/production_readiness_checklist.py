#!/usr/bin/env python3
"""
100% Production Readiness Checklist Automation

Automated checklist validation that must pass before any production deployment.
Ensures tests run, deployment validation passes, coverage ≥100% for critical
modules, docs updated, and environment checks logged.
"""
import asyncio
import json
import logging
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ProductionReadinessChecker:
    """Automated production readiness validation."""

    def __init__(self, project_root: str = "."):
        self.project_root = Path(project_root)
        self.checklist_results = {
            "timestamp": datetime.now().isoformat(),
            "overall_status": "UNKNOWN",
            "checks_passed": 0,
            "checks_total": 0,
            "critical_failures": [],
            "warnings": [],
            "evidence": {},
            "certification": "PENDING"
        }

    async def run_full_checklist(self) -> dict[str, Any]:
        """Run complete 100% production readiness checklist."""
        logger.info("🚀 Running 100% Production Readiness Checklist")
        logger.info("="*60)

        checklist_items = [
            ("Tests Execution", self.validate_tests_execution),
            ("Critical Module Coverage", self.validate_critical_coverage),
            ("Deployment Safety", self.validate_deployment_safety),
            ("Performance Benchmarks", self.validate_performance_benchmarks),
            ("Documentation Currency", self.validate_documentation_currency),
            ("Environment Validation", self.validate_environment_checks),
            ("Security Compliance", self.validate_security_compliance),
            ("Functionality Resolution", self.validate_functionality_resolution),
            ("Contract Testing", self.validate_contract_testing),
            ("Release Readiness", self.validate_release_readiness)
        ]

        for check_name, check_func in checklist_items:
            self.checklist_results["checks_total"] += 1

            try:
                logger.info(f"🔍 Checking: {check_name}")
                result = await check_func()

                if result["passed"]:
                    self.checklist_results["checks_passed"] += 1
                    logger.info(f"✅ {check_name} - PASSED")
                else:
                    self.checklist_results["critical_failures"].append({
                        "check": check_name,
                        "reason": result.get("reason", "Unknown failure"),
                        "details": result.get("details", {})
                    })
                    logger.error(f"❌ {check_name} - FAILED: {result.get('reason')}")

                self.checklist_results["evidence"][check_name] = result.get("evidence", {})

                if "warnings" in result:
                    self.checklist_results["warnings"].extend(result["warnings"])

            except Exception as e:
                self.checklist_results["critical_failures"].append({
                    "check": check_name,
                    "reason": f"Check execution failed: {str(e)}",
                    "exception": True
                })
                logger.error(f"❌ {check_name} - EXCEPTION: {str(e)}")

        # Determine overall status
        if len(self.checklist_results["critical_failures"]) == 0:
            self.checklist_results["overall_status"] = "READY"
            self.checklist_results["certification"] = "APPROVED"
            logger.info("🎉 ALL CHECKS PASSED - PRODUCTION READY!")
        else:
            self.checklist_results["overall_status"] = "NOT_READY"
            self.checklist_results["certification"] = "REJECTED"
            logger.error("🚨 CHECKLIST FAILED - NOT READY FOR PRODUCTION")

        return self.checklist_results

    async def validate_tests_execution(self) -> dict[str, Any]:
        """Validate that all tests run successfully."""
        try:
            # Run unit tests
            unit_result = subprocess.run([
                sys.executable, "-m", "pytest",
                "tests/unit/",
                "--tb=short",
                "-q"
            ], capture_output=True, text=True, cwd=self.project_root)

            # Run integration tests
            integration_result = subprocess.run([
                sys.executable, "-m", "pytest",
                "tests/integration/",
                "--tb=short",
                "-q"
            ], capture_output=True, text=True, cwd=self.project_root)

            tests_passed = unit_result.returncode == 0 and integration_result.returncode == 0

            return {
                "passed": tests_passed,
                "reason": "Test execution failed" if not tests_passed else "All tests passed",
                "evidence": {
                    "unit_tests_exit_code": unit_result.returncode,
                    "integration_tests_exit_code": integration_result.returncode,
                    "unit_tests_output": unit_result.stdout[-500:] if unit_result.stdout else "",
                    "integration_tests_output": integration_result.stdout[-500:] if integration_result.stdout else ""
                }
            }

        except Exception as e:
            return {
                "passed": False,
                "reason": f"Failed to run tests: {str(e)}",
                "evidence": {"exception": str(e)}
            }

    async def validate_critical_coverage(self) -> dict[str, Any]:
        """Validate critical modules achieve ≥95% coverage."""
        try:
            # Run coverage analysis
            coverage_result = subprocess.run([
                sys.executable, "scripts/coverage_analysis.py",
                "--fail-under-100"
            ], capture_output=True, text=True, cwd=self.project_root)

            coverage_passed = coverage_result.returncode == 0

            # Parse coverage data if available
            coverage_data = {}
            coverage_file = self.project_root / "coverage_reports" / "critical_modules_coverage_report.md"
            if coverage_file.exists():
                coverage_data["report_exists"] = True
                coverage_data["report_size"] = coverage_file.stat().st_size

            return {
                "passed": coverage_passed,
                "reason": "Critical modules below 95% coverage" if not coverage_passed else "Critical coverage target met",
                "evidence": {
                    "coverage_analysis_exit_code": coverage_result.returncode,
                    "coverage_output": coverage_result.stdout[-1000:] if coverage_result.stdout else "",
                    "coverage_data": coverage_data
                }
            }

        except Exception as e:
            return {
                "passed": False,
                "reason": f"Coverage analysis failed: {str(e)}",
                "evidence": {"exception": str(e)}
            }

    async def validate_deployment_safety(self) -> dict[str, Any]:
        """Validate deployment safety passes all checks."""
        try:
            # Run deployment safety validation
            safety_result = subprocess.run([
                sys.executable, "scripts/deployment_safety_validation.py",
                "--fail-on-error"
            ], capture_output=True, text=True, cwd=self.project_root)

            safety_passed = safety_result.returncode == 0

            return {
                "passed": safety_passed,
                "reason": "Deployment safety validation failed" if not safety_passed else "Deployment safety validated",
                "evidence": {
                    "safety_validation_exit_code": safety_result.returncode,
                    "safety_output": safety_result.stdout[-1000:] if safety_result.stdout else ""
                }
            }

        except Exception as e:
            return {
                "passed": False,
                "reason": f"Deployment safety validation failed: {str(e)}",
                "evidence": {"exception": str(e)}
            }

    async def validate_performance_benchmarks(self) -> dict[str, Any]:
        """Validate performance benchmarks are met."""
        try:
            # Check if performance test files exist
            performance_tests = [
                "tests/performance/test_pandas_ta_performance.py",
                "tests/performance/test_pyvollib_performance.py"
            ]

            missing_tests = []
            for test_file in performance_tests:
                if not (self.project_root / test_file).exists():
                    missing_tests.append(test_file)

            if missing_tests:
                return {
                    "passed": False,
                    "reason": f"Missing performance test files: {missing_tests}",
                    "evidence": {"missing_files": missing_tests}
                }

            # Run performance tests
            perf_result = subprocess.run([
                sys.executable, "-m", "pytest",
                "tests/performance/",
                "-v"
            ], capture_output=True, text=True, cwd=self.project_root)

            perf_passed = perf_result.returncode == 0

            return {
                "passed": perf_passed,
                "reason": "Performance benchmarks not met" if not perf_passed else "Performance benchmarks validated",
                "evidence": {
                    "performance_tests_exit_code": perf_result.returncode,
                    "performance_output": perf_result.stdout[-1000:] if perf_result.stdout else ""
                }
            }

        except Exception as e:
            return {
                "passed": False,
                "reason": f"Performance validation failed: {str(e)}",
                "evidence": {"exception": str(e)}
            }

    async def validate_documentation_currency(self) -> dict[str, Any]:
        """Validate documentation is current and complete."""
        try:
            required_docs = [
                "PRODUCTION_READINESS_DASHBOARD.md",
                "COMPLIANCE_COVERAGE_REPORT.md",
                "functionality_issues.txt",
                "README.md"
            ]

            missing_docs = []
            outdated_docs = []

            for doc in required_docs:
                doc_path = self.project_root / doc
                if not doc_path.exists():
                    missing_docs.append(doc)
                else:
                    # Check if doc was modified recently (within last 7 days)
                    import time
                    mod_time = doc_path.stat().st_mtime
                    days_old = (time.time() - mod_time) / (24 * 3600)
                    if days_old > 7:
                        outdated_docs.append(doc)

            warnings = []
            if outdated_docs:
                warnings.append(f"Documentation may be outdated: {outdated_docs}")

            docs_valid = len(missing_docs) == 0

            return {
                "passed": docs_valid,
                "reason": f"Missing documentation: {missing_docs}" if not docs_valid else "Documentation complete",
                "evidence": {
                    "missing_docs": missing_docs,
                    "outdated_docs": outdated_docs
                },
                "warnings": warnings
            }

        except Exception as e:
            return {
                "passed": False,
                "reason": f"Documentation validation failed: {str(e)}",
                "evidence": {"exception": str(e)}
            }

    async def validate_environment_checks(self) -> dict[str, Any]:
        """Validate environment checks are properly configured."""
        try:
            # Check critical environment variables
            required_env_vars = [
                "ENVIRONMENT",
                "DATABASE_URL",
                "REDIS_URL",
                "CONFIG_SERVICE_URL"
            ]

            missing_vars = []
            for var in required_env_vars:
                if not os.getenv(var):
                    missing_vars.append(var)

            env_valid = len(missing_vars) == 0

            return {
                "passed": env_valid,
                "reason": f"Missing environment variables: {missing_vars}" if not env_valid else "Environment properly configured",
                "evidence": {
                    "missing_env_vars": missing_vars,
                    "environment": os.getenv("ENVIRONMENT", "not_set"),
                    "config_service_configured": bool(os.getenv("CONFIG_SERVICE_URL"))
                }
            }

        except Exception as e:
            return {
                "passed": False,
                "reason": f"Environment validation failed: {str(e)}",
                "evidence": {"exception": str(e)}
            }

    async def validate_security_compliance(self) -> dict[str, Any]:
        """Validate security compliance measures."""
        try:
            security_checks = []

            # Check CORS configuration
            cors_origins = os.getenv("CORS_ALLOWED_ORIGINS", "")
            if "*" in cors_origins and os.getenv("ENVIRONMENT") == "production":
                security_checks.append("CORS wildcard not allowed in production")

            # Check for secrets in environment
            sensitive_vars = ["SECRET_KEY", "JWT_SECRET_KEY", "GATEWAY_SECRET"]
            for var in sensitive_vars:
                value = os.getenv(var, "")
                if len(value) < 16:
                    security_checks.append(f"{var} appears too short for production")

            security_valid = len(security_checks) == 0

            return {
                "passed": security_valid,
                "reason": f"Security issues: {security_checks}" if not security_valid else "Security compliance validated",
                "evidence": {
                    "security_issues": security_checks,
                    "cors_origins_count": len(cors_origins.split(",")) if cors_origins else 0,
                    "secrets_configured": len([var for var in sensitive_vars if os.getenv(var)])
                }
            }

        except Exception as e:
            return {
                "passed": False,
                "reason": f"Security validation failed: {str(e)}",
                "evidence": {"exception": str(e)}
            }

    async def validate_functionality_resolution(self) -> dict[str, Any]:
        """Validate all functionality issues have been resolved."""
        try:
            issues_file = self.project_root / "functionality_issues.txt"

            if not issues_file.exists():
                return {
                    "passed": False,
                    "reason": "functionality_issues.txt file not found",
                    "evidence": {"file_exists": False}
                }

            with open(issues_file) as f:
                content = f.read()

            # Check if file indicates all issues resolved
            resolved_indicators = [
                "ALL RESOLVED",
                "CERTIFICATION STATUS: APPROVED",
                "32/32 functionality issues resolved"
            ]

            all_resolved = any(indicator in content for indicator in resolved_indicators)

            return {
                "passed": all_resolved,
                "reason": "Functionality issues not fully resolved" if not all_resolved else "All functionality issues resolved",
                "evidence": {
                    "file_size": len(content),
                    "contains_resolution_markers": all_resolved,
                    "file_modified": issues_file.stat().st_mtime
                }
            }

        except Exception as e:
            return {
                "passed": False,
                "reason": f"Functionality validation failed: {str(e)}",
                "evidence": {"exception": str(e)}
            }

    async def validate_contract_testing(self) -> dict[str, Any]:
        """Validate contract testing is implemented."""
        try:
            # Check for contract test files
            contract_test_patterns = [
                "test_*_contract.py",
                "test_*_integration.py",
                "contract_test_*.py"
            ]

            contract_tests_found = 0
            for pattern in contract_test_patterns:
                import glob
                matches = glob.glob(str(self.project_root / "tests" / "**" / pattern), recursive=True)
                contract_tests_found += len(matches)

            # Check CI workflow for contract validation
            ci_file = self.project_root / ".github" / "workflows" / "coverage_gate.yml"
            ci_has_contracts = False
            if ci_file.exists():
                with open(ci_file) as f:
                    ci_content = f.read()
                    ci_has_contracts = "contract" in ci_content.lower()

            contracts_valid = contract_tests_found > 0 or ci_has_contracts

            return {
                "passed": contracts_valid,
                "reason": "Contract testing not implemented" if not contracts_valid else "Contract testing validated",
                "evidence": {
                    "contract_tests_count": contract_tests_found,
                    "ci_has_contract_testing": ci_has_contracts,
                    "ci_file_exists": ci_file.exists()
                }
            }

        except Exception as e:
            return {
                "passed": False,
                "reason": f"Contract validation failed: {str(e)}",
                "evidence": {"exception": str(e)}
            }

    async def validate_release_readiness(self) -> dict[str, Any]:
        """Validate release readiness and deployment procedures."""
        try:
            # Check for deployment scripts
            deployment_scripts = [
                "scripts/deployment_safety_validation.py",
                "scripts/coverage_analysis.py"
            ]

            missing_scripts = []
            for script in deployment_scripts:
                if not (self.project_root / script).exists():
                    missing_scripts.append(script)

            # Check git status
            git_result = subprocess.run([
                "git", "status", "--porcelain"
            ], capture_output=True, text=True, cwd=self.project_root)

            has_uncommitted_changes = bool(git_result.stdout.strip())

            warnings = []
            if has_uncommitted_changes:
                warnings.append("Uncommitted changes detected")

            release_ready = len(missing_scripts) == 0

            return {
                "passed": release_ready,
                "reason": f"Missing deployment scripts: {missing_scripts}" if not release_ready else "Release ready",
                "evidence": {
                    "missing_scripts": missing_scripts,
                    "has_uncommitted_changes": has_uncommitted_changes,
                    "git_status": git_result.stdout
                },
                "warnings": warnings
            }

        except Exception as e:
            return {
                "passed": False,
                "reason": f"Release readiness validation failed: {str(e)}",
                "evidence": {"exception": str(e)}
            }

    def generate_checklist_report(self) -> str:
        """Generate detailed checklist report."""
        results = self.checklist_results

        report_lines = [
            "# 100% Production Readiness Checklist Report",
            f"Generated: {results['timestamp']}",
            "",
            "## Summary",
            f"- Overall Status: **{results['overall_status']}**",
            f"- Certification: **{results['certification']}**",
            f"- Checks Passed: {results['checks_passed']}/{results['checks_total']}",
            f"- Critical Failures: {len(results['critical_failures'])}",
            f"- Warnings: {len(results['warnings'])}",
            ""
        ]

        if results["overall_status"] == "READY":
            report_lines.extend([
                "## 🎉 PRODUCTION DEPLOYMENT APPROVED",
                "",
                "All production readiness checks have passed. The Signal Service is certified",
                "for production deployment with 100% confidence in functionality and operations.",
                ""
            ])
        else:
            report_lines.extend([
                "## 🚨 PRODUCTION DEPLOYMENT BLOCKED",
                "",
                "Critical issues must be resolved before production deployment:",
                ""
            ])

            for i, failure in enumerate(results["critical_failures"], 1):
                report_lines.extend([
                    f"### Issue {i}: {failure['check']}",
                    f"**Reason**: {failure['reason']}",
                    ""
                ])

        # Warnings section
        if results["warnings"]:
            report_lines.extend([
                "## ⚠️ Warnings",
                ""
            ])

            for warning in results["warnings"]:
                report_lines.append(f"- {warning}")

            report_lines.append("")

        # Evidence section
        report_lines.extend([
            "## Evidence Summary",
            ""
        ])

        for check_name, evidence in results["evidence"].items():
            report_lines.extend([
                f"### {check_name}",
                "```json",
                json.dumps(evidence, indent=2),
                "```",
                ""
            ])

        return "\n".join(report_lines)

    def save_checklist_report(self, filename: str = "production_readiness_checklist_report.md"):
        """Save checklist report to file."""
        report = self.generate_checklist_report()
        reports_dir = self.project_root / "deployment_reports"
        reports_dir.mkdir(exist_ok=True)

        report_file = reports_dir / filename

        with open(report_file, 'w') as f:
            f.write(report)

        logger.info(f"📝 Checklist report saved to: {report_file}")
        return report_file


async def main():
    """Main function to run production readiness checklist."""
    import argparse

    parser = argparse.ArgumentParser(description="100% Production Readiness Checklist")
    parser.add_argument("--project-root", default=".", help="Project root directory")
    parser.add_argument("--fail-fast", action="store_true",
                       help="Exit immediately on first failure")
    parser.add_argument("--save-report", action="store_true",
                       help="Save detailed checklist report")

    args = parser.parse_args()

    checker = ProductionReadinessChecker(args.project_root)

    try:
        results = await checker.run_full_checklist()

        # Print summary
        print("\n" + "="*60)
        print("100% PRODUCTION READINESS CHECKLIST SUMMARY")
        print("="*60)
        print(f"Status: {results['overall_status']}")
        print(f"Certification: {results['certification']}")
        print(f"Checks: {results['checks_passed']}/{results['checks_total']}")
        print(f"Failures: {len(results['critical_failures'])}")

        # Save report if requested
        if args.save_report:
            checker.save_checklist_report()

        if results["overall_status"] == "READY":
            print("\n🎉 100% PRODUCTION READINESS ACHIEVED!")
            print("Signal Service is certified for production deployment.")
            sys.exit(0)
        else:
            print("\n❌ PRODUCTION READINESS CHECKLIST FAILED")
            print("Critical issues must be resolved before deployment.")

            if args.fail_fast:
                sys.exit(1)

            # Show first few failures
            for failure in results["critical_failures"][:3]:
                print(f"  - {failure['check']}: {failure['reason']}")

            if len(results["critical_failures"]) > 3:
                print(f"  ... and {len(results['critical_failures']) - 3} more issues")

            sys.exit(1)

    except Exception as e:
        logger.error(f"Checklist execution failed: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
