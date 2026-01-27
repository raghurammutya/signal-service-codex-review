#!/usr/bin/env python3
"""
Database Contract Validation Script

Validates that the database implementation matches the documented contracts
in DATABASE_CONTRACTS.md. Ensures downstream service compatibility.
"""
import json
import logging
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DatabaseContractValidator:
    """Validates database contracts for downstream service compatibility."""

    def __init__(self, project_root: str = "."):
        self.project_root = Path(project_root)
        self.validation_results = {
            "timestamp": datetime.now().isoformat(),
            "contract_validations": {},
            "schema_validations": {},
            "query_validations": {},
            "performance_validations": {},
            "overall_compliance": False
        }

        # Contract specifications from DATABASE_CONTRACTS.md
        self.expected_tables = {
            "signal_greeks": {
                "required_columns": [
                    "id", "signal_id", "instrument_key", "timestamp",
                    "delta", "gamma", "theta", "vega", "rho",
                    "implied_volatility", "theoretical_value",
                    "underlying_price", "strike_price", "time_to_expiry",
                    "created_at"
                ],
                "required_indexes": [
                    "idx_signal_greeks_instrument_timestamp",
                    "idx_signal_greeks_signal_id"
                ]
            },
            "signal_indicators": {
                "required_columns": [
                    "id", "signal_id", "instrument_key", "timestamp",
                    "indicator_name", "parameters", "values", "created_at"
                ],
                "required_indexes": [
                    "idx_signal_indicators_instrument_indicator_timestamp",
                    "idx_signal_indicators_signal_id",
                    "idx_signal_indicators_parameters"
                ]
            },
            "signal_moneyness_greeks": {
                "required_columns": [
                    "id", "underlying_symbol", "moneyness_level", "expiry_date",
                    "timestamp", "spot_price", "all_delta", "all_gamma",
                    "calls_count", "puts_count", "strike_count", "created_at"
                ],
                "required_indexes": [
                    "idx_moneyness_greeks_symbol_level_timestamp"
                ]
            }
        }

        # Contract query patterns that must be supported
        self.contract_queries = {
            "latest_greeks": {
                "pattern": r"SELECT.*FROM signal_greeks.*WHERE instrument_key.*ORDER BY timestamp DESC.*LIMIT 1",
                "file": "app/repositories/signal_repository.py",
                "method": "get_latest_greeks"
            },
            "historical_aggregation": {
                "pattern": r"time_bucket.*timestamp.*GROUP BY.*instrument_key",
                "file": "app/repositories/signal_repository.py",
                "method": "get_historical_greeks"
            },
            "latest_indicator": {
                "pattern": r"SELECT.*FROM signal_indicators.*WHERE instrument_key.*AND indicator_name.*ORDER BY timestamp DESC",
                "file": "app/repositories/signal_repository.py",
                "method": "get_latest_indicator"
            }
        }

    def validate_contracts(self, strict_mode: bool = False) -> dict[str, Any]:
        """Run comprehensive contract validation."""
        logger.info("🔍 Starting Database Contract Validation")
        logger.info("=" * 60)

        # 1. Schema Contract Validation
        self._validate_schema_contracts()

        # 2. Query Contract Validation
        self._validate_query_contracts()

        # 3. Performance Contract Validation
        self._validate_performance_contracts()

        # 4. Data Format Contract Validation
        self._validate_data_format_contracts()

        # Calculate overall compliance
        self._calculate_compliance_score()

        # Generate compliance report
        self._generate_contract_compliance_report()

        if strict_mode and not self.validation_results["overall_compliance"]:
            raise Exception("Database contract validation failed in strict mode")

        return self.validation_results

    def _validate_schema_contracts(self):
        """Validate database schema matches contract specifications."""
        logger.info("Validating schema contracts...")

        schema_results = {
            "table_validations": {},
            "missing_tables": [],
            "missing_columns": [],
            "missing_indexes": [],
            "compliance_score": 0.0
        }

        # Check repository file for schema usage patterns
        repository_file = self.project_root / "app/repositories/signal_repository.py"

        if repository_file.exists():
            with open(repository_file) as f:
                content = f.read()

            # Validate each expected table
            for table_name, table_spec in self.expected_tables.items():
                table_validation = {
                    "table_found": False,
                    "columns_found": [],
                    "missing_columns": [],
                    "query_patterns_found": 0,
                    "compliance_score": 0.0
                }

                # Check if table is referenced
                table_pattern = f"(FROM|INSERT INTO|UPDATE) {table_name}"
                table_matches = re.findall(table_pattern, content, re.IGNORECASE)
                table_validation["table_found"] = len(table_matches) > 0

                if table_validation["table_found"]:
                    # Check for required columns in queries
                    for column in table_spec["required_columns"]:
                        column_pattern = f"\\b{column}\\b"
                        if re.search(column_pattern, content, re.IGNORECASE):
                            table_validation["columns_found"].append(column)
                        else:
                            table_validation["missing_columns"].append(column)

                    # Count query patterns using this table
                    query_patterns = [
                        f"SELECT.*FROM {table_name}",
                        f"INSERT INTO {table_name}",
                        f"UPDATE {table_name}"
                    ]

                    for pattern in query_patterns:
                        matches = re.findall(pattern, content, re.IGNORECASE)
                        table_validation["query_patterns_found"] += len(matches)

                    # Calculate table compliance score
                    columns_score = len(table_validation["columns_found"]) / len(table_spec["required_columns"]) * 100
                    usage_score = min(100, table_validation["query_patterns_found"] * 25)  # Up to 4 patterns
                    table_validation["compliance_score"] = (columns_score * 0.7 + usage_score * 0.3)

                schema_results["table_validations"][table_name] = table_validation

                if not table_validation["table_found"]:
                    schema_results["missing_tables"].append(table_name)

                schema_results["missing_columns"].extend(table_validation["missing_columns"])

        # Calculate overall schema compliance
        if schema_results["table_validations"]:
            total_tables = len(self.expected_tables)
            compliant_tables = sum(
                1 for validation in schema_results["table_validations"].values()
                if validation["compliance_score"] >= 80
            )
            schema_results["compliance_score"] = (compliant_tables / total_tables) * 100

        self.validation_results["schema_validations"] = schema_results

    def _validate_query_contracts(self):
        """Validate query patterns match contract specifications."""
        logger.info("Validating query contracts...")

        query_results = {
            "query_validations": {},
            "missing_patterns": [],
            "compliance_score": 0.0
        }

        repository_file = self.project_root / "app/repositories/signal_repository.py"

        if repository_file.exists():
            with open(repository_file) as f:
                content = f.read()

            # Validate each contract query pattern
            for query_name, query_spec in self.contract_queries.items():
                query_validation = {
                    "pattern_found": False,
                    "method_exists": False,
                    "timescaledb_functions": False,
                    "parametrized_query": False,
                    "compliance_score": 0.0
                }

                # Check if query pattern exists
                pattern_matches = re.search(query_spec["pattern"], content, re.IGNORECASE | re.DOTALL)
                query_validation["pattern_found"] = pattern_matches is not None

                # Check if method exists
                method_pattern = f"def {query_spec['method']}\\("
                method_matches = re.search(method_pattern, content)
                query_validation["method_exists"] = method_matches is not None

                # Check for TimescaleDB-specific functions
                if "time_bucket" in query_spec["pattern"]:
                    timescale_matches = re.search(r"time_bucket\(", content)
                    query_validation["timescaledb_functions"] = timescale_matches is not None

                # Check for parametrized queries (security contract)
                if query_validation["pattern_found"]:
                    param_matches = re.findall(r"\$\d+", content)
                    query_validation["parametrized_query"] = len(param_matches) > 0

                # Calculate query compliance score
                score_components = []
                if query_validation["pattern_found"]:
                    score_components.append(40)  # Pattern found
                if query_validation["method_exists"]:
                    score_components.append(30)  # Method exists
                if query_validation["parametrized_query"]:
                    score_components.append(20)  # Security compliance
                if query_validation["timescaledb_functions"] or "time_bucket" not in query_spec["pattern"]:
                    score_components.append(10)  # TimescaleDB optimization

                query_validation["compliance_score"] = sum(score_components)

                query_results["query_validations"][query_name] = query_validation

                if not query_validation["pattern_found"]:
                    query_results["missing_patterns"].append(query_name)

        # Calculate overall query compliance
        if query_results["query_validations"]:
            total_queries = len(self.contract_queries)
            avg_score = sum(
                validation["compliance_score"]
                for validation in query_results["query_validations"].values()
            ) / total_queries
            query_results["compliance_score"] = avg_score

        self.validation_results["query_validations"] = query_results

    def _validate_performance_contracts(self):
        """Validate performance contract requirements."""
        logger.info("Validating performance contracts...")

        performance_results = {
            "connection_pool_config": {},
            "query_timeout_config": {},
            "index_optimization": {},
            "compliance_score": 0.0
        }

        # Check connection pool configuration
        database_file = self.project_root / "common/storage/database.py"
        if database_file.exists():
            with open(database_file) as f:
                content = f.read()

            # Validate connection pool settings
            pool_configs = {
                "min_size": re.search(r"min_size\s*=\s*(\d+)", content),
                "max_size": re.search(r"max_size\s*=\s*(\d+)", content),
                "command_timeout": re.search(r"command_timeout\s*=\s*(\d+)", content)
            }

            performance_results["connection_pool_config"] = {
                "min_size_found": pool_configs["min_size"] is not None,
                "max_size_found": pool_configs["max_size"] is not None,
                "timeout_found": pool_configs["command_timeout"] is not None,
                "values": {
                    "min_size": int(pool_configs["min_size"].group(1)) if pool_configs["min_size"] else None,
                    "max_size": int(pool_configs["max_size"].group(1)) if pool_configs["max_size"] else None,
                    "command_timeout": int(pool_configs["command_timeout"].group(1)) if pool_configs["command_timeout"] else None
                }
            }

            # Validate against contract requirements (2-10 pool size, 30s timeout)
            pool_config = performance_results["connection_pool_config"]
            pool_score = 0
            if pool_config["values"]["min_size"] == 2:
                pool_score += 25
            if pool_config["values"]["max_size"] == 10:
                pool_score += 25
            if pool_config["values"]["command_timeout"] == 30:
                pool_score += 25
            if all(pool_config[f"{k}_found"] for k in ["min_size", "max_size", "timeout"]):
                pool_score += 25

            performance_results["compliance_score"] = pool_score

        self.validation_results["performance_validations"] = performance_results

    def _validate_data_format_contracts(self):
        """Validate data format and validation contracts."""
        logger.info("Validating data format contracts...")

        format_results = {
            "instrument_key_format": False,
            "timestamp_format": False,
            "json_field_usage": False,
            "decimal_precision": False,
            "compliance_score": 0.0
        }

        repository_file = self.project_root / "app/repositories/signal_repository.py"

        if repository_file.exists():
            with open(repository_file) as f:
                content = f.read()

            # Check instrument_key format validation
            instrument_pattern = re.search(r"instrument_key", content, re.IGNORECASE)
            format_results["instrument_key_format"] = instrument_pattern is not None

            # Check timestamp handling
            timestamp_pattern = re.search(r"timestamp.*TIMESTAMPTZ|timestamp.*UTC", content, re.IGNORECASE)
            format_results["timestamp_format"] = timestamp_pattern is not None

            # Check JSON field usage
            json_pattern = re.search(r"json\\.dumps|json\\.loads|JSONB", content, re.IGNORECASE)
            format_results["json_field_usage"] = json_pattern is not None

            # Check decimal precision usage
            decimal_pattern = re.search(r"DECIMAL\\(\\d+,\\d+\\)", content, re.IGNORECASE)
            format_results["decimal_precision"] = decimal_pattern is not None

            # Calculate format compliance score
            format_checks = [
                format_results["instrument_key_format"],
                format_results["timestamp_format"],
                format_results["json_field_usage"],
                format_results["decimal_precision"]
            ]
            format_results["compliance_score"] = (sum(format_checks) / len(format_checks)) * 100

        self.validation_results["contract_validations"]["data_format"] = format_results

    def _calculate_compliance_score(self):
        """Calculate overall contract compliance score."""
        scores = []

        if "schema_validations" in self.validation_results:
            scores.append(self.validation_results["schema_validations"]["compliance_score"])

        if "query_validations" in self.validation_results:
            scores.append(self.validation_results["query_validations"]["compliance_score"])

        if "performance_validations" in self.validation_results:
            scores.append(self.validation_results["performance_validations"]["compliance_score"])

        if "contract_validations" in self.validation_results:
            data_format_score = self.validation_results["contract_validations"].get("data_format", {}).get("compliance_score", 0)
            scores.append(data_format_score)

        if scores:
            overall_score = sum(scores) / len(scores)
            self.validation_results["overall_compliance"] = overall_score >= 95.0
            self.validation_results["overall_score"] = overall_score
        else:
            self.validation_results["overall_compliance"] = False
            self.validation_results["overall_score"] = 0.0

    def _generate_contract_compliance_report(self):
        """Generate contract compliance report."""
        results = self.validation_results

        report_lines = [
            "# Database Contract Compliance Report",
            f"**Generated**: {results['timestamp']}",
            f"**Overall Compliance**: {'✅ PASSING' if results['overall_compliance'] else '❌ FAILING'}",
            f"**Compliance Score**: {results.get('overall_score', 0):.1f}%",
            "",
            "## Contract Validation Results",
            ""
        ]

        # Schema validation results
        if "schema_validations" in results:
            schema = results["schema_validations"]
            report_lines.extend([
                f"### Schema Contracts - {schema['compliance_score']:.1f}%",
                f"- Tables Validated: {len(schema['table_validations'])}",
                f"- Missing Tables: {len(schema['missing_tables'])}",
                f"- Missing Columns: {len(schema['missing_columns'])}",
                ""
            ])

            for table_name, validation in schema["table_validations"].items():
                status = "✅" if validation["compliance_score"] >= 80 else "❌"
                report_lines.append(
                    f"  {status} **{table_name}**: {validation['compliance_score']:.1f}% "
                    f"({len(validation['columns_found'])}/{len(self.expected_tables[table_name]['required_columns'])} columns)"
                )

        # Query validation results
        if "query_validations" in results:
            query = results["query_validations"]
            report_lines.extend([
                "",
                f"### Query Contracts - {query['compliance_score']:.1f}%",
                f"- Query Patterns Validated: {len(query['query_validations'])}",
                f"- Missing Patterns: {len(query['missing_patterns'])}",
                ""
            ])

            for query_name, validation in query["query_validations"].items():
                status = "✅" if validation["compliance_score"] >= 80 else "❌"
                report_lines.append(
                    f"  {status} **{query_name}**: {validation['compliance_score']:.1f}% "
                    f"({'Pattern✅' if validation['pattern_found'] else 'Pattern❌'}, "
                    f"{'Method✅' if validation['method_exists'] else 'Method❌'})"
                )

        # Performance validation results
        if "performance_validations" in results:
            perf = results["performance_validations"]
            report_lines.extend([
                "",
                f"### Performance Contracts - {perf['compliance_score']:.1f}%",
                ""
            ])

            pool_config = perf.get("connection_pool_config", {})
            if pool_config:
                values = pool_config.get("values", {})
                report_lines.extend([
                    "- Connection Pool Configuration:",
                    f"  - Min Size: {values.get('min_size', 'Not Found')} (Expected: 2)",
                    f"  - Max Size: {values.get('max_size', 'Not Found')} (Expected: 10)",
                    f"  - Timeout: {values.get('command_timeout', 'Not Found')}s (Expected: 30s)"
                ])

        # Recommendations
        if not results["overall_compliance"]:
            report_lines.extend([
                "",
                "## 🔧 Recommendations for Contract Compliance",
                ""
            ])

            if "schema_validations" in results and results["schema_validations"]["missing_tables"]:
                report_lines.append(f"- Add missing table references: {', '.join(results['schema_validations']['missing_tables'])}")

            if "query_validations" in results and results["query_validations"]["missing_patterns"]:
                report_lines.append(f"- Implement missing query patterns: {', '.join(results['query_validations']['missing_patterns'])}")

        # Save report
        reports_dir = self.project_root / "coverage_reports"
        reports_dir.mkdir(exist_ok=True)

        report_file = reports_dir / "database_contract_compliance_report.md"
        with open(report_file, 'w') as f:
            f.write("\\n".join(report_lines))

        logger.info(f"Contract compliance report saved: {report_file}")

def main():
    """Main function for database contract validation."""
    import argparse

    parser = argparse.ArgumentParser(description="Database Contract Validation")
    parser.add_argument("--project-root", default=".", help="Project root directory")
    parser.add_argument("--strict", action="store_true", help="Fail on any contract violations")
    parser.add_argument("--output-format", choices=["json", "text"], default="text", help="Output format")

    args = parser.parse_args()

    validator = DatabaseContractValidator(args.project_root)

    try:
        results = validator.validate_contracts(strict_mode=args.strict)

        if args.output_format == "json":
            print(json.dumps(results, indent=2))
        else:
            print("\\n" + "=" * 60)
            print("DATABASE CONTRACT VALIDATION SUMMARY")
            print("=" * 60)
            print(f"Overall Compliance: {'✅ PASSING' if results['overall_compliance'] else '❌ FAILING'}")
            print(f"Compliance Score: {results.get('overall_score', 0):.1f}%")

            if results["overall_compliance"]:
                print("\\n🎉 All database contracts are compliant!")
                print("✅ Schema contracts validated")
                print("✅ Query patterns validated")
                print("✅ Performance contracts validated")
                print("✅ Data format contracts validated")
                return 0
            print("\\n❌ Contract compliance issues found:")
            if "schema_validations" in results:
                schema = results["schema_validations"]
                if schema["missing_tables"]:
                    print(f"  - Missing tables: {', '.join(schema['missing_tables'])}")
                if schema["missing_columns"]:
                    print(f"  - Missing columns: {len(schema['missing_columns'])} total")

            if "query_validations" in results:
                query = results["query_validations"]
                if query["missing_patterns"]:
                    print(f"  - Missing query patterns: {', '.join(query['missing_patterns'])}")

            return 1 if args.strict else 0

    except Exception as e:
        logger.error(f"Contract validation failed: {str(e)}")
        return 1

if __name__ == "__main__":
    import sys
    sys.exit(main())
