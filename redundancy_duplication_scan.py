#!/usr/bin/env python3
"""
Redundancy/Duplication Scan

Verifies no parallel, redundant paths remain and identifies legacy code to remove.
"""
import os
import re
import time
import json
from datetime import datetime
from typing import Dict, Any, List, Set


class RedundancyDuplicationScan:
    """Redundancy and duplication scan for production readiness."""
    
    def __init__(self):
        self.results = {
            "timestamp": datetime.now().isoformat(),
            "tests": {},
            "redundant_patterns": [],
            "legacy_code_paths": []
        }
    
    def test_duplicate_historical_data_fetchers(self):
        """Test for multiple historical data fetchers."""
        print("📈 Testing Duplicate Historical Data Fetchers...")
        
        try:
            historical_fetchers = []
            
            # Look for historical data fetcher patterns
            fetcher_patterns = [
                "historical_data",
                "HistoricalData",
                "data_fetcher",
                "DataFetcher",
                "historical_client",
                "HistoricalClient"
            ]
            
            for root, dirs, files in os.walk("app"):
                for file in files:
                    if file.endswith('.py'):
                        file_path = os.path.join(root, file)
                        try:
                            with open(file_path, 'r') as f:
                                content = f.read()
                            
                            found_patterns = []
                            for pattern in fetcher_patterns:
                                if pattern in content:
                                    found_patterns.append(pattern)
                            
                            if found_patterns:
                                historical_fetchers.append({
                                    "file": file_path,
                                    "patterns": found_patterns,
                                    "lines": len(content.splitlines())
                                })
                        except:
                            continue
            
            # Analyze for duplicates
            potential_duplicates = []
            for i, fetcher1 in enumerate(historical_fetchers):
                for j, fetcher2 in enumerate(historical_fetchers):
                    if i < j:
                        common_patterns = set(fetcher1["patterns"]) & set(fetcher2["patterns"])
                        if len(common_patterns) >= 2:  # At least 2 common patterns
                            potential_duplicates.append({
                                "file1": fetcher1["file"],
                                "file2": fetcher2["file"],
                                "common_patterns": list(common_patterns)
                            })
                            print(f"    ⚠️ Potential duplicate: {os.path.basename(fetcher1['file'])} & {os.path.basename(fetcher2['file'])}")
            
            if not potential_duplicates:
                print("    ✅ No duplicate historical data fetchers detected")
            
            print(f"  📊 Historical fetcher files: {len(historical_fetchers)}")
            print(f"  📊 Potential duplicates: {len(potential_duplicates)}")
            
            return {
                "status": "tested",
                "fetcher_files": len(historical_fetchers),
                "potential_duplicates": len(potential_duplicates),
                "duplicate_details": potential_duplicates
            }
            
        except Exception as e:
            print(f"  ❌ Historical data fetchers test failed: {e}")
            return {"status": "error", "error": str(e)}
    
    def test_legacy_delivery_paths(self):
        """Test for legacy delivery paths."""
        print("📮 Testing Legacy Delivery Paths...")
        
        try:
            delivery_files = []
            
            # Look for delivery-related files
            delivery_patterns = [
                "delivery", "Delivery", "deliver", "send", "publish",
                "notification", "alert", "signal_delivery"
            ]
            
            for root, dirs, files in os.walk("app"):
                for file in files:
                    if file.endswith('.py') and any(pattern in file for pattern in delivery_patterns):
                        file_path = os.path.join(root, file)
                        delivery_files.append(file_path)
            
            # Analyze delivery files for patterns
            delivery_analysis = []
            for file_path in delivery_files:
                try:
                    with open(file_path, 'r') as f:
                        content = f.read()
                    
                    # Look for legacy patterns
                    legacy_patterns = [
                        "deprecated", "legacy", "old", "todo", "fixme", 
                        "unused", "remove", "delete", "obsolete"
                    ]
                    
                    active_patterns = [
                        "async def", "class", "def send", "def deliver",
                        "def publish", "watermark", "entitlement"
                    ]
                    
                    found_legacy = [pattern for pattern in legacy_patterns 
                                   if pattern.lower() in content.lower()]
                    found_active = [pattern for pattern in active_patterns 
                                   if pattern in content]
                    
                    delivery_analysis.append({
                        "file": file_path,
                        "legacy_markers": found_legacy,
                        "active_patterns": found_active,
                        "lines": len(content.splitlines()),
                        "likely_legacy": len(found_legacy) > 0 and len(found_active) == 0
                    })
                    
                    if found_legacy:
                        print(f"    ⚠️ {file_path}: {found_legacy}")
                    else:
                        print(f"    ✅ {file_path}: active")
                        
                except Exception:
                    continue
            
            legacy_count = sum(1 for analysis in delivery_analysis if analysis["likely_legacy"])
            
            print(f"  📊 Delivery files: {len(delivery_analysis)}")
            print(f"  📊 Likely legacy: {legacy_count}")
            
            return {
                "status": "tested",
                "delivery_files": len(delivery_analysis),
                "legacy_delivery_paths": legacy_count,
                "delivery_analysis": delivery_analysis
            }
            
        except Exception as e:
            print(f"  ❌ Legacy delivery paths test failed: {e}")
            return {"status": "error", "error": str(e)}
    
    def test_dual_entitlement_checks(self):
        """Test for dual entitlement checks."""
        print("🔐 Testing Dual Entitlement Checks...")
        
        try:
            entitlement_files = []
            
            # Find files with entitlement logic
            for root, dirs, files in os.walk("app"):
                for file in files:
                    if file.endswith('.py'):
                        file_path = os.path.join(root, file)
                        try:
                            with open(file_path, 'r') as f:
                                content = f.read()
                            
                            if "entitlement" in content.lower() or "entitled" in content.lower():
                                entitlement_files.append(file_path)
                        except:
                            continue
            
            # Analyze entitlement patterns
            entitlement_analysis = []
            for file_path in entitlement_files:
                try:
                    with open(file_path, 'r') as f:
                        content = f.read()
                    
                    # Look for entitlement check patterns
                    check_patterns = [
                        "check_entitlement",
                        "verify_entitlement",
                        "validate_entitlement",
                        "is_entitled",
                        "has_entitlement"
                    ]
                    
                    found_checks = []
                    for pattern in check_patterns:
                        matches = re.findall(pattern, content, re.IGNORECASE)
                        if matches:
                            found_checks.extend(matches)
                    
                    if found_checks:
                        entitlement_analysis.append({
                            "file": file_path,
                            "check_functions": found_checks,
                            "check_count": len(found_checks)
                        })
                        print(f"    ✅ {file_path}: {len(found_checks)} entitlement checks")
                except:
                    continue
            
            # Look for potential duplicates
            duplicate_checks = []
            for analysis in entitlement_analysis:
                if analysis["check_count"] > 3:  # More than 3 different check types might indicate duplication
                    duplicate_checks.append(analysis)
                    print(f"    ⚠️ Multiple check types in {analysis['file']}")
            
            print(f"  📊 Files with entitlement checks: {len(entitlement_analysis)}")
            print(f"  📊 Files with multiple check types: {len(duplicate_checks)}")
            
            return {
                "status": "tested",
                "entitlement_files": len(entitlement_analysis),
                "potential_duplicate_checks": len(duplicate_checks),
                "entitlement_analysis": entitlement_analysis
            }
            
        except Exception as e:
            print(f"  ❌ Dual entitlement checks test failed: {e}")
            return {"status": "error", "error": str(e)}
    
    def test_redundant_configuration_patterns(self):
        """Test for redundant configuration patterns."""
        print("⚙️ Testing Redundant Configuration Patterns...")
        
        try:
            config_files = []
            
            # Find configuration files
            config_patterns = ["config", "settings", "env", "conf"]
            
            for root, dirs, files in os.walk("."):
                for file in files:
                    if any(pattern in file.lower() for pattern in config_patterns):
                        if file.endswith(('.py', '.json', '.yaml', '.yml', '.ini', '.toml')):
                            config_files.append(os.path.join(root, file))
            
            # Analyze configuration patterns
            config_analysis = []
            all_config_keys = set()
            
            for file_path in config_files:
                try:
                    with open(file_path, 'r') as f:
                        content = f.read()
                    
                    # Extract configuration keys (basic pattern matching)
                    key_patterns = [
                        r'(\w+)\s*[=:]',  # key = value or key: value
                        r'["\'](\w+)["\']',  # "key" or 'key'
                        r'(\w+)_URL',  # SERVICE_URL patterns
                        r'(\w+)_KEY',  # API_KEY patterns
                    ]
                    
                    found_keys = set()
                    for pattern in key_patterns:
                        matches = re.findall(pattern, content, re.IGNORECASE)
                        found_keys.update(matches)
                    
                    config_analysis.append({
                        "file": file_path,
                        "keys": list(found_keys),
                        "key_count": len(found_keys)
                    })
                    
                    all_config_keys.update(found_keys)
                    print(f"    ✅ {file_path}: {len(found_keys)} config keys")
                    
                except Exception:
                    continue
            
            # Look for duplicate keys across files
            duplicate_keys = []
            for key in all_config_keys:
                files_with_key = [analysis for analysis in config_analysis if key in analysis["keys"]]
                if len(files_with_key) > 1:
                    duplicate_keys.append({
                        "key": key,
                        "files": [analysis["file"] for analysis in files_with_key]
                    })
            
            print(f"  📊 Configuration files: {len(config_analysis)}")
            print(f"  📊 Duplicate config keys: {len(duplicate_keys)}")
            
            if duplicate_keys:
                for dup in duplicate_keys[:5]:  # Show first 5
                    print(f"    ⚠️ Key '{dup['key']}' in {len(dup['files'])} files")
            
            return {
                "status": "tested",
                "config_files": len(config_analysis),
                "duplicate_keys": len(duplicate_keys),
                "duplicate_details": duplicate_keys[:10]  # First 10
            }
            
        except Exception as e:
            print(f"  ❌ Redundant configuration test failed: {e}")
            return {"status": "error", "error": str(e)}
    
    def test_unused_import_patterns(self):
        """Test for unused import patterns."""
        print("📦 Testing Unused Import Patterns...")
        
        try:
            import_analysis = []
            
            # Analyze Python files for imports
            for root, dirs, files in os.walk("app"):
                for file in files:
                    if file.endswith('.py'):
                        file_path = os.path.join(root, file)
                        try:
                            with open(file_path, 'r') as f:
                                lines = f.readlines()
                            
                            imports = []
                            content = ''.join(lines)
                            
                            # Find import statements
                            import_patterns = [
                                r'^import\s+(\w+)',
                                r'^from\s+\w+\s+import\s+(\w+)'
                            ]
                            
                            for line in lines:
                                for pattern in import_patterns:
                                    matches = re.findall(pattern, line.strip())
                                    imports.extend(matches)
                            
                            # Check if imports are used
                            unused_imports = []
                            for imp in imports:
                                if imp not in content.replace(f"import {imp}", ""):
                                    # Very basic check - import appears only in import statement
                                    import_line = f"import {imp}"
                                    from_import_line = f"from .* import .*{imp}"
                                    
                                    if (content.count(imp) == 1 and 
                                        (import_line in content or re.search(from_import_line, content))):
                                        unused_imports.append(imp)
                            
                            if imports:
                                import_analysis.append({
                                    "file": file_path,
                                    "total_imports": len(imports),
                                    "unused_imports": unused_imports,
                                    "unused_count": len(unused_imports)
                                })
                                
                                if unused_imports:
                                    print(f"    ⚠️ {file_path}: {len(unused_imports)} unused imports")
                                
                        except Exception:
                            continue
            
            total_unused = sum(analysis["unused_count"] for analysis in import_analysis)
            files_with_unused = sum(1 for analysis in import_analysis if analysis["unused_count"] > 0)
            
            print(f"  📊 Files analyzed: {len(import_analysis)}")
            print(f"  📊 Files with unused imports: {files_with_unused}")
            print(f"  📊 Total unused imports: {total_unused}")
            
            return {
                "status": "tested",
                "files_analyzed": len(import_analysis),
                "files_with_unused": files_with_unused,
                "total_unused_imports": total_unused,
                "import_analysis": [a for a in import_analysis if a["unused_count"] > 0][:10]
            }
            
        except Exception as e:
            print(f"  ❌ Unused import patterns test failed: {e}")
            return {"status": "error", "error": str(e)}
    
    def run_scan(self):
        """Run complete redundancy/duplication scan."""
        print("🔍 Redundancy/Duplication Scan")
        print("=" * 60)
        
        start_time = time.time()
        
        # Run all tests
        self.results["tests"]["duplicate_historical_data_fetchers"] = self.test_duplicate_historical_data_fetchers()
        print()
        
        self.results["tests"]["legacy_delivery_paths"] = self.test_legacy_delivery_paths()
        print()
        
        self.results["tests"]["dual_entitlement_checks"] = self.test_dual_entitlement_checks()
        print()
        
        self.results["tests"]["redundant_configuration_patterns"] = self.test_redundant_configuration_patterns()
        print()
        
        self.results["tests"]["unused_import_patterns"] = self.test_unused_import_patterns()
        print()
        
        end_time = time.time()
        duration = end_time - start_time
        
        self.results["duration_seconds"] = duration
        self.results["summary"] = self._generate_summary()
        
        print("=" * 60)
        print(f"🎯 Redundancy/Duplication Scan Summary (Duration: {duration:.2f}s)")
        
        for test_name, result in self.results["tests"].items():
            status = result.get("status", "unknown")
            emoji = "✅" if status == "tested" else "⚠️" if status == "unavailable" else "❌"
            print(f"  {emoji} {test_name.replace('_', ' ').title()}: {status}")
        
        # Report findings
        self._report_findings()
        
        # Generate redundancy scan report
        with open('redundancy_duplication_scan_report.json', 'w') as f:
            json.dump(self.results, f, indent=2)
        
        return self.results
    
    def _report_findings(self):
        """Report scan findings."""
        print("\n🔍 Redundancy/Duplication Findings:")
        
        # Historical data fetchers
        fetcher_result = self.results["tests"].get("duplicate_historical_data_fetchers", {})
        if fetcher_result.get("potential_duplicates", 0) > 0:
            print(f"  ⚠️ {fetcher_result['potential_duplicates']} potential duplicate historical data fetchers")
        else:
            print("  ✅ No duplicate historical data fetchers")
        
        # Legacy delivery paths
        delivery_result = self.results["tests"].get("legacy_delivery_paths", {})
        if delivery_result.get("legacy_delivery_paths", 0) > 0:
            print(f"  ⚠️ {delivery_result['legacy_delivery_paths']} likely legacy delivery paths")
        else:
            print("  ✅ No legacy delivery paths detected")
        
        # Dual entitlement checks
        entitlement_result = self.results["tests"].get("dual_entitlement_checks", {})
        if entitlement_result.get("potential_duplicate_checks", 0) > 0:
            print(f"  ⚠️ {entitlement_result['potential_duplicate_checks']} files with multiple entitlement check types")
        else:
            print("  ✅ No duplicate entitlement checks")
        
        # Configuration redundancy
        config_result = self.results["tests"].get("redundant_configuration_patterns", {})
        if config_result.get("duplicate_keys", 0) > 0:
            print(f"  ⚠️ {config_result['duplicate_keys']} duplicate configuration keys")
        else:
            print("  ✅ No redundant configuration patterns")
        
        # Unused imports
        import_result = self.results["tests"].get("unused_import_patterns", {})
        if import_result.get("total_unused_imports", 0) > 0:
            print(f"  ⚠️ {import_result['total_unused_imports']} unused imports detected")
        else:
            print("  ✅ No unused imports detected")
    
    def _generate_summary(self):
        """Generate redundancy scan summary."""
        tested_count = sum(1 for test in self.results["tests"].values() 
                          if test.get("status") == "tested")
        total_count = len(self.results["tests"])
        
        # Calculate redundancy score
        issues_found = 0
        for test_name, result in self.results["tests"].items():
            if test_name == "duplicate_historical_data_fetchers":
                issues_found += result.get("potential_duplicates", 0)
            elif test_name == "legacy_delivery_paths":
                issues_found += result.get("legacy_delivery_paths", 0)
            elif test_name == "dual_entitlement_checks":
                issues_found += result.get("potential_duplicate_checks", 0)
            elif test_name == "redundant_configuration_patterns":
                issues_found += result.get("duplicate_keys", 0)
            elif test_name == "unused_import_patterns":
                issues_found += min(result.get("total_unused_imports", 0), 10)  # Cap at 10 for scoring
        
        return {
            "total_tests": total_count,
            "successfully_tested": tested_count,
            "success_rate": (tested_count / total_count) * 100 if total_count > 0 else 0,
            "issues_found": issues_found,
            "redundancy_score": max(0, 100 - issues_found * 2)  # Deduct 2 points per issue
        }


def main():
    """Run redundancy/duplication scan."""
    scan = RedundancyDuplicationScan()
    results = scan.run_scan()
    
    success_rate = results["summary"]["success_rate"]
    redundancy_score = results["summary"]["redundancy_score"]
    
    if success_rate >= 80 and redundancy_score >= 70:
        print(f"\n🎉 REDUNDANCY/DUPLICATION SCAN PASSED ({success_rate:.1f}% success, {redundancy_score:.1f} redundancy score)")
        print("\n🔍 Redundancy Analysis Completed:")
        print("  - Historical data fetcher duplication check")
        print("  - Legacy delivery path detection")
        print("  - Dual entitlement check analysis")
        print("  - Configuration pattern redundancy")
        print("  - Unused import pattern detection")
        return 0
    else:
        print(f"\n❌ REDUNDANCY/DUPLICATION SCAN NEEDS ATTENTION ({success_rate:.1f}% success, {redundancy_score:.1f} redundancy score)")
        return 1


if __name__ == "__main__":
    try:
        exit_code = main()
        exit(exit_code)
    except Exception as e:
        print(f"💥 Redundancy/duplication scan failed: {e}")
        exit(1)