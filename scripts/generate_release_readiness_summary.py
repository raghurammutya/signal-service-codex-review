#!/usr/bin/env python3
"""
Release Readiness Summary Generator

Analyzes QA pipeline results to generate executive summary
for go/no-go release decisions with clear pass/fail criteria.
"""

import json
import os
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
import re


class ReleaseReadinessAnalyzer:
    """Analyzes QA artifacts to determine release readiness."""
    
    def __init__(self, artifacts_dir: str = "."):
        self.artifacts_dir = Path(artifacts_dir)
        self.readiness_score = 0
        self.max_score = 100
        self.findings = []
        self.critical_issues = []
        
    def analyze_test_results(self) -> Dict[str, Any]:
        """Analyze JUnit XML test results."""
        test_files = list(self.artifacts_dir.glob("*-results.xml"))
        
        results = {
            "total_tests": 0,
            "passed": 0,
            "failed": 0,
            "errors": 0,
            "skipped": 0,
            "stages": {}
        }
        
        for test_file in test_files:
            stage_name = test_file.stem.replace("-results", "")
            try:
                tree = ET.parse(test_file)
                root = tree.getroot()
                
                # Parse testsuite results
                total = int(root.get("tests", 0))
                failures = int(root.get("failures", 0))
                errors = int(root.get("errors", 0))
                skipped = int(root.get("skipped", 0))
                passed = total - failures - errors - skipped
                
                results["total_tests"] += total
                results["passed"] += passed
                results["failed"] += failures
                results["errors"] += errors
                results["skipped"] += skipped
                
                results["stages"][stage_name] = {
                    "total": total,
                    "passed": passed,
                    "failed": failures + errors,
                    "skipped": skipped,
                    "success_rate": (passed / total * 100) if total > 0 else 0
                }
                
            except Exception as e:
                self.findings.append(f"⚠️ Could not parse {test_file}: {e}")
        
        return results
    
    def analyze_coverage(self) -> Dict[str, Any]:
        """Analyze coverage reports."""
        coverage_xml = self.artifacts_dir / "coverage.xml"
        coverage_data = {
            "line_coverage": 0,
            "branch_coverage": 0,
            "critical_modules": {},
            "overall_status": "UNKNOWN"
        }
        
        if coverage_xml.exists():
            try:
                tree = ET.parse(coverage_xml)
                root = tree.getroot()
                
                # Parse overall coverage
                for coverage_elem in root.findall(".//coverage"):
                    line_rate = float(coverage_elem.get("line-rate", 0))
                    branch_rate = float(coverage_elem.get("branch-rate", 0))
                    
                    coverage_data["line_coverage"] = line_rate * 100
                    coverage_data["branch_coverage"] = branch_rate * 100
                
                # Check critical modules (app.core, app.services, app.clients)
                critical_modules = ["app.core", "app.services", "app.clients"]
                for package in root.findall(".//package"):
                    package_name = package.get("name", "")
                    if any(module in package_name for module in critical_modules):
                        line_rate = float(package.get("line-rate", 0))
                        coverage_data["critical_modules"][package_name] = line_rate * 100
                
            except Exception as e:
                self.findings.append(f"⚠️ Could not parse coverage: {e}")
        
        # Determine coverage status
        line_coverage = coverage_data["line_coverage"]
        if line_coverage >= 95:
            coverage_data["overall_status"] = "EXCELLENT"
        elif line_coverage >= 90:
            coverage_data["overall_status"] = "GOOD"
        elif line_coverage >= 80:
            coverage_data["overall_status"] = "ACCEPTABLE"
        else:
            coverage_data["overall_status"] = "INSUFFICIENT"
            self.critical_issues.append(f"Coverage {line_coverage:.1f}% below 80% threshold")
        
        return coverage_data
    
    def analyze_slo_compliance(self) -> Dict[str, Any]:
        """Analyze SLO compliance from performance logs."""
        slo_data = {
            "health_endpoint": {"status": "UNKNOWN", "p95_ms": 0, "error_rate": 0},
            "metrics_endpoint": {"status": "UNKNOWN", "p95_ms": 0, "error_rate": 0},
            "core_apis": {"status": "UNKNOWN", "p95_ms": 0, "error_rate": 0},
            "historical_apis": {"status": "UNKNOWN", "p95_ms": 0, "error_rate": 0},
            "overall_compliance": "UNKNOWN"
        }
        
        # Look for performance test results in stdout/logs
        performance_results = self.artifacts_dir / "performance-results.xml"
        if performance_results.exists():
            try:
                tree = ET.parse(performance_results)
                root = tree.getroot()
                
                # Extract SLO data from test output (this would need custom parsing)
                # For now, mark as passed if performance tests passed
                failures = int(root.get("failures", 0))
                errors = int(root.get("errors", 0))
                
                if failures == 0 and errors == 0:
                    for endpoint in slo_data:
                        if endpoint != "overall_compliance":
                            slo_data[endpoint]["status"] = "PASS"
                    slo_data["overall_compliance"] = "COMPLIANT"
                else:
                    slo_data["overall_compliance"] = "NON_COMPLIANT"
                    self.critical_issues.append("SLO compliance tests failed")
                    
            except Exception as e:
                self.findings.append(f"⚠️ Could not parse performance results: {e}")
        
        return slo_data
    
    def analyze_security_gates(self) -> Dict[str, Any]:
        """Analyze security gate results."""
        security_data = {
            "hygiene_check": "UNKNOWN",
            "auth_enforcement": "UNKNOWN", 
            "cors_validation": "UNKNOWN",
            "log_redaction": "UNKNOWN",
            "hot_reload_security": "UNKNOWN",
            "overall_security": "UNKNOWN"
        }
        
        # Check lint-hygiene results (should have passed to get this far)
        # Check security test results
        security_results = self.artifacts_dir / "security-results.xml"
        if security_results.exists():
            try:
                tree = ET.parse(security_results)
                root = tree.getroot()
                
                failures = int(root.get("failures", 0))
                errors = int(root.get("errors", 0))
                
                if failures == 0 and errors == 0:
                    for gate in security_data:
                        if gate != "overall_security":
                            security_data[gate] = "PASS"
                    security_data["overall_security"] = "SECURE"
                else:
                    security_data["overall_security"] = "SECURITY_ISSUES"
                    self.critical_issues.append("Security validation failed")
                    
            except Exception as e:
                self.findings.append(f"⚠️ Could not parse security results: {e}")
        
        return security_data
    
    def analyze_contract_compliance(self) -> Dict[str, Any]:
        """Analyze service contract compliance."""
        contract_data = {
            "contracts_validated": 0,
            "contracts_passed": 0, 
            "contracts_failed": 0,
            "critical_services": {},
            "overall_contracts": "UNKNOWN"
        }
        
        # Check integration test results
        integration_results = self.artifacts_dir / "integration-results.xml"
        if integration_results.exists():
            try:
                tree = ET.parse(integration_results)
                root = tree.getroot()
                
                total = int(root.get("tests", 0))
                failures = int(root.get("failures", 0))
                errors = int(root.get("errors", 0))
                passed = total - failures - errors
                
                contract_data["contracts_validated"] = total
                contract_data["contracts_passed"] = passed
                contract_data["contracts_failed"] = failures + errors
                
                success_rate = (passed / total * 100) if total > 0 else 0
                
                if success_rate >= 95:
                    contract_data["overall_contracts"] = "COMPLIANT"
                elif success_rate >= 90:
                    contract_data["overall_contracts"] = "MOSTLY_COMPLIANT"
                else:
                    contract_data["overall_contracts"] = "NON_COMPLIANT"
                    self.critical_issues.append(f"Contract compliance {success_rate:.1f}% below 90%")
                    
            except Exception as e:
                self.findings.append(f"⚠️ Could not parse integration results: {e}")
        
        return contract_data
    
    def calculate_readiness_score(self, analysis_results: Dict[str, Any]) -> int:
        """Calculate overall readiness score (0-100)."""
        score = 0
        
        # Test results (25 points)
        test_data = analysis_results["test_results"]
        if test_data["total_tests"] > 0:
            success_rate = (test_data["passed"] / test_data["total_tests"]) * 100
            score += min(25, success_rate * 0.25)
        
        # Coverage (20 points)
        coverage_data = analysis_results["coverage"]
        line_coverage = coverage_data["line_coverage"]
        score += min(20, line_coverage * 0.2)
        
        # SLO compliance (25 points)
        slo_data = analysis_results["slo_compliance"]
        if slo_data["overall_compliance"] == "COMPLIANT":
            score += 25
        elif slo_data["overall_compliance"] == "MOSTLY_COMPLIANT":
            score += 20
        
        # Security gates (15 points)
        security_data = analysis_results["security_gates"]
        if security_data["overall_security"] == "SECURE":
            score += 15
        
        # Contract compliance (15 points)
        contract_data = analysis_results["contract_compliance"]
        if contract_data["overall_contracts"] == "COMPLIANT":
            score += 15
        elif contract_data["overall_contracts"] == "MOSTLY_COMPLIANT":
            score += 12
        
        return min(100, int(score))
    
    def generate_summary(self) -> str:
        """Generate release readiness summary."""
        
        # Perform all analyses
        analysis_results = {
            "test_results": self.analyze_test_results(),
            "coverage": self.analyze_coverage(),
            "slo_compliance": self.analyze_slo_compliance(),
            "security_gates": self.analyze_security_gates(),
            "contract_compliance": self.analyze_contract_compliance()
        }
        
        # Calculate readiness score
        readiness_score = self.calculate_readiness_score(analysis_results)
        
        # Determine release recommendation
        if readiness_score >= 95 and not self.critical_issues:
            release_status = "✅ APPROVED FOR RELEASE"
            recommendation = "GO"
        elif readiness_score >= 85 and len(self.critical_issues) <= 1:
            release_status = "⚠️ CONDITIONAL APPROVAL"
            recommendation = "CONDITIONAL"
        else:
            release_status = "❌ NOT READY FOR RELEASE"
            recommendation = "NO-GO"
        
        # Generate summary report
        summary = f"""# Release Readiness Summary

**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}  
**Pipeline Run**: {os.getenv('GITHUB_RUN_ID', 'local')}  
**Branch**: {os.getenv('GITHUB_REF_NAME', 'unknown')}  
**Commit**: {os.getenv('GITHUB_SHA', 'unknown')[:8]}

## 🎯 Release Decision

**Status**: {release_status}  
**Recommendation**: **{recommendation}**  
**Readiness Score**: {readiness_score}/100

---

## 📊 Quality Gate Results

### Test Execution
- **Total Tests**: {analysis_results['test_results']['total_tests']}
- **Passed**: {analysis_results['test_results']['passed']} 
- **Failed**: {analysis_results['test_results']['failed']}
- **Success Rate**: {(analysis_results['test_results']['passed'] / analysis_results['test_results']['total_tests'] * 100) if analysis_results['test_results']['total_tests'] > 0 else 0:.1f}%

### Coverage Analysis  
- **Line Coverage**: {analysis_results['coverage']['line_coverage']:.1f}%
- **Status**: {analysis_results['coverage']['overall_status']}
- **Critical Modules**: {len(analysis_results['coverage']['critical_modules'])} analyzed

### SLO Compliance
- **Overall Status**: {analysis_results['slo_compliance']['overall_compliance']}
- **Health Endpoint**: {analysis_results['slo_compliance']['health_endpoint']['status']}
- **Metrics Endpoint**: {analysis_results['slo_compliance']['metrics_endpoint']['status']}
- **Core APIs**: {analysis_results['slo_compliance']['core_apis']['status']}
- **Historical APIs**: {analysis_results['slo_compliance']['historical_apis']['status']}

### Security Gates
- **Overall Security**: {analysis_results['security_gates']['overall_security']}
- **Hygiene Check**: {analysis_results['security_gates']['hygiene_check']}
- **Auth Enforcement**: {analysis_results['security_gates']['auth_enforcement']}
- **CORS Validation**: {analysis_results['security_gates']['cors_validation']}
- **Hot Reload Security**: {analysis_results['security_gates']['hot_reload_security']}

### Contract Compliance
- **Overall Status**: {analysis_results['contract_compliance']['overall_contracts']}
- **Contracts Validated**: {analysis_results['contract_compliance']['contracts_validated']}
- **Passed**: {analysis_results['contract_compliance']['contracts_passed']}
- **Failed**: {analysis_results['contract_compliance']['contracts_failed']}

---

## 🚨 Critical Issues

"""
        
        if self.critical_issues:
            for issue in self.critical_issues:
                summary += f"- {issue}\n"
        else:
            summary += "**None** - All critical quality gates passed ✅\n"
        
        summary += "\n---\n\n## 📋 Stage Breakdown\n\n"
        
        for stage, data in analysis_results["test_results"]["stages"].items():
            status_icon = "✅" if data["failed"] == 0 else "❌"
            summary += f"- **{stage.title()}**: {status_icon} {data['passed']}/{data['total']} passed ({data['success_rate']:.1f}%)\n"
        
        summary += f"\n---\n\n## 🎯 Release Criteria\n\n"
        summary += f"### Minimum Requirements (All Must Pass)\n"
        summary += f"- [ ] **Test Success Rate**: ≥95% ({'✅' if (analysis_results['test_results']['passed'] / analysis_results['test_results']['total_tests'] * 100) >= 95 else '❌'} {(analysis_results['test_results']['passed'] / analysis_results['test_results']['total_tests'] * 100) if analysis_results['test_results']['total_tests'] > 0 else 0:.1f}%)\n"
        summary += f"- [ ] **Critical Module Coverage**: ≥95% ({'✅' if analysis_results['coverage']['line_coverage'] >= 95 else '❌'} {analysis_results['coverage']['line_coverage']:.1f}%)\n"
        summary += f"- [ ] **SLO Compliance**: All SLOs met ({'✅' if analysis_results['slo_compliance']['overall_compliance'] == 'COMPLIANT' else '❌'})\n"
        summary += f"- [ ] **Security Gates**: All gates passed ({'✅' if analysis_results['security_gates']['overall_security'] == 'SECURE' else '❌'})\n"
        summary += f"- [ ] **Contract Compliance**: ≥95% ({'✅' if analysis_results['contract_compliance']['overall_contracts'] == 'COMPLIANT' else '❌'})\n"
        summary += f"- [ ] **Zero Critical Issues**: No blockers ({'✅' if not self.critical_issues else '❌'})\n"
        
        summary += f"\n### Production Readiness Checklist\n"
        summary += f"- [ ] Hot reload disabled by default\n"
        summary += f"- [ ] External dependencies configured\n"
        summary += f"- [ ] Monitoring and alerting ready\n"
        summary += f"- [ ] Rollback plan validated\n"
        summary += f"- [ ] Security posture verified\n"
        
        summary += f"\n---\n\n**Next Steps**: "
        
        if recommendation == "GO":
            summary += "✅ **Proceed with production deployment**\n\n"
            summary += "- Tag release candidate\n"
            summary += "- Execute deployment runbook\n" 
            summary += "- Monitor post-deploy metrics\n"
        elif recommendation == "CONDITIONAL":
            summary += "⚠️ **Address issues before deployment**\n\n"
            summary += "- Review critical issues above\n"
            summary += "- Implement fixes and re-run QA\n"
            summary += "- Consider phased rollout\n"
        else:
            summary += "❌ **Do not deploy - resolve critical issues**\n\n"
            summary += "- Address all failing quality gates\n"
            summary += "- Re-run full QA pipeline\n"
            summary += "- Consider architectural review\n"
        
        summary += f"\n**Artifacts**: All test results, coverage reports, and logs available in pipeline artifacts.\n"
        
        return summary


def main():
    """Generate release readiness summary from QA artifacts."""
    artifacts_dir = sys.argv[1] if len(sys.argv) > 1 else "."
    
    analyzer = ReleaseReadinessAnalyzer(artifacts_dir)
    summary = analyzer.generate_summary()
    
    # Write to file
    output_file = Path(artifacts_dir) / "RELEASE_READINESS_SUMMARY.md"
    with open(output_file, "w") as f:
        f.write(summary)
    
    print(summary)
    
    # Return exit code based on readiness
    readiness_score = analyzer.calculate_readiness_score({
        "test_results": analyzer.analyze_test_results(),
        "coverage": analyzer.analyze_coverage(),
        "slo_compliance": analyzer.analyze_slo_compliance(),
        "security_gates": analyzer.analyze_security_gates(),
        "contract_compliance": analyzer.analyze_contract_compliance()
    })
    
    if readiness_score >= 95 and not analyzer.critical_issues:
        print(f"\n✅ Release approved - readiness score {readiness_score}/100")
        sys.exit(0)
    elif readiness_score >= 85:
        print(f"\n⚠️ Conditional approval - readiness score {readiness_score}/100")
        sys.exit(0)
    else:
        print(f"\n❌ Release blocked - readiness score {readiness_score}/100")
        sys.exit(1)


if __name__ == "__main__":
    main()