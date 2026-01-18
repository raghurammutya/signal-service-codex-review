#!/usr/bin/env python3
"""
QA Pipeline Setup Validator (Simplified)

Validates that the Signal Service QA pipeline is properly configured
and all required components are in place.
"""

import os
import sys
from pathlib import Path

def check_file_exists(path: str, description: str) -> bool:
    """Check if a file exists and report status."""
    if Path(path).exists():
        print(f"✅ {description}: {path}")
        return True
    else:
        print(f"❌ {description}: {path} (MISSING)")
        return False

def validate_qa_setup():
    """Validate complete QA setup."""
    print("🔍 Signal Service QA Pipeline Validation")
    print("=" * 50)
    
    all_checks_passed = True
    
    # Core pipeline files
    core_files = [
        (".github/workflows/signal-service-qa.yml", "GitHub Actions Workflow"),
        ("scripts/generate_release_readiness_summary.py", "Release Readiness Generator"),
        ("scripts/generate_contract_matrix.py", "Contract Matrix Generator"),
        ("requirements-dev.txt", "Development Dependencies"),
        ("docs/RELEASE_READINESS_CRITERIA.md", "Release Criteria Documentation"),
    ]
    
    print("\n📋 Core Pipeline Files:")
    for file_path, description in core_files:
        if not check_file_exists(file_path, description):
            all_checks_passed = False
    
    # Test files
    test_files = [
        ("tests/smoke/test_health_and_metrics.py", "Smoke Tests - Health & Metrics"),
        ("tests/smoke/test_gateway_auth.py", "Smoke Tests - Gateway Auth"),
        ("tests/performance/test_load_backpressure.py", "Performance Tests"),
    ]
    
    print("\n🧪 Test Files:")
    for file_path, description in test_files:
        if not check_file_exists(file_path, description):
            all_checks_passed = False
    
    # Workflow basic check
    print("\n⚙️  Workflow Configuration:")
    workflow_path = ".github/workflows/signal-service-qa.yml"
    if Path(workflow_path).exists():
        with open(workflow_path, 'r') as f:
            content = f.read()
            
        # Basic structure checks
        if 'name: signal-service-qa' in content:
            print("✅ Workflow name: signal-service-qa")
        else:
            print("❌ Workflow name: Not found")
            all_checks_passed = False
            
        if 'on:' in content and 'push:' in content and 'pull_request:' in content:
            print("✅ Workflow triggers: push, pull_request")
        else:
            print("❌ Workflow triggers: Missing or incorrect")
            all_checks_passed = False
            
        # Count job stages
        job_count = content.count('runs-on: ubuntu-latest')
        if job_count >= 8:
            print(f"✅ Workflow stages: {job_count} jobs configured")
        else:
            print(f"❌ Workflow stages: {job_count} jobs (expected ≥8)")
            all_checks_passed = False
            
    else:
        print("❌ Cannot validate workflow - file missing")
        all_checks_passed = False
    
    # Directory structure
    print("\n📁 Directory Structure:")
    required_dirs = [
        ".github/workflows",
        "scripts",
        "tests/smoke", 
        "tests/performance",
        "docs"
    ]
    
    for dir_path in required_dirs:
        if Path(dir_path).is_dir():
            print(f"✅ Directory: {dir_path}")
        else:
            print(f"❌ Directory: {dir_path} (MISSING)")
            all_checks_passed = False
    
    # Check key pipeline components
    print("\n🔧 Pipeline Components:")
    
    # Check for key stages in workflow
    if Path(workflow_path).exists():
        with open(workflow_path, 'r') as f:
            content = f.read()
            
        stages = [
            'lint-hygiene:',
            'smoke:',
            'integration:',
            'security:',
            'performance:',
            'coverage:',
            'acceptance:'
        ]
        
        for stage in stages:
            if stage in content:
                print(f"✅ Pipeline stage: {stage.replace(':', '')}")
            else:
                print(f"❌ Pipeline stage: {stage.replace(':', '')} (MISSING)")
                all_checks_passed = False
    
    # Environment validation
    print("\n🔧 Environment Configuration:")
    print("ℹ️  GitHub Secrets Required:")
    print("   - CONFIG_SERVICE_URL (for external config service)")
    print("   - INTERNAL_API_KEY (for service-to-service auth)")
    print("ℹ️  Pipeline Features:")
    print("   - 8+ quality gate stages")
    print("   - SLO compliance validation")
    print("   - Security hygiene checks")
    print("   - Release readiness analysis")
    print("   - Comprehensive artifact collection")
    
    # Final result
    print("\n" + "=" * 50)
    if all_checks_passed:
        print("🎉 QA PIPELINE VALIDATION PASSED")
        print("✅ All required components are in place")
        print("🚀 Ready for production deployment")
        print("\n📋 Next Steps:")
        print("   1. Commit and push these changes to trigger pipeline")
        print("   2. Configure GitHub repository secrets")
        print("   3. Monitor first pipeline execution")
        print("   4. Review release readiness score")
        print("   5. Address any failing quality gates")
        print("\n🔗 Pipeline will run automatically on:")
        print("   - Every push to any branch")
        print("   - Every pull request")
        print("   - Manual workflow dispatch")
        return True
    else:
        print("❌ QA PIPELINE VALIDATION FAILED")
        print("🚨 Missing required components")
        print("🔧 Please address issues above before proceeding")
        return False

if __name__ == "__main__":
    success = validate_qa_setup()
    sys.exit(0 if success else 1)