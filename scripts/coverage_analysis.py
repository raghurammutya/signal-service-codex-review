#!/usr/bin/env python3
"""
Coverage Analysis Script for Critical Modules

Generates per-module coverage reports and identifies uncovered branches
for critical signal service modules to achieve 100% coverage.
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

# Critical modules that must achieve 100% coverage
CRITICAL_MODULES = [
    "app.services.signal_processor",
    "app.core.health_checker",
    "app.services.scaling_components",
    "app.services.historical_data_manager",
    "app.services.signal_delivery_service",
    "app.services.pandas_ta_executor",
    "app.services.vectorized_pyvollib_engine",
    "app.core.distributed_health_manager",
    "app.services.stream_abuse_protection"
]

class CoverageAnalyzer:
    """Analyze coverage reports and identify gaps for 100% target."""

    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.reports_dir = self.project_root / "coverage_reports"
        self.reports_dir.mkdir(exist_ok=True)

    def run_module_coverage(self, module: str) -> dict[str, Any]:
        """Run coverage for a specific module and return detailed results."""
        print(f"📊 Analyzing coverage for {module}...")

        # Convert module path to file path
        module.replace(".", "/") + ".py"

        coverage_file = self.reports_dir / f"coverage_{module.replace('.', '_')}.json"
        html_dir = self.reports_dir / f"html_{module.replace('.', '_')}"

        cmd = [
            sys.executable, "-m", "pytest",
            f"tests/unit/test_{module.split('.')[-1]}.py",
            f"tests/integration/test_{module.split('.')[-1]}_integration.py",
            f"--cov={module}",
            f"--cov-report=json:{coverage_file}",
            f"--cov-report=html:{html_dir}",
            "--cov-report=term-missing",
            "--cov-fail-under=100",
            "-v"
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, cwd=self.project_root)

            # Load coverage data
            coverage_data = {}
            if coverage_file.exists():
                with open(coverage_file) as f:
                    coverage_data = json.load(f)

            return {
                "module": module,
                "success": result.returncode == 0,
                "coverage_data": coverage_data,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "missing_lines": self._extract_missing_lines(result.stdout)
            }

        except Exception as e:
            return {
                "module": module,
                "success": False,
                "error": str(e),
                "coverage_data": {},
                "missing_lines": []
            }

    def _extract_missing_lines(self, stdout: str) -> list[str]:
        """Extract missing line numbers from pytest coverage output."""
        missing_lines = []

        for line in stdout.split('\n'):
            if "TOTAL" not in line and "%" in line and ("missing" in line.lower() or "branch" in line.lower()):
                missing_lines.append(line.strip())

        return missing_lines

    def analyze_all_critical_modules(self) -> dict[str, Any]:
        """Analyze coverage for all critical modules."""
        results = {}

        print("🎯 Running Coverage Analysis for Critical Modules")
        print("=" * 60)

        for module in CRITICAL_MODULES:
            results[module] = self.run_module_coverage(module)

        return results

    def generate_coverage_summary(self, results: dict[str, Any]) -> dict[str, Any]:
        """Generate summary of coverage analysis results."""
        summary = {
            "total_modules": len(CRITICAL_MODULES),
            "modules_at_100_percent": 0,
            "modules_below_100_percent": [],
            "overall_critical_coverage": 0.0,
            "missing_branches": {},
            "action_items": []
        }

        total_coverage = 0.0

        for module, result in results.items():
            if result["success"]:
                coverage_data = result["coverage_data"]
                if coverage_data and "totals" in coverage_data:
                    percent_covered = coverage_data["totals"].get("percent_covered", 0)
                    total_coverage += percent_covered

                    if percent_covered >= 100.0:
                        summary["modules_at_100_percent"] += 1
                    else:
                        summary["modules_below_100_percent"].append({
                            "module": module,
                            "coverage": percent_covered,
                            "missing_lines": result["missing_lines"]
                        })

                        # Extract specific missing branches
                        summary["missing_branches"][module] = result["missing_lines"]
            else:
                summary["modules_below_100_percent"].append({
                    "module": module,
                    "coverage": 0.0,
                    "error": result.get("error", "Test execution failed")
                })

        summary["overall_critical_coverage"] = total_coverage / len(CRITICAL_MODULES)

        # Generate action items for gaps
        for module_info in summary["modules_below_100_percent"]:
            module = module_info["module"]
            coverage = module_info.get("coverage", 0)

            if coverage < 100:
                summary["action_items"].append(
                    f"Add tests for {module}: {100 - coverage:.1f}% gap remaining"
                )

        return summary

    def generate_report(self, results: dict[str, Any], summary: dict[str, Any]) -> str:
        """Generate detailed coverage report."""
        report_lines = [
            "# Critical Modules Coverage Analysis Report",
            f"Generated: {self._get_timestamp()}",
            "",
            "## Summary",
            f"- Total Critical Modules: {summary['total_modules']}",
            f"- Modules at 100%: {summary['modules_at_100_percent']}",
            f"- Overall Critical Coverage: {summary['overall_critical_coverage']:.2f}%",
            "- Target: 100% for all critical modules",
            ""
        ]

        if summary["modules_at_100_percent"] == summary["total_modules"]:
            report_lines.extend([
                "## 🎉 SUCCESS: All Critical Modules at 100% Coverage!",
                "",
                "All critical modules have achieved 100% branch and line coverage.",
                "The signal service is ready for production deployment.",
                ""
            ])
        else:
            report_lines.extend([
                "## 🚨 Coverage Gaps Requiring Attention",
                ""
            ])

            for module_info in summary["modules_below_100_percent"]:
                module = module_info["module"]
                coverage = module_info.get("coverage", 0)

                report_lines.extend([
                    f"### {module}",
                    f"- Current Coverage: {coverage:.2f}%",
                    f"- Gap: {100 - coverage:.2f}%",
                    ""
                ])

                if "missing_lines" in module_info and module_info["missing_lines"]:
                    report_lines.append("Missing Coverage:")
                    for line in module_info["missing_lines"]:
                        report_lines.append(f"  - {line}")
                    report_lines.append("")

        # Action items
        if summary["action_items"]:
            report_lines.extend([
                "## Action Items for 100% Coverage",
                ""
            ])

            for i, action in enumerate(summary["action_items"], 1):
                report_lines.append(f"{i}. {action}")

            report_lines.append("")

        # Detailed results
        report_lines.extend([
            "## Detailed Module Results",
            ""
        ])

        for module, result in results.items():
            status = "✅" if result["success"] else "❌"
            report_lines.append(f"{status} **{module}**")

            if result["success"] and result["coverage_data"]:
                coverage_data = result["coverage_data"]
                if "totals" in coverage_data:
                    totals = coverage_data["totals"]
                    report_lines.extend([
                        f"  - Coverage: {totals.get('percent_covered', 0):.2f}%",
                        f"  - Lines: {totals.get('covered_lines', 0)}/{totals.get('num_statements', 0)}",
                        f"  - Branches: {totals.get('covered_branches', 0)}/{totals.get('num_branches', 0)}",
                        ""
                    ])
            else:
                error_msg = result.get("error", "Coverage analysis failed")
                report_lines.extend([f"  - Error: {error_msg}", ""])

        return "\n".join(report_lines)

    def _get_timestamp(self) -> str:
        """Get current timestamp string."""
        from datetime import datetime
        return datetime.now().isoformat()

    def save_report(self, report: str, filename: str = "critical_modules_coverage_report.md"):
        """Save coverage report to file."""
        report_file = self.reports_dir / filename

        with open(report_file, 'w') as f:
            f.write(report)

        print(f"📝 Coverage report saved to: {report_file}")
        return report_file


def main():
    parser = argparse.ArgumentParser(description="Analyze coverage for critical modules")
    parser.add_argument("--project-root", default=".", help="Project root directory")
    parser.add_argument("--module", help="Analyze specific module only")
    parser.add_argument("--fail-under-100", action="store_true",
                       help="Exit with non-zero code if any critical module < 100%")

    args = parser.parse_args()

    analyzer = CoverageAnalyzer(args.project_root)

    if args.module:
        # Analyze single module
        result = analyzer.run_module_coverage(args.module)
        print(json.dumps(result, indent=2))

        if args.fail_under_100 and not result["success"]:
            sys.exit(1)
    else:
        # Analyze all critical modules
        results = analyzer.analyze_all_critical_modules()
        summary = analyzer.generate_coverage_summary(results)
        report = analyzer.generate_report(results, summary)

        # Print summary
        print("\n" + "="*60)
        print("CRITICAL MODULES COVERAGE SUMMARY")
        print("="*60)
        print(f"Modules at 100%: {summary['modules_at_100_percent']}/{summary['total_modules']}")
        print(f"Overall Coverage: {summary['overall_critical_coverage']:.2f}%")

        if summary["modules_below_100_percent"]:
            print("\nModules needing attention:")
            for module_info in summary["modules_below_100_percent"]:
                print(f"  - {module_info['module']}: {module_info.get('coverage', 0):.2f}%")

        # Save detailed report
        analyzer.save_report(report)

        # Exit with error if not all modules at 100% and flag set
        if args.fail_under_100 and summary["modules_at_100_percent"] < summary["total_modules"]:
            print("\n❌ CRITICAL MODULES COVERAGE CHECK FAILED")
            print("Some critical modules are below 100% coverage threshold.")
            sys.exit(1)

        if summary["modules_at_100_percent"] == summary["total_modules"]:
            print("\n🎉 SUCCESS: All critical modules at 100% coverage!")
        else:
            print(f"\n⚠️  {len(summary['modules_below_100_percent'])} modules need attention for 100% coverage")


if __name__ == "__main__":
    main()
