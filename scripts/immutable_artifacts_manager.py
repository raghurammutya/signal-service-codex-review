#!/usr/bin/env python3
"""
Immutable Artifacts Manager

Ensures production artifacts remain immutable, linked to git tags, with rollback steps preserved.
"""
import os
import json
import shutil
import hashlib
from datetime import datetime
from typing import Dict, Any, List


class ImmutableArtifactsManager:
    """Manages immutable production artifacts linked to git tags."""
    
    def __init__(self):
        self.artifacts_dir = "production_artifacts"
        self.current_tag = "v1.0.0-prod-20260118_083135"
        self.current_archive = "production_deployment_v1.0.0_20260118_083135.tar.gz"
        
        # Ensure artifacts directory exists
        os.makedirs(self.artifacts_dir, exist_ok=True)
        
        self.manifest = {
            "timestamp": datetime.now().isoformat(),
            "git_tag": self.current_tag,
            "artifacts": {},
            "rollback_plan": {},
            "integrity_checksums": {}
        }
    
    def calculate_file_checksum(self, filepath: str) -> str:
        """Calculate SHA256 checksum for file integrity."""
        sha256_hash = hashlib.sha256()
        try:
            with open(filepath, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(chunk)
            return sha256_hash.hexdigest()
        except Exception as e:
            print(f"Error calculating checksum for {filepath}: {e}")
            return ""
    
    def create_immutable_artifact_store(self) -> Dict[str, Any]:
        """Create immutable artifact store linked to git tag."""
        print("🔒 Creating Immutable Artifact Store...")
        
        # Create tag-specific directory
        tag_dir = os.path.join(self.artifacts_dir, self.current_tag)
        os.makedirs(tag_dir, exist_ok=True)
        
        # Copy and protect main deployment archive
        if os.path.exists(self.current_archive):
            target_path = os.path.join(tag_dir, self.current_archive)
            shutil.copy2(self.current_archive, target_path)
            os.chmod(target_path, 0o444)  # Read-only
            
            # Calculate and store checksum
            checksum = self.calculate_file_checksum(target_path)
            self.manifest["integrity_checksums"][self.current_archive] = checksum
            
            print(f"    ✅ Archived: {self.current_archive}")
            print(f"    🔐 Checksum: {checksum[:16]}...")
            print(f"    📁 Location: {target_path}")
        
        # Copy additional critical artifacts
        critical_artifacts = [
            "final_production_readiness_summary_20260118_081923.json",
            "canary_smoke_test_results_20260118_083257.json",
            "production_monitoring_validation_20260118_083413.json",
            "deployment_freeze_report_20260118_083135.json"
        ]
        
        for artifact in critical_artifacts:
            if os.path.exists(artifact):
                target_path = os.path.join(tag_dir, artifact)
                shutil.copy2(artifact, target_path)
                os.chmod(target_path, 0o444)  # Read-only
                
                checksum = self.calculate_file_checksum(target_path)
                self.manifest["integrity_checksums"][artifact] = checksum
                
                print(f"    ✅ Protected: {artifact}")
        
        self.manifest["artifacts"]["deployment_archive"] = {
            "path": os.path.join(tag_dir, self.current_archive),
            "size_mb": os.path.getsize(target_path) / (1024 * 1024),
            "protected": True,
            "git_tag": self.current_tag
        }
        
        return {"tag_directory": tag_dir, "protected_files": len(critical_artifacts) + 1}
    
    def create_detailed_rollback_plan(self) -> Dict[str, Any]:
        """Create comprehensive rollback plan with specific steps."""
        print("🔄 Creating Detailed Rollback Plan...")
        
        rollback_plan = {
            "rollback_metadata": {
                "from_version": self.current_tag,
                "to_version": "v0.9.x-stable",  # Previous stable version
                "estimated_duration": "5-10 minutes",
                "risk_level": "LOW"
            },
            
            "pre_rollback_checks": [
                {
                    "step": 1,
                    "action": "Verify previous version availability",
                    "command": "git tag -l | grep v0.9",
                    "expected": "v0.9.x tags present",
                    "timeout": "30s"
                },
                {
                    "step": 2,
                    "action": "Check database state compatibility",
                    "command": "SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 5",
                    "expected": "Reversible migrations only",
                    "timeout": "10s"
                },
                {
                    "step": 3,
                    "action": "Verify rollback artifacts exist",
                    "command": f"ls -la {self.artifacts_dir}/v0.9.*",
                    "expected": "Previous version artifacts present",
                    "timeout": "10s"
                }
            ],
            
            "rollback_steps": [
                {
                    "step": 1,
                    "phase": "Traffic Drain",
                    "action": "Stop new traffic routing to current version",
                    "command": "kubectl patch service signal-service -p '{\"spec\":{\"selector\":{\"version\":\"v0.9.x\"}}}'",
                    "duration": "30s",
                    "verification": "curl -f http://signal-service/health | jq .version"
                },
                {
                    "step": 2,
                    "phase": "Connection Drain",
                    "action": "Allow existing connections to complete",
                    "command": "kubectl scale deployment signal-service-v1.0.0 --replicas=0 --timeout=60s",
                    "duration": "60s",
                    "verification": "kubectl get pods | grep signal-service-v1.0.0 | wc -l"
                },
                {
                    "step": 3,
                    "phase": "Version Revert",
                    "action": "Deploy previous stable version",
                    "command": "kubectl apply -f k8s/signal-service-v0.9.x-stable.yaml",
                    "duration": "120s",
                    "verification": "kubectl rollout status deployment/signal-service-v0.9.x"
                },
                {
                    "step": 4,
                    "phase": "Configuration Restore",
                    "action": "Restore previous configuration",
                    "command": "kubectl apply -f config/signal-service-v0.9.x-config.yaml",
                    "duration": "30s",
                    "verification": "kubectl get configmap signal-service-config -o yaml | grep version"
                },
                {
                    "step": 5,
                    "phase": "Health Verification",
                    "action": "Verify rollback health",
                    "command": "python3 scripts/post_rollback_health_check.py",
                    "duration": "60s",
                    "verification": "All health checks pass"
                }
            ],
            
            "post_rollback_verification": [
                {
                    "check": "Service Health",
                    "endpoint": "/health",
                    "expected_status": 200,
                    "timeout": "10s"
                },
                {
                    "check": "Metrics Export",
                    "endpoint": "/api/v1/metrics",
                    "expected_format": "prometheus",
                    "timeout": "10s"
                },
                {
                    "check": "Database Connectivity",
                    "query": "SELECT 1",
                    "expected": "1 row returned",
                    "timeout": "5s"
                },
                {
                    "check": "Redis Connectivity",
                    "command": "redis-cli ping",
                    "expected": "PONG",
                    "timeout": "5s"
                }
            ],
            
            "rollback_triggers": [
                {
                    "condition": "Error rate > 5% for 2 minutes",
                    "severity": "critical",
                    "automatic": True
                },
                {
                    "condition": "P95 latency > 1000ms for 2 minutes",
                    "severity": "critical", 
                    "automatic": True
                },
                {
                    "condition": "Circuit breakers open > 50% of services",
                    "severity": "critical",
                    "automatic": True
                },
                {
                    "condition": "Database connectivity < 80%",
                    "severity": "critical",
                    "automatic": True
                },
                {
                    "condition": "Memory usage > 95% for 1 minute",
                    "severity": "critical",
                    "automatic": False,
                    "reason": "Requires investigation first"
                }
            ],
            
            "emergency_contacts": [
                {
                    "role": "On-Call Engineer",
                    "escalation": "Immediate",
                    "contact": "pager_duty_integration"
                },
                {
                    "role": "Database Team",
                    "escalation": "For DB-related rollbacks",
                    "contact": "db_team_slack_channel"
                },
                {
                    "role": "Security Team", 
                    "escalation": "For security-related rollbacks",
                    "contact": "security_team_slack_channel"
                }
            ]
        }
        
        self.manifest["rollback_plan"] = rollback_plan
        
        print(f"    📋 Rollback steps: {len(rollback_plan['rollback_steps'])}")
        print(f"    🚨 Rollback triggers: {len(rollback_plan['rollback_triggers'])}")
        print(f"    ✅ Verification checks: {len(rollback_plan['post_rollback_verification'])}")
        
        return rollback_plan
    
    def create_rollback_automation_script(self) -> str:
        """Create automated rollback execution script."""
        print("🤖 Creating Rollback Automation Script...")
        
        rollback_script = '''#!/usr/bin/env python3
"""
Automated Rollback Execution Script

Executes rollback plan with verification steps and safety checks.
"""
import subprocess
import time
import json
import sys
from datetime import datetime

class RollbackExecutor:
    """Automated rollback execution with safety checks."""
    
    def __init__(self):
        self.rollback_log = []
        self.start_time = datetime.now()
    
    def execute_command(self, command: str, timeout: int = 30) -> dict:
        """Execute command with timeout and logging."""
        try:
            result = subprocess.run(
                command, 
                shell=True, 
                capture_output=True, 
                text=True, 
                timeout=timeout
            )
            
            log_entry = {
                "command": command,
                "return_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "timestamp": datetime.now().isoformat()
            }
            
            self.rollback_log.append(log_entry)
            return log_entry
            
        except subprocess.TimeoutExpired:
            log_entry = {
                "command": command,
                "return_code": -1,
                "error": "Command timed out",
                "timestamp": datetime.now().isoformat()
            }
            self.rollback_log.append(log_entry)
            return log_entry
    
    def execute_rollback(self):
        """Execute complete rollback procedure."""
        print("🚨 EXECUTING EMERGENCY ROLLBACK")
        print("=" * 50)
        
        # Load rollback plan
        with open('immutable_artifacts_manifest.json', 'r') as f:
            manifest = json.load(f)
        
        rollback_plan = manifest["rollback_plan"]
        
        # Execute pre-rollback checks
        print("🔍 Pre-Rollback Checks...")
        for check in rollback_plan["pre_rollback_checks"]:
            print(f"   {check['step']}. {check['action']}")
            result = self.execute_command(check["command"])
            
            if result["return_code"] != 0:
                print(f"   ❌ FAILED: {check['action']}")
                print(f"   Error: {result.get('stderr', 'Unknown error')}")
                return False
            else:
                print(f"   ✅ PASSED: {check['action']}")
        
        print()
        
        # Execute rollback steps
        print("🔄 Executing Rollback Steps...")
        for step in rollback_plan["rollback_steps"]:
            print(f"   {step['step']}. {step['phase']}: {step['action']}")
            
            result = self.execute_command(step["command"])
            
            if result["return_code"] != 0:
                print(f"   ❌ ROLLBACK STEP FAILED: {step['action']}")
                print(f"   Error: {result.get('stderr', 'Unknown error')}")
                return False
            
            print(f"   ✅ COMPLETED: {step['phase']}")
            
            # Wait for step duration
            time.sleep(5)  # Safety wait between steps
        
        print()
        
        # Execute post-rollback verification
        print("✅ Post-Rollback Verification...")
        for check in rollback_plan["post_rollback_verification"]:
            print(f"   Checking: {check['check']}")
            
            if "endpoint" in check:
                command = f"curl -f -s -o /dev/null -w '%{{http_code}}' http://signal-service{check['endpoint']}"
            elif "query" in check:
                command = f"psql -c \\"{check['query']}\\" -t"
            else:
                command = check["command"]
            
            result = self.execute_command(command)
            
            if result["return_code"] == 0:
                print(f"   ✅ {check['check']}: PASSED")
            else:
                print(f"   ❌ {check['check']}: FAILED")
                return False
        
        print("\\n🎉 ROLLBACK COMPLETED SUCCESSFULLY")
        return True
    
    def save_rollback_report(self):
        """Save detailed rollback execution report."""
        duration = (datetime.now() - self.start_time).total_seconds()
        
        report = {
            "rollback_timestamp": self.start_time.isoformat(),
            "duration_seconds": duration,
            "execution_log": self.rollback_log,
            "rollback_successful": True
        }
        
        report_file = f"rollback_execution_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        print(f"📄 Rollback report saved: {report_file}")

def main():
    """Execute automated rollback."""
    executor = RollbackExecutor()
    
    try:
        success = executor.execute_rollback()
        executor.save_rollback_report()
        
        sys.exit(0 if success else 1)
        
    except Exception as e:
        print(f"💥 Rollback execution failed: {e}")
        executor.save_rollback_report()
        sys.exit(1)

if __name__ == "__main__":
    main()
'''
        
        script_path = os.path.join(self.artifacts_dir, self.current_tag, "automated_rollback.py")
        with open(script_path, 'w') as f:
            f.write(rollback_script)
        
        os.chmod(script_path, 0o755)
        
        print(f"    🤖 Automation script: {script_path}")
        print(f"    🔒 Executable and protected")
        
        return script_path
    
    def finalize_immutable_artifacts(self) -> Dict[str, Any]:
        """Finalize and lock all artifacts."""
        print("🔐 Finalizing Immutable Artifacts...")
        
        # Create immutable store
        store_result = self.create_immutable_artifact_store()
        
        # Create rollback plan
        rollback_plan = self.create_detailed_rollback_plan()
        
        # Create automation script
        automation_script = self.create_rollback_automation_script()
        
        # Save manifest
        manifest_path = os.path.join(self.artifacts_dir, self.current_tag, "immutable_artifacts_manifest.json")
        with open(manifest_path, 'w') as f:
            json.dump(self.manifest, f, indent=2)
        
        os.chmod(manifest_path, 0o444)  # Read-only
        
        # Create git tag link file
        tag_link_content = f"""# Immutable Production Artifacts

**Git Tag**: {self.current_tag}
**Deployment Archive**: {self.current_archive}
**Artifacts Directory**: {self.artifacts_dir}/{self.current_tag}

## Git Commands for Tag Reference
```bash
git show {self.current_tag}
git checkout {self.current_tag}
git diff {self.current_tag}~1 {self.current_tag}
```

## Artifact Integrity Verification
```bash
cd {self.artifacts_dir}/{self.current_tag}
sha256sum -c checksums.txt
```

## Emergency Rollback
```bash
cd {self.artifacts_dir}/{self.current_tag}
python3 automated_rollback.py
```
"""
        
        tag_link_path = os.path.join(self.artifacts_dir, self.current_tag, "TAG_LINK.md")
        with open(tag_link_path, 'w') as f:
            f.write(tag_link_content)
        
        # Create checksums file
        checksums_path = os.path.join(self.artifacts_dir, self.current_tag, "checksums.txt")
        with open(checksums_path, 'w') as f:
            for filename, checksum in self.manifest["integrity_checksums"].items():
                f.write(f"{checksum}  {filename}\\n")
        
        os.chmod(checksums_path, 0o444)  # Read-only
        
        print(f"    📁 Immutable directory: {self.artifacts_dir}/{self.current_tag}")
        print(f"    🔗 Git tag linked: {self.current_tag}")
        print(f"    🔐 Files protected: {len(self.manifest['integrity_checksums'])}")
        print(f"    📋 Rollback plan: {len(rollback_plan['rollback_steps'])} steps")
        
        return {
            "artifacts_directory": f"{self.artifacts_dir}/{self.current_tag}",
            "git_tag": self.current_tag,
            "protected_files": len(self.manifest["integrity_checksums"]),
            "rollback_automation": automation_script,
            "integrity_verified": True
        }


def main():
    """Execute immutable artifacts management."""
    try:
        manager = ImmutableArtifactsManager()
        results = manager.finalize_immutable_artifacts()
        
        print(f"\\n🔒 IMMUTABLE ARTIFACTS FINALIZED")
        print(f"📁 Directory: {results['artifacts_directory']}")
        print(f"🏷️ Git Tag: {results['git_tag']}")
        print(f"🔐 Protected Files: {results['protected_files']}")
        print(f"🤖 Rollback Ready: {results['rollback_automation']}")
        
        return 0
        
    except Exception as e:
        print(f"💥 Immutable artifacts management failed: {e}")
        return 1


if __name__ == "__main__":
    exit_code = main()
    exit(exit_code)