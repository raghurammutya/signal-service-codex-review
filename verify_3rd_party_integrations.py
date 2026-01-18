#!/usr/bin/env python3
"""
3rd Party Package Integration Verification Script

This script runs comprehensive verification of PyVolLib, scikit-learn, and pandas_ta
integrations to detect any wiring gaps, false integrations, or placeholder implementations.

Usage:
    python verify_3rd_party_integrations.py [--api-base-url URL] [--verbose]
    
Exit codes:
    0: All verifications passed
    1: One or more verifications failed
    2: Critical error (service unreachable, import failures)
"""

import sys
import os
import json
import subprocess
import requests
import time
from datetime import datetime
from typing import Dict, List, Tuple, Optional
import argparse


class Colors:
    """Terminal color codes for output formatting"""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    PURPLE = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'


class VerificationResult:
    """Represents the result of a single verification step"""
    
    def __init__(self, step: str, description: str, passed: bool, details: str = "", error: str = ""):
        self.step = step
        self.description = description
        self.passed = passed
        self.details = details
        self.error = error
        self.timestamp = datetime.now()


class IntegrationVerifier:
    """Runs comprehensive verification of 3rd party package integrations"""
    
    def __init__(self, api_base_url: str = "http://localhost:8003", verbose: bool = False):
        self.api_base_url = api_base_url.rstrip('/')
        self.verbose = verbose
        self.results: List[VerificationResult] = []
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'X-User-ID': 'test-verification'
        })
    
    def log(self, message: str, color: str = Colors.WHITE):
        """Log message with optional color"""
        if self.verbose:
            print(f"{color}{message}{Colors.END}")
    
    def log_step(self, step: str, description: str):
        """Log the start of a verification step"""
        print(f"{Colors.BLUE}[{step}]{Colors.END} {description}")
    
    def log_result(self, result: VerificationResult):
        """Log the result of a verification step"""
        status_color = Colors.GREEN if result.passed else Colors.RED
        status_text = "✓ PASS" if result.passed else "✗ FAIL"
        
        print(f"  {status_color}{status_text}{Colors.END}")
        
        if result.details and self.verbose:
            print(f"    {Colors.CYAN}Details: {result.details}{Colors.END}")
        
        if result.error and not result.passed:
            print(f"    {Colors.RED}Error: {result.error}{Colors.END}")
    
    def run_command(self, command: str, description: str = "") -> Tuple[bool, str, str]:
        """Run a shell command and return success status, stdout, stderr"""
        try:
            self.log(f"Running: {command}", Colors.YELLOW)
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=120  # 2 minute timeout
            )
            success = result.returncode == 0
            return success, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return False, "", f"Command timed out after 120 seconds"
        except Exception as e:
            return False, "", f"Command execution failed: {str(e)}"
    
    def make_api_request(self, endpoint: str, method: str = "GET", data: Dict = None) -> Tuple[bool, Dict, str]:
        """Make API request and return success status, response data, error message"""
        try:
            url = f"{self.api_base_url}{endpoint}"
            self.log(f"API {method}: {url}", Colors.YELLOW)
            
            if method.upper() == "GET":
                response = self.session.get(url, timeout=30)
            elif method.upper() == "POST":
                response = self.session.post(url, json=data, timeout=30)
            else:
                return False, {}, f"Unsupported HTTP method: {method}"
            
            response.raise_for_status()
            return True, response.json(), ""
            
        except requests.exceptions.RequestException as e:
            return False, {}, f"API request failed: {str(e)}"
        except json.JSONDecodeError as e:
            return False, {}, f"Invalid JSON response: {str(e)}"
        except Exception as e:
            return False, {}, f"Unexpected error: {str(e)}"
    
    def verify_pyvollib_integration(self) -> List[VerificationResult]:
        """Verify PyVolLib Greeks integration"""
        results = []
        
        # Step 1: Test vectorized engine fallback
        self.log_step("PYVOLLIB-1", "PyVolLib vectorized engine fallback tests")
        success, stdout, stderr = self.run_command(
            "python -m pytest tests/unit/test_pyvollib_vectorized_engine_fallback.py -v --tb=short"
        )
        
        coverage_check = "coverage" in stdout.lower() and "95%" in stdout
        details = f"Coverage check: {'✓' if coverage_check else '✗'}"
        
        results.append(VerificationResult(
            "PYVOLLIB-1", "Vectorized engine fallback tests",
            success and coverage_check,
            details,
            stderr if not success else ""
        ))
        
        # Step 2: Complete PyVolLib integration test
        self.log_step("PYVOLLIB-2", "Complete PyVolLib integration test")
        success, stdout, stderr = self.run_command(
            "python test_complete_pyvollib_integration.py"
        )
        
        registration_check = "registration" in stdout.lower() and "success" in stdout.lower()
        details = f"Registration check: {'✓' if registration_check else '✗'}"
        
        results.append(VerificationResult(
            "PYVOLLIB-2", "Complete integration test",
            success and registration_check,
            details,
            stderr if not success else ""
        ))
        
        # Step 3: API accessibility test
        self.log_step("PYVOLLIB-3", "PyVolLib API accessibility")
        success, response_data, error = self.make_api_request(
            "/api/v2/indicators/available-indicators"
        )
        
        greeks_indicators = []
        if success and isinstance(response_data, dict):
            greeks_indicators = response_data.get("greeks", [])
        
        expected_greeks = ["option_delta", "option_gamma", "option_theta", "option_vega", "option_rho"]
        greeks_found = len([g for g in expected_greeks if any(ind.get("name") == g for ind in greeks_indicators)])
        
        details = f"Found {len(greeks_indicators)} Greeks indicators, {greeks_found}/{len(expected_greeks)} expected ones"
        
        results.append(VerificationResult(
            "PYVOLLIB-3", "API accessibility",
            success and greeks_found >= 5,
            details,
            error if not success else ""
        ))
        
        # Step 4: Real calculation test (option_delta)
        self.log_step("PYVOLLIB-4", "Real PyVolLib calculation test")
        calc_data = {
            "indicator": "option_delta",
            "parameters": {
                "option_type": "call",
                "spot_price": 100.0,
                "strike_price": 105.0,
                "time_to_expiry": 0.25,
                "risk_free_rate": 0.05,
                "volatility": 0.2
            }
        }
        
        success, response_data, error = self.make_api_request(
            "/api/v2/indicators/calculate", "POST", calc_data
        )
        
        is_real_value = False
        if success and isinstance(response_data, dict):
            value = response_data.get("value", response_data.get("result"))
            is_real_value = isinstance(value, (int, float)) and 0 < value < 1  # Delta should be between 0 and 1
        
        details = f"Delta calculation returned: {response_data.get('value', 'N/A') if success else 'Failed'}"
        
        results.append(VerificationResult(
            "PYVOLLIB-4", "Real calculation test",
            success and is_real_value,
            details,
            error if not success else "Calculation did not return valid delta value"
        ))
        
        return results
    
    def verify_sklearn_clustering(self) -> List[VerificationResult]:
        """Verify scikit-learn clustering integration"""
        results = []
        
        # Step 1: Clustering indicators test
        self.log_step("SKLEARN-1", "Clustering indicators test")
        success, stdout, stderr = self.run_command(
            "python -c \"from app.services.clustering_indicators import cluster_support_resistance, kmeans_price_levels, price_outliers; print('All clustering indicators imported successfully')\""
        )
        
        results.append(VerificationResult(
            "SKLEARN-1", "Clustering indicators import",
            success,
            "Direct import test",
            stderr if not success else ""
        ))
        
        # Step 2: Check indicator registry
        self.log_step("SKLEARN-2", "Clustering indicators in registry")
        success, response_data, error = self.make_api_request(
            "/api/v2/indicators/available-indicators"
        )
        
        clustering_indicators = []
        if success and isinstance(response_data, dict):
            clustering_indicators = response_data.get("clustering", [])
        
        expected_clustering = ["cluster_support_resistance", "kmeans_price_levels", "price_outliers"]
        clustering_found = len([c for c in expected_clustering if any(ind.get("name") == c for ind in clustering_indicators)])
        
        details = f"Found {len(clustering_indicators)} clustering indicators, {clustering_found}/{len(expected_clustering)} expected ones"
        
        results.append(VerificationResult(
            "SKLEARN-2", "Registry availability",
            success and clustering_found >= 3,
            details,
            error if not success else ""
        ))
        
        # Step 3: Scikit-learn dependency check
        self.log_step("SKLEARN-3", "Scikit-learn dependency verification")
        success, stdout, stderr = self.run_command(
            "python -c \"import sklearn; print(f'sklearn version: {sklearn.__version__}')\""
        )
        
        version_check = success and "version:" in stdout
        
        results.append(VerificationResult(
            "SKLEARN-3", "Dependency verification",
            version_check,
            stdout.strip() if success else "Import failed",
            stderr if not success else ""
        ))
        
        return results
    
    def verify_pandas_ta_integration(self) -> List[VerificationResult]:
        """Verify pandas_ta integration"""
        results = []
        
        # Step 1: Pandas TA coverage test
        self.log_step("PANDAS_TA-1", "Pandas TA coverage with real data")
        success, stdout, stderr = self.run_command(
            "python -m pytest tests/unit/test_pandas_ta_coverage_with_real_data.py -v --tb=short"
        )
        
        coverage_check = "coverage" in stdout.lower() and ("95%" in stdout or "90%" in stdout)
        details = f"Coverage test: {'✓' if coverage_check else '✗'}"
        
        results.append(VerificationResult(
            "PANDAS_TA-1", "Coverage with real data test",
            success and coverage_check,
            details,
            stderr if not success else ""
        ))
        
        # Step 2: Pandas TA executor test
        self.log_step("PANDAS_TA-2", "Pandas TA executor functionality")
        success, stdout, stderr = self.run_command(
            "python -c \"from app.services.pandas_ta_executor import PandasTAExecutor; executor = PandasTAExecutor(); print('Executor initialized successfully')\""
        )
        
        results.append(VerificationResult(
            "PANDAS_TA-2", "Executor functionality",
            success,
            "Direct executor test",
            stderr if not success else ""
        ))
        
        # Step 3: API fallback test (RSI)
        self.log_step("PANDAS_TA-3", "API fallback test with RSI")
        calc_data = {
            "indicator": "rsi",
            "parameters": {
                "length": 14
            }
        }
        
        success, response_data, error = self.make_api_request(
            "/api/v2/indicators/calculate", "POST", calc_data
        )
        
        has_valid_response = success and isinstance(response_data, dict) and "value" in response_data
        
        results.append(VerificationResult(
            "PANDAS_TA-3", "API fallback test",
            has_valid_response,
            f"RSI calculation response: {response_data if success else 'Failed'}",
            error if not success else ""
        ))
        
        # Step 4: Check pandas_ta dependency
        self.log_step("PANDAS_TA-4", "Pandas TA dependency verification")
        success, stdout, stderr = self.run_command(
            "python -c \"import pandas_ta as ta; print(f'pandas_ta version: {ta.version}')\""
        )
        
        version_check = success and "version:" in stdout
        
        results.append(VerificationResult(
            "PANDAS_TA-4", "Dependency verification",
            version_check,
            stdout.strip() if success else "Import failed",
            stderr if not success else ""
        ))
        
        return results
    
    def verify_universal_compute(self) -> List[VerificationResult]:
        """Verify universal computation API"""
        results = []
        
        # Step 1: Universal compute integration test
        self.log_step("UNIVERSAL-1", "Universal compute integration test")
        success, stdout, stderr = self.run_command(
            "python -m pytest tests/integration/test_signal_processing_coverage.py::test_universal_compute -v"
        )
        
        results.append(VerificationResult(
            "UNIVERSAL-1", "Integration test",
            success,
            "Universal compute test coverage",
            stderr if not success else ""
        ))
        
        # Step 2: Check supported libraries
        self.log_step("UNIVERSAL-2", "Supported libraries enumeration")
        success, response_data, error = self.make_api_request(
            "/api/v2/universal/libraries"
        )
        
        expected_libraries = ["py_vollib", "scikit-learn", "pandas_ta"]
        libraries_found = 0
        
        if success and isinstance(response_data, dict):
            libraries = response_data.get("libraries", {})
            libraries_found = sum(1 for lib in expected_libraries if lib in libraries)
        
        details = f"Found {libraries_found}/{len(expected_libraries)} expected libraries"
        
        results.append(VerificationResult(
            "UNIVERSAL-2", "Libraries enumeration",
            success and libraries_found >= 3,
            details,
            error if not success else ""
        ))
        
        return results
    
    def verify_indicator_registration(self) -> List[VerificationResult]:
        """Verify indicator registration at startup"""
        results = []
        
        # Step 1: Indicator count verification
        self.log_step("REGISTRATION-1", "Indicator count verification")
        success, stdout, stderr = self.run_command(
            "python -c \"from app.services.register_indicators import register_all_indicators; from app.services.indicator_registry import IndicatorRegistry; register_all_indicators(); print(f'Total indicators: {IndicatorRegistry.count()}'); counts = IndicatorRegistry.count_by_category(); [print(f'{cat}: {count}') for cat, count in sorted(counts.items())]\""
        )
        
        indicator_count_check = success and "Total indicators:" in stdout
        has_greeks = "greeks:" in stdout.lower()
        has_clustering = "clustering:" in stdout.lower()
        
        details = f"Registration check: {'✓' if indicator_count_check else '✗'}, Greeks: {'✓' if has_greeks else '✗'}, Clustering: {'✓' if has_clustering else '✗'}"
        
        results.append(VerificationResult(
            "REGISTRATION-1", "Indicator count verification",
            indicator_count_check and has_greeks and has_clustering,
            details,
            stderr if not success else ""
        ))
        
        return results
    
    def verify_qa_pipeline_artifacts(self) -> List[VerificationResult]:
        """Verify QA pipeline artifacts reference integrations"""
        results = []
        
        # Check for key documentation files
        docs_to_check = [
            ("COMPLIANCE_COVERAGE_REPORT.md", "compliance coverage report"),
            ("PRODUCTION_READINESS_DASHBOARD.md", "production readiness dashboard"),
            ("3RD_PARTY_PACKAGE_VERIFICATION_CHECKLIST.md", "verification checklist")
        ]
        
        for doc_file, description in docs_to_check:
            self.log_step(f"QA-{doc_file}", f"Check {description}")
            
            if os.path.exists(doc_file):
                try:
                    with open(doc_file, 'r') as f:
                        content = f.read().lower()
                    
                    has_pyvollib = "pyvollib" in content or "py_vollib" in content
                    has_sklearn = "sklearn" in content or "scikit-learn" in content
                    has_pandas_ta = "pandas_ta" in content or "pandas-ta" in content
                    
                    integration_coverage = sum([has_pyvollib, has_sklearn, has_pandas_ta])
                    details = f"PyVolLib: {'✓' if has_pyvollib else '✗'}, Sklearn: {'✓' if has_sklearn else '✗'}, Pandas_ta: {'✓' if has_pandas_ta else '✗'}"
                    
                    results.append(VerificationResult(
                        f"QA-{doc_file}", description,
                        integration_coverage >= 2,  # At least 2 of 3 integrations mentioned
                        details,
                        ""
                    ))
                    
                except Exception as e:
                    results.append(VerificationResult(
                        f"QA-{doc_file}", description,
                        False,
                        "",
                        f"Failed to read file: {str(e)}"
                    ))
            else:
                results.append(VerificationResult(
                    f"QA-{doc_file}", description,
                    False,
                    "",
                    f"File {doc_file} not found"
                ))
        
        return results
    
    def run_all_verifications(self) -> bool:
        """Run all verification steps and return overall success"""
        print(f"{Colors.BOLD}{Colors.PURPLE}=" * 80)
        print("3RD PARTY PACKAGE INTEGRATION VERIFICATION")
        print("=" * 80 + Colors.END)
        print(f"Timestamp: {datetime.now().isoformat()}")
        print(f"API Base URL: {self.api_base_url}")
        print()
        
        # Wait for service to be ready
        print(f"{Colors.YELLOW}Waiting for service to be ready...{Colors.END}")
        max_retries = 30
        for i in range(max_retries):
            try:
                success, _, _ = self.make_api_request("/health")
                if success:
                    print(f"{Colors.GREEN}✓ Service is ready{Colors.END}")
                    break
            except:
                pass
            
            if i == max_retries - 1:
                print(f"{Colors.RED}✗ Service failed to become ready after {max_retries} attempts{Colors.END}")
                return False
            
            time.sleep(2)
        
        print()
        
        # Run all verification categories
        verification_categories = [
            ("PyVolLib Integration", self.verify_pyvollib_integration),
            ("Scikit-learn Clustering", self.verify_sklearn_clustering),
            ("Pandas TA Integration", self.verify_pandas_ta_integration),
            ("Universal Computation", self.verify_universal_compute),
            ("Indicator Registration", self.verify_indicator_registration),
            ("QA Pipeline Artifacts", self.verify_qa_pipeline_artifacts),
        ]
        
        all_passed = True
        
        for category_name, verification_func in verification_categories:
            print(f"{Colors.BOLD}{Colors.CYAN}{category_name}{Colors.END}")
            print("-" * len(category_name))
            
            try:
                category_results = verification_func()
                for result in category_results:
                    self.log_result(result)
                    self.results.append(result)
                    if not result.passed:
                        all_passed = False
            except Exception as e:
                error_result = VerificationResult(
                    category_name, f"{category_name} verification",
                    False, "", f"Verification failed with exception: {str(e)}"
                )
                self.log_result(error_result)
                self.results.append(error_result)
                all_passed = False
            
            print()
        
        # Print summary
        self.print_summary()
        
        return all_passed
    
    def print_summary(self):
        """Print verification summary"""
        print(f"{Colors.BOLD}{Colors.PURPLE}=" * 80)
        print("VERIFICATION SUMMARY")
        print("=" * 80 + Colors.END)
        
        passed_count = sum(1 for r in self.results if r.passed)
        total_count = len(self.results)
        
        summary_color = Colors.GREEN if passed_count == total_count else Colors.RED
        print(f"{summary_color}Results: {passed_count}/{total_count} verifications passed{Colors.END}")
        
        if passed_count == total_count:
            print(f"{Colors.GREEN}{Colors.BOLD}✓ ALL INTEGRATIONS VERIFIED - READY FOR RELEASE{Colors.END}")
        else:
            print(f"{Colors.RED}{Colors.BOLD}✗ INTEGRATION ISSUES DETECTED - DO NOT RELEASE{Colors.END}")
            print()
            print(f"{Colors.YELLOW}Failed verifications:{Colors.END}")
            for result in self.results:
                if not result.passed:
                    print(f"  - {result.step}: {result.description}")
                    if result.error:
                        print(f"    {Colors.RED}Error: {result.error}{Colors.END}")
        
        print()
        print(f"Verification completed at: {datetime.now().isoformat()}")
        print("=" * 80)


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Verify 3rd party package integrations")
    parser.add_argument(
        "--api-base-url",
        default="http://localhost:8003",
        help="Base URL for API requests (default: http://localhost:8003)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output"
    )
    
    args = parser.parse_args()
    
    verifier = IntegrationVerifier(api_base_url=args.api_base_url, verbose=args.verbose)
    
    try:
        success = verifier.run_all_verifications()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Verification interrupted by user{Colors.END}")
        sys.exit(2)
    except Exception as e:
        print(f"{Colors.RED}Critical error during verification: {str(e)}{Colors.END}")
        sys.exit(2)


if __name__ == "__main__":
    main()