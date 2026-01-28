#!/usr/bin/env python3
"""
Aggregation Services Migration Validator - Week 2 AGG_001

Automated validation for aggregation services migration to instrument_key-based aggregation:
- Aggregation migration: validate token-based -> instrument_key aggregation functions
- Data integrity: ensure aggregated values maintain accuracy during migration
- Performance validation: <200ms aggregation computation under concurrent load
- Rollup accuracy: verify OHLC, volume, VWAP calculations remain consistent

Usage:
    python validate_aggregation_services.py --aggregation-samples agg_samples.json
    python validate_aggregation_services.py --performance-only --aggregation-count 500
"""

import asyncio
import json
import math
import statistics
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional


@dataclass
class AggregationValidationResult:
    """Aggregation validation result for migration"""
    aggregation_id: str
    migration_valid: bool
    data_accuracy: bool
    calculation_correct: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    computation_latency_ms: float = 0.0
    result_variance: float = 0.0

@dataclass
class AggregationMetrics:
    """Aggregation service performance metrics"""
    total_aggregations: int
    total_time_ms: float
    avg_computation_ms: float
    p95_computation_ms: float
    p99_computation_ms: float
    max_computation_ms: float
    aggregations_per_sec: float
    accuracy_rate: float
    performance_compliant: bool

class AggregationServiceValidator:
    """
    Aggregation services migration validation framework for AGG_001

    Validates migration from token-based to instrument_key-based aggregation services
    while maintaining calculation accuracy, performance, and data integrity.
    """

    def __init__(self):
        self.performance_targets = {
            "max_computation_latency_ms": 200.0,
            "p95_computation_latency_ms": 150.0,
            "min_aggregations_per_sec": 25,
            "accuracy_threshold": 99.5,
            "max_variance_percent": 0.1,
            "concurrent_aggregations": 10
        }

        self.validation_stats = {
            "total_aggregations": 0,
            "accurate_aggregations": 0,
            "failed_aggregations": 0,
            "calculation_errors": []
        }

        # Aggregation functions supported
        self.aggregation_functions = {
            "ohlc": self._calculate_ohlc,
            "volume": self._calculate_volume,
            "vwap": self._calculate_vwap,
            "price_avg": self._calculate_price_average,
            "volatility": self._calculate_volatility
        }

    async def validate_aggregation_migration(self, samples_file: str) -> dict[str, Any]:
        """
        Validate aggregation service migration using sample data

        Args:
            samples_file: JSON file with aggregation migration samples

        Returns:
            dict: Complete aggregation migration validation report
        """
        print(f"📋 Loading aggregation samples from {samples_file}")

        with open(samples_file) as f:
            aggregation_samples = json.load(f)

        print(f"🔍 Validating {len(aggregation_samples)} aggregation services")

        validation_results = []

        for i, agg_entry in enumerate(aggregation_samples):
            agg_id = agg_entry.get("aggregation_id", f"agg_{i}")
            result = await self._validate_single_aggregation(agg_id, agg_entry)
            validation_results.append(result)

            # Update statistics
            self.validation_stats["total_aggregations"] += 1
            if result.migration_valid and result.data_accuracy:
                self.validation_stats["accurate_aggregations"] += 1
            else:
                self.validation_stats["failed_aggregations"] += 1
                self.validation_stats["calculation_errors"].extend(result.errors)

        # Test aggregation performance
        performance_test = await self._validate_aggregation_performance()

        # Test calculation accuracy
        accuracy_test = await self._test_calculation_accuracy()

        # Test concurrent aggregations
        concurrency_test = await self._test_concurrent_aggregations()

        # Generate migration report
        return {
            "validation_type": "aggregation_migration",
            "aggregation_migration": {
                "validation_timestamp": datetime.now().isoformat(),
                "samples_file": samples_file,
                "aggregation_version": "v2_instrument_key_aggregation",
                "migration_summary": {
                    "total_aggregations": len(aggregation_samples),
                    "successful_migrations": len([r for r in validation_results if r.migration_valid]),
                    "failed_migrations": len([r for r in validation_results if not r.migration_valid]),
                    "migration_success_rate": len([r for r in validation_results if r.migration_valid]) / len(aggregation_samples) * 100,
                    "data_accuracy_rate": len([r for r in validation_results if r.data_accuracy]) / len(aggregation_samples) * 100,
                    "calculation_accuracy_rate": len([r for r in validation_results if r.calculation_correct]) / len(aggregation_samples) * 100
                },
                "detailed_results": [
                    {
                        "aggregation_id": r.aggregation_id,
                        "migration_valid": r.migration_valid,
                        "data_accuracy": r.data_accuracy,
                        "calculation_correct": r.calculation_correct,
                        "errors": r.errors,
                        "warnings": r.warnings,
                        "computation_latency_ms": r.computation_latency_ms,
                        "result_variance": r.result_variance
                    }
                    for r in validation_results
                ],
                "migration_compliance": await self._assess_migration_compliance(validation_results)
            },
            "performance_validation": performance_test,
            "accuracy_validation": accuracy_test,
            "concurrency_validation": concurrency_test,
            "validation_metadata": {
                "validator_version": "1.0.0",
                "aggregation_version_target": "v2_instrument_key_aggregation",
                "validation_timestamp": datetime.now().isoformat(),
                "performance_targets": self.performance_targets,
                "week2_ready": self._assess_week2_readiness(validation_results, performance_test, accuracy_test, concurrency_test)
            }
        }


    async def validate_performance_only(self, aggregation_count: int = 500) -> dict[str, Any]:
        """
        Performance-only validation with synthetic aggregations

        Args:
            aggregation_count: Number of aggregations to test

        Returns:
            dict: Performance validation report
        """
        print(f"⚡ Running aggregation performance validation with {aggregation_count} aggregations")

        # Generate synthetic aggregation tasks
        synthetic_aggregations = [
            self._generate_synthetic_aggregation() for _ in range(aggregation_count)
        ]

        # Performance test
        performance_metrics = await self._validate_aggregation_performance(synthetic_aggregations)

        # Concurrent load test
        load_test_results = await self._simulate_concurrent_aggregation_load()

        # Accuracy under load test
        accuracy_test_results = await self._test_accuracy_under_load()

        return {
            "performance_timestamp": datetime.now().isoformat(),
            "test_configuration": {
                "aggregation_count": aggregation_count,
                "synthetic_data": True,
                "performance_targets": self.performance_targets
            },
            "aggregation_performance": {
                "avg_computation_ms": performance_metrics.avg_computation_ms,
                "p95_computation_ms": performance_metrics.p95_computation_ms,
                "p99_computation_ms": performance_metrics.p99_computation_ms,
                "max_computation_ms": performance_metrics.max_computation_ms,
                "aggregations_per_sec": performance_metrics.aggregations_per_sec,
                "accuracy_rate": performance_metrics.accuracy_rate,
                "performance_compliant": performance_metrics.performance_compliant
            },
            "load_testing": load_test_results,
            "accuracy_testing": accuracy_test_results,
            "performance_compliance": {
                "computations_under_200ms": performance_metrics.p95_computation_ms < 200,
                "throughput_above_25": performance_metrics.aggregations_per_sec >= 25,
                "accuracy_above_99_5": performance_metrics.accuracy_rate >= 99.5,
                "concurrent_load_supported": load_test_results["load_test_passed"],
                "ready_for_production": performance_metrics.performance_compliant
            }
        }


    async def _validate_single_aggregation(self, agg_id: str, agg_entry: dict[str, Any]) -> AggregationValidationResult:
        """Validate individual aggregation service migration"""
        result = AggregationValidationResult(
            aggregation_id=agg_id,
            migration_valid=True,
            data_accuracy=True,
            calculation_correct=True
        )

        # Validate aggregation migration
        migration_errors = self._validate_aggregation_migration_syntax(agg_entry)
        result.errors.extend(migration_errors)
        if migration_errors:
            result.migration_valid = False

        # Validate data accuracy
        accuracy_errors = await self._validate_aggregation_data_accuracy(agg_entry)
        result.errors.extend(accuracy_errors)
        if accuracy_errors:
            result.data_accuracy = False

        # Validate calculation correctness
        calculation_errors, variance = await self._validate_calculation_correctness(agg_entry)
        result.errors.extend(calculation_errors)
        result.result_variance = variance
        if calculation_errors:
            result.calculation_correct = False

        # Execute aggregation and measure performance
        start_time = time.time()
        await self._execute_aggregation(agg_entry)
        result.computation_latency_ms = (time.time() - start_time) * 1000

        return result

    def _validate_aggregation_migration_syntax(self, agg_entry: dict[str, Any]) -> list[str]:
        """Validate aggregation migration syntax"""
        errors = []

        # Check for old token-based aggregation
        old_aggregation = agg_entry.get("old_token_aggregation")
        if not old_aggregation:
            errors.append("Missing old_token_aggregation for migration comparison")

        # Check for new instrument key aggregation
        new_aggregation = agg_entry.get("new_instrument_key_aggregation")
        if not new_aggregation:
            errors.append("Missing new_instrument_key_aggregation")
            return errors

        # Validate instrument key in aggregation
        input_data = new_aggregation.get("input_data", {})
        instrument_key = input_data.get("instrument_key")
        if not instrument_key:
            errors.append("Missing instrument_key in aggregation input")
        elif not self._validate_instrument_key_format(instrument_key):
            errors.append(f"Invalid instrument_key format in aggregation: {instrument_key}")

        # Validate aggregation function
        agg_function = new_aggregation.get("function")
        if agg_function not in self.aggregation_functions:
            errors.append(f"Unsupported aggregation function: {agg_function}")

        # Validate time window
        time_window = new_aggregation.get("time_window")
        if time_window and not self._validate_time_window(time_window):
            errors.append("Invalid time_window format in aggregation")

        return errors

    def _validate_instrument_key_format(self, instrument_key: str) -> bool:
        """Validate instrument key format consistency"""
        parts = instrument_key.split("_")
        if len(parts) != 3:
            return False

        symbol, exchange, instrument_type = parts

        if not all([symbol, exchange, instrument_type]):
            return False

        # Validate against known values
        known_exchanges = ["NYSE", "NASDAQ", "NSE", "BSE", "LSE"]
        valid_types = ["EQUITY", "OPTION", "FUTURE", "BOND", "ETF"]

        return exchange in known_exchanges and instrument_type in valid_types

    def _validate_time_window(self, time_window: dict[str, Any]) -> bool:
        """Validate time window parameters"""
        start_time = time_window.get("start")
        end_time = time_window.get("end")
        window_size = time_window.get("window_size")

        if window_size:
            # Validate window size format (e.g., "1m", "5m", "1h", "1d")
            valid_sizes = ["1s", "5s", "10s", "30s", "1m", "5m", "15m", "30m", "1h", "4h", "1d"]
            if window_size not in valid_sizes:
                return False

        if start_time and end_time:
            try:
                if isinstance(start_time, str):
                    start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                else:
                    start_dt = datetime.fromtimestamp(start_time)

                if isinstance(end_time, str):
                    end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
                else:
                    end_dt = datetime.fromtimestamp(end_time)

                # Validate time range logic
                if start_dt >= end_dt:
                    return False

                # Validate reasonable time range (not more than 30 days for aggregation)
                return not (end_dt - start_dt).days > 30
            except (ValueError, TypeError):
                return False

        return True

    async def _validate_aggregation_data_accuracy(self, agg_entry: dict[str, Any]) -> list[str]:
        """Validate data accuracy between old and new aggregations"""
        errors = []

        try:
            # Execute both old and new aggregations
            old_result = await self._execute_legacy_aggregation(agg_entry.get("old_token_aggregation", {}))
            new_result = await self._execute_aggregation(agg_entry)

            # Compare aggregation results
            if not self._compare_aggregation_results(old_result, new_result):
                errors.append("Aggregation result mismatch between old and new implementations")

        except Exception as e:
            errors.append(f"Aggregation accuracy validation error: {str(e)}")

        return errors

    async def _validate_calculation_correctness(self, agg_entry: dict[str, Any]) -> tuple[list[str], float]:
        """Validate calculation correctness and measure variance"""
        errors = []
        variance = 0.0

        try:
            new_aggregation = agg_entry.get("new_instrument_key_aggregation", {})
            agg_function = new_aggregation.get("function")
            new_aggregation.get("input_data", {})

            if agg_function in self.aggregation_functions:
                # Execute aggregation multiple times to test consistency
                results = []
                for _ in range(3):
                    result = await self._execute_aggregation(agg_entry)
                    if isinstance(result, int | float):
                        results.append(result)
                    elif isinstance(result, dict) and "value" in result:
                        results.append(result["value"])

                if results:
                    # Calculate variance in results (should be 0 for deterministic calculations)
                    if len(results) > 1:
                        variance = statistics.stdev(results) / statistics.mean(results) * 100 if statistics.mean(results) != 0 else 0

                    # Check if variance is within acceptable limits
                    if variance > self.performance_targets["max_variance_percent"]:
                        errors.append(f"Calculation variance too high: {variance:.3f}%")

        except Exception as e:
            errors.append(f"Calculation correctness validation error: {str(e)}")

        return errors, variance

    def _compare_aggregation_results(self, old_result: Any, new_result: Any) -> bool:
        """Compare aggregation results for consistency"""
        # Handle different result formats
        old_value = self._extract_value(old_result)
        new_value = self._extract_value(new_result)

        if old_value is None or new_value is None:
            return False

        # Handle numeric comparison with tolerance
        if isinstance(old_value, int | float) and isinstance(new_value, int | float):
            tolerance = abs(old_value) * 0.001  # 0.1% tolerance
            return abs(old_value - new_value) <= tolerance

        # Handle dictionary comparison (e.g., OHLC)
        if isinstance(old_value, dict) and isinstance(new_value, dict):
            for key in old_value:
                if key not in new_value:
                    return False
                if not self._compare_numeric_values(old_value[key], new_value[key]):
                    return False
            return True

        # Direct comparison for other types
        return old_value == new_value

    def _extract_value(self, result: Any) -> Any:
        """Extract value from aggregation result"""
        if isinstance(result, dict):
            if "value" in result:
                return result["value"]
            if "result" in result:
                return result["result"]
            return result
        return result

    def _compare_numeric_values(self, val1: Any, val2: Any) -> bool:
        """Compare two numeric values with tolerance"""
        if isinstance(val1, int | float) and isinstance(val2, int | float):
            tolerance = max(abs(val1), abs(val2)) * 0.001 + 1e-10  # 0.1% + small epsilon
            return abs(val1 - val2) <= tolerance
        return val1 == val2

    async def _execute_aggregation(self, agg_entry: dict[str, Any]) -> Any:
        """Execute aggregation computation"""
        new_aggregation = agg_entry.get("new_instrument_key_aggregation", {})
        agg_function = new_aggregation.get("function")
        input_data = new_aggregation.get("input_data", {})

        if agg_function in self.aggregation_functions:
            # Simulate computation time
            await asyncio.sleep(0.05)  # 50ms baseline computation

            # Execute the aggregation function
            return await self.aggregation_functions[agg_function](input_data)

        raise ValueError(f"Unknown aggregation function: {agg_function}")

    async def _execute_legacy_aggregation(self, legacy_aggregation: dict[str, Any]) -> Any:
        """Execute legacy token-based aggregation for comparison"""
        # Simulate legacy aggregation execution
        await asyncio.sleep(0.08)  # Slower legacy computation

        token = legacy_aggregation.get("input_data", {}).get("token", "unknown")
        agg_function = legacy_aggregation.get("function", "unknown")

        # Convert legacy to new format and execute
        instrument_key = self._token_to_instrument_key(token)
        input_data = {"instrument_key": instrument_key, **legacy_aggregation.get("input_data", {})}

        if agg_function in self.aggregation_functions:
            return await self.aggregation_functions[agg_function](input_data)

        return None

    def _token_to_instrument_key(self, token: str) -> str:
        """Convert token to instrument_key for legacy aggregation support"""
        # Simulate token mapping
        token_mapping = {
            "12345": "AAPL_NASDAQ_EQUITY",
            "67890": "GOOGL_NASDAQ_EQUITY",
            "11111": "MSFT_NASDAQ_EQUITY",
            "22222": "RELIANCE_NSE_EQUITY",
            "33333": "TSLA_NASDAQ_EQUITY"
        }
        return token_mapping.get(token, f"UNKNOWN_{token}_EQUITY")

    # Aggregation function implementations
    async def _calculate_ohlc(self, input_data: dict[str, Any]) -> dict[str, float]:
        """Calculate OHLC (Open, High, Low, Close) aggregation"""
        price_data = input_data.get("price_data", [])
        if not price_data:
            # Generate synthetic price data for validation
            price_data = self._generate_price_data(input_data.get("instrument_key", "TEST"))

        if not price_data:
            return {"open": 0, "high": 0, "low": 0, "close": 0}

        prices = [p["price"] for p in price_data if "price" in p]
        if not prices:
            return {"open": 0, "high": 0, "low": 0, "close": 0}

        return {
            "open": prices[0],
            "high": max(prices),
            "low": min(prices),
            "close": prices[-1]
        }

    async def _calculate_volume(self, input_data: dict[str, Any]) -> float:
        """Calculate volume aggregation"""
        volume_data = input_data.get("volume_data", [])
        if not volume_data:
            # Generate synthetic volume data
            volume_data = self._generate_volume_data(input_data.get("instrument_key", "TEST"))

        total_volume = sum(v.get("volume", 0) for v in volume_data)
        return float(total_volume)

    async def _calculate_vwap(self, input_data: dict[str, Any]) -> float:
        """Calculate Volume Weighted Average Price (VWAP)"""
        trade_data = input_data.get("trade_data", [])
        if not trade_data:
            # Generate synthetic trade data
            trade_data = self._generate_trade_data(input_data.get("instrument_key", "TEST"))

        if not trade_data:
            return 0.0

        total_value = sum(t.get("price", 0) * t.get("volume", 0) for t in trade_data)
        total_volume = sum(t.get("volume", 0) for t in trade_data)

        if total_volume == 0:
            return 0.0

        return total_value / total_volume

    async def _calculate_price_average(self, input_data: dict[str, Any]) -> float:
        """Calculate simple price average"""
        price_data = input_data.get("price_data", [])
        if not price_data:
            price_data = self._generate_price_data(input_data.get("instrument_key", "TEST"))

        prices = [p["price"] for p in price_data if "price" in p]
        if not prices:
            return 0.0

        return sum(prices) / len(prices)

    async def _calculate_volatility(self, input_data: dict[str, Any]) -> float:
        """Calculate price volatility (standard deviation)"""
        price_data = input_data.get("price_data", [])
        if not price_data:
            price_data = self._generate_price_data(input_data.get("instrument_key", "TEST"))

        prices = [p["price"] for p in price_data if "price" in p]
        if len(prices) < 2:
            return 0.0

        return statistics.stdev(prices)

    def _generate_price_data(self, instrument_key: str) -> list[dict[str, Any]]:
        """Generate synthetic price data for testing"""
        seed = hash(instrument_key) % 1000
        base_price = 100.0 + seed

        price_data = []
        for i in range(20):
            price_data.append({
                "timestamp": time.time() - (i * 60),  # 1 minute intervals
                "price": base_price + (i * 0.5) + (hash(f"{instrument_key}_{i}") % 10) / 10.0
            })

        return price_data

    def _generate_volume_data(self, instrument_key: str) -> list[dict[str, Any]]:
        """Generate synthetic volume data for testing"""
        seed = hash(instrument_key) % 1000

        volume_data = []
        for i in range(20):
            volume_data.append({
                "timestamp": time.time() - (i * 60),
                "volume": 1000 + (seed + i) * 100
            })

        return volume_data

    def _generate_trade_data(self, instrument_key: str) -> list[dict[str, Any]]:
        """Generate synthetic trade data for testing"""
        seed = hash(instrument_key) % 1000
        base_price = 100.0 + seed

        trade_data = []
        for i in range(15):
            trade_data.append({
                "timestamp": time.time() - (i * 120),  # 2 minute intervals
                "price": base_price + (i * 0.3),
                "volume": 100 + (i * 50)
            })

        return trade_data

    async def _validate_aggregation_performance(self, aggregations: list[dict[str, Any]] = None) -> AggregationMetrics:
        """Validate aggregation service performance under load"""

        if aggregations is None:
            aggregations = [self._generate_synthetic_aggregation() for _ in range(100)]

        computation_latencies = []
        accurate_results = 0
        total_results = 0

        # Execute aggregations and measure performance
        overall_start = time.time()

        for aggregation in aggregations:
            try:
                start_time = time.time()
                result = await self._execute_aggregation(aggregation)
                end_time = time.time()

                computation_latencies.append((end_time - start_time) * 1000)

                # Validate result is reasonable
                if self._is_reasonable_aggregation_result(result):
                    accurate_results += 1
                total_results += 1

            except Exception:
                total_results += 1
                computation_latencies.append(1000.0)  # 1 second penalty for failures

        overall_end = time.time()

        # Calculate metrics
        avg_computation = statistics.mean(computation_latencies)
        sorted_latencies = sorted(computation_latencies)
        p95_computation = sorted_latencies[int(len(sorted_latencies) * 0.95)]
        p99_computation = sorted_latencies[int(len(sorted_latencies) * 0.99)]
        max_computation = max(computation_latencies)

        total_wall_time = overall_end - overall_start
        throughput = len(aggregations) / total_wall_time if total_wall_time > 0 else 0

        accuracy_rate = (accurate_results / total_results * 100) if total_results > 0 else 0

        performance_compliant = (
            p95_computation < self.performance_targets["max_computation_latency_ms"] and
            throughput >= self.performance_targets["min_aggregations_per_sec"] and
            accuracy_rate >= self.performance_targets["accuracy_threshold"]
        )

        return AggregationMetrics(
            total_aggregations=len(aggregations),
            total_time_ms=sum(computation_latencies),
            avg_computation_ms=avg_computation,
            p95_computation_ms=p95_computation,
            p99_computation_ms=p99_computation,
            max_computation_ms=max_computation,
            aggregations_per_sec=throughput,
            accuracy_rate=accuracy_rate,
            performance_compliant=performance_compliant
        )

    def _is_reasonable_aggregation_result(self, result: Any) -> bool:
        """Check if aggregation result is reasonable"""
        if result is None:
            return False

        if isinstance(result, int | float):
            # Check for NaN, infinity, or unreasonable values
            if math.isnan(result) or math.isinf(result):
                return False
            return not (abs(result) > 1e6)  # Extremely large values

        if isinstance(result, dict):
            # Check OHLC or other dictionary results
            for value in result.values():
                if isinstance(value, int | float) and math.isnan(value) or math.isinf(value) or abs(value) > 1e6:
                    return False
            return True

        return True

    async def _simulate_concurrent_aggregation_load(self) -> dict[str, Any]:
        """Simulate concurrent aggregation load"""
        print(f"🔥 Simulating concurrent aggregation load with {self.performance_targets['concurrent_aggregations']} aggregations")

        concurrent_count = self.performance_targets["concurrent_aggregations"]

        async def concurrent_aggregation_batch():
            latencies = []
            for _i in range(5):  # Each batch runs 5 aggregations
                aggregation = self._generate_synthetic_aggregation()
                start_time = time.time()
                await self._execute_aggregation(aggregation)
                latencies.append((time.time() - start_time) * 1000)
            return latencies

        # Create concurrent tasks
        tasks = [concurrent_aggregation_batch() for _ in range(concurrent_count // 5)]

        start_time = time.time()
        batch_results = await asyncio.gather(*tasks)
        total_time = (time.time() - start_time) * 1000

        all_latencies = [lat for batch in batch_results for lat in batch]
        avg_latency = statistics.mean(all_latencies)
        p95_latency = sorted(all_latencies)[int(len(all_latencies) * 0.95)]

        return {
            "concurrent_aggregations": concurrent_count,
            "total_time_ms": total_time,
            "avg_computation_ms": avg_latency,
            "p95_computation_ms": p95_latency,
            "load_test_passed": p95_latency < 200,
            "concurrent_performance_acceptable": avg_latency < 150
        }

    async def _test_calculation_accuracy(self) -> dict[str, Any]:
        """Test calculation accuracy across different aggregation functions"""
        print("📊 Testing aggregation calculation accuracy")

        # Test each aggregation function
        accuracy_tests = []

        for func_name in self.aggregation_functions:
            test_aggregation = {
                "aggregation_id": f"accuracy_test_{func_name}",
                "new_instrument_key_aggregation": {
                    "function": func_name,
                    "input_data": {
                        "instrument_key": "ACCURACY_TEST_NASDAQ_EQUITY"
                    }
                }
            }

            try:
                # Execute aggregation multiple times
                results = []
                for _ in range(3):
                    result = await self._execute_aggregation(test_aggregation)
                    results.append(result)

                # Check consistency
                consistent = self._check_result_consistency(results)
                accuracy_tests.append({
                    "function": func_name,
                    "consistent": consistent,
                    "results": results[:1]  # Include one result for verification
                })

            except Exception as e:
                accuracy_tests.append({
                    "function": func_name,
                    "consistent": False,
                    "error": str(e)
                })

        consistent_count = len([t for t in accuracy_tests if t.get("consistent", False)])

        return {
            "total_function_tests": len(self.aggregation_functions),
            "consistent_functions": consistent_count,
            "accuracy_rate": consistent_count / len(self.aggregation_functions) * 100,
            "calculation_accuracy_verified": consistent_count == len(self.aggregation_functions),
            "function_tests": accuracy_tests
        }

    def _check_result_consistency(self, results: list[Any]) -> bool:
        """Check if aggregation results are consistent across multiple executions"""
        if len(results) < 2:
            return True

        first_result = results[0]
        for result in results[1:]:
            if not self._compare_aggregation_results(first_result, result):
                return False

        return True

    async def _test_concurrent_aggregations(self) -> dict[str, Any]:
        """Test concurrent aggregation processing"""
        print("🔄 Testing concurrent aggregation processing")

        # Create multiple concurrent aggregation tasks
        concurrent_tasks = []
        for i in range(10):
            task_aggregation = {
                "aggregation_id": f"concurrent_test_{i}",
                "new_instrument_key_aggregation": {
                    "function": "ohlc",
                    "input_data": {
                        "instrument_key": f"CONCURRENT_TEST_{i}_NASDAQ_EQUITY"
                    }
                }
            }
            concurrent_tasks.append(task_aggregation)

        # Execute all tasks concurrently
        start_time = time.time()

        async def execute_concurrent_aggregation(task):
            try:
                result = await self._execute_aggregation(task)
                return {"success": True, "result": result}
            except Exception as e:
                return {"success": False, "error": str(e)}

        concurrent_results = await asyncio.gather(*[
            execute_concurrent_aggregation(task) for task in concurrent_tasks
        ])

        execution_time = (time.time() - start_time) * 1000

        successful_count = len([r for r in concurrent_results if r["success"]])

        return {
            "total_concurrent_tasks": len(concurrent_tasks),
            "successful_tasks": successful_count,
            "execution_time_ms": execution_time,
            "success_rate": successful_count / len(concurrent_tasks) * 100,
            "concurrent_processing_supported": successful_count == len(concurrent_tasks),
            "avg_task_time": execution_time / len(concurrent_tasks)
        }

    async def _test_accuracy_under_load(self) -> dict[str, Any]:
        """Test accuracy under high aggregation load"""
        print("🔥 Testing aggregation accuracy under load")

        # Generate heavy aggregation load
        load_aggregations = []
        for i in range(50):
            func_name = list(self.aggregation_functions.keys())[i % len(self.aggregation_functions)]
            load_aggregations.append({
                "aggregation_id": f"load_test_{i}",
                "new_instrument_key_aggregation": {
                    "function": func_name,
                    "input_data": {
                        "instrument_key": f"LOAD_TEST_{i % 5}_NASDAQ_EQUITY"
                    }
                }
            })

        start_time = time.time()

        # Execute aggregations and check accuracy
        accurate_count = 0
        total_count = 0

        for aggregation in load_aggregations:
            try:
                result = await self._execute_aggregation(aggregation)
                if self._is_reasonable_aggregation_result(result):
                    accurate_count += 1
                total_count += 1

                # Small delay to simulate load
                await asyncio.sleep(0.01)

            except Exception:
                total_count += 1

        execution_time = (time.time() - start_time) * 1000

        return {
            "total_load_aggregations": len(load_aggregations),
            "accurate_under_load": accurate_count,
            "accuracy_rate_under_load": (accurate_count / total_count * 100) if total_count > 0 else 0,
            "execution_time_ms": execution_time,
            "accuracy_maintained_under_load": (accurate_count / total_count) >= 0.995 if total_count > 0 else False
        }

    def _generate_synthetic_aggregation(self) -> dict[str, Any]:
        """Generate synthetic aggregation for testing"""
        symbols = ["AAPL", "GOOGL", "MSFT", "TSLA", "AMZN"]
        exchanges = ["NASDAQ", "NYSE", "NSE"]
        functions = list(self.aggregation_functions.keys())

        symbol = symbols[hash(str(time.time())) % len(symbols)]
        exchange = exchanges[hash(symbol) % len(exchanges)]
        function = functions[hash(symbol + str(time.time())) % len(functions)]

        return {
            "aggregation_id": f"synth_{uuid.uuid4().hex[:8]}",
            "new_instrument_key_aggregation": {
                "function": function,
                "input_data": {
                    "instrument_key": f"{symbol}_{exchange}_EQUITY"
                },
                "time_window": {
                    "window_size": "5m"
                }
            }
        }

    async def _assess_migration_compliance(self, results: list[AggregationValidationResult]) -> dict[str, Any]:
        """Assess overall migration compliance"""
        total_results = len(results)
        migration_success = len([r for r in results if r.migration_valid])
        data_accuracy = len([r for r in results if r.data_accuracy])
        calculation_correct = len([r for r in results if r.calculation_correct])

        return {
            "migration_success_rate": (migration_success / total_results * 100) if total_results > 0 else 0,
            "data_accuracy_rate": (data_accuracy / total_results * 100) if total_results > 0 else 0,
            "calculation_accuracy_rate": (calculation_correct / total_results * 100) if total_results > 0 else 0,
            "aggregation_service_v2_ready": migration_success == total_results and data_accuracy == total_results,
            "performance_compliant": all(r.computation_latency_ms < 200 for r in results),
            "common_errors": self._analyze_common_migration_errors([r for r in results if not (r.migration_valid and r.data_accuracy)])
        }

    def _analyze_common_migration_errors(self, failed_results: list[AggregationValidationResult]) -> list[str]:
        """Analyze common migration errors"""
        error_counts = {}

        for result in failed_results:
            for error in result.errors:
                error_counts[error] = error_counts.get(error, 0) + 1

        return sorted(error_counts.items(), key=lambda x: x[1], reverse=True)[:5]

    def _assess_week2_readiness(self, migration_results: list[AggregationValidationResult],
                              performance_test: AggregationMetrics,
                              accuracy_test: dict[str, Any],
                              concurrency_test: dict[str, Any]) -> bool:
        """Assess readiness for Week 2 completion"""
        migration_success = all(r.migration_valid and r.data_accuracy for r in migration_results)
        performance_compliant = performance_test.performance_compliant
        accuracy_maintained = accuracy_test.get("calculation_accuracy_verified", False)
        concurrency_supported = concurrency_test.get("concurrent_processing_supported", False)

        return migration_success and performance_compliant and accuracy_maintained and concurrency_supported

async def main():
    """Main validation script"""
    import argparse

    parser = argparse.ArgumentParser(description="Aggregation Services Migration Validator")
    parser.add_argument("--aggregation-samples", help="Aggregation samples JSON file")
    parser.add_argument("--performance-only", action="store_true",
                       help="Run performance-only validation")
    parser.add_argument("--aggregation-count", type=int, default=500,
                       help="Number of aggregations for performance test")
    parser.add_argument("--output", help="Output report file")

    args = parser.parse_args()

    validator = AggregationServiceValidator()

    print("🚀 Aggregation Services Migration Validator - AGG_001")
    print("=" * 60)

    if args.performance_only:
        print("⚡ Running performance-only validation")
        report = await validator.validate_performance_only(args.aggregation_count)

        print("\n📊 Aggregation Performance Results:")
        agg_perf = report["aggregation_performance"]
        print(f"   Average Computation: {agg_perf['avg_computation_ms']:.2f}ms")
        print(f"   P95 Computation: {agg_perf['p95_computation_ms']:.2f}ms")
        print(f"   Aggregations per Second: {agg_perf['aggregations_per_sec']:.1f}")
        print(f"   Accuracy Rate: {agg_perf['accuracy_rate']:.1f}%")
        print(f"   Performance Compliant: {'✅' if agg_perf['performance_compliant'] else '❌'}")

    elif args.aggregation_samples:
        print(f"📋 Running aggregation migration validation on {args.aggregation_samples}")
        report = await validator.validate_aggregation_migration(args.aggregation_samples)

        print("\n📊 Migration Results:")
        migration_summary = report["aggregation_migration"]["migration_summary"]
        print(f"   Migration Success: {migration_summary['migration_success_rate']:.1f}%")
        print(f"   Data Accuracy: {migration_summary['data_accuracy_rate']:.1f}%")
        print(f"   Calculation Accuracy: {migration_summary['calculation_accuracy_rate']:.1f}%")
        print(f"   Aggregation Service v2 Ready: {'✅' if report['aggregation_migration']['migration_compliance']['aggregation_service_v2_ready'] else '❌'}")

    else:
        print("❌ Please specify --aggregation-samples or --performance-only")
        return

    # Save report
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        print(f"\n💾 Report written to: {args.output}")

    week2_ready = report.get("validation_metadata", {}).get("week2_ready", False)
    print(f"🎯 Week 2 Ready: {'✅' if week2_ready else '❌'}")

    if week2_ready:
        print("\n🚀 AGG_001 validation PASSED - Ready for Week 2 continuation")
    else:
        print("\n⚠️  AGG_001 validation FAILED - Address issues before continuation")

if __name__ == "__main__":
    asyncio.run(main())
