#!/usr/bin/env python3
"""
Registry Integration Metrics

Prometheus metrics for registry integration monitoring, alerting,
and SLA compliance tracking according to Phase 3 requirements.
"""

import logging
import time
from typing import Any

from prometheus_client import Counter, Enum, Gauge, Histogram

logger = logging.getLogger(__name__)

# Registry Integration Metrics
registry_events_total = Counter(
    'signal_registry_events_total',
    'Total registry events processed',
    ['event_type', 'status']
)

registry_event_processing_duration = Histogram(
    'signal_registry_event_processing_seconds',
    'Time spent processing registry events',
    ['event_type'],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]
)

registry_cache_invalidations_total = Counter(
    'signal_registry_cache_invalidations_total',
    'Total cache invalidations triggered by registry events',
    ['cache_type', 'status']
)

registry_greeks_recalculations_total = Counter(
    'signal_registry_greeks_recalculations_total',
    'Total Greeks recalculations triggered by registry',
    ['status']
)

registry_api_calls_total = Counter(
    'signal_registry_api_calls_total',
    'Total calls to registry APIs',
    ['endpoint', 'status']
)

registry_api_duration = Histogram(
    'signal_registry_api_duration_seconds',
    'Duration of registry API calls',
    ['endpoint'],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

# Circuit Breaker Metrics
registry_circuit_breaker_state = Enum(
    'signal_registry_circuit_breaker_state',
    'Current state of registry circuit breaker',
    ['service'],
    states=['closed', 'open', 'half_open']
)

registry_circuit_breaker_trips_total = Counter(
    'signal_registry_circuit_breaker_trips_total',
    'Total circuit breaker trips',
    ['reason']
)

registry_fallback_activations_total = Counter(
    'signal_registry_fallback_activations_total',
    'Total fallback activations when registry unavailable',
    ['fallback_type', 'reason']
)

# Shadow Mode Metrics
registry_shadow_comparisons_total = Counter(
    'signal_registry_shadow_comparisons_total',
    'Total shadow mode comparisons',
    ['result_match']
)

registry_shadow_latency_comparison = Histogram(
    'signal_registry_shadow_latency_difference_seconds',
    'Latency difference between registry and legacy (registry - legacy)',
    buckets=[-5.0, -1.0, -0.5, -0.1, -0.05, 0.0, 0.05, 0.1, 0.5, 1.0, 5.0]
)

registry_shadow_match_rate = Gauge(
    'signal_registry_shadow_match_rate',
    'Current shadow mode match rate percentage'
)

# Cache Performance Metrics
registry_cache_hit_rate = Gauge(
    'signal_registry_cache_hit_rate',
    'Registry client cache hit rate',
    ['cache_type']
)

registry_cache_size = Gauge(
    'signal_registry_cache_size',
    'Number of entries in registry cache',
    ['cache_type']
)

registry_cache_operations_total = Counter(
    'signal_registry_cache_operations_total',
    'Total cache operations',
    ['operation', 'cache_type', 'result']
)

# Data Freshness Metrics
registry_data_freshness_seconds = Gauge(
    'signal_registry_data_freshness_seconds',
    'Age of data from registry in seconds',
    ['data_type', 'instrument']
)

registry_data_staleness_violations_total = Counter(
    'signal_registry_data_staleness_violations_total',
    'Total data staleness SLA violations',
    ['data_type', 'sla_threshold']
)

# Integration Health Metrics
registry_integration_health = Gauge(
    'signal_registry_integration_health',
    'Overall health of registry integration (1=healthy, 0=unhealthy)'
)

registry_service_availability = Gauge(
    'signal_registry_service_availability',
    'Registry service availability percentage'
)

# SLA Compliance Metrics (Phase 3 requirements)
registry_sla_latency_p95 = Gauge(
    'signal_registry_sla_latency_p95_seconds',
    'Registry API P95 latency for SLA compliance'
)

registry_sla_availability = Gauge(
    'signal_registry_sla_availability_percentage',
    'Registry availability for SLA compliance'
)

registry_sla_violations_total = Counter(
    'signal_registry_sla_violations_total',
    'Total SLA violations',
    ['sla_type', 'severity']
)

# Error Tracking
registry_errors_total = Counter(
    'signal_registry_errors_total',
    'Total registry integration errors',
    ['error_type', 'component', 'severity']
)

class RegistryMetricsCollector:
    """Collects and manages registry integration metrics"""

    def __init__(self):
        self.start_time = time.time()
        self.last_metrics_update = time.time()

        # SLA thresholds from Phase 3 plan
        self.sla_thresholds = {
            "latency_p95_ms": 100,      # <100ms P95 latency
            "availability_pct": 99.9,   # >99.9% availability
            "event_lag_ms": 1000,       # <1s event propagation
            "cache_hit_rate_pct": 95    # >95% cache hit rate
        }

    def record_event_processing(self, event_type: str, processing_time: float, success: bool):
        """Record event processing metrics"""
        status = "success" if success else "error"

        registry_events_total.labels(
            event_type=event_type,
            status=status
        ).inc()

        registry_event_processing_duration.labels(
            event_type=event_type
        ).observe(processing_time)

        # Check SLA compliance
        if processing_time > (self.sla_thresholds["event_lag_ms"] / 1000):
            registry_sla_violations_total.labels(
                sla_type="event_processing_latency",
                severity="warning"
            ).inc()

    def record_api_call(self, endpoint: str, duration: float, success: bool):
        """Record registry API call metrics"""
        status = "success" if success else "error"

        registry_api_calls_total.labels(
            endpoint=endpoint,
            status=status
        ).inc()

        registry_api_duration.labels(
            endpoint=endpoint
        ).observe(duration)

        # Update SLA latency tracking
        current_p95 = registry_api_duration.labels(endpoint=endpoint)._value.quantile(0.95)[1] * 1000
        registry_sla_latency_p95.set(current_p95)

        # Check latency SLA
        if current_p95 > self.sla_thresholds["latency_p95_ms"]:
            registry_sla_violations_total.labels(
                sla_type="api_latency_p95",
                severity="critical"
            ).inc()

    def record_cache_operation(self, operation: str, cache_type: str, success: bool):
        """Record cache operation metrics"""
        result = "hit" if success and operation == "get" else "miss" if operation == "get" else "success" if success else "error"

        registry_cache_operations_total.labels(
            operation=operation,
            cache_type=cache_type,
            result=result
        ).inc()

    def update_cache_metrics(self, cache_type: str, hit_rate: float, size: int):
        """Update cache performance metrics"""
        registry_cache_hit_rate.labels(cache_type=cache_type).set(hit_rate)
        registry_cache_size.labels(cache_type=cache_type).set(size)

        # Check cache hit rate SLA
        if hit_rate < (self.sla_thresholds["cache_hit_rate_pct"] / 100):
            registry_sla_violations_total.labels(
                sla_type="cache_hit_rate",
                severity="warning"
            ).inc()

    def record_shadow_comparison(self, registry_latency: float, legacy_latency: float, match: bool):
        """Record shadow mode comparison metrics"""
        match_label = "match" if match else "mismatch"

        registry_shadow_comparisons_total.labels(
            result_match=match_label
        ).inc()

        latency_diff = registry_latency - legacy_latency
        registry_shadow_latency_comparison.observe(latency_diff)

        # Calculate rolling match rate
        total_comparisons = registry_shadow_comparisons_total._value.sum()
        matches = registry_shadow_comparisons_total.labels(result_match="match")._value._value

        if total_comparisons > 0:
            match_rate = (matches / total_comparisons) * 100
            registry_shadow_match_rate.set(match_rate)

    def record_circuit_breaker_trip(self, reason: str, new_state: str):
        """Record circuit breaker state change"""
        registry_circuit_breaker_trips_total.labels(reason=reason).inc()
        registry_circuit_breaker_state.labels(service="registry").state(new_state)

        if new_state == "open":
            registry_sla_violations_total.labels(
                sla_type="circuit_breaker_trip",
                severity="critical"
            ).inc()

    def record_fallback_activation(self, fallback_type: str, reason: str):
        """Record fallback activation"""
        registry_fallback_activations_total.labels(
            fallback_type=fallback_type,
            reason=reason
        ).inc()

        registry_sla_violations_total.labels(
            sla_type="fallback_activation",
            severity="major"
        ).inc()

    def record_cache_invalidation(self, cache_type: str, count: int, success: bool):
        """Record cache invalidation metrics"""
        status = "success" if success else "error"

        for _ in range(count):
            registry_cache_invalidations_total.labels(
                cache_type=cache_type,
                status=status
            ).inc()

    def record_greeks_recalculation(self, success: bool):
        """Record Greeks recalculation metrics"""
        status = "success" if success else "error"
        registry_greeks_recalculations_total.labels(status=status).inc()

    def record_error(self, error_type: str, component: str, severity: str = "error"):
        """Record error metrics"""
        registry_errors_total.labels(
            error_type=error_type,
            component=component,
            severity=severity
        ).inc()

        # Critical errors trigger SLA violations
        if severity == "critical":
            registry_sla_violations_total.labels(
                sla_type="critical_error",
                severity="critical"
            ).inc()

    def update_service_health(self, healthy: bool, availability_pct: float):
        """Update overall service health metrics"""
        registry_integration_health.set(1 if healthy else 0)
        registry_service_availability.set(availability_pct)
        registry_sla_availability.set(availability_pct)

        # Check availability SLA
        if availability_pct < self.sla_thresholds["availability_pct"]:
            registry_sla_violations_total.labels(
                sla_type="service_availability",
                severity="critical"
            ).inc()

    def update_data_freshness(self, data_type: str, instrument: str, age_seconds: float):
        """Update data freshness metrics"""
        registry_data_freshness_seconds.labels(
            data_type=data_type,
            instrument=instrument
        ).set(age_seconds)

        # Check staleness thresholds
        staleness_thresholds = {
            "market_data": 30,      # 30s for market data
            "greeks": 60,          # 1 minute for Greeks
            "chain_data": 300,     # 5 minutes for chain data
        }

        threshold = staleness_thresholds.get(data_type, 300)
        if age_seconds > threshold:
            registry_data_staleness_violations_total.labels(
                data_type=data_type,
                sla_threshold=str(threshold)
            ).inc()

    def get_sla_summary(self) -> dict[str, Any]:
        """Get current SLA compliance summary"""
        try:
            current_p95 = registry_sla_latency_p95._value._value
            current_availability = registry_sla_availability._value._value
            current_cache_hit_rate = registry_cache_hit_rate.labels(cache_type="registry")._value._value * 100

            return {
                "latency_p95_ms": current_p95,
                "latency_sla_met": current_p95 < self.sla_thresholds["latency_p95_ms"],
                "availability_pct": current_availability,
                "availability_sla_met": current_availability >= self.sla_thresholds["availability_pct"],
                "cache_hit_rate_pct": current_cache_hit_rate,
                "cache_sla_met": current_cache_hit_rate >= self.sla_thresholds["cache_hit_rate_pct"],
                "overall_sla_compliance": (
                    current_p95 < self.sla_thresholds["latency_p95_ms"] and
                    current_availability >= self.sla_thresholds["availability_pct"] and
                    current_cache_hit_rate >= self.sla_thresholds["cache_hit_rate_pct"]
                )
            }
        except Exception:
            return {"error": "Unable to calculate SLA summary"}

# Global metrics collector instance
_metrics_collector: RegistryMetricsCollector | None = None

def get_registry_metrics() -> RegistryMetricsCollector:
    """Get or create registry metrics collector"""
    global _metrics_collector

    if _metrics_collector is None:
        _metrics_collector = RegistryMetricsCollector()
        logger.info("Registry metrics collector initialized")

    return _metrics_collector

# Convenience functions for common metrics operations
def record_registry_event(event_type: str, processing_time: float, success: bool = True):
    """Record registry event processing"""
    get_registry_metrics().record_event_processing(event_type, processing_time, success)

def record_registry_api_call(endpoint: str, duration: float, success: bool = True):
    """Record registry API call"""
    get_registry_metrics().record_api_call(endpoint, duration, success)

def record_shadow_mode_result(registry_latency: float, legacy_latency: float, match: bool):
    """Record shadow mode comparison result"""
    get_registry_metrics().record_shadow_comparison(registry_latency, legacy_latency, match)

def record_cache_invalidation_batch(cache_type: str, count: int, success: bool = True):
    """Record batch cache invalidation"""
    get_registry_metrics().record_cache_invalidation(cache_type, count, success)

def update_integration_health(healthy: bool, availability_pct: float = 100.0):
    """Update overall integration health"""
    get_registry_metrics().update_service_health(healthy, availability_pct)
