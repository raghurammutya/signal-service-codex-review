#!/usr/bin/env python3
"""
Test script to verify indicator registry status and 3rd party library access
without requiring ticker service or historical data.

This script tests:
1. Indicator registry initialization and counts
2. Available pandas_ta indicators via API
3. Third-party library accessibility (pandas_ta, findpeaks, trendln, scikit-learn, scipy)
4. Mock/test computations that don't require external data
5. Registry status from various endpoints
"""

import asyncio
import json
import sys
from datetime import datetime
from typing import Any

import httpx
import numpy as np
import pandas as pd


class IndicatorRegistryTester:
    """Test indicator registry and 3rd party libraries without ticker service dependency"""

    def __init__(self, base_url: str = "http://localhost:8003"):
        self.base_url = base_url
        self.client = None
        self.results = {}
        self.errors = []

    async def __aenter__(self):
        self.client = httpx.AsyncClient(timeout=30.0)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.client:
            await self.client.aclose()

    def log_result(self, test_name: str, status: str, details: Any = None, error: str = None):
        """Log test result"""
        result = {
            "test": test_name,
            "status": status,
            "timestamp": datetime.now().isoformat(),
            "details": details,
            "error": error
        }
        self.results[test_name] = result

        status_emoji = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
        print(f"{status_emoji} {test_name}: {status}")
        if error:
            print(f"   Error: {error}")
        if details and status == "PASS":
            if isinstance(details, dict) and "count" in details:
                print(f"   Count: {details['count']}")

    async def test_service_health(self) -> bool:
        """Test if the signal service is running and healthy"""
        try:
            response = await self.client.get(f"{self.base_url}/health")
            if response.status_code == 200:
                health_data = response.json()
                self.log_result("service_health", "PASS", health_data)
                return True
            self.log_result("service_health", "FAIL", error=f"HTTP {response.status_code}")
            return False
        except Exception as e:
            self.log_result("service_health", "FAIL", error=str(e))
            return False

    async def test_available_indicators_endpoint(self):
        """Test the /indicators/available-indicators endpoint"""
        try:
            response = await self.client.get(f"{self.base_url}/api/v2/indicators/available-indicators")
            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    indicators = data.get("data", {})
                    self.log_result(
                        "available_indicators_api",
                        "PASS",
                        {"count": len(indicators), "sample_indicators": list(indicators.keys())[:10]}
                    )
                    return indicators
                self.log_result("available_indicators_api", "FAIL", error=data.get("message"))
            else:
                self.log_result("available_indicators_api", "FAIL", error=f"HTTP {response.status_code}")
        except Exception as e:
            self.log_result("available_indicators_api", "FAIL", error=str(e))
        return {}

    async def test_universal_computations_endpoint(self):
        """Test the /universal/computations endpoint"""
        try:
            response = await self.client.get(f"{self.base_url}/api/v2/universal/computations")
            if response.status_code == 200:
                data = response.json()
                computations = data.get("computations", [])
                self.log_result(
                    "universal_computations_api",
                    "PASS",
                    {
                        "count": len(computations),
                        "total": data.get("total"),
                        "sample_types": [comp["name"] for comp in computations[:5]]
                    }
                )
                return computations
            self.log_result("universal_computations_api", "FAIL", error=f"HTTP {response.status_code}")
        except Exception as e:
            self.log_result("universal_computations_api", "FAIL", error=str(e))
        return []

    async def test_universal_health_endpoint(self):
        """Test the /universal/health endpoint for registry info"""
        try:
            response = await self.client.get(f"{self.base_url}/api/v2/universal/health")
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "healthy":
                    capabilities = data.get("capabilities", {})
                    self.log_result(
                        "universal_health_api",
                        "PASS",
                        {
                            "total_computations": capabilities.get("total_computations"),
                            "asset_coverage": capabilities.get("asset_coverage"),
                            "supported_assets": capabilities.get("supported_assets", [])[:5]
                        }
                    )
                else:
                    self.log_result("universal_health_api", "FAIL", error=f"Status: {data.get('status')}")
            else:
                self.log_result("universal_health_api", "FAIL", error=f"HTTP {response.status_code}")
        except Exception as e:
            self.log_result("universal_health_api", "FAIL", error=str(e))

    async def test_third_party_library_access(self):
        """Test if we can access third-party libraries directly"""

        # Test pandas_ta
        try:
            import pandas_ta as ta
            # Get available indicators
            ta_indicators = []
            for name, obj in vars(ta).items():
                if callable(obj) and not name.startswith('_') and hasattr(obj, '__module__'):
                    ta_indicators.append(name)

            self.log_result(
                "pandas_ta_library",
                "PASS",
                {"count": len(ta_indicators), "sample": ta_indicators[:10]}
            )
        except Exception as e:
            self.log_result("pandas_ta_library", "FAIL", error=str(e))

        # Test findpeaks
        try:
            import findpeaks
            findpeaks.findpeaks()
            self.log_result("findpeaks_library", "PASS", {"version": getattr(findpeaks, "__version__", "unknown")})
        except Exception as e:
            self.log_result("findpeaks_library", "FAIL", error=str(e))

        # Test trendln
        try:
            import trendln
            self.log_result("trendln_library", "PASS", {"version": getattr(trendln, "__version__", "unknown")})
        except Exception as e:
            self.log_result("trendln_library", "FAIL", error=str(e))

        # Test scikit-learn
        try:
            import sklearn
            self.log_result("sklearn_library", "PASS", {"version": sklearn.__version__})
        except Exception as e:
            self.log_result("sklearn_library", "FAIL", error=str(e))

        # Test scipy
        try:
            import scipy
            self.log_result("scipy_library", "PASS", {"version": scipy.__version__})
        except Exception as e:
            self.log_result("scipy_library", "FAIL", error=str(e))

    async def test_mock_computations(self):
        """Test computations using mock data instead of ticker service"""

        # Create sample OHLCV data
        dates = pd.date_range(start='2023-01-01', periods=100, freq='D')
        mock_data = pd.DataFrame({
            'timestamp': dates,
            'open': np.random.uniform(100, 105, 100),
            'high': np.random.uniform(105, 110, 100),
            'low': np.random.uniform(95, 100, 100),
            'close': np.random.uniform(100, 105, 100),
            'volume': np.random.randint(1000, 10000, 100)
        })
        mock_data.set_index('timestamp', inplace=True)

        try:
            # Test pandas_ta directly with mock data
            import pandas_ta as ta

            # Test SMA
            sma_20 = ta.sma(mock_data['close'], length=20)
            self.log_result("mock_sma_calculation", "PASS", {"last_value": float(sma_20.iloc[-1])})

            # Test RSI
            rsi = ta.rsi(mock_data['close'], length=14)
            self.log_result("mock_rsi_calculation", "PASS", {"last_value": float(rsi.iloc[-1])})

            # Test MACD
            macd_data = ta.macd(mock_data['close'])
            self.log_result("mock_macd_calculation", "PASS", {"columns": list(macd_data.columns)})

        except Exception as e:
            self.log_result("mock_calculations", "FAIL", error=str(e))

    async def test_indicator_cache_stats(self):
        """Test indicator cache statistics endpoint"""
        try:
            response = await self.client.get(f"{self.base_url}/api/v2/indicators/cache/stats")
            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    cache_stats = data.get("data", {})
                    self.log_result("indicator_cache_stats", "PASS", cache_stats)
                else:
                    self.log_result("indicator_cache_stats", "FAIL", error=data.get("message"))
            else:
                self.log_result("indicator_cache_stats", "FAIL", error=f"HTTP {response.status_code}")
        except Exception as e:
            self.log_result("indicator_cache_stats", "FAIL", error=str(e))

    async def test_worker_affinity_status(self):
        """Test worker affinity status endpoint"""
        try:
            response = await self.client.get(f"{self.base_url}/api/v2/indicators/worker-affinity/status")
            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    affinity_stats = data.get("data", {})
                    self.log_result("worker_affinity_status", "PASS", affinity_stats)
                else:
                    self.log_result("worker_affinity_status", "FAIL", error=data.get("message"))
            else:
                self.log_result("worker_affinity_status", "FAIL", error=f"HTTP {response.status_code}")
        except Exception as e:
            self.log_result("worker_affinity_status", "FAIL", error=str(e))

    async def test_admin_service_status(self):
        """Test admin service status endpoint (if accessible)"""
        try:
            # Try with a simple token - in production this would need proper auth
            headers = {"Authorization": "Bearer admin-test-token"}
            response = await self.client.get(
                f"{self.base_url}/api/v2/admin/status",
                headers=headers,
                params={"token": "admin-test"}
            )
            if response.status_code == 200:
                data = response.json()
                service_metrics = data.get("service", {})
                self.log_result("admin_service_status", "PASS", service_metrics)
            elif response.status_code == 403:
                self.log_result("admin_service_status", "SKIP", error="Admin access required")
            else:
                self.log_result("admin_service_status", "FAIL", error=f"HTTP {response.status_code}")
        except Exception as e:
            self.log_result("admin_service_status", "FAIL", error=str(e))

    async def run_all_tests(self) -> dict[str, Any]:
        """Run all indicator registry tests"""
        print("🔍 Testing Signal Service Indicator Registry Status")
        print("=" * 60)

        # Test service health first
        is_healthy = await self.test_service_health()
        if not is_healthy:
            print("❌ Service is not healthy, stopping tests")
            return self.generate_report()

        # Run all tests
        await asyncio.gather(
            self.test_available_indicators_endpoint(),
            self.test_universal_computations_endpoint(),
            self.test_universal_health_endpoint(),
            self.test_indicator_cache_stats(),
            self.test_worker_affinity_status(),
            self.test_admin_service_status(),
            return_exceptions=True
        )

        # Test libraries (synchronous)
        await self.test_third_party_library_access()

        # Test mock computations
        await self.test_mock_computations()

        return self.generate_report()

    def generate_report(self) -> dict[str, Any]:
        """Generate final test report"""
        total_tests = len(self.results)
        passed_tests = len([r for r in self.results.values() if r["status"] == "PASS"])
        failed_tests = len([r for r in self.results.values() if r["status"] == "FAIL"])
        skipped_tests = len([r for r in self.results.values() if r["status"] == "SKIP"])

        report = {
            "summary": {
                "total_tests": total_tests,
                "passed": passed_tests,
                "failed": failed_tests,
                "skipped": skipped_tests,
                "success_rate": f"{(passed_tests/total_tests)*100:.1f}%" if total_tests > 0 else "0%"
            },
            "test_results": self.results,
            "timestamp": datetime.now().isoformat()
        }

        print("\n" + "=" * 60)
        print("📊 TEST SUMMARY")
        print("=" * 60)
        print(f"Total Tests: {total_tests}")
        print(f"✅ Passed: {passed_tests}")
        print(f"❌ Failed: {failed_tests}")
        print(f"⚠️ Skipped: {skipped_tests}")
        print(f"Success Rate: {report['summary']['success_rate']}")

        if failed_tests > 0:
            print("\n❌ Failed Tests:")
            for test_name, result in self.results.items():
                if result["status"] == "FAIL":
                    print(f"   - {test_name}: {result['error']}")

        return report


async def main():
    """Main test runner"""
    import argparse

    parser = argparse.ArgumentParser(description="Test Signal Service Indicator Registry")
    parser.add_argument("--url", default="http://localhost:8003", help="Service base URL")
    parser.add_argument("--output", help="Save report to JSON file")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()

    async with IndicatorRegistryTester(args.url) as tester:
        try:
            report = await tester.run_all_tests()

            if args.output:
                with open(args.output, 'w') as f:
                    json.dump(report, f, indent=2)
                print(f"\n📄 Report saved to: {args.output}")

            if args.verbose:
                print("\n📋 DETAILED RESULTS:")
                print(json.dumps(report, indent=2))

            # Return appropriate exit code
            failed_tests = len([r for r in report["test_results"].values() if r["status"] == "FAIL"])
            return 0 if failed_tests == 0 else 1

        except KeyboardInterrupt:
            print("\n⚠️ Tests interrupted by user")
            return 1
        except Exception as e:
            print(f"\n❌ Test runner error: {e}")
            return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
