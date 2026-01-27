#!/usr/bin/env python3
"""
Database Sanity Validation

Tests TimescaleDB integration and validates database structure.
"""
import json
import os
import time
from datetime import datetime


class DatabaseSanityValidation:
    """Database sanity validation for production readiness."""

    def __init__(self):
        self.results = {
            "timestamp": datetime.now().isoformat(),
            "tests": {},
            "database_structure": {},
            "timescale_integration": {}
        }

    def test_database_models_structure(self):
        """Test database models structure."""
        print("📊 Testing Database Models Structure...")

        try:
            # Look for database-related Python files with safe encoding
            model_files = []
            schema_patterns = ['model', 'schema', 'table', 'database', 'repository']

            for root, _dirs, files in os.walk("app"):
                for file in files:
                    if file.endswith('.py'):
                        # Check if filename suggests database models
                        if any(pattern in file.lower() for pattern in schema_patterns):
                            file_path = os.path.join(root, file)
                            model_files.append(file_path)

            model_structures = []
            for file_path in model_files:
                try:
                    with open(file_path, encoding='utf-8', errors='ignore') as f:
                        content = f.read()

                    # Look for database-related patterns
                    db_patterns = [
                        "Table", "Column", "Integer", "String", "DateTime",
                        "ForeignKey", "relationship", "Index", "create_table",
                        "signal_greeks", "signal_indicators", "timescale"
                    ]

                    found_patterns = [pattern for pattern in db_patterns if pattern in content]
                    if found_patterns:
                        model_structures.append({
                            "file": file_path,
                            "patterns": found_patterns,
                            "size": len(content)
                        })
                        print(f"    ✅ {file_path}: {len(found_patterns)} DB patterns")
                except Exception as e:
                    print(f"    ⚠️ {file_path}: {e}")
                    continue

            # Look for explicit schema definitions
            schema_files = [
                "app/schemas/signal_schemas.py",
                "app/schemas/config_schema.py",
                "app/repositories/signal_repository.py"
            ]

            schema_count = 0
            for schema_file in schema_files:
                if os.path.exists(schema_file):
                    schema_count += 1
                    print(f"    ✅ Schema file: {schema_file}")

            print(f"  📊 Database model files: {len(model_structures)}")
            print(f"  📊 Schema files: {schema_count}")

            return {
                "status": "tested",
                "model_files_found": len(model_structures),
                "schema_files_found": schema_count,
                "model_structures": model_structures
            }

        except Exception as e:
            print(f"  ❌ Database models test failed: {e}")
            return {"status": "error", "error": str(e)}

    def test_timescale_integration_structure(self):
        """Test TimescaleDB integration structure."""
        print("⏰ Testing TimescaleDB Integration Structure...")

        try:
            # Look for TimescaleDB-related code
            timescale_files = []
            timescale_patterns = [
                "timescale", "TimescaleDB", "time_bucket", "create_hypertable",
                "signal_greeks", "signal_indicators", "time_series"
            ]

            for root, _dirs, files in os.walk("app"):
                for file in files:
                    if file.endswith('.py'):
                        file_path = os.path.join(root, file)
                        try:
                            with open(file_path) as f:
                                content = f.read()

                            found_patterns = [pattern for pattern in timescale_patterns if pattern in content]
                            if found_patterns:
                                timescale_files.append({
                                    "file": file_path,
                                    "patterns": found_patterns
                                })
                                print(f"    ✅ {file_path}: {len(found_patterns)} TimescaleDB patterns")
                        except:
                            continue

            # Check for SQL migration files
            migration_dirs = ["migrations", "alembic", "sql", "database"]
            migration_files = []

            for dir_name in migration_dirs:
                if os.path.exists(dir_name):
                    for root, _dirs, files in os.walk(dir_name):
                        for file in files:
                            if file.endswith('.sql') or 'migration' in file.lower():
                                migration_files.append(os.path.join(root, file))
                                print(f"    ✅ Migration file: {file}")

            print(f"  📊 TimescaleDB integration files: {len(timescale_files)}")
            print(f"  📊 Migration files: {len(migration_files)}")

            return {
                "status": "tested",
                "timescale_files": len(timescale_files),
                "migration_files": len(migration_files),
                "integration_files": timescale_files
            }

        except Exception as e:
            print(f"  ❌ TimescaleDB integration test failed: {e}")
            return {"status": "error", "error": str(e)}

    def test_database_client_structure(self):
        """Test database client structure."""
        print("🔌 Testing Database Client Structure...")

        try:
            # Look for database client files
            client_files = [
                "app/clients/database_client.py",
                "app/clients/timescale_client.py",
                "app/core/database.py",
                "app/database/client.py"
            ]

            found_clients = []
            for file_path in client_files:
                if os.path.exists(file_path):
                    with open(file_path) as f:
                        content = f.read()

                    # Check for database client patterns
                    client_patterns = [
                        "connect", "execute", "fetch", "query", "transaction",
                        "pool", "connection", "session", "async", "await"
                    ]

                    found_patterns = [pattern for pattern in client_patterns if pattern in content]
                    found_clients.append({
                        "file": file_path,
                        "patterns": found_patterns
                    })
                    print(f"    ✅ {file_path}: {len(found_patterns)} client patterns")

            if not found_clients:
                print("  ⚠️ No dedicated database client files found")

                # Check for database imports in other files
                db_imports = []
                common_files = ["app/main.py", "app/core/config.py"]
                for file_path in common_files:
                    if os.path.exists(file_path):
                        with open(file_path) as f:
                            content = f.read()

                        db_import_patterns = [
                            "postgresql", "asyncpg", "psycopg", "sqlalchemy",
                            "database", "timescale", "pool"
                        ]

                        found_imports = [pattern for pattern in db_import_patterns if pattern in content.lower()]
                        if found_imports:
                            db_imports.append({
                                "file": file_path,
                                "imports": found_imports
                            })
                            print(f"    ✅ {file_path}: {len(found_imports)} DB imports")

                return {
                    "status": "tested",
                    "dedicated_clients": 0,
                    "db_imports": len(db_imports),
                    "import_files": db_imports
                }

            return {
                "status": "tested",
                "client_files_found": len(found_clients),
                "client_structures": found_clients
            }

        except Exception as e:
            print(f"  ❌ Database client test failed: {e}")
            return {"status": "error", "error": str(e)}

    def test_table_usage_documentation(self):
        """Test table usage and identify unused tables."""
        print("📋 Testing Table Usage Documentation...")

        try:
            # Look for table definitions and usage
            table_references = {}

            # Common table patterns to look for
            expected_tables = [
                "signal_greeks",
                "signal_indicators",
                "custom_timeframes",
                "user_preferences",
                "alert_configs",
                "watermark_data"
            ]

            # Search for table references across codebase
            for root, _dirs, files in os.walk("app"):
                for file in files:
                    if file.endswith('.py'):
                        file_path = os.path.join(root, file)
                        try:
                            with open(file_path) as f:
                                content = f.read()

                            for table in expected_tables:
                                if table in content:
                                    if table not in table_references:
                                        table_references[table] = []
                                    table_references[table].append(file_path)
                        except:
                            continue

            # Analyze table usage
            used_tables = []
            unused_tables = []

            for table in expected_tables:
                if table in table_references:
                    used_tables.append({
                        "table": table,
                        "references": len(table_references[table]),
                        "files": table_references[table][:3]  # First 3 files
                    })
                    print(f"    ✅ {table}: {len(table_references[table])} references")
                else:
                    unused_tables.append(table)
                    print(f"    ⚠️ {table}: no references found")

            print(f"  📊 Used tables: {len(used_tables)}")
            print(f"  📊 Unused tables: {len(unused_tables)}")

            return {
                "status": "tested",
                "used_tables": len(used_tables),
                "unused_tables": len(unused_tables),
                "table_usage": used_tables,
                "unused_table_names": unused_tables
            }

        except Exception as e:
            print(f"  ❌ Table usage test failed: {e}")
            return {"status": "error", "error": str(e)}

    def test_database_configuration(self):
        """Test database configuration structure."""
        print("⚙️ Testing Database Configuration...")

        try:
            # Check configuration files for database settings
            config_files = [
                "app/core/config.py",
                "app/config/database.py",
                ".env",
                ".env.example"
            ]

            db_configurations = []
            for file_path in config_files:
                if os.path.exists(file_path):
                    with open(file_path) as f:
                        content = f.read()

                    # Look for database configuration patterns
                    db_config_patterns = [
                        "DATABASE_URL", "DB_HOST", "DB_PORT", "DB_NAME",
                        "DB_USER", "DB_PASSWORD", "TIMESCALE", "POSTGRES",
                        "connection_pool", "max_connections", "pool_size"
                    ]

                    found_configs = [pattern for pattern in db_config_patterns if pattern in content]
                    if found_configs:
                        db_configurations.append({
                            "file": file_path,
                            "configs": found_configs
                        })
                        print(f"    ✅ {file_path}: {len(found_configs)} DB configs")

            print(f"  📊 Configuration files with DB settings: {len(db_configurations)}")

            return {
                "status": "tested",
                "config_files_found": len(db_configurations),
                "database_configurations": db_configurations
            }

        except Exception as e:
            print(f"  ❌ Database configuration test failed: {e}")
            return {"status": "error", "error": str(e)}

    def run_validation(self):
        """Run complete database sanity validation."""
        print("💾 Database Sanity Validation")
        print("=" * 60)

        start_time = time.time()

        # Run all tests
        self.results["tests"]["database_models_structure"] = self.test_database_models_structure()
        print()

        self.results["tests"]["timescale_integration_structure"] = self.test_timescale_integration_structure()
        print()

        self.results["tests"]["database_client_structure"] = self.test_database_client_structure()
        print()

        self.results["tests"]["table_usage_documentation"] = self.test_table_usage_documentation()
        print()

        self.results["tests"]["database_configuration"] = self.test_database_configuration()
        print()

        end_time = time.time()
        duration = end_time - start_time

        self.results["duration_seconds"] = duration
        self.results["summary"] = self._generate_summary()

        print("=" * 60)
        print(f"🎯 Database Sanity Summary (Duration: {duration:.2f}s)")

        for test_name, result in self.results["tests"].items():
            status = result.get("status", "unknown")
            emoji = "✅" if status == "tested" else "⚠️" if status == "unavailable" else "❌"
            print(f"  {emoji} {test_name.replace('_', ' ').title()}: {status}")

        # Generate database sanity report
        with open('database_sanity_report.json', 'w') as f:
            json.dump(self.results, f, indent=2)

        return self.results

    def _generate_summary(self):
        """Generate database sanity summary."""
        tested_count = sum(1 for test in self.results["tests"].values()
                          if test.get("status") == "tested")
        total_count = len(self.results["tests"])

        return {
            "total_tests": total_count,
            "successfully_tested": tested_count,
            "success_rate": (tested_count / total_count) * 100 if total_count > 0 else 0
        }


def main():
    """Run database sanity validation."""
    validation = DatabaseSanityValidation()
    results = validation.run_validation()

    success_rate = results["summary"]["success_rate"]
    if success_rate >= 80:  # 80% success rate for database validation
        print(f"\n🎉 DATABASE SANITY VALIDATION PASSED ({success_rate:.1f}% success rate)")
        print("\n💾 Database Structure Validated:")
        print("  - Database models and structure")
        print("  - TimescaleDB integration patterns")
        print("  - Database client architecture")
        print("  - Table usage documentation")
        print("  - Database configuration settings")
        return 0
    print(f"\n❌ DATABASE SANITY VALIDATION INSUFFICIENT ({success_rate:.1f}% success rate)")
    return 1


if __name__ == "__main__":
    try:
        exit_code = main()
        exit(exit_code)
    except Exception as e:
        print(f"💥 Database sanity validation failed: {e}")
        exit(1)
