#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <release-tag> [release-name]"
  exit 1
fi

RELEASE_TAG=$1
RELEASE_NAME=${2:-$RELEASE_TAG}

function ensure_gh_cli() {
  if ! command -v gh >/dev/null 2>&1; then
    echo "error: GitHub CLI (gh) is required."
    exit 1
  fi
}

scripts/release_production.sh "$RELEASE_TAG" "$RELEASE_NAME"

REPORT_FILE="release_readiness_report_${RELEASE_TAG}.md"
python scripts/consolidated_release_report.py "$RELEASE_TAG" "$REPORT_FILE"

NOTES_FILE="release_notes_${RELEASE_TAG}.md"
python scripts/render_release_notes.py "$RELEASE_TAG" "$RELEASE_NAME" "$NOTES_FILE"

QA_BUNDLE=""
if [[ -f .last_release_qa_bundle ]]; then
  QA_BUNDLE=$(cat .last_release_qa_bundle)
fi
if [[ -z "$QA_BUNDLE" ]]; then
  QA_BUNDLE=$(ls production_qa_${RELEASE_TAG}_*.tar.gz 2>/dev/null | head -n1 || true)
fi
if [[ -z "$QA_BUNDLE" ]]; then
  echo "error: QA artifact bundle not found."
  exit 1
fi

ensure_gh_cli

gh release create "$RELEASE_TAG" \
  "$QA_BUNDLE" \
  "$REPORT_FILE" \
  "$NOTES_FILE" \
  --title "$RELEASE_NAME" \
  --notes-file "$NOTES_FILE" \
  --confirm

echo "Release $RELEASE_TAG published"
