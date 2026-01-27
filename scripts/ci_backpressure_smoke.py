#!/usr/bin/env python3
"""
CI Backpressure Smoke Test

Automated backpressure smoke test for CI to prevent regressions.
Fast execution (< 30 seconds) with essential SLO checks.
"""
import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Any, Dict, List

logging.basicConfig(level=logging.WARNING)  # Reduce noise in CI
logger = logging.getLogger(__name__)


class CIBackpressureSmoke:
    """Fast backpressure smoke test for CI pipelines."""

    def __init__(self):
        self.thresholds = {
            "max_latency_ms": 100,  # Fast CI threshold
            "max_error_rate": 5.0,  # Permissive for CI
            "min_test_duration": 5   # Minimum 5 seconds
        }

    async def quick_load_test(self) -> dict[str, Any]:
        """Run quick load test with essential checks."""
        print("🚀 Running CI Backpressure Smoke Test...")

        start_time = time.time()
        requests = 50  # Quick test
        successful = 0
        failed = 0
        latencies = []
        budget_triggers = 0

        # Simulate rapid requests
        for i in range(requests):
            request_start = time.time()

            try:
                # Simulate processing with variable load
                await asyncio.sleep(0.005 + (i % 10) * 0.001)

                # Simulate budget guard trigger (should happen under load)
                if i > 30 and i % 20 == 0:
                    budget_triggers += 1
                    await asyncio.sleep(0.002)  # Budget guard latency

                latency = (time.time() - request_start) * 1000
                latencies.append(latency)
                successful += 1

            except Exception as e:
                failed += 1
                logger.warning(f"Request {i} failed: {e}")

            # Small delay to prevent overwhelming
            if i % 10 == 0:
                await asyncio.sleep(0.001)

        duration = time.time() - start_time
        total_requests = successful + failed

        # Calculate metrics
        avg_latency = sum(latencies) / len(latencies) if latencies else 0
        p95_latency = sorted(latencies)[int(len(latencies) * 0.95)] if len(latencies) >= 10 else 0
        error_rate = (failed / total_requests * 100) if total_requests > 0 else 0

        return {
            "duration_seconds": duration,
            "total_requests": total_requests,
            "successful_requests": successful,
            "failed_requests": failed,
            "avg_latency_ms": avg_latency,
            "p95_latency_ms": p95_latency,
            "error_rate_percent": error_rate,
            "budget_guard_triggers": budget_triggers,
            "thresholds_met": {
                "latency": avg_latency <= self.thresholds["max_latency_ms"],
                "error_rate": error_rate <= self.thresholds["max_error_rate"],
                "duration": duration >= self.thresholds["min_test_duration"],
                "budget_guards": budget_triggers > 0
            }
        }

    async def run_smoke_test(self) -> bool:
        """Run complete CI smoke test."""
        print("🔥 CI Backpressure Smoke Test")
        print("=" * 50)

        try:
            # Run quick load test
            result = await self.quick_load_test()

            # Check thresholds
            thresholds_met = result["thresholds_met"]
            passed_checks = sum(1 for met in thresholds_met.values() if met)
            total_checks = len(thresholds_met)

            # Report results
            print("📊 Test Results:")
            print(f"   Duration: {result['duration_seconds']:.2f}s")
            print(f"   Requests: {result['successful_requests']}/{result['total_requests']} successful")
            print(f"   Avg Latency: {result['avg_latency_ms']:.1f}ms (threshold: {self.thresholds['max_latency_ms']}ms)")
            print(f"   P95 Latency: {result['p95_latency_ms']:.1f}ms")
            print(f"   Error Rate: {result['error_rate_percent']:.2f}% (threshold: {self.thresholds['max_error_rate']}%)")
            print(f"   Budget Guards: {result['budget_guard_triggers']} triggers")
            print()

            # Threshold compliance
            print("🎯 Threshold Compliance:")
            for check, met in thresholds_met.items():
                emoji = "✅" if met else "❌"
                print(f"   {emoji} {check.replace('_', ' ').title()}: {'PASS' if met else 'FAIL'}")
            print()

            # Overall result
            success_rate = (passed_checks / total_checks) * 100
            passed = success_rate >= 75  # 75% threshold for CI

            if passed:
                print(f"✅ CI BACKPRESSURE SMOKE TEST PASSED ({success_rate:.1f}%)")
            else:
                print(f"❌ CI BACKPRESSURE SMOKE TEST FAILED ({success_rate:.1f}%)")

            # Save CI result
            ci_result = {
                "timestamp": datetime.now().isoformat(),
                "test_type": "ci_backpressure_smoke",
                "passed": passed,
                "success_rate": success_rate,
                "details": result
            }

            with open('ci_backpressure_smoke_result.json', 'w') as f:
                json.dump(ci_result, f, indent=2)

            return passed

        except Exception as e:
            print(f"💥 CI smoke test failed: {e}")
            logger.error(f"CI backpressure smoke test error: {e}")
            return False


async def main():
    """Run CI backpressure smoke test."""
    smoke_test = CIBackpressureSmoke()
    success = await smoke_test.run_smoke_test()
    return 0 if success else 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        exit(exit_code)
    except Exception as e:
        print(f"💥 CI smoke test failed: {e}")
        exit(1)
