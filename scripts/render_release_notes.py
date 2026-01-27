#!/usr/bin/env python3
import re
import subprocess
import sys
from pathlib import Path


def fill_template(template_path: Path, output_path: Path, context: dict):
    template = template_path.read_text()
    for key, value in context.items():
        template = template.replace(f"{{{{ {key} }}}}", str(value))
    output_path.write_text(template)
    print(f"Rendered release notes to {output_path}")

def main():
    if len(sys.argv) != 4:
        print("Usage: scripts/render_release_notes.py <tag> <release-name> <output>")
        sys.exit(1)

    tag = sys.argv[1]
    release_name = sys.argv[2]
    output_path = Path(sys.argv[3])
    template_path = Path("docs/release_notes_template.md")
    if not template_path.exists():
        raise FileNotFoundError(f"{template_path} missing")

    summary = Path("RELEASE_READINESS_SUMMARY.md").read_text()
    score_match = re.search(r"Readiness Score[:\s]+([0-9]+(?:\.[0-9]+)?)", summary, re.IGNORECASE)
    score = score_match.group(1) if score_match else "N/A"
    decision = "APPROVED" if "APPROVED FOR RELEASE" in summary.upper() else "PENDING"
    readiness_line = next((line for line in summary.splitlines() if "Readiness" in line), "")
    try:
        commit_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except subprocess.CalledProcessError:
        commit_sha = "unknown"

    context = {
        "release_tag": tag,
        "release_name": release_name,
        "readiness_score": score,
        "readiness_decision": decision,
        "commit_sha": commit_sha,
        "qa_bundle": Path(".last_release_qa_bundle").read_text().strip() if Path(".last_release_qa_bundle").exists() else "N/A",
        "ready_summary_line": readiness_line.strip()
    }

    fill_template(template_path, output_path, context)

if __name__ == "__main__":
    main()
