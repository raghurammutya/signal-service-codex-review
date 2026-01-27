#!/usr/bin/env python3
"""
Ruff Exemption Management Tool

Manages exemptions for files that cannot be immediately fixed,
with documentation and tracking for technical debt.
"""

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional


def run_command(cmd: list[str]) -> tuple[int, str, str]:
    """Run shell command and return exit code, stdout, stderr"""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        return result.returncode, result.stdout, result.stderr
    except Exception as e:
        return 1, "", str(e)


class RuffExemptionManager:
    """Manages Ruff exemptions with tracking and documentation"""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.ruffignore_path = repo_root / ".ruffignore"
        self.exemptions_db_path = repo_root / "evidence" / "ruff_exemptions.json"
        self.exemptions_db_path.parent.mkdir(parents=True, exist_ok=True)

    def load_exemptions_db(self) -> dict:
        """Load exemptions database"""
        if self.exemptions_db_path.exists():
            with open(self.exemptions_db_path) as f:
                return json.load(f)
        return {
            "exemptions": {},
            "metadata": {
                "created": datetime.now().isoformat(),
                "last_updated": datetime.now().isoformat()
            }
        }

    def save_exemptions_db(self, db: dict) -> None:
        """Save exemptions database"""
        db["metadata"]["last_updated"] = datetime.now().isoformat()
        with open(self.exemptions_db_path, 'w') as f:
            json.dump(db, f, indent=2)

    def get_current_exemptions(self) -> set[str]:
        """Get current exemptions from .ruffignore"""
        if not self.ruffignore_path.exists():
            return set()

        exemptions = set()
        with open(self.ruffignore_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    exemptions.add(line)

        return exemptions

    def add_exemption(
        self,
        path_pattern: str,
        reason: str,
        rules: list[str] | None = None,
        temporary: bool = False,
        review_date: str | None = None,
        assignee: str | None = None
    ) -> bool:
        """Add exemption with documentation"""

        # Load current database
        db = self.load_exemptions_db()

        # Create exemption record
        exemption_id = f"exempt_{len(db['exemptions']) + 1:03d}"
        exemption_record = {
            "path_pattern": path_pattern,
            "reason": reason,
            "rules": rules or [],
            "temporary": temporary,
            "review_date": review_date,
            "assignee": assignee,
            "created_date": datetime.now().isoformat(),
            "status": "active"
        }

        db["exemptions"][exemption_id] = exemption_record

        # Update .ruffignore
        current_exemptions = self.get_current_exemptions()
        if path_pattern not in current_exemptions:
            self._add_to_ruffignore(path_pattern, reason, exemption_id)

        # Save database
        self.save_exemptions_db(db)

        print(f"✅ Added exemption {exemption_id}: {path_pattern}")
        return True

    def _add_to_ruffignore(self, path_pattern: str, reason: str, exemption_id: str) -> None:
        """Add entry to .ruffignore with documentation"""

        # Read existing content
        existing_content = ""
        if self.ruffignore_path.exists():
            with open(self.ruffignore_path) as f:
                existing_content = f.read()

        # Add new exemption with documentation
        exemption_entry = f"""
# {exemption_id}: {reason}
{path_pattern}
"""

        with open(self.ruffignore_path, 'w') as f:
            f.write(existing_content + exemption_entry)

    def list_exemptions(self, show_inactive: bool = False) -> None:
        """list all exemptions"""
        db = self.load_exemptions_db()

        if not db["exemptions"]:
            print("No exemptions found")
            return

        print("📋 **Ruff Exemptions**\n")

        for exemption_id, record in db["exemptions"].items():
            if not show_inactive and record.get("status") != "active":
                continue

            status_emoji = "🟢" if record.get("status") == "active" else "🔴"
            temp_indicator = " (TEMPORARY)" if record.get("temporary") else ""

            print(f"{status_emoji} **{exemption_id}**{temp_indicator}")
            print(f"   Path: {record['path_pattern']}")
            print(f"   Reason: {record['reason']}")

            if record.get("rules"):
                print(f"   Rules: {', '.join(record['rules'])}")

            if record.get("assignee"):
                print(f"   Assignee: {record['assignee']}")

            if record.get("review_date"):
                print(f"   Review Date: {record['review_date']}")

            print(f"   Created: {record['created_date']}")
            print()

    def review_exemptions(self) -> None:
        """Review exemptions that need attention"""
        db = self.load_exemptions_db()

        now = datetime.now()
        needs_review = []

        for exemption_id, record in db["exemptions"].items():
            if record.get("status") != "active":
                continue

            # Check if temporary exemptions are overdue
            if record.get("temporary"):
                created = datetime.fromisoformat(record["created_date"])
                days_old = (now - created).days
                if days_old > 30:  # Temporary exemptions older than 30 days
                    needs_review.append((exemption_id, record, f"Temporary exemption {days_old} days old"))

            # Check review dates
            if record.get("review_date"):
                review_date = datetime.fromisoformat(record["review_date"])
                if review_date <= now:
                    needs_review.append((exemption_id, record, "Scheduled for review"))

        if not needs_review:
            print("✅ No exemptions need review")
            return

        print("⚠️ **Exemptions Needing Review**\n")

        for exemption_id, record, reason in needs_review:
            print(f"🔍 **{exemption_id}**: {record['path_pattern']}")
            print(f"   Reason: {reason}")
            print(f"   Original justification: {record['reason']}")
            print()

    def remove_exemption(self, exemption_id: str) -> bool:
        """Remove an exemption"""
        db = self.load_exemptions_db()

        if exemption_id not in db["exemptions"]:
            print(f"❌ Exemption {exemption_id} not found")
            return False

        # Mark as inactive instead of deleting for audit trail
        db["exemptions"][exemption_id]["status"] = "removed"
        db["exemptions"][exemption_id]["removed_date"] = datetime.now().isoformat()

        # Remove from .ruffignore
        path_pattern = db["exemptions"][exemption_id]["path_pattern"]
        self._remove_from_ruffignore(exemption_id, path_pattern)

        self.save_exemptions_db(db)

        print(f"✅ Removed exemption {exemption_id}")
        return True

    def _remove_from_ruffignore(self, exemption_id: str, path_pattern: str) -> None:
        """Remove entry from .ruffignore"""
        if not self.ruffignore_path.exists():
            return

        with open(self.ruffignore_path) as f:
            content = f.read()

        # Remove the exemption and its comment
        pattern = rf"# {exemption_id}:.*?\n{re.escape(path_pattern)}\n?"
        content = re.sub(pattern, "", content, flags=re.MULTILINE | re.DOTALL)

        with open(self.ruffignore_path, 'w') as f:
            f.write(content)

    def generate_report(self) -> str:
        """Generate exemption report"""
        db = self.load_exemptions_db()

        active_exemptions = [r for r in db["exemptions"].values() if r.get("status") == "active"]
        temporary_exemptions = [r for r in active_exemptions if r.get("temporary")]
        permanent_exemptions = [r for r in active_exemptions if not r.get("temporary")]

        report = f"""# Ruff Exemptions Report

**Generated**: {datetime.now().isoformat()}
**Total Active Exemptions**: {len(active_exemptions)}
**Temporary Exemptions**: {len(temporary_exemptions)}
**Permanent Exemptions**: {len(permanent_exemptions)}

## Summary by Reason

"""

        # Group by reason
        reasons = {}
        for record in active_exemptions:
            reason = record["reason"]
            if reason not in reasons:
                reasons[reason] = []
            reasons[reason].append(record)

        for reason, exemptions in sorted(reasons.items()):
            report += f"### {reason} ({len(exemptions)} files)\n\n"
            for exemption in exemptions:
                temp_note = " (TEMPORARY)" if exemption.get("temporary") else ""
                report += f"- `{exemption['path_pattern']}`{temp_note}\n"
            report += "\n"

        # Temporary exemptions needing review
        if temporary_exemptions:
            report += "## Temporary Exemptions Status\n\n"
            now = datetime.now()

            for record in temporary_exemptions:
                created = datetime.fromisoformat(record["created_date"])
                days_old = (now - created).days

                status = "🟢 Recent" if days_old < 7 else "🟡 Review Soon" if days_old < 30 else "🔴 Overdue"

                report += f"- `{record['path_pattern']}`: {status} ({days_old} days)\n"
                if record.get("assignee"):
                    report += f"  - Assignee: {record['assignee']}\n"

            report += "\n"

        return report


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Manage Ruff exemptions with tracking and documentation"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Add exemption
    add_parser = subparsers.add_parser("add", help="Add new exemption")
    add_parser.add_argument("path", help="Path pattern to exempt")
    add_parser.add_argument("reason", help="Reason for exemption")
    add_parser.add_argument("--rules", nargs="+", help="Specific rules to exempt")
    add_parser.add_argument("--temporary", action="store_true", help="Temporary exemption")
    add_parser.add_argument("--review-date", help="Date to review exemption (YYYY-MM-DD)")
    add_parser.add_argument("--assignee", help="Person responsible for eventual fix")

    # list exemptions
    list_parser = subparsers.add_parser("list", help="list exemptions")
    list_parser.add_argument("--all", action="store_true", help="Include inactive exemptions")

    # Review exemptions
    subparsers.add_parser("review", help="Review exemptions needing attention")

    # Remove exemption
    remove_parser = subparsers.add_parser("remove", help="Remove exemption")
    remove_parser.add_argument("exemption_id", help="ID of exemption to remove")

    # Generate report
    subparsers.add_parser("report", help="Generate exemption report")

    # Suggest exemptions
    subparsers.add_parser("suggest", help="Suggest files for exemption based on violation counts")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Initialize manager
    repo_root = Path.cwd()
    manager = RuffExemptionManager(repo_root)

    # Execute command
    if args.command == "add":
        return 0 if manager.add_exemption(
            args.path,
            args.reason,
            args.rules,
            args.temporary,
            args.review_date,
            args.assignee
        ) else 1

    if args.command == "list":
        manager.list_exemptions(show_inactive=args.all)
        return 0

    if args.command == "review":
        manager.review_exemptions()
        return 0

    if args.command == "remove":
        return 0 if manager.remove_exemption(args.exemption_id) else 1

    if args.command == "report":
        report = manager.generate_report()

        # Save report
        report_path = repo_root / "evidence" / f"ruff_exemptions_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        with open(report_path, 'w') as f:
            f.write(report)

        print(report)
        print(f"\n📋 Report saved to: {report_path}")
        return 0

    if args.command == "suggest":
        # Run triage to identify high-violation files
        print("🔍 Analyzing high-violation files for exemption candidates...")

        exit_code, stdout, stderr = run_command([
            "python", "scripts/triage_ruff_violations.py",
            "--output-dir", "evidence/exemption_suggestions"
        ])

        if exit_code == 0:
            print("✅ Analysis complete. Check evidence/exemption_suggestions/ for candidates")
        else:
            print(f"❌ Analysis failed: {stderr}")
            return 1

        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
