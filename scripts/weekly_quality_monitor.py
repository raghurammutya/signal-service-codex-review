#!/usr/bin/env python3
"""
Weekly Quality Monitor - Local/Manual Execution
Comprehensive code quality monitoring with P0 regression detection

Provides the same monitoring capabilities as the GitHub Actions workflow
but can be run locally or in custom CI environments.

Usage:
    python scripts/weekly_quality_monitor.py
    python scripts/weekly_quality_monitor.py --alert-test
    python scripts/weekly_quality_monitor.py --trend-only
"""

import argparse
import json
import os
import subprocess
import statistics
import time
from datetime import datetime, timedelta
from glob import glob
from pathlib import Path
from typing import Any, Dict, List, Optional


class WeeklyQualityMonitor:
    """
    Weekly code quality monitoring system
    
    Tracks Ruff violations over time, detects P0 regressions,
    and generates executive reports for stakeholders.
    """

    def __init__(self, project_root: str = "."):
        self.project_root = Path(project_root).absolute()
        self.evidence_dir = self.project_root / "evidence" / "weekly"
        self.ensure_directories()
        
        # P0 rules that actually block CI (syntax errors and critical issues)
        self.p0_rules = [
            'E999',  # SyntaxError
            'F821',  # undefined-name  
            'F822',  # undefined-export
            'F811',  # redefined-while-unused
            'F402',  # import-shadowed-by-loop-var
            'F823',  # undefined-local
            'E902',  # IOError
            'E999'   # SyntaxError (duplicate for safety)
        ]
        
    def ensure_directories(self):
        """Create necessary evidence directories"""
        for subdir in ["", "alerts", "reports", "trends"]:
            (self.evidence_dir / subdir).mkdir(parents=True, exist_ok=True)

    def run_monitoring(self, force_alert: bool = False) -> Dict[str, Any]:
        """
        Run complete weekly monitoring cycle
        
        Args:
            force_alert: Force P0 alert for testing
            
        Returns:
            Dict: Complete monitoring results
        """
        print("🔍 Weekly Code Quality Monitoring")
        print("=" * 50)
        
        # Collect current metrics
        current_metrics = self.collect_current_metrics()
        
        # Analyze trends
        trend_analysis = self.analyze_trends()
        
        # Generate monitoring report
        report = self.generate_monitoring_report(current_metrics, trend_analysis)
        
        # Check for alerts
        alert_data = None
        if current_metrics["p0_critical_violations"] > 0 or force_alert:
            alert_data = self.create_alert(current_metrics, force_alert)
        
        # Generate executive summary
        exec_summary = self.generate_executive_summary(report, trend_analysis, alert_data)
        
        # Save all data
        self.save_monitoring_data(report, trend_analysis, exec_summary, alert_data)
        
        # Display summary
        self.display_results(report, trend_analysis, alert_data)
        
        return {
            "report": report,
            "trends": trend_analysis,
            "executive_summary": exec_summary,
            "alert": alert_data
        }

    def collect_current_metrics(self) -> Dict[str, Any]:
        """Collect current Ruff violation metrics"""
        print("📊 Collecting current violation statistics...")
        
        try:
            # Run Ruff with statistics
            stats_result = subprocess.run(
                ["python3", "-m", "ruff", "check", ".", "--statistics"],
                capture_output=True,
                text=True,
                cwd=self.project_root
            )
            
            # Run Ruff with JSON output for details
            json_result = subprocess.run(
                ["python3", "-m", "ruff", "check", ".", "--output-format=json"],
                capture_output=True,
                text=True,
                cwd=self.project_root
            )
            
            # Parse statistics
            metrics = self.parse_ruff_statistics(stats_result.stdout)
            
            # Parse violation details
            try:
                violation_details = json.loads(json_result.stdout) if json_result.stdout.strip() else []
            except json.JSONDecodeError:
                violation_details = []
            
            metrics["violation_details"] = violation_details[:50]  # Limit for size
            metrics["files_affected"] = len(set(v.get("filename", "") for v in violation_details))
            
            return metrics
            
        except Exception as e:
            print(f"❌ Error collecting metrics: {e}")
            return {
                "total_violations": 0,
                "p0_critical_violations": 0,
                "auto_fixable_violations": 0,
                "violation_breakdown": {},
                "violation_details": [],
                "files_affected": 0,
                "collection_error": str(e)
            }

    def parse_ruff_statistics(self, stats_output: str) -> Dict[str, Any]:
        """Parse Ruff statistics output"""
        total_violations = 0
        p0_violations = 0
        auto_fixable = 0
        violation_breakdown = {}
        
        for line in stats_output.split('\n'):
            if line.strip() and not line.startswith('[*]'):
                parts = line.split('\t')
                if len(parts) >= 2:
                    try:
                        count = int(parts[0].strip())
                        rule = parts[1].strip()
                        flags = parts[2].strip() if len(parts) > 2 else ''
                        
                        total_violations += count
                        violation_breakdown[rule] = count
                        
                        # Check if P0 (critical)
                        if rule in self.p0_rules:
                            p0_violations += count
                        
                        # Check if auto-fixable
                        if '[*]' in flags:
                            auto_fixable += count
                    except ValueError:
                        continue
        
        return {
            "total_violations": total_violations,
            "p0_critical_violations": p0_violations,
            "auto_fixable_violations": auto_fixable,
            "violation_breakdown": violation_breakdown,
            "ci_blocking": p0_violations > 0
        }

    def analyze_trends(self) -> Dict[str, Any]:
        """Analyze quality trends from historical data"""
        print("📈 Analyzing quality trends...")
        
        # Load historical weekly reports
        report_files = sorted(self.evidence_dir.glob("weekly_monitoring_report_*.json"))
        
        if len(report_files) < 2:
            return {
                "trend_analysis": "insufficient_data",
                "weeks_analyzed": len(report_files),
                "message": "Need at least 2 weekly reports for trend analysis"
            }
        
        # Load recent reports (last 8 weeks)
        recent_reports = []
        for file_path in report_files[-8:]:
            try:
                with open(file_path, 'r') as f:
                    report = json.load(f)
                    recent_reports.append(report)
            except Exception as e:
                print(f"⚠️ Error reading {file_path}: {e}")
        
        if len(recent_reports) < 2:
            return {"trend_analysis": "insufficient_data", "message": "Need at least 2 valid reports"}
        
        # Calculate trends
        total_violations = [r["quality_metrics"]["total_violations"] for r in recent_reports]
        p0_violations = [r["quality_metrics"]["p0_critical_violations"] for r in recent_reports]
        auto_fixable = [r["quality_metrics"]["auto_fixable_violations"] for r in recent_reports]
        
        # Determine trend direction
        if len(total_violations) >= 3:
            recent_avg = statistics.mean(total_violations[-3:])
            older_avg = statistics.mean(total_violations[:-3]) if len(total_violations) >= 4 else total_violations[0]
            
            if recent_avg < older_avg * 0.95:
                trend_direction = "improving"
            elif recent_avg > older_avg * 1.05:
                trend_direction = "degrading"
            else:
                trend_direction = "stable"
        else:
            trend_direction = "stable"
        
        return {
            "trend_analysis": "complete",
            "weeks_analyzed": len(recent_reports),
            "trend_direction": trend_direction,
            "metrics_history": {
                "total_violations": total_violations,
                "p0_violations": p0_violations,
                "auto_fixable": auto_fixable
            },
            "summary": {
                "current_total": total_violations[-1] if total_violations else 0,
                "previous_total": total_violations[-2] if len(total_violations) > 1 else 0,
                "change_since_last": total_violations[-1] - total_violations[-2] if len(total_violations) > 1 else 0,
                "p0_stable": all(v == 0 for v in p0_violations[-4:]) if len(p0_violations) >= 4 else p0_violations[-1] == 0 if p0_violations else True
            }
        }

    def generate_monitoring_report(self, metrics: Dict[str, Any], trends: Dict[str, Any]) -> Dict[str, Any]:
        """Generate comprehensive monitoring report"""
        timestamp = datetime.now()
        
        return {
            "monitoring_timestamp": timestamp.isoformat(),
            "report_id": f"weekly_monitoring_{timestamp.strftime('%Y%m%d_%H%M%S')}",
            "quality_metrics": metrics,
            "quality_status": {
                "p0_compliant": metrics["p0_critical_violations"] == 0,
                "improvement_available": metrics["auto_fixable_violations"] > 0,
                "quality_grade": "PASS" if metrics["p0_critical_violations"] == 0 else "FAIL",
                "trend_direction": trends.get("trend_direction", "unknown")
            },
            "trend_analysis": trends,
            "monitoring_metadata": {
                "ruff_version": self.get_ruff_version(),
                "python_version": "3.11",
                "monitoring_frequency": "weekly",
                "alert_threshold_p0": 1,
                "monitor_version": "1.0"
            }
        }

    def create_alert(self, metrics: Dict[str, Any], force: bool = False) -> Dict[str, Any]:
        """Create P0 regression alert"""
        timestamp = datetime.now()
        
        alert_data = {
            "alert_type": "P0_REGRESSION" if metrics["p0_critical_violations"] > 0 else "TEST_ALERT",
            "severity": "HIGH" if metrics["p0_critical_violations"] > 0 else "INFO",
            "timestamp": timestamp.isoformat(),
            "metrics": metrics,
            "action_required": metrics["p0_critical_violations"] > 0,
            "alert_message": (
                f"🚨 P0 REGRESSION DETECTED: {metrics['p0_critical_violations']} blocking violations found!"
                if metrics["p0_critical_violations"] > 0
                else "🧪 Test alert triggered manually"
            ),
            "forced": force
        }
        
        return alert_data

    def generate_executive_summary(self, report: Dict[str, Any], trends: Dict[str, Any], alert: Optional[Dict[str, Any]]) -> str:
        """Generate executive summary report"""
        timestamp = datetime.now()
        metrics = report["quality_metrics"]
        
        summary = f"""# Weekly Code Quality Report
## {timestamp.strftime('%B %d, %Y')}

### 🎯 Quality Status Overview

| Metric | Current | Status |
|--------|---------|--------|
| **P0 Critical Violations** | {metrics['p0_critical_violations']} | {'🟢 PASS' if metrics['p0_critical_violations'] == 0 else '🔴 FAIL'} |
| **Total Violations** | {metrics['total_violations']:,} | {'🟡 Improving' if trends.get('trend_direction') == 'improving' else '🔵 Stable' if trends.get('trend_direction') == 'stable' else '🟠 Needs Attention'} |
| **Auto-Fixable** | {metrics['auto_fixable_violations']:,} | {'🛠️ Available' if metrics['auto_fixable_violations'] > 0 else '✨ Clean'} |
| **Files Affected** | {metrics['files_affected']:,} | {'📁 Multiple' if metrics['files_affected'] > 10 else '📄 Limited'} |
| **CI Pipeline** | {'Blocked' if metrics['p0_critical_violations'] > 0 else 'Unblocked'} | {'🔴 Action Required' if metrics['p0_critical_violations'] > 0 else '🟢 Operational'} |

### 📈 Quality Trends

**Trend Direction:** {trends.get('trend_direction', 'Unknown').title()}

{self.format_trend_details(trends)}

### 🚨 Alerts & Actions

{'**🚨 CRITICAL: P0 violations detected!**' if metrics['p0_critical_violations'] > 0 else '✅ No critical issues detected'}
{f'- **{metrics["p0_critical_violations"]} P0 violations** are blocking CI pipeline' if metrics['p0_critical_violations'] > 0 else '- CI pipeline remains unblocked'}
{f'- **Immediate action required** to resolve blocking issues' if metrics['p0_critical_violations'] > 0 else '- Continue regular quality maintenance'}
{f'- **{metrics["auto_fixable_violations"]} violations** can be auto-fixed with `ruff --fix`' if metrics['auto_fixable_violations'] > 0 else ''}

### 📊 Automation Status

- **Weekly Monitoring:** ✅ Active
- **P0 Detection:** ✅ {'Alert Triggered' if alert else 'Monitoring'}
- **Style Cleanup:** {'🛠️ Needed' if metrics['auto_fixable_violations'] > 0 else '✅ Current'}
- **Evidence Collection:** ✅ Complete

### 🔗 Resources

- **Manual Monitoring:** `python scripts/weekly_quality_monitor.py`
- **Style Cleanup:** `python scripts/ruff_style_cleanup_automation.py`
- **Violation Fix:** `python -m ruff check . --fix`
- **Evidence Location:** `evidence/weekly/`

### 📞 Next Steps

{f'1. **URGENT:** Fix {metrics["p0_critical_violations"]} P0 violations to unblock CI' if metrics['p0_critical_violations'] > 0 else '1. Continue monitoring for regressions'}
{f'2. Run style cleanup automation to fix {metrics["auto_fixable_violations"]} auto-fixable violations' if metrics['auto_fixable_violations'] > 0 else '2. Maintain current quality standards'}
{'3. Review alert details and triage critical violations' if alert else '3. Review weekly trends for improvement opportunities'}

---
**Report Generated:** {timestamp.strftime('%Y-%m-%d %H:%M:%S')} UTC  
**Monitor Version:** Weekly Quality Monitor v1.0  
**Next Report:** {(timestamp + timedelta(days=7)).strftime('%B %d, %Y')}
"""
        return summary

    def format_trend_details(self, trends: Dict[str, Any]) -> str:
        """Format trend analysis details"""
        if trends.get("trend_analysis") != "complete":
            return "**Insufficient data** for trend analysis (need at least 2 reports)"
        
        summary = trends.get("summary", {})
        current = summary.get("current_total", 0)
        previous = summary.get("previous_total", 0)
        change = summary.get("change_since_last", 0)
        
        change_text = f"+{change}" if change > 0 else str(change)
        
        return f"""
**Recent Change:** {change_text} violations since last report
**P0 Stability:** {'🟢 Stable' if summary.get('p0_stable', False) else '🟡 Monitoring'}
**Weeks Analyzed:** {trends.get('weeks_analyzed', 0)}
"""

    def save_monitoring_data(self, report: Dict[str, Any], trends: Dict[str, Any], 
                           executive_summary: str, alert: Optional[Dict[str, Any]]):
        """Save all monitoring data to evidence directory"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save monitoring report
        report_file = self.evidence_dir / f"weekly_monitoring_report_{timestamp}.json"
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        
        # Save trend analysis
        trend_file = self.evidence_dir / "trends" / f"trend_analysis_{timestamp}.json"
        with open(trend_file, 'w') as f:
            json.dump(trends, f, indent=2, default=str)
        
        # Save executive summary
        summary_file = self.evidence_dir / "reports" / f"executive_summary_{timestamp}.md"
        with open(summary_file, 'w') as f:
            f.write(executive_summary)
        
        # Save alert if generated
        if alert:
            alert_file = self.evidence_dir / "alerts" / f"p0_alert_{timestamp}.json"
            with open(alert_file, 'w') as f:
                json.dump(alert, f, indent=2, default=str)
        
        print(f"💾 Monitoring data saved to evidence/weekly/")

    def display_results(self, report: Dict[str, Any], trends: Dict[str, Any], alert: Optional[Dict[str, Any]]):
        """Display monitoring results"""
        metrics = report["quality_metrics"]
        
        print(f"\n📊 Weekly Quality Monitoring Results")
        print("=" * 50)
        print(f"📅 Report Date: {datetime.now().strftime('%B %d, %Y')}")
        print(f"🎯 P0 Critical: {metrics['p0_critical_violations']}")
        print(f"📊 Total Violations: {metrics['total_violations']:,}")
        print(f"🛠️ Auto-fixable: {metrics['auto_fixable_violations']:,}")
        print(f"📁 Files Affected: {metrics['files_affected']:,}")
        print(f"🔄 Trend: {trends.get('trend_direction', 'unknown').title()}")
        print(f"🚨 Alert: {'YES' if alert else 'NO'}")
        print(f"🚀 CI Status: {'BLOCKED' if metrics['ci_blocking'] else 'UNBLOCKED'}")
        
        if alert:
            print(f"\n🚨 {alert['alert_message']}")
            if metrics['p0_critical_violations'] > 0:
                print(f"⚡ Action Required: Fix P0 violations immediately!")
        
        print(f"\n📁 Evidence: evidence/weekly/")
        print(f"🔧 Next Action: {'Fix P0 violations' if metrics['p0_critical_violations'] > 0 else 'Continue monitoring'}")

    def get_ruff_version(self) -> str:
        """Get Ruff version"""
        try:
            result = subprocess.run(
                ["python3", "-m", "ruff", "--version"],
                capture_output=True,
                text=True,
                cwd=self.project_root
            )
            return result.stdout.strip()
        except Exception:
            return "unknown"


def main():
    """Main monitoring script"""
    parser = argparse.ArgumentParser(description="Weekly Code Quality Monitor")
    parser.add_argument("--alert-test", action="store_true",
                       help="Force P0 alert for testing")
    parser.add_argument("--trend-only", action="store_true",
                       help="Only analyze trends from existing data")
    parser.add_argument("--project-root", default=".",
                       help="Project root directory")
    
    args = parser.parse_args()
    
    monitor = WeeklyQualityMonitor(args.project_root)
    
    try:
        if args.trend_only:
            print("📈 Trend Analysis Only Mode")
            trends = monitor.analyze_trends()
            print(json.dumps(trends, indent=2, default=str))
        else:
            results = monitor.run_monitoring(force_alert=args.alert_test)
            
            # Exit with error if P0 violations found
            if results["report"]["quality_metrics"]["p0_critical_violations"] > 0:
                print("\n❌ MONITORING FAILED: P0 violations detected")
                exit(1)
            else:
                print("\n✅ MONITORING PASSED: No P0 violations")
                
    except KeyboardInterrupt:
        print("\n⚠️ Monitoring interrupted by user")
        exit(1)
    except Exception as e:
        print(f"\n❌ Monitoring failed: {e}")
        exit(1)


if __name__ == "__main__":
    main()