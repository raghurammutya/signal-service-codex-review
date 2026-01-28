#!/usr/bin/env python3
"""
Production Readiness Bundle Creation

Creates a dated 'Production Readiness' bundle with all validation artifacts.
"""
import json
import os
import tarfile
import time
from datetime import datetime


class ProductionReadinessBundle:
    """Creates comprehensive production readiness bundle."""

    def __init__(self):
        self.bundle_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.bundle_name = f"production_readiness_bundle_{self.bundle_timestamp}"
        self.artifacts = []

        # Define all artifacts to collect
        self.required_artifacts = [
            # Validation outputs
            "validation_hardening_output.log",
            "validation.json",
            "contract_validation_matrix.md",
            "simple_smoke_output.log",
            "smoke_test_output.log",
            "load_backpressure_output.log",
            "load_backpressure_drill_report.json",
            "security_validation_output.log",
            "simple_security_validation_output.log",
            "database_sanity_output.log",
            "database_sanity_report.json",
            "coverage_spot_check_output.log",
            "coverage_spot_check_report.json",
            "redundancy_scan_output.log",
            "redundancy_duplication_scan_report.json",

            # Validation scripts
            "scripts/validate_production_hardening.py",
            "scripts/deployment_safety_validation.py",
            "scripts/validate_config_driven_budgets.py",
            "simple_smoke_validation.py",
            "smoke_test_critical_flows.py",
            "load_backpressure_drill.py",
            "security_validation.py",
            "simple_security_validation.py",
            "database_sanity_validation.py",
            "coverage_spot_check.py",
            "redundancy_duplication_scan.py",

            # Configuration files
            "app/core/config.py",
            "app/config/budget_config.py",
            "pytest.ini",
            ".coveragerc",
            "pyproject.toml"
        ]

    def collect_artifacts(self):
        """Collect all available artifacts."""
        print("📦 Collecting Production Readiness Artifacts...")

        found_artifacts = []
        missing_artifacts = []

        for artifact in self.required_artifacts:
            if os.path.exists(artifact):
                file_size = os.path.getsize(artifact)
                found_artifacts.append({
                    "file": artifact,
                    "size_bytes": file_size,
                    "last_modified": datetime.fromtimestamp(os.path.getmtime(artifact)).isoformat()
                })
                print(f"    ✅ {artifact} ({file_size} bytes)")
            else:
                missing_artifacts.append(artifact)
                print(f"    ❌ {artifact} (missing)")

        print(f"  📊 Found artifacts: {len(found_artifacts)}")
        print(f"  📊 Missing artifacts: {len(missing_artifacts)}")

        self.artifacts = found_artifacts

        return {
            "found_count": len(found_artifacts),
            "missing_count": len(missing_artifacts),
            "found_artifacts": found_artifacts,
            "missing_artifacts": missing_artifacts
        }

    def create_summary_report(self):
        """Create comprehensive summary report."""
        print("📋 Creating Summary Report...")

        summary = {
            "bundle_metadata": {
                "creation_timestamp": datetime.now().isoformat(),
                "bundle_name": self.bundle_name,
                "total_artifacts": len(self.artifacts)
            },
            "validation_summary": {},
            "production_readiness_status": {},
            "bootstrap_requirements": {
                "environment_variables": [
                    "ENVIRONMENT=production",
                    "CONFIG_SERVICE_URL=http://config-service:8100",
                    "INTERNAL_API_KEY=<secure_internal_key>",
                    "SERVICE_NAME=signal-service"
                ],
                "config_service_keys": [
                    "database_pool_config",
                    "budget_guards_config",
                    "circuit_breaker_config",
                    "metrics_export_config"
                ]
            },
            "how_to_start_in_production": {
                "step_1": "set required environment variables",
                "step_2": "Ensure config service is accessible",
                "step_3": "Verify database connectivity (TimescaleDB)",
                "step_4": "Run production hardening validation: python3 scripts/validate_production_hardening.py",
                "step_5": "Start service: uvicorn app.main:app --host 0.0.0.0 --port 8000"
            }
        }

        # Collect validation results
        validation_files = {
            "hardening_validation": "validation_hardening_output.log",
            "deployment_safety": "validation.json",
            "smoke_tests": "simple_smoke_output.log",
            "load_backpressure": "load_backpressure_output.log",
            "security_validation": "security_validation_output.log",
            "database_sanity": "database_sanity_output.log",
            "coverage_check": "coverage_spot_check_output.log",
            "redundancy_scan": "redundancy_scan_output.log"
        }

        for validation_name, file_path in validation_files.items():
            if os.path.exists(file_path):
                try:
                    with open(file_path) as f:
                        content = f.read()

                    # Extract key information
                    if "PASSED" in content:
                        status = "PASSED"
                        if "%" in content:
                            # Extract percentage
                            import re
                            percentages = re.findall(r'(\d+\.?\d*)%', content)
                            score = percentages[-1] if percentages else "N/A"  # Last percentage found
                        else:
                            score = "N/A"
                    elif "INSUFFICIENT" in content or "NEEDS ATTENTION" in content:
                        status = "NEEDS_ATTENTION"
                        score = "N/A"
                    else:
                        status = "UNKNOWN"
                        score = "N/A"

                    summary["validation_summary"][validation_name] = {
                        "status": status,
                        "score": score,
                        "file": file_path
                    }

                except Exception as e:
                    summary["validation_summary"][validation_name] = {
                        "status": "ERROR",
                        "error": str(e),
                        "file": file_path
                    }
            else:
                summary["validation_summary"][validation_name] = {
                    "status": "MISSING",
                    "file": file_path
                }

        # Calculate overall readiness status
        passed_validations = sum(1 for v in summary["validation_summary"].values()
                               if v.get("status") == "PASSED")
        total_validations = len(summary["validation_summary"])
        readiness_percentage = (passed_validations / total_validations) * 100 if total_validations > 0 else 0

        summary["production_readiness_status"] = {
            "overall_status": "READY" if readiness_percentage >= 75 else "NEEDS_WORK",
            "readiness_percentage": f"{readiness_percentage:.1f}%",
            "passed_validations": passed_validations,
            "total_validations": total_validations,
            "critical_issues": []
        }

        # Identify critical issues
        if summary["validation_summary"].get("hardening_validation", {}).get("status") != "PASSED":
            summary["production_readiness_status"]["critical_issues"].append("Production hardening validation failed")

        if summary["validation_summary"].get("security_validation", {}).get("status") != "PASSED":
            summary["production_readiness_status"]["critical_issues"].append("Security validation failed")

        # Save summary
        summary_file = f"{self.bundle_name}_summary.json"
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2)

        print(f"    ✅ Summary report created: {summary_file}")
        print(f"    📊 Overall readiness: {summary['production_readiness_status']['overall_status']} ({readiness_percentage:.1f}%)")

        return summary_file, summary

    def create_bundle_archive(self, summary_file: str):
        """Create compressed bundle archive."""
        print("📦 Creating Bundle Archive...")

        archive_name = f"{self.bundle_name}.tar.gz"

        try:
            with tarfile.open(archive_name, 'w:gz') as tar:
                # Add summary first
                tar.add(summary_file, arcname=f"{self.bundle_name}/summary.json")

                # Add all collected artifacts
                for artifact in self.artifacts:
                    file_path = artifact["file"]
                    try:
                        # Preserve directory structure in archive
                        arcname = f"{self.bundle_name}/{file_path}"
                        tar.add(file_path, arcname=arcname)
                        print(f"    ✅ Added: {file_path}")
                    except Exception as e:
                        print(f"    ❌ Failed to add {file_path}: {e}")

                # Add this bundle creation script
                tar.add(__file__, arcname=f"{self.bundle_name}/create_production_readiness_bundle.py")

            bundle_size = os.path.getsize(archive_name)
            print(f"    ✅ Archive created: {archive_name} ({bundle_size} bytes)")

            return archive_name, bundle_size

        except Exception as e:
            print(f"    ❌ Failed to create archive: {e}")
            return None, 0

    def create_how_to_start_guide(self):
        """Create production startup guide."""
        print("📖 Creating 'How to Start in Production' Guide...")

        guide_content = f"""# Production Deployment Guide - Signal Service
Generated: {datetime.now().isoformat()}

## 🚀 Quick Start

### Required Environment Variables
```bash
export ENVIRONMENT=production
export CONFIG_SERVICE_URL=http://config-service:8100
export INTERNAL_API_KEY=<secure_internal_key>
export SERVICE_NAME=signal-service
```

### Required Config Service Keys
- `database_pool_config`: Database connection pool settings
- `budget_guards_config`: Memory and CPU budget configurations
- `circuit_breaker_config`: Circuit breaker settings for all external services
- `metrics_export_config`: Metrics collection and export settings

### Pre-Deployment Validation
```bash
# Run production hardening validation
python3 scripts/validate_production_hardening.py

# Run deployment safety validation
python3 scripts/deployment_safety_validation.py

# Run smoke tests
python3 simple_smoke_validation.py
```

### Service Startup
```bash
# Start the service
uvicorn app.main:app --host 0.0.0.0 --port 8000

# Verify health
curl http://localhost:8000/health

# Check metrics
curl http://localhost:8000/metrics
```

### Critical Dependencies
1. **TimescaleDB**: Time-series database for signal storage
2. **Config Service**: Centralized configuration management
3. **Redis**: Caching and rate limiting
4. **External Services**:
   - Ticker Service
   - User Service
   - Alert Service
   - Communications Service

### Health Checks
- `/health`: Basic health check
- `/health/live`: Liveness probe
- `/health/ready`: Readiness probe
- `/metrics`: Prometheus metrics

### Monitoring & Observability
- Metrics exported to Prometheus format
- Structured logging with sensitive data redaction
- Circuit breaker status monitoring
- Budget guard and backpressure monitoring

### Security Notes
- All API endpoints require proper authentication
- Admin endpoints require special admin tokens
- Sensitive data is automatically redacted from logs
- CORS configured for production (no wildcards)

### Troubleshooting
1. **Config Service Connection Issues**: Verify CONFIG_SERVICE_URL and network connectivity
2. **Database Connection Issues**: Check TimescaleDB availability and credentials
3. **Circuit Breaker Trips**: Monitor external service health
4. **Budget Guard Triggers**: Check memory/CPU usage and adjust budget configs

For detailed validation results, see the production readiness bundle artifacts.
"""

        guide_file = f"production_startup_guide_{self.bundle_timestamp}.md"
        with open(guide_file, 'w') as f:
            f.write(guide_content)

        print(f"    ✅ Startup guide created: {guide_file}")
        return guide_file

    def run_bundle_creation(self):
        """Run complete bundle creation process."""
        print("🎁 Production Readiness Bundle Creation")
        print("=" * 60)

        start_time = time.time()

        # Step 1: Collect artifacts
        collection_result = self.collect_artifacts()
        print()

        # Step 2: Create summary report
        summary_file, summary_data = self.create_summary_report()
        print()

        # Step 3: Create startup guide
        guide_file = self.create_how_to_start_guide()
        print()

        # Step 4: Create bundle archive
        archive_file, archive_size = self.create_bundle_archive(summary_file)
        print()

        end_time = time.time()
        duration = end_time - start_time

        # Final results
        print("=" * 60)
        print(f"🎯 Production Readiness Bundle Complete (Duration: {duration:.2f}s)")
        print(f"  📦 Bundle: {archive_file}")
        print(f"  📊 Size: {archive_size:,} bytes")
        print(f"  📋 Summary: {summary_file}")
        print(f"  📖 Guide: {guide_file}")
        print(f"  🗂️ Artifacts: {collection_result['found_count']}/{len(self.required_artifacts)}")

        # Display readiness status
        readiness_status = summary_data["production_readiness_status"]
        print(f"\n🚀 Production Readiness Status: {readiness_status['overall_status']}")
        print(f"   📈 Score: {readiness_status['readiness_percentage']}")
        print(f"   ✅ Passed Validations: {readiness_status['passed_validations']}/{readiness_status['total_validations']}")

        if readiness_status.get("critical_issues"):
            print("   ⚠️ Critical Issues:")
            for issue in readiness_status["critical_issues"]:
                print(f"     - {issue}")

        return {
            "bundle_file": archive_file,
            "summary_file": summary_file,
            "guide_file": guide_file,
            "readiness_status": readiness_status,
            "artifacts_collected": collection_result['found_count'],
            "total_artifacts": len(self.required_artifacts)
        }


def main():
    """Run production readiness bundle creation."""
    try:
        bundle_creator = ProductionReadinessBundle()
        result = bundle_creator.run_bundle_creation()

        readiness = result["readiness_status"]
        if readiness["overall_status"] == "READY":
            print("\n🎉 PRODUCTION READINESS BUNDLE CREATED SUCCESSFULLY")
            print("📦 Bundle ready for production deployment review")
            return 0
        print("\n⚠️ PRODUCTION READINESS BUNDLE CREATED WITH ISSUES")
        print("🔧 Review critical issues before production deployment")
        return 1

    except Exception as e:
        print(f"💥 Bundle creation failed: {e}")
        return 1


if __name__ == "__main__":
    exit_code = main()
    exit(exit_code)
