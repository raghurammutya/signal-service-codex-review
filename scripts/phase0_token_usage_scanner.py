#!/usr/bin/env python3
"""
Phase 0 Token Usage Scanner

Automated scanning tool to inventory all remaining instrument_token usage
across the codebase and generate migration priority reports.
"""

import ast
import json
import os
import re
import sqlite3
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple


@dataclass
class TokenUsageFindings:
    """Structured findings from token usage scan"""
    file_path: str
    line_number: int
    usage_type: str  # api_parameter, database_column, cache_key, business_logic, broker_integration
    code_snippet: str
    severity: str    # critical, high, medium, low
    migration_effort: str  # 1-5 scale
    context: str

class TokenUsageScanner:
    """Comprehensive scanner for instrument_token usage patterns"""

    def __init__(self, codebase_root: str):
        self.codebase_root = Path(codebase_root)
        self.findings: list[TokenUsageFindings] = []

        # Token patterns to detect
        self.token_patterns = {
            'direct_token_usage': [
                r'instrument_token\s*[=:]\s*',
                r'\.token\b(?!\w)',
                r'token_id\s*[=:]',
                r'broker_token\s*[=:]',
                r'ticker_token\s*[=:]'
            ],
            'api_parameters': [
                r'def\s+\w+\([^)]*instrument_token',
                r'@app\.route.*instrument_token',
                r'request\.get\([\'"]instrument_token',
                r'request\.json\[[\'"]instrument_token'
            ],
            'database_operations': [
                r'SELECT.*instrument_token',
                r'INSERT.*instrument_token',
                r'UPDATE.*instrument_token',
                r'WHERE.*instrument_token',
                r'ORDER BY.*instrument_token',
                r'GROUP BY.*instrument_token'
            ],
            'cache_operations': [
                r'cache\.get\([\'"].*token',
                r'redis\.get\([\'"].*token',
                r'cache_key.*token',
                r'key_prefix.*token'
            ],
            'broker_integration': [
                r'broker.*\..*token',
                r'client\..*token',
                r'api_call.*token',
                r'ticker.*token'
            ]
        }

        # File patterns to include/exclude
        self.include_patterns = [
            '*.py', '*.sql', '*.yml', '*.yaml', '*.md', '*.json'
        ]
        self.exclude_patterns = [
            '__pycache__', '.git', 'node_modules', '*.pyc', 'venv', '.venv'
        ]

    def scan_codebase(self) -> dict[str, Any]:
        """Execute comprehensive codebase scan"""
        print("🔍 Starting comprehensive token usage scan...")

        # Scan all relevant files
        files_scanned = 0
        for file_path in self._get_files_to_scan():
            try:
                self._scan_file(file_path)
                files_scanned += 1
                if files_scanned % 100 == 0:
                    print(f"   📄 Scanned {files_scanned} files...")
            except Exception as e:
                print(f"   ⚠️  Error scanning {file_path}: {e}")

        print(f"✅ Scan complete: {files_scanned} files analyzed")

        # Generate analysis report
        return self._generate_analysis_report()

    def _get_files_to_scan(self) -> list[Path]:
        """Get list of files to scan based on include/exclude patterns"""
        files = []

        for include_pattern in self.include_patterns:
            for file_path in self.codebase_root.rglob(include_pattern):
                if self._should_include_file(file_path):
                    files.append(file_path)

        return sorted(files)

    def _should_include_file(self, file_path: Path) -> bool:
        """Check if file should be included in scan"""
        file_str = str(file_path)

        # Check exclude patterns
        for exclude_pattern in self.exclude_patterns:
            if exclude_pattern in file_str:
                return False

        # Skip binary files
        try:
            with open(file_path, encoding='utf-8') as f:
                f.read(1024)  # Test if file is readable as text
            return True
        except (UnicodeDecodeError, PermissionError):
            return False

    def _scan_file(self, file_path: Path):
        """Scan individual file for token usage patterns"""
        try:
            with open(file_path, encoding='utf-8') as f:
                content = f.read()
        except Exception:
            return

        lines = content.split('\n')

        for usage_type, patterns in self.token_patterns.items():
            for pattern in patterns:
                for match in re.finditer(pattern, content, re.IGNORECASE | re.MULTILINE):
                    line_num = content[:match.start()].count('\n') + 1

                    # Get context around the match
                    start_line = max(0, line_num - 3)
                    end_line = min(len(lines), line_num + 2)
                    context_lines = lines[start_line:end_line]

                    finding = TokenUsageFindings(
                        file_path=str(file_path.relative_to(self.codebase_root)),
                        line_number=line_num,
                        usage_type=usage_type,
                        code_snippet=lines[line_num - 1].strip() if line_num <= len(lines) else "",
                        severity=self._assess_severity(usage_type, match.group()),
                        migration_effort=self._assess_migration_effort(usage_type, file_path),
                        context='\n'.join(context_lines)
                    )

                    self.findings.append(finding)

    def _assess_severity(self, usage_type: str, match_text: str) -> str:
        """Assess severity of token usage finding"""
        if usage_type == 'api_parameters':
            return 'critical'  # Breaking API changes required
        if usage_type == 'database_operations':
            return 'high'      # Data migration required
        if usage_type == 'broker_integration':
            return 'medium'    # Internal logic changes
        return 'low'       # Cache keys, etc.

    def _assess_migration_effort(self, usage_type: str, file_path: Path) -> str:
        """Assess migration effort on 1-5 scale"""
        # Core services require more effort
        if 'order_service' in str(file_path):
            return '5'
        if 'algo_engine' in str(file_path):
            return '4'
        if any(service in str(file_path) for service in ['market_data', 'subscription']):
            return '3'
        return '2'

    def _generate_analysis_report(self) -> dict[str, Any]:
        """Generate comprehensive analysis report"""

        # Group findings by various dimensions
        by_severity = self._group_by('severity')
        by_usage_type = self._group_by('usage_type')
        by_service = self._group_by_service()

        # Calculate migration priorities
        migration_priorities = self._calculate_migration_priorities()

        # Generate summary statistics
        summary_stats = {
            'total_findings': len(self.findings),
            'files_affected': len({f.file_path for f in self.findings}),
            'critical_issues': len([f for f in self.findings if f.severity == 'critical']),
            'high_priority_issues': len([f for f in self.findings if f.severity in ['critical', 'high']]),
            'services_requiring_migration': len({self._extract_service(f.file_path) for f in self.findings})
        }

        return {
            'scan_timestamp': datetime.now().isoformat(),
            'summary_statistics': summary_stats,
            'findings_by_severity': by_severity,
            'findings_by_usage_type': by_usage_type,
            'findings_by_service': by_service,
            'migration_priorities': migration_priorities,
            'detailed_findings': [asdict(f) for f in self.findings]
        }

    def _group_by(self, field: str) -> dict[str, int]:
        """Group findings by specified field"""
        groups = {}
        for finding in self.findings:
            value = getattr(finding, field)
            groups[value] = groups.get(value, 0) + 1
        return groups

    def _group_by_service(self) -> dict[str, int]:
        """Group findings by service"""
        services = {}
        for finding in self.findings:
            service = self._extract_service(finding.file_path)
            services[service] = services.get(service, 0) + 1
        return services

    def _extract_service(self, file_path: str) -> str:
        """Extract service name from file path"""
        path_parts = file_path.split('/')

        # Look for service indicators
        service_indicators = [
            'order_service', 'market_data', 'algo_engine', 'subscription',
            'notification', 'risk', 'position', 'instrument_registry'
        ]

        for part in path_parts:
            for indicator in service_indicators:
                if indicator in part.lower():
                    return indicator

        return 'unknown'

    def _calculate_migration_priorities(self) -> list[dict[str, Any]]:
        """Calculate migration priorities for services"""
        service_priorities = {}

        for finding in self.findings:
            service = self._extract_service(finding.file_path)
            if service not in service_priorities:
                service_priorities[service] = {
                    'service': service,
                    'total_findings': 0,
                    'critical_findings': 0,
                    'high_findings': 0,
                    'estimated_effort_weeks': 0,
                    'migration_priority': 0
                }

            priority = service_priorities[service]
            priority['total_findings'] += 1

            if finding.severity == 'critical':
                priority['critical_findings'] += 1
            elif finding.severity == 'high':
                priority['high_findings'] += 1

            priority['estimated_effort_weeks'] += int(finding.migration_effort) * 0.1

        # Calculate priority scores
        for service, priority in service_priorities.items():
            # Priority score based on critical issues, total findings, and effort
            score = (
                priority['critical_findings'] * 10 +
                priority['high_findings'] * 5 +
                priority['total_findings'] * 1
            ) / max(priority['estimated_effort_weeks'], 0.5)

            priority['migration_priority'] = round(score, 2)

        # Sort by priority score (highest first)
        return sorted(service_priorities.values(),
                     key=lambda x: x['migration_priority'], reverse=True)

def generate_token_inventory_report(codebase_root: str, output_file: str = None) -> str:
    """Generate comprehensive token usage inventory report"""
    scanner = TokenUsageScanner(codebase_root)
    results = scanner.scan_codebase()

    # Generate output filename if not provided
    if not output_file:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = f'token_usage_inventory_{timestamp}.json'

    # Write results to file
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)

    # Generate summary report
    summary = f"""
🔍 TOKEN USAGE INVENTORY REPORT
{'='*50}

📊 SUMMARY STATISTICS:
   • Total token usage findings: {results['summary_statistics']['total_findings']}
   • Files affected: {results['summary_statistics']['files_affected']}
   • Critical issues: {results['summary_statistics']['critical_issues']}
   • High priority issues: {results['summary_statistics']['high_priority_issues']}
   • Services requiring migration: {results['summary_statistics']['services_requiring_migration']}

🎯 TOP MIGRATION PRIORITIES:
"""

    for i, priority in enumerate(results['migration_priorities'][:5], 1):
        summary += f"   {i}. {priority['service']}: {priority['total_findings']} findings "
        summary += f"({priority['critical_findings']} critical, score: {priority['migration_priority']})\n"

    summary += """
📋 FINDINGS BY SEVERITY:
"""
    for severity, count in sorted(results['findings_by_severity'].items()):
        summary += f"   • {severity}: {count} findings\n"

    summary += """
🔧 FINDINGS BY TYPE:
"""
    for usage_type, count in sorted(results['findings_by_usage_type'].items()):
        summary += f"   • {usage_type}: {count} findings\n"

    summary += f"""
📁 Detailed findings saved to: {output_file}
"""

    print(summary)
    return output_file

# CLI interface
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Scan codebase for instrument_token usage')
    parser.add_argument('--codebase', '-c', default='.',
                       help='Root directory of codebase to scan')
    parser.add_argument('--output', '-o',
                       help='Output file for detailed results (JSON)')
    parser.add_argument('--summary-only', '-s', action='store_true',
                       help='Show only summary statistics')

    args = parser.parse_args()

    print("🚀 Starting Phase 0 Token Usage Audit...")
    output_file = generate_token_inventory_report(args.codebase, args.output)
    print(f"✅ Token usage inventory complete: {output_file}")
