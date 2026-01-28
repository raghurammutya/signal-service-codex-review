#!/usr/bin/env python3
"""
Subscription Latency Monitor - SUB_001 Hardening

Addresses latency margin concerns with comprehensive P95/P99 tracking:
- Real-time latency percentile monitoring
- SLA breach alerting before Phase 3 guardrails trigger
- Load-aware performance tracking for Day 2 streaming pressure
"""

import statistics
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any


@dataclass
class LatencyMetrics:
    """Comprehensive latency metrics with percentiles"""
    operation_type: str
    sample_count: int
    avg_ms: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    max_ms: float
    sla_breaches: int
    measurement_window_minutes: int
    timestamp: datetime = field(default_factory=datetime.now)

class SubscriptionLatencyMonitor:
    """
    Real-time latency monitoring for subscription operations

    Tracks P95/P99 to ensure Phase 3 SLA compliance under Day 2 streaming load:
    - <107ms P95 SLA enforcement
    - Early warning at 90ms P95
    - Load correlation analysis
    """

    def __init__(self, window_minutes: int = 15, max_samples: int = 1000):
        self.window_minutes = window_minutes
        self.max_samples = max_samples

        # Latency tracking per operation type
        self.latency_samples: dict[str, deque] = {
            "subscription_create": deque(maxlen=max_samples),
            "subscription_cancel": deque(maxlen=max_samples),
            "registry_lookup": deque(maxlen=max_samples),
            "user_subscriptions_query": deque(maxlen=max_samples),
            "migration_operation": deque(maxlen=max_samples)
        }

        # SLA thresholds
        self.sla_thresholds = {
            "p95_warning_ms": 90,   # Early warning before 107ms
            "p95_critical_ms": 107, # Phase 3 SLA limit
            "p99_critical_ms": 200, # P99 safety margin
            "avg_target_ms": 50     # Performance target
        }

        # Breach tracking
        self.breach_history: list[dict[str, Any]] = []
        self.current_load_level = "normal"  # normal, elevated, high

    async def record_latency(self, operation_type: str, latency_ms: float, metadata: dict[str, Any] = None):
        """Record operation latency with timestamp"""
        if operation_type not in self.latency_samples:
            return

        sample = {
            "latency_ms": latency_ms,
            "timestamp": datetime.now(),
            "metadata": metadata or {}
        }

        self.latency_samples[operation_type].append(sample)

        # Check for immediate SLA breaches
        await self._check_immediate_breach(operation_type, latency_ms, metadata)

    async def get_current_metrics(self, operation_type: str = None) -> dict[str, LatencyMetrics]:
        """Get current latency metrics for operations"""
        current_time = datetime.now()
        cutoff_time = current_time - timedelta(minutes=self.window_minutes)

        metrics = {}

        operations = [operation_type] if operation_type else self.latency_samples.keys()

        for op_type in operations:
            # Filter samples to current window
            recent_samples = [
                sample for sample in self.latency_samples[op_type]
                if sample["timestamp"] >= cutoff_time
            ]

            if not recent_samples:
                continue

            latencies = [sample["latency_ms"] for sample in recent_samples]

            metrics[op_type] = LatencyMetrics(
                operation_type=op_type,
                sample_count=len(latencies),
                avg_ms=statistics.mean(latencies),
                p50_ms=statistics.median(latencies),
                p95_ms=self._calculate_percentile(latencies, 95),
                p99_ms=self._calculate_percentile(latencies, 99),
                max_ms=max(latencies),
                sla_breaches=len([latency for latency in latencies if latency > self.sla_thresholds["p95_critical_ms"]]),
                measurement_window_minutes=self.window_minutes
            )

        return metrics

    async def analyze_load_correlation(self) -> dict[str, Any]:
        """Analyze latency correlation with load levels"""
        metrics = await self.get_current_metrics()

        # Determine current load level based on operation frequency
        total_ops_per_minute = sum(
            m.sample_count / self.window_minutes for m in metrics.values()
        )

        if total_ops_per_minute > 100:
            load_level = "high"
        elif total_ops_per_minute > 50:
            load_level = "elevated"
        else:
            load_level = "normal"

        self.current_load_level = load_level

        # Calculate load impact on latencies
        return {
            "current_load_level": load_level,
            "operations_per_minute": total_ops_per_minute,
            "latency_impact": {
                op_type: {
                    "avg_ms": metrics[op_type].avg_ms,
                    "p95_ms": metrics[op_type].p95_ms,
                    "sla_margin_ms": self.sla_thresholds["p95_critical_ms"] - metrics[op_type].p95_ms,
                    "sla_risk": "HIGH" if metrics[op_type].p95_ms > self.sla_thresholds["p95_warning_ms"] else "LOW"
                }
                for op_type in metrics
            },
            "day_2_readiness": {
                "streaming_pressure_tolerance": load_level != "high",
                "sla_safety_margin": min([
                    self.sla_thresholds["p95_critical_ms"] - m.p95_ms
                    for m in metrics.values()
                ]),
                "recommended_action": self._get_load_recommendation(load_level, metrics)
            }
        }


    async def generate_sla_compliance_report(self) -> dict[str, Any]:
        """Generate comprehensive SLA compliance report"""
        metrics = await self.get_current_metrics()
        load_analysis = await self.analyze_load_correlation()

        # Calculate overall compliance
        compliance_status = {}
        overall_compliant = True

        for op_type, metric in metrics.items():
            op_compliant = (
                metric.p95_ms < self.sla_thresholds["p95_critical_ms"] and
                metric.avg_ms < self.sla_thresholds["avg_target_ms"]
            )

            compliance_status[op_type] = {
                "sla_compliant": op_compliant,
                "p95_within_sla": metric.p95_ms < self.sla_thresholds["p95_critical_ms"],
                "avg_within_target": metric.avg_ms < self.sla_thresholds["avg_target_ms"],
                "breach_rate": metric.sla_breaches / max(1, metric.sample_count),
                "performance_grade": self._calculate_performance_grade(metric)
            }

            if not op_compliant:
                overall_compliant = False

        return {
            "report_timestamp": datetime.now().isoformat(),
            "measurement_window_minutes": self.window_minutes,
            "overall_sla_compliant": overall_compliant,
            "phase_3_guardrails_status": "MAINTAINED" if overall_compliant else "AT_RISK",
            "operation_compliance": compliance_status,
            "load_analysis": load_analysis,
            "sla_thresholds": self.sla_thresholds,
            "breach_history_count": len(self.breach_history),
            "recommendations": self._generate_recommendations(metrics, load_analysis)
        }

    def _calculate_percentile(self, values: list[float], percentile: int) -> float:
        """Calculate percentile value"""
        if not values:
            return 0.0

        sorted_values = sorted(values)
        index = (percentile / 100.0) * (len(sorted_values) - 1)

        if index.is_integer():
            return sorted_values[int(index)]
        lower = sorted_values[int(index)]
        upper = sorted_values[int(index) + 1]
        return lower + (upper - lower) * (index - int(index))

    async def _check_immediate_breach(self, operation_type: str, latency_ms: float, metadata: dict[str, Any]):
        """Check for immediate SLA breach and alert"""
        if latency_ms > self.sla_thresholds["p95_critical_ms"]:
            breach_record = {
                "operation_type": operation_type,
                "latency_ms": latency_ms,
                "threshold_ms": self.sla_thresholds["p95_critical_ms"],
                "timestamp": datetime.now().isoformat(),
                "metadata": metadata,
                "load_level": self.current_load_level
            }

            self.breach_history.append(breach_record)

            # Alert - in production would send to monitoring system
            print(f"🚨 SLA BREACH ALERT: {operation_type} took {latency_ms:.1f}ms (SLA: {self.sla_thresholds['p95_critical_ms']}ms)")

    def _calculate_performance_grade(self, metrics: LatencyMetrics) -> str:
        """Calculate performance grade for operation"""
        if metrics.p95_ms < self.sla_thresholds["avg_target_ms"]:
            return "EXCELLENT"
        if metrics.p95_ms < self.sla_thresholds["p95_warning_ms"]:
            return "GOOD"
        if metrics.p95_ms < self.sla_thresholds["p95_critical_ms"]:
            return "ACCEPTABLE"
        return "POOR"

    def _get_load_recommendation(self, load_level: str, metrics: dict[str, LatencyMetrics]) -> str:
        """Get recommendation based on load and performance"""
        if load_level == "high":
            return "REDUCE_LOAD: Consider throttling before Day 2 streaming deployment"
        if load_level == "elevated":
            max_p95 = max(m.p95_ms for m in metrics.values())
            if max_p95 > self.sla_thresholds["p95_warning_ms"]:
                return "MONITOR_CLOSELY: Approaching SLA limits under elevated load"
            return "PROCEED_CAUTIOUSLY: Load elevated but performance acceptable"
        return "PROCEED: Performance good under normal load"

    def _generate_recommendations(self, metrics: dict[str, LatencyMetrics], load_analysis: dict[str, Any]) -> list[str]:
        """Generate operational recommendations"""
        recommendations = []

        # Check for P95 approaching limits
        for op_type, metric in metrics.items():
            if metric.p95_ms > self.sla_thresholds["p95_warning_ms"]:
                recommendations.append(f"OPTIMIZE_{op_type.upper()}: P95 latency approaching SLA limit")

        # Load-based recommendations
        if load_analysis["current_load_level"] == "high":
            recommendations.append("IMPLEMENT_THROTTLING: High load detected before Day 2 streaming")

        # Day 2 readiness
        if not load_analysis["day_2_readiness"]["streaming_pressure_tolerance"]:
            recommendations.append("DELAY_STREAM_001: System not ready for additional streaming load")

        if not recommendations:
            recommendations.append("PROCEED_TO_DAY_2: All latency metrics within acceptable ranges")

        return recommendations

# Global monitor instance for subscription service
subscription_latency_monitor = SubscriptionLatencyMonitor()

async def record_subscription_latency(operation: str, latency_ms: float, **metadata):
    """Convenience function to record latency"""
    await subscription_latency_monitor.record_latency(operation, latency_ms, metadata)

async def get_latency_dashboard() -> dict[str, Any]:
    """Get current latency dashboard data"""
    return await subscription_latency_monitor.generate_sla_compliance_report()
