#!/usr/bin/env python3

import subprocess


def test_ruff_call():
    """Debug Ruff subprocess call"""
    result = subprocess.run(
        ["python3", "-m", "ruff", "check", ".", "--statistics"],
        capture_output=True,
        text=True,
        cwd="/home/stocksadmin/signal-service-codex-review"
    )

    print(f"Return code: {result.returncode}")
    print(f"STDOUT length: {len(result.stdout)}")
    print(f"STDERR length: {len(result.stderr)}")
    print("\nSTDOUT content:")
    print(result.stdout[:500])
    print("\nSTDERR content:")
    print(result.stderr[:500])

    # Parse stderr like the automation script
    output_lines = result.stderr.strip().split('\n')
    total_violations = 0
    auto_fixable = 0

    for line in output_lines:
        print(f"Processing line: '{line}'")
        if line and not line.startswith('[*]'):
            parts = line.split('\t')
            if len(parts) >= 2:
                try:
                    count = int(parts[0].strip())
                    total_violations += count

                    # Check if auto-fixable
                    if len(parts) >= 3 and '[*]' in parts[2]:
                        auto_fixable += count
                        print(f"  -> Auto-fixable: {count}")
                except ValueError as e:
                    print(f"  -> Parse error: {e}")
                    continue

    print(f"\nTotal violations: {total_violations}")
    print(f"Auto-fixable: {auto_fixable}")

if __name__ == "__main__":
    test_ruff_call()
