#!/usr/bin/env python3
"""
Syntax Error Triage Script

Identifies and categorizes the 2,144 invalid syntax violations for immediate P0 remediation.
Generates actionable task assignments by module and creates GitHub-ready issue templates.
"""

import json
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path


def run_command(cmd: list[str]) -> tuple[int, str, str]:
    """Run shell command and return exit code, stdout, stderr"""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        return result.returncode, result.stdout, result.stderr
    except Exception as e:
        return 1, "", str(e)


def get_ruff_command() -> str:
    """Get appropriate Ruff command"""
    if run_command(["ruff", "--version"])[0] == 0:
        return "ruff"
    return ".venv/bin/ruff"


def get_syntax_error_details() -> list[dict]:
    """Get detailed syntax error information"""
    ruff_cmd = get_ruff_command()

    # Get JSON output for all violations
    exit_code, stdout, stderr = run_command([
        ruff_cmd, "check", ".", "--exclude", "signal_service_legacy",
        "--output-format", "json"
    ])

    if exit_code != 0 and not stdout:
        print(f"❌ Error getting Ruff output: {stderr}")
        return []

    try:
        all_violations = json.loads(stdout) if stdout else []
    except json.JSONDecodeError:
        print("❌ Could not parse JSON output")
        return []

    # Filter for syntax-related issues
    syntax_violations = []

    for violation in all_violations:
        # Look for violations that might be syntax errors
        code = violation.get("code", "")
        message = violation.get("message", "").lower()

        # Common syntax error indicators
        syntax_indicators = [
            "syntax error",
            "invalid syntax",
            "unexpected token",
            "unterminated",
            "indentation",
            "unexpected indent",
            "expected",
            "missing",
            "unexpected eof",
            "invalid character"
        ]

        # Check if this looks like a syntax error
        is_syntax_error = (
            not code or  # Empty code often indicates syntax error
            code == "E999" or  # Direct syntax error (deprecated but might appear)
            any(indicator in message for indicator in syntax_indicators)
        )

        if is_syntax_error:
            syntax_violations.append(violation)

    return syntax_violations


def categorize_syntax_errors(syntax_violations: list[dict]) -> dict:
    """Categorize syntax errors by module and type"""

    categories = {
        "by_module": defaultdict(list),
        "by_error_type": defaultdict(list),
        "by_file": defaultdict(list),
        "summary": {
            "total_files": 0,
            "total_errors": len(syntax_violations),
            "modules_affected": set()
        }
    }

    files_with_errors = set()

    for violation in syntax_violations:
        filename = violation.get("filename", "unknown")
        message = violation.get("message", "")

        # Extract module from filename
        path_obj = Path(filename)
        if len(path_obj.parts) > 1:
            module = path_obj.parts[0]
            if len(path_obj.parts) > 2 and module in ['app', 'tests', 'scripts']:
                module = f"{path_obj.parts[0]}/{path_obj.parts[1]}"
        else:
            module = "root"

        # Add to categories
        categories["by_module"][module].append(violation)
        categories["by_file"][filename].append(violation)

        # Categorize by error type
        error_type = categorize_error_message(message)
        categories["by_error_type"][error_type].append(violation)

        files_with_errors.add(filename)
        categories["summary"]["modules_affected"].add(module)

    categories["summary"]["total_files"] = len(files_with_errors)
    categories["summary"]["modules_affected"] = list(categories["summary"]["modules_affected"])

    return categories


def categorize_error_message(message: str) -> str:
    """Categorize error message into common types"""
    message_lower = message.lower()

    if "indentation" in message_lower or "indent" in message_lower:
        return "indentation_error"
    if "unterminated" in message_lower:
        return "unterminated_string"
    if "expected" in message_lower and (":" in message_lower or "(" in message_lower):
        return "missing_syntax"
    if "unexpected" in message_lower:
        return "unexpected_token"
    if "eof" in message_lower:
        return "unexpected_eof"
    if "invalid character" in message_lower:
        return "invalid_character"
    if not message.strip():
        return "parsing_error"
    return "other_syntax"


def generate_fix_assignments(categories: dict) -> str:
    """Generate actionable fix assignments by module"""

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    report = f"""# 🚨 P0 CRITICAL: Syntax Error Fix Assignments

**Generated:** {timestamp}
**Total Syntax Errors:** {categories['summary']['total_errors']:,}
**Files Affected:** {categories['summary']['total_files']:,}
**Modules Affected:** {len(categories['summary']['modules_affected'])}

## Executive Summary

**CRITICAL BLOCKER:** {categories['summary']['total_errors']:,} syntax errors are blocking all CI merges. These are actual code problems requiring immediate manual fix - they cannot be auto-resolved.

## Module Assignments

"""

    # Sort modules by error count
    module_errors = [(module, len(errors)) for module, errors in categories["by_module"].items()]
    module_errors.sort(key=lambda x: x[1], reverse=True)

    for module, error_count in module_errors:
        module_violations = categories["by_module"][module]

        # Get unique files in this module
        module_files = {v.get("filename", "") for v in module_violations}

        report += f"""### 🔥 {module} ({error_count:,} errors, {len(module_files)} files)

**Assignee:** [TBD - Assign team lead for {module}]
**Priority:** P0 - IMMEDIATE
**Deadline:** Within 48 hours

#### Files requiring fixes:
"""

        # Group by file within module
        file_errors = defaultdict(int)
        for violation in module_violations:
            file_errors[violation.get("filename", "")] += 1

        # Show top error files
        sorted_files = sorted(file_errors.items(), key=lambda x: x[1], reverse=True)
        for filename, count in sorted_files[:10]:  # Top 10 files
            relative_path = str(Path(filename).relative_to(Path.cwd())) if filename else "unknown"
            report += f"- `{relative_path}`: {count} errors\n"

        if len(sorted_files) > 10:
            remaining_files = len(sorted_files) - 10
            remaining_errors = sum(count for _, count in sorted_files[10:])
            report += f"- *{remaining_files} more files*: {remaining_errors} errors\n"

        report += f"""
#### Commands to identify issues:
```bash
# Check all syntax errors in {module}
ruff check {module}/ --exclude signal_service_legacy

# Get detailed output for specific files
python -m py_compile {module}/[filename].py
```

#### Acceptance criteria:
- [ ] All syntax errors resolved in {module}
- [ ] Files can be imported without Python syntax errors
- [ ] Ruff check passes for {module}/
- [ ] CI pipeline can parse all files

---

"""

    return report


def generate_error_type_analysis(categories: dict) -> str:
    """Generate analysis by error type"""

    report = """## Error Type Analysis

Understanding the types of syntax errors helps prioritize fixing approach:

"""

    error_type_counts = [(error_type, len(errors)) for error_type, errors in categories["by_error_type"].items()]
    error_type_counts.sort(key=lambda x: x[1], reverse=True)

    for error_type, count in error_type_counts:
        percentage = (count / categories["summary"]["total_errors"]) * 100

        # Provide fix guidance based on error type
        guidance = get_fix_guidance(error_type)

        report += f"""### {error_type.replace('_', ' ').title()} ({count:,} errors - {percentage:.1f}%)

{guidance}

**Sample files with this error type:**
"""

        # Show sample files
        sample_errors = categories["by_error_type"][error_type][:3]
        for error in sample_errors:
            filename = error.get("filename", "unknown")
            relative_path = str(Path(filename).relative_to(Path.cwd())) if filename else "unknown"
            line = error.get("location", {}).get("row", "?")
            message = error.get("message", "No message")
            report += f"- `{relative_path}:{line}`: {message}\n"

        report += "\n"

    return report


def get_fix_guidance(error_type: str) -> str:
    """Get specific fix guidance for error type"""
    guidance_map = {
        "indentation_error": "**Fix approach:** Check for mixed tabs/spaces, incorrect indentation levels, missing indentation after colons.",
        "unterminated_string": "**Fix approach:** Find and close unterminated strings, fix quote mismatches, escape characters properly.",
        "missing_syntax": "**Fix approach:** Add missing colons after if/for/def statements, close parentheses and brackets.",
        "unexpected_token": "**Fix approach:** Remove invalid characters, fix operator spacing, check for typos in keywords.",
        "unexpected_eof": "**Fix approach:** Close open parentheses/brackets, complete incomplete statements.",
        "invalid_character": "**Fix approach:** Remove or escape invalid Unicode characters, fix encoding issues.",
        "parsing_error": "**Fix approach:** Use `python -m py_compile filename.py` to get detailed Python error messages.",
        "other_syntax": "**Fix approach:** Run individual files through Python parser to identify specific issues."
    }

    return guidance_map.get(error_type, "**Fix approach:** Manual review required - run file through Python parser.")


def generate_github_issues(categories: dict) -> list[dict]:
    """Generate GitHub issue templates for major modules"""

    issues = []

    # Create issues for modules with >100 errors
    major_modules = [(module, errors) for module, errors in categories["by_module"].items()
                     if len(errors) > 100]
    major_modules.sort(key=lambda x: len(x[1]), reverse=True)

    for module, errors in major_modules[:5]:  # Top 5 modules
        error_count = len(errors)
        files_affected = len({e.get("filename", "") for e in errors})

        issue = {
            "title": f"🚨 P0: Fix {error_count} syntax errors in {module}/",
            "body": f"""## 🚨 CRITICAL SYNTAX ERRORS - BLOCKS CI

**Module:** {module}/
**Errors:** {error_count:,}
**Files affected:** {files_affected}
**Priority:** P0 - IMMEDIATE (Blocks all merges)

### Impact
These syntax errors prevent the CI pipeline from processing files in `{module}/`. All pull requests are currently blocked until these are resolved.

### Identification Commands
```bash
# Check syntax errors in this module
ruff check {module}/ --exclude signal_service_legacy

# Test individual files
python -m py_compile {module}/[filename].py

# Get detailed Python errors
python -c "import ast; ast.parse(open('{module}/[filename].py').read())"
```

### Top Error Files
""",
            "labels": ["P0", "critical", "syntax-error", f"module-{module.replace('/', '-')}"],
            "assignees": []
        }

        # Add file list to issue body
        file_errors = defaultdict(int)
        for error in errors:
            file_errors[error.get("filename", "")] += 1

        sorted_files = sorted(file_errors.items(), key=lambda x: x[1], reverse=True)[:10]
        for filename, count in sorted_files:
            relative_path = str(Path(filename).relative_to(Path.cwd())) if filename else "unknown"
            issue["body"] += f"\n- [ ] `{relative_path}`: {count} errors"

        issue["body"] += f"""

### Acceptance Criteria
- [ ] All files in `{module}/` pass `python -m py_compile`
- [ ] `ruff check {module}/` reports 0 syntax errors
- [ ] CI pipeline can parse all files in module
- [ ] All tests in module can be imported

### Deadline
**48 hours** - This is blocking all development

---
**Auto-generated by syntax error triage system**
"""

        issues.append(issue)

    return issues


def main():
    """Main triage execution"""
    print("🚨 Starting syntax error triage...")

    # Get syntax error details
    print("📊 Analyzing syntax violations...")
    syntax_violations = get_syntax_error_details()

    if not syntax_violations:
        print("✅ No syntax violations found!")
        return 0

    print(f"📋 Found {len(syntax_violations):,} syntax-related violations")

    # Categorize errors
    print("🏗️ Categorizing by module and error type...")
    categories = categorize_syntax_errors(syntax_violations)

    # Generate outputs
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    evidence_dir = Path("evidence/syntax_triage")
    evidence_dir.mkdir(parents=True, exist_ok=True)

    print("📋 Generating fix assignments...")
    fix_assignments = generate_fix_assignments(categories)

    print("🔍 Analyzing error types...")
    error_analysis = generate_error_type_analysis(categories)

    print("🎫 Creating GitHub issue templates...")
    github_issues = generate_github_issues(categories)

    # Save outputs
    assignments_file = evidence_dir / f"syntax_fix_assignments_{timestamp}.md"
    with open(assignments_file, 'w') as f:
        f.write(fix_assignments + "\n" + error_analysis)

    issues_file = evidence_dir / f"github_issues_{timestamp}.json"
    with open(issues_file, 'w') as f:
        json.dump(github_issues, f, indent=2)

    # Raw data
    raw_data_file = evidence_dir / f"syntax_errors_raw_{timestamp}.json"
    with open(raw_data_file, 'w') as f:
        json.dump({
            "timestamp": timestamp,
            "syntax_violations": syntax_violations,
            "categories": {
                "by_module": {k: len(v) for k, v in categories["by_module"].items()},
                "by_error_type": {k: len(v) for k, v in categories["by_error_type"].items()},
                "summary": categories["summary"]
            }
        }, f, indent=2, default=str)

    # Summary
    print(f"""
✅ Syntax error triage complete!

📊 **Critical findings:**
- Total syntax errors: {categories['summary']['total_errors']:,}
- Files affected: {categories['summary']['total_files']:,}
- Modules affected: {len(categories['summary']['modules_affected'])}

📁 **Generated outputs:**
- Fix assignments: {assignments_file}
- GitHub issues: {issues_file}
- Raw data: {raw_data_file}

🚨 **IMMEDIATE ACTION REQUIRED:**
Top modules needing fixes:
""")

    # Show top modules
    module_errors = [(module, len(errors)) for module, errors in categories["by_module"].items()]
    module_errors.sort(key=lambda x: x[1], reverse=True)

    for module, error_count in module_errors[:5]:
        files_count = len({e.get("filename", "") for e in categories["by_module"][module]})
        print(f"  🔥 {module}: {error_count:,} errors in {files_count} files")

    print(f"""
💡 **Next steps:**
1. Assign modules to team leads using {assignments_file}
2. Create GitHub issues from {issues_file}
3. Start with highest error count modules
4. Use validation script to track progress

⚠️ **REMINDER:** These block ALL CI merges until resolved!
""")

    return 0


if __name__ == "__main__":
    sys.exit(main())
