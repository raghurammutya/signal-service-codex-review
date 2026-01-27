#!/usr/bin/env python3
import re
import sys
from pathlib import Path


def parse_readiness(summary_path: Path):
    text = summary_path.read_text()
    score = None
    decision = "UNKNOWN"
    match = re.search(r"Readiness Score[:\s]+([0-9]+(?:\.[0-9]+)?)", text, re.IGNORECASE)
    if match:
        score = float(match.group(1))
    upper = text.upper()
    if "APPROVED FOR RELEASE" in upper:
        decision = "APPROVED"
    elif "CONDITIONAL" in upper:
        decision = "CONDITIONAL"
    elif "NOT READY" in upper or "BLOCKED" in upper:
        decision = "BLOCKED"
    return score, decision, text

def list_artifacts(artifact_dir: Path):
    if not artifact_dir.exists():
        return []
    artifacts = []
    for path in sorted(artifact_dir.rglob("*")):
        if path.is_file():
            artifacts.append(str(path.relative_to(Path.cwd())))
    return artifacts

def main(tag: str, report_path: Path):
    summary_path = Path("RELEASE_READINESS_SUMMARY.md")
    if not summary_path.exists():
        print("Error: RELEASE_READINESS_SUMMARY.md missing", file=sys.stderr)
        sys.exit(1)

    score, decision, summary_text = parse_readiness(summary_path)
    artifact_list = list_artifacts(Path("coverage_reports"))
    contract_matrix = Path("docs/contract_matrix.md")
    if contract_matrix.exists():
        artifact_list.append(str(contract_matrix))

    qa_bundle_path = Path(".last_release_qa_bundle")
    qa_bundle = qa_bundle_path.read_text().strip() if qa_bundle_path.exists() else "N/A"

    report_lines = [
        f"# Release Readiness Report - {tag}",
        "",
        f"- Score: {score if score is not None else 'N/A'}",
        f"- Decision: {decision}",
        f"- QA bundle: {qa_bundle}",
        "",
        "## Release Summary (first 20 lines)",
    ]

    report_lines.extend(summary_text.strip().splitlines()[:20])
    report_lines.append("")
    report_lines.append("## Artifact Manifest")
    if artifact_list:
        report_lines.extend(f"- {entry}" for entry in artifact_list)
    else:
        report_lines.append("- (no artifacts found)")

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(report_lines))
    print(f"Consolidated release report written to {report_path}")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: scripts/consolidated_release_report.py <release-tag> <output-path>")
        sys.exit(1)
    main(sys.argv[1], Path(sys.argv[2]))
