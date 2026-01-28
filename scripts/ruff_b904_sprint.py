#!/usr/bin/env python3
"""
B904 Exception Chaining Sprint Automation
Targeted automation for systematic B904 violation remediation

Provides focused sprint planning, file targeting, fix templates,
and evidence collection for the 278 B904 exception chaining violations.

Usage:
    python scripts/ruff_b904_sprint.py
    python scripts/ruff_b904_sprint.py --generate-issues
    python scripts/ruff_b904_sprint.py --progress-report
"""

import argparse
import json
import subprocess
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


class B904SprintAutomation:
    """
    B904 Exception Chaining Sprint Automation

    Systematically processes B904 violations to support focused
    sprint work with evidence collection and progress tracking.
    """

    def __init__(self, project_root: str = "."):
        self.project_root = Path(project_root).absolute()
        self.evidence_dir = self.project_root / "evidence" / "b904_sprint"
        self.evidence_dir.mkdir(parents=True, exist_ok=True)

    def run_sprint_automation(self, generate_issues: bool = False,
                            progress_only: bool = False) -> dict[str, Any]:
        """
        Run complete B904 sprint automation cycle

        Args:
            generate_issues: Create GitHub issue templates
            progress_only: Only analyze progress from existing data

        Returns:
            dict: Complete sprint automation results
        """
        print("🎯 B904 Exception Chaining Sprint Automation")
        print("=" * 60)

        if progress_only:
            return self.generate_progress_report()

        # Collect B904 violations
        b904_violations = self.collect_b904_violations()

        # Analyze violations by file
        file_analysis = self.analyze_violations_by_file(b904_violations)

        # Generate sprint targets
        sprint_targets = self.generate_sprint_targets(file_analysis)

        # Create fix templates and guides
        fix_templates = self.generate_fix_templates(b904_violations)

        # Generate sprint summary
        sprint_summary = self.generate_sprint_summary(sprint_targets, file_analysis)

        # Save all evidence
        evidence_data = self.save_sprint_evidence(
            b904_violations, file_analysis, sprint_targets,
            fix_templates, sprint_summary
        )

        # Generate GitHub issues if requested
        if generate_issues:
            issue_templates = self.generate_github_issues(file_analysis)
            evidence_data["github_issues"] = issue_templates

        # Display results
        self.display_sprint_results(sprint_targets, file_analysis)

        return evidence_data

    def collect_b904_violations(self) -> list[dict[str, Any]]:
        """Collect all B904 violations using Ruff"""
        print("📊 Collecting B904 exception chaining violations...")

        try:
            result = subprocess.run(
                ["python3", "-m", "ruff", "check", ".", "--select", "B904", "--output-format=json"],
                capture_output=True,
                text=True,
                cwd=self.project_root
            )

            violations = json.loads(result.stdout) if result.stdout.strip() else []

            print(f"✅ Found {len(violations)} B904 violations")
            return violations

        except Exception as e:
            print(f"❌ Error collecting B904 violations: {e}")
            return []

    def analyze_violations_by_file(self, violations: list[dict[str, Any]]) -> dict[str, Any]:
        """Analyze B904 violations grouped by file"""
        by_file = defaultdict(list)

        for violation in violations:
            filename = violation.get("filename", "unknown")
            by_file[filename].append(violation)

        # Sort files by violation count (descending)
        sorted_files = sorted(by_file.items(), key=lambda x: len(x[1]), reverse=True)

        # Calculate sprint statistics
        total_files = len(sorted_files)
        total_violations = len(violations)
        avg_violations_per_file = total_violations / total_files if total_files > 0 else 0

        # Categorize files by effort required
        high_effort_files = [(f, v) for f, v in sorted_files if len(v) >= 10]
        medium_effort_files = [(f, v) for f, v in sorted_files if 5 <= len(v) < 10]
        low_effort_files = [(f, v) for f, v in sorted_files if 1 <= len(v) < 5]

        return {
            "sorted_files": sorted_files,
            "statistics": {
                "total_files": total_files,
                "total_violations": total_violations,
                "avg_violations_per_file": avg_violations_per_file,
                "high_effort_files": len(high_effort_files),
                "medium_effort_files": len(medium_effort_files),
                "low_effort_files": len(low_effort_files)
            },
            "effort_categories": {
                "high_effort": high_effort_files,
                "medium_effort": medium_effort_files,
                "low_effort": low_effort_files
            },
            "top_10_files": sorted_files[:10]
        }

    def generate_sprint_targets(self, file_analysis: dict[str, Any]) -> dict[str, Any]:
        """Generate sprint planning targets"""
        stats = file_analysis["statistics"]
        effort_cats = file_analysis["effort_categories"]

        # Sprint planning suggestions
        sprint_plan = {
            "sprint_1_quick_wins": {
                "target": "Low effort files (1-4 violations per file)",
                "files": len(effort_cats["low_effort"]),
                "violations": sum(len(v) for _, v in effort_cats["low_effort"]),
                "estimated_days": 1,
                "description": "Quick wins to build momentum and establish patterns"
            },
            "sprint_2_medium_files": {
                "target": "Medium effort files (5-9 violations per file)",
                "files": len(effort_cats["medium_effort"]),
                "violations": sum(len(v) for _, v in effort_cats["medium_effort"]),
                "estimated_days": 2,
                "description": "Systematic processing of moderate complexity files"
            },
            "sprint_3_high_impact": {
                "target": "High effort files (10+ violations per file)",
                "files": len(effort_cats["high_effort"]),
                "violations": sum(len(v) for _, v in effort_cats["high_effort"]),
                "estimated_days": 3,
                "description": "Deep refactoring of exception handling patterns"
            }
        }

        return {
            "sprint_overview": {
                "total_violations": stats["total_violations"],
                "total_files": stats["total_files"],
                "estimated_total_days": 6,
                "sprints": 3
            },
            "sprint_breakdown": sprint_plan,
            "success_metrics": {
                "target_reduction": stats["total_violations"],
                "completion_rate_target": 100,
                "quality_improvement": "Better error traceability in production",
                "progress_toward_goal": "Reduces total violations from 780 to ~502 (36% reduction)"
            }
        }

    def generate_fix_templates(self, violations: list[dict[str, Any]]) -> dict[str, Any]:
        """Generate fix templates and examples for B904 violations"""

        # Common B904 patterns and their fixes
        fix_patterns = {
            "basic_reraise": {
                "description": "Basic exception re-raising with context",
                "before": """try:
    risky_operation()
except Exception as e:
    raise ValueError(f"Operation failed: {e}")""",
                "after": """try:
    risky_operation()
except Exception as e:
    raise ValueError(f"Operation failed: {e}") from e""",
                "explanation": "Add 'from e' to preserve exception chain"
            },

            "conditional_reraise": {
                "description": "Conditional re-raising with different exceptions",
                "before": """try:
    api_call()
except httpx.HTTPStatusError as e:
    if e.response.status_code == 404:
        raise ValueError("Resource not found")
    raise APIError("Request failed")""",
                "after": """try:
    api_call()
except httpx.HTTPStatusError as e:
    if e.response.status_code == 404:
        raise ValueError("Resource not found") from e
    raise APIError("Request failed") from e""",
                "explanation": "Add 'from e' to both exception paths"
            },

            "suppress_chain": {
                "description": "Suppress exception chain when original error isn't relevant",
                "before": """try:
    fallback_operation()
except Exception as e:
    raise CustomError("Fallback failed")""",
                "after": """try:
    fallback_operation()
except Exception as e:
    raise CustomError("Fallback failed") from None""",
                "explanation": "Use 'from None' when original exception should be suppressed"
            }
        }

        # File-specific examples from actual violations
        example_fixes = []
        seen_files = set()

        for violation in violations[:10]:  # Show examples from first 10 violations
            filename = violation.get("filename", "")
            if filename in seen_files:
                continue
            seen_files.add(filename)

            line_number = violation.get("location", {}).get("row", 0)
            message = violation.get("message", "")

            example_fixes.append({
                "file": filename,
                "line": line_number,
                "issue": message,
                "fix_approach": "Add 'from e' or 'from None' to preserve/suppress exception chain"
            })

        return {
            "fix_patterns": fix_patterns,
            "example_fixes": example_fixes,
            "checklist": {
                "before_fix": [
                    "🔍 Identify the original exception variable (usually 'e')",
                    "🤔 Determine if original exception context is helpful",
                    "📋 Check if this is a re-raise or new exception"
                ],
                "during_fix": [
                    "✏️ Add 'from e' to preserve exception chain",
                    "🚫 Use 'from None' to suppress irrelevant original exceptions",
                    "🔗 Ensure exception message is still informative"
                ],
                "after_fix": [
                    "✅ Verify exception chain makes sense in logs",
                    "🧪 Test error handling still works correctly",
                    "📝 Run 'ruff check --select B904' to confirm fix"
                ]
            }
        }

    def generate_sprint_summary(self, sprint_targets: dict[str, Any],
                              file_analysis: dict[str, Any]) -> str:
        """Generate comprehensive sprint summary in Markdown"""
        timestamp = datetime.now()
        stats = file_analysis["statistics"]

        return f"""# B904 Exception Chaining Sprint Summary
## {timestamp.strftime('%B %d, %Y')}

### 🎯 Sprint Objectives

**Mission**: Systematically eliminate 278 B904 exception chaining violations to improve error traceability and drive total violations below 502.

### 📊 Current Status

| Metric | Value |
|--------|-------|
| **Total B904 Violations** | {stats['total_violations']} |
| **Files Affected** | {stats['total_files']} |
| **Average per File** | {stats['avg_violations_per_file']:.1f} |
| **Impact on Total** | 780 → ~502 violations (36% reduction) |

### 🚀 Sprint Breakdown

#### Sprint 1: Quick Wins (Day 1)
- **Target**: {sprint_targets['sprint_breakdown']['sprint_1_quick_wins']['files']} files with 1-4 violations each
- **Violations**: {sprint_targets['sprint_breakdown']['sprint_1_quick_wins']['violations']} total
- **Goal**: Build momentum and establish fix patterns

#### Sprint 2: Medium Files (Days 2-3)
- **Target**: {sprint_targets['sprint_breakdown']['sprint_2_medium_files']['files']} files with 5-9 violations each
- **Violations**: {sprint_targets['sprint_breakdown']['sprint_2_medium_files']['violations']} total
- **Goal**: Systematic processing of moderate complexity

#### Sprint 3: High Impact (Days 4-6)
- **Target**: {sprint_targets['sprint_breakdown']['sprint_3_high_impact']['files']} files with 10+ violations each
- **Violations**: {sprint_targets['sprint_breakdown']['sprint_3_high_impact']['violations']} total
- **Goal**: Deep refactoring of exception patterns

### 🔧 Fix Templates

**Basic Pattern**:
```python
# Before
raise ValueError(f"Error: {{e}}")

# After
raise ValueError(f"Error: {{e}}") from e
```

**When to suppress**:
```python
# Use 'from None' when original exception isn't helpful
raise CustomError("Clean error message") from None
```

### 📈 Success Metrics

- **Completion Rate**: Target 100% of 278 violations
- **Quality Impact**: Better error traceability in production
- **Progress Goal**: Reduce total violations by 36%
- **Timeline**: 6 days total across 3 focused sprints

### 🛠️ Resources

- **Sprint Tool**: `python scripts/ruff_b904_sprint.py`
- **Progress Check**: `python scripts/ruff_b904_sprint.py --progress-report`
- **Weekly Monitor**: `python scripts/weekly_quality_monitor.py`
- **Evidence**: `evidence/b904_sprint/`

### 📞 Next Steps

1. **Start Sprint 1**: Focus on low-effort files for quick wins
2. **Use Fix Templates**: Apply consistent exception chaining patterns
3. **Track Progress**: Use automation tools for evidence collection
4. **Monitor Impact**: Weekly pipeline will capture improvements

---
**Sprint Generated**: {timestamp.strftime('%Y-%m-%d %H:%M:%S')} UTC
**Sprint Automation**: B904 Sprint Tool v1.0
**Evidence Location**: `evidence/b904_sprint/`
"""

    def generate_github_issues(self, file_analysis: dict[str, Any]) -> list[dict[str, Any]]:
        """Generate GitHub issue templates for sprint work"""
        issues = []

        for category, files in file_analysis["effort_categories"].items():
            if not files:
                continue

            # Create one issue per category
            effort_map = {
                "low_effort": {"title": "Quick Wins", "estimate": "1 day", "priority": "P2"},
                "medium_effort": {"title": "Medium Files", "estimate": "2 days", "priority": "P1"},
                "high_effort": {"title": "High Impact", "estimate": "3 days", "priority": "P0"}
            }

            meta = effort_map[category]
            violation_count = sum(len(v) for _, v in files)

            issue = {
                "title": f"B904 Sprint: {meta['title']} - {len(files)} files ({violation_count} violations)",
                "labels": ["code-quality", "b904-sprint", meta["priority"]],
                "estimate": meta["estimate"],
                "body": self.generate_issue_body(category, files, meta),
                "category": category
            }

            issues.append(issue)

        return issues

    def generate_issue_body(self, category: str, files: list[tuple[str, list]],
                          meta: dict[str, str]) -> str:
        """Generate GitHub issue body for a sprint category"""
        violation_count = sum(len(v) for _, v in files)

        body = f"""## B904 Exception Chaining Sprint - {meta['title']}

### 🎯 Objective
Fix B904 exception chaining violations in {len(files)} files ({violation_count} total violations).

### 📋 Files to Process

| File | Violations | Lines |
|------|------------|-------|"""

        for filename, violations in files:
            lines = [str(v.get("location", {}).get("row", "?")) for v in violations]
            line_summary = f"{lines[0]}" if len(lines) == 1 else f"{lines[0]}...+{len(lines)-1} more"
            body += f"\n| `{filename}` | {len(violations)} | {line_summary} |"

        body += f"""

### 🔧 Fix Pattern

Apply exception chaining to preserve error context:

```python
# Before
except Exception as e:
    raise ValueError(f"Operation failed: {{e}}")

# After
except Exception as e:
    raise ValueError(f"Operation failed: {{e}}") from e
```

### ✅ Acceptance Criteria

- [ ] All B904 violations fixed in listed files
- [ ] Exception chains preserve meaningful error context
- [ ] Run `python3 -m ruff check --select B904` shows 0 violations
- [ ] Update sprint progress with `python scripts/ruff_b904_sprint.py --progress-report`

### 🔗 Resources

- **Sprint Tool**: `python scripts/ruff_b904_sprint.py`
- **Fix Examples**: `evidence/b904_sprint/fix_templates.json`
- **Weekly Monitor**: Tracks progress automatically

---
**Estimate**: {meta['estimate']}
**Sprint Category**: {category.replace('_', ' ').title()}
"""

        return body

    def generate_progress_report(self) -> dict[str, Any]:
        """Generate progress report from existing sprint data"""
        print("📈 Generating B904 sprint progress report...")

        # Get current B904 count
        current_violations = self.collect_b904_violations()

        # Load baseline from latest sprint target file
        baseline_files = list(self.evidence_dir.glob("b904_targets_*.json"))
        baseline_count = 278  # Default if no baseline found

        if baseline_files:
            latest_baseline = sorted(baseline_files)[-1]
            try:
                with open(latest_baseline) as f:
                    baseline_data = json.load(f)
                    baseline_count = baseline_data.get("total_violations", 278)
            except Exception:
                pass

        progress = {
            "baseline_violations": baseline_count,
            "current_violations": len(current_violations),
            "violations_fixed": baseline_count - len(current_violations),
            "completion_rate": ((baseline_count - len(current_violations)) / baseline_count * 100) if baseline_count > 0 else 0,
            "remaining_work": len(current_violations),
            "report_timestamp": datetime.now().isoformat()
        }

        # Save progress report
        progress_file = self.evidence_dir / f"progress_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(progress_file, 'w') as f:
            json.dump(progress, f, indent=2, default=str)

        print(f"📊 Progress: {progress['violations_fixed']}/{baseline_count} violations fixed ({progress['completion_rate']:.1f}%)")

        return progress

    def save_sprint_evidence(self, violations: list[dict[str, Any]],
                           file_analysis: dict[str, Any],
                           sprint_targets: dict[str, Any],
                           fix_templates: dict[str, Any],
                           sprint_summary: str) -> dict[str, Any]:
        """Save all sprint evidence to evidence directory"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Save violations data
        violations_file = self.evidence_dir / f"b904_violations_{timestamp}.json"
        with open(violations_file, 'w') as f:
            json.dump(violations, f, indent=2, default=str)

        # Save sprint targets
        targets_file = self.evidence_dir / f"b904_targets_{timestamp}.json"
        targets_data = {
            "timestamp": datetime.now().isoformat(),
            "total_violations": len(violations),
            "file_analysis": file_analysis,
            "sprint_targets": sprint_targets
        }
        with open(targets_file, 'w') as f:
            json.dump(targets_data, f, indent=2, default=str)

        # Save fix templates
        templates_file = self.evidence_dir / "fix_templates.json"
        with open(templates_file, 'w') as f:
            json.dump(fix_templates, f, indent=2, default=str)

        # Save sprint summary
        summary_file = self.evidence_dir / "b904_sprint_summary.md"
        with open(summary_file, 'w') as f:
            f.write(sprint_summary)

        print("💾 Sprint evidence saved to evidence/b904_sprint/")

        return {
            "violations_file": str(violations_file),
            "targets_file": str(targets_file),
            "templates_file": str(templates_file),
            "summary_file": str(summary_file),
            "evidence_dir": str(self.evidence_dir)
        }

    def display_sprint_results(self, sprint_targets: dict[str, Any],
                             file_analysis: dict[str, Any]):
        """Display sprint automation results"""
        stats = file_analysis["statistics"]

        print("\n🎯 B904 Sprint Automation Results")
        print("=" * 50)
        print(f"📊 Total B904 Violations: {stats['total_violations']}")
        print(f"📁 Files Affected: {stats['total_files']}")
        print(f"📈 Average per File: {stats['avg_violations_per_file']:.1f}")
        print("🎯 Impact: 780 → ~502 total violations (36% reduction)")

        print("\n📋 Sprint Breakdown:")
        for sprint_name, sprint_data in sprint_targets['sprint_breakdown'].items():
            print(f"   {sprint_name}: {sprint_data['files']} files, {sprint_data['violations']} violations")

        print("\n📁 Top Files by Violation Count:")
        for filename, violations in file_analysis['top_10_files'][:5]:
            print(f"   {filename}: {len(violations)} violations")

        print("\n🔗 Resources:")
        print("   Sprint Summary: evidence/b904_sprint/b904_sprint_summary.md")
        print("   Fix Templates: evidence/b904_sprint/fix_templates.json")
        print("   Progress Check: python scripts/ruff_b904_sprint.py --progress-report")


def main():
    """Main B904 sprint automation script"""
    parser = argparse.ArgumentParser(description="B904 Exception Chaining Sprint Automation")
    parser.add_argument("--generate-issues", action="store_true",
                       help="Generate GitHub issue templates")
    parser.add_argument("--progress-report", action="store_true",
                       help="Generate progress report from existing data")
    parser.add_argument("--project-root", default=".",
                       help="Project root directory")

    args = parser.parse_args()

    automation = B904SprintAutomation(args.project_root)

    try:
        automation.run_sprint_automation(
            generate_issues=args.generate_issues,
            progress_only=args.progress_report
        )

        if args.progress_report:
            print("\n✅ Progress report generated")
        else:
            print("\n✅ B904 sprint automation complete")
            print("📁 Evidence: evidence/b904_sprint/")

    except KeyboardInterrupt:
        print("\n⚠️ Sprint automation interrupted by user")
        exit(1)
    except Exception as e:
        print(f"\n❌ Sprint automation failed: {e}")
        exit(1)


if __name__ == "__main__":
    main()
