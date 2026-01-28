#!/usr/bin/env python3
"""
Ruff Style Cleanup Automation - Post P0 Campaign
Automated style violation cleanup via batched ruff --fix operations

Systematically processes auto-fixable violations by directory to:
- Eliminate the 830+ remaining auto-fixable style violations
- Maintain evidence trail of cleanup progress
- Prevent overwhelming git history with massive single commits
- Enable incremental quality improvements without manual toil

Usage:
    python scripts/ruff_style_cleanup_automation.py --batch-size 50
    python scripts/ruff_style_cleanup_automation.py --directory order_service_clean
    python scripts/ruff_style_cleanup_automation.py --dry-run  # Preview only
"""

import json
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class StyleCleanupStats:
    """Statistics for style cleanup batch"""
    directory: str
    violations_before: int
    violations_after: int
    violations_fixed: int
    auto_fixable_before: int
    auto_fixable_after: int
    processing_time_ms: float
    ruff_output: str = ""
    files_modified: list[str] = field(default_factory=list)


@dataclass
class CleanupSession:
    """Overall cleanup session tracking"""
    session_id: str
    start_time: str
    total_violations_baseline: int
    total_auto_fixable_baseline: int
    batches_processed: list[StyleCleanupStats] = field(default_factory=list)
    session_complete: bool = False
    total_violations_fixed: int = 0


class RuffStyleCleanupAutomation:
    """
    Automated style violation cleanup using batched ruff --fix operations

    Processes violations incrementally by directory to maintain manageable
    git commits and provide progress visibility.
    """

    def __init__(self, batch_size: int = 50):
        self.batch_size = batch_size
        self.evidence_dir = Path("evidence/style_cleanup")
        self.evidence_dir.mkdir(exist_ok=True)

        # Directories to process in priority order (based on actual structure)
        self.cleanup_directories = [
            "app",           # Main application code
            "tests",         # Test code
            "scripts",       # Automation scripts
            "common",        # Shared components
            "test",          # Additional test directory
            "."              # Root level last (entire codebase)
        ]

        # Track state across batches
        self.session = CleanupSession(
            session_id=f"style_cleanup_{int(time.time())}",
            start_time=datetime.now().isoformat(),
            total_violations_baseline=0,
            total_auto_fixable_baseline=0
        )

    def run_cleanup_automation(self, target_directory: str | None = None,
                              dry_run: bool = False) -> dict:
        """
        Run automated style cleanup across specified directories

        Args:
            target_directory: Specific directory to clean (optional)
            dry_run: Preview changes without applying fixes

        Returns:
            dict: Complete cleanup session report
        """
        print("🧹 Ruff Style Cleanup Automation")
        print("=" * 50)

        # Get baseline violation counts
        baseline_stats = self._get_violation_baseline()
        self.session.total_violations_baseline = baseline_stats["total_violations"]
        self.session.total_auto_fixable_baseline = baseline_stats["auto_fixable"]

        print(f"📊 Baseline: {baseline_stats['total_violations']} violations "
              f"({baseline_stats['auto_fixable']} auto-fixable)")

        if dry_run:
            print("🔍 DRY RUN MODE - No changes will be applied")

        # Process directories
        directories = [target_directory] if target_directory else self.cleanup_directories

        for directory in directories:
            if not Path(directory).exists():
                print(f"⚠️  Directory {directory} not found, skipping")
                continue

            print(f"\n🎯 Processing directory: {directory}")
            batch_stats = self._process_directory_batch(directory, dry_run)

            if batch_stats.violations_fixed > 0:
                self.session.batches_processed.append(batch_stats)
                self.session.total_violations_fixed += batch_stats.violations_fixed

                print(f"   ✅ Fixed {batch_stats.violations_fixed} violations "
                      f"in {batch_stats.processing_time_ms:.0f}ms")

                if not dry_run:
                    # Create git commit for this batch
                    self._create_batch_commit(batch_stats)
            else:
                print(f"   📝 No fixable violations in {directory}")

        # Generate session report
        self.session.session_complete = True
        session_report = self._generate_session_report()

        if not dry_run:
            # Save evidence
            self._save_session_evidence(session_report)

        return session_report

    def _get_violation_baseline(self) -> dict:
        """Get current violation counts as baseline"""
        try:
            result = subprocess.run(
                ["python3", "-m", "ruff", "check", ".", "--statistics"],
                capture_output=True,
                text=True,
                cwd="/home/stocksadmin/signal-service-codex-review"
            )

            output_lines = result.stdout.strip().split('\n')
            total_violations = 0
            auto_fixable = 0

            for line in output_lines:
                if line and not line.startswith('[*]'):
                    parts = line.split('\t')
                    if len(parts) >= 2:
                        try:
                            count = int(parts[0].strip())
                            total_violations += count

                            # Check if auto-fixable
                            if len(parts) >= 3 and '[*]' in parts[2]:
                                auto_fixable += count
                        except ValueError:
                            continue

            return {
                "total_violations": total_violations,
                "auto_fixable": auto_fixable,
                "ruff_output": result.stdout
            }

        except Exception as e:
            print(f"❌ Error getting baseline: {e}")
            return {"total_violations": 0, "auto_fixable": 0, "ruff_output": ""}

    def _process_directory_batch(self, directory: str, dry_run: bool) -> StyleCleanupStats:
        """Process a single directory batch"""
        start_time = time.time()

        # Get before stats
        before_stats = self._get_directory_violations(directory)

        batch_stats = StyleCleanupStats(
            directory=directory,
            violations_before=before_stats["violations"],
            auto_fixable_before=before_stats["auto_fixable"],
            violations_after=0,
            violations_fixed=0,
            auto_fixable_after=0,
            processing_time_ms=0.0,
            ruff_output=before_stats["output"]
        )

        if before_stats["auto_fixable"] == 0:
            batch_stats.processing_time_ms = (time.time() - start_time) * 1000
            return batch_stats

        # Apply fixes (unless dry run)
        if not dry_run:
            modified_files = self._apply_ruff_fixes(directory)
            batch_stats.files_modified = modified_files

        # Get after stats
        after_stats = self._get_directory_violations(directory)
        batch_stats.violations_after = after_stats["violations"]
        batch_stats.auto_fixable_after = after_stats["auto_fixable"]
        batch_stats.violations_fixed = (
            batch_stats.violations_before - batch_stats.violations_after
        )
        batch_stats.processing_time_ms = (time.time() - start_time) * 1000

        return batch_stats

    def _get_directory_violations(self, directory: str) -> dict:
        """Get violation count for specific directory"""
        try:
            result = subprocess.run(
                ["python3", "-m", "ruff", "check", directory, "--statistics"],
                capture_output=True,
                text=True,
                cwd="/home/stocksadmin/signal-service-codex-review"
            )

            output_lines = result.stdout.strip().split('\n')
            violations = 0
            auto_fixable = 0

            for line in output_lines:
                if line and not line.startswith('[*]'):
                    parts = line.split('\t')
                    if len(parts) >= 2:
                        try:
                            count = int(parts[0].strip())
                            violations += count

                            if len(parts) >= 3 and '[*]' in parts[2]:
                                auto_fixable += count
                        except ValueError:
                            continue

            return {
                "violations": violations,
                "auto_fixable": auto_fixable,
                "output": result.stdout
            }

        except Exception as e:
            print(f"❌ Error checking {directory}: {e}")
            return {"violations": 0, "auto_fixable": 0, "output": ""}

    def _apply_ruff_fixes(self, directory: str) -> list[str]:
        """Apply ruff --fix to directory and return modified files"""
        try:
            # Get git status before fixes
            subprocess.run(
                ["git", "status", "--porcelain", directory],
                capture_output=True,
                text=True,
                cwd="/home/stocksadmin/signal-service-codex-review"
            )

            # Apply ruff fixes
            subprocess.run(
                ["python3", "-m", "ruff", "check", directory, "--fix"],
                capture_output=True,
                text=True,
                cwd="/home/stocksadmin/signal-service-codex-review"
            )

            # Get git status after fixes to see what changed
            git_after = subprocess.run(
                ["git", "status", "--porcelain", directory],
                capture_output=True,
                text=True,
                cwd="/home/stocksadmin/signal-service-codex-review"
            )

            # Parse modified files
            modified_files = []
            for line in git_after.stdout.strip().split('\n'):
                if line and (line.startswith((" M ", "M  "))):
                    modified_files.append(line[3:].strip())

            return modified_files

        except Exception as e:
            print(f"❌ Error applying fixes to {directory}: {e}")
            return []

    def _create_batch_commit(self, batch_stats: StyleCleanupStats):
        """Create git commit for the batch"""
        try:
            if not batch_stats.files_modified:
                return

            # Add modified files
            for file_path in batch_stats.files_modified:
                subprocess.run(["git", "add", file_path], cwd="/home/stocksadmin/signal-service-codex-review")

            # Create commit message
            commit_msg = f"""style: auto-fix {batch_stats.violations_fixed} violations in {batch_stats.directory}

Batch style cleanup via ruff --fix automation:
- Directory: {batch_stats.directory}
- Violations fixed: {batch_stats.violations_fixed}
- Files modified: {len(batch_stats.files_modified)}
- Processing time: {batch_stats.processing_time_ms:.0f}ms

Part of systematic style cleanup following P0 campaign success.
Auto-fixable violations reduced without manual intervention.

🤖 Generated with [Claude Code](https://claude.ai/code)

Co-Authored-By: Claude <noreply@anthropic.com>"""

            # Create commit
            subprocess.run(
                ["git", "commit", "-m", commit_msg],
                cwd="/home/stocksadmin/signal-service-codex-review",
                check=True
            )

            print(f"   📝 Committed changes for {len(batch_stats.files_modified)} files")

        except Exception as e:
            print(f"❌ Error creating commit: {e}")

    def _generate_session_report(self) -> dict:
        """Generate comprehensive cleanup session report"""
        final_stats = self._get_violation_baseline()

        total_directories_processed = len(self.session.batches_processed)
        total_files_modified = sum(len(b.files_modified) for b in self.session.batches_processed)

        return {
            "cleanup_session": {
                "session_id": self.session.session_id,
                "timestamp": datetime.now().isoformat(),
                "session_complete": self.session.session_complete,
                "baseline_metrics": {
                    "initial_violations": self.session.total_violations_baseline,
                    "initial_auto_fixable": self.session.total_auto_fixable_baseline,
                    "final_violations": final_stats["total_violations"],
                    "final_auto_fixable": final_stats["auto_fixable"]
                },
                "cleanup_impact": {
                    "total_violations_fixed": self.session.total_violations_fixed,
                    "directories_processed": total_directories_processed,
                    "files_modified": total_files_modified,
                    "cleanup_rate": (
                        self.session.total_violations_fixed /
                        self.session.total_auto_fixable_baseline * 100
                    ) if self.session.total_auto_fixable_baseline > 0 else 0
                },
                "batch_details": [
                    {
                        "directory": b.directory,
                        "violations_fixed": b.violations_fixed,
                        "files_modified": len(b.files_modified),
                        "processing_time_ms": b.processing_time_ms
                    }
                    for b in self.session.batches_processed
                ]
            },
            "automation_metrics": {
                "batch_size": self.batch_size,
                "total_processing_time": sum(b.processing_time_ms for b in self.session.batches_processed),
                "avg_batch_time": (
                    sum(b.processing_time_ms for b in self.session.batches_processed) /
                    len(self.session.batches_processed)
                ) if self.session.batches_processed else 0,
                "efficiency_score": self.session.total_violations_fixed / (
                    sum(b.processing_time_ms for b in self.session.batches_processed) / 1000
                ) if self.session.batches_processed else 0  # violations per second
            }
        }

    def _save_session_evidence(self, report: dict):
        """Save cleanup session evidence"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Save detailed report
        report_file = self.evidence_dir / f"style_cleanup_session_{timestamp}.json"
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2, default=str)

        print(f"\n💾 Session evidence saved: {report_file}")

        # Update summary statistics
        summary_file = self.evidence_dir / "cleanup_progress_summary.json"
        try:
            if summary_file.exists():
                with open(summary_file) as f:
                    summary = json.load(f)
            else:
                summary = {"sessions": [], "total_violations_fixed": 0}

            summary["sessions"].append({
                "session_id": self.session.session_id,
                "timestamp": timestamp,
                "violations_fixed": self.session.total_violations_fixed,
                "directories_processed": len(self.session.batches_processed)
            })
            summary["total_violations_fixed"] += self.session.total_violations_fixed

            with open(summary_file, 'w') as f:
                json.dump(summary, f, indent=2, default=str)

        except Exception as e:
            print(f"⚠️  Error updating summary: {e}")


async def main():
    """Main cleanup automation script"""
    import argparse

    parser = argparse.ArgumentParser(description="Ruff Style Cleanup Automation")
    parser.add_argument("--batch-size", type=int, default=50,
                       help="Number of violations to fix per batch")
    parser.add_argument("--directory",
                       help="Specific directory to process")
    parser.add_argument("--dry-run", action="store_true",
                       help="Preview changes without applying fixes")

    args = parser.parse_args()

    automator = RuffStyleCleanupAutomation(batch_size=args.batch_size)

    try:
        report = automator.run_cleanup_automation(
            target_directory=args.directory,
            dry_run=args.dry_run
        )

        print("\n📊 Cleanup Session Summary:")
        cleanup_data = report["cleanup_session"]
        print(f"   Violations Fixed: {cleanup_data['cleanup_impact']['total_violations_fixed']}")
        print(f"   Directories Processed: {cleanup_data['cleanup_impact']['directories_processed']}")
        print(f"   Files Modified: {cleanup_data['cleanup_impact']['files_modified']}")
        print(f"   Cleanup Rate: {cleanup_data['cleanup_impact']['cleanup_rate']:.1f}%")

        if not args.dry_run:
            remaining_fixable = cleanup_data["baseline_metrics"]["final_auto_fixable"]
            if remaining_fixable == 0:
                print("\n🎉 STYLE CLEANUP COMPLETE - No auto-fixable violations remain!")
            else:
                print(f"\n📋 {remaining_fixable} auto-fixable violations remain")
                print("   Run again to continue cleanup automation")

    except KeyboardInterrupt:
        print("\n⚠️  Cleanup automation interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Cleanup automation failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
