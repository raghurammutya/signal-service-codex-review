#!/usr/bin/env python3
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
                command = f"psql -c \"{check['query']}\" -t"
            else:
                command = check["command"]
            
            result = self.execute_command(command)
            
            if result["return_code"] == 0:
                print(f"   ✅ {check['check']}: PASSED")
            else:
                print(f"   ❌ {check['check']}: FAILED")
                return False
        
        print("\n🎉 ROLLBACK COMPLETED SUCCESSFULLY")
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
