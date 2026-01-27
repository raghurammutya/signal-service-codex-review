#!/usr/bin/env python3
"""
Session 5B SLA Monitoring Integration

Integrates selective invalidation logic with Phase 3 SLA monitoring matrix,
Prometheus metrics for invalidation volume, and cache miss ratio tracking.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from prometheus_client import Counter, Gauge, Histogram

logger = logging.getLogger(__name__)

# Phase 3 SLA Monitoring Metrics for Session 5B Cache Invalidation
class Session5BSLAMetrics:
    """Prometheus metrics aligned with Phase 3 SLA monitoring matrix"""

    def __init__(self):
        # Cache Invalidation Volume Metrics (Phase 3 SLA Requirement)
        self.cache_invalidation_volume_total = Counter(
            'session_5b_cache_invalidation_volume_total',
            'Total cache invalidation operations performed',
            ['service', 'invalidation_type', 'selective']
        )

        self.cache_invalidation_keys_total = Counter(
            'session_5b_cache_invalidation_keys_total',
            'Total cache keys invalidated',
            ['service', 'cache_type', 'pattern']
        )

        # Cache Miss Ratio Monitoring (SLA: >95% hit rate)
        self.cache_hit_rate = Gauge(
            'session_5b_cache_hit_rate',
            'Cache hit rate percentage by service and cache type',
            ['service', 'cache_type']
        )

        self.cache_miss_ratio = Gauge(
            'session_5b_cache_miss_ratio',
            'Cache miss ratio percentage by service and cache type',
            ['service', 'cache_type']
        )

        # Selective Invalidation Efficiency (Phase 3 Performance)
        self.selective_invalidation_efficiency = Gauge(
            'session_5b_selective_invalidation_efficiency',
            'Efficiency of selective vs full invalidation (keys saved %)',
            ['service', 'trigger_type']
        )

        # Cache Recovery Latency (Phase 3 SLA: <30s invalidation completion)
        self.cache_recovery_latency = Histogram(
            'session_5b_cache_recovery_latency_seconds',
            'Time from invalidation to cache repopulation',
            ['service', 'cache_type', 'recovery_type'],
            buckets=[0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0]
        )

        # SLA Compliance Tracking
        self.sla_cache_invalidation_completion = Histogram(
            'session_5b_sla_cache_invalidation_completion_seconds',
            'Cache invalidation completion time vs 30s SLA',
            ['service', 'sla_met'],
            buckets=[1.0, 5.0, 10.0, 20.0, 30.0, 45.0, 60.0]
        )

        # SLA Violations Counter
        self.sla_violations_total = Counter(
            'session_5b_sla_violations_total',
            'SLA violations in cache invalidation operations',
            ['violation_type', 'severity', 'service']
        )

        # Cache Coordination Performance (Session 5B specific)
        self.coordination_latency = Histogram(
            'session_5b_coordination_latency_seconds',
            'End-to-end coordination latency across all cache services',
            ['coordination_type', 'services_count'],
            buckets=[0.01, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0]
        )

        # Stale Data Detection and Recovery
        self.stale_data_detection_total = Counter(
            'session_5b_stale_data_detection_total',
            'Stale data instances detected and recovered',
            ['service', 'data_type', 'staleness_severity']
        )

        # Cache Pattern Effectiveness
        self.cache_pattern_effectiveness = Gauge(
            'session_5b_cache_pattern_effectiveness',
            'Effectiveness of cache invalidation patterns (precision %)',
            ['service', 'pattern_type']
        )

@dataclass
class SLAViolation:
    """SLA violation tracking"""
    violation_type: str
    severity: str  # critical, major, minor
    service: str
    threshold_value: float
    actual_value: float
    timestamp: datetime
    metadata: dict[str, Any] = None

class Session5BSLAMonitor:
    """Monitors Session 5B cache operations against Phase 3 SLA requirements"""

    def __init__(self):
        self.metrics = Session5BSLAMetrics()

        # Phase 3 SLA Thresholds from monitoring matrix
        self.sla_thresholds = {
            "cache_invalidation_completion_seconds": 30.0,    # <30s completion
            "cache_hit_rate_minimum": 95.0,                   # >95% hit rate
            "coordination_latency_p95_seconds": 0.1,          # <100ms P95
            "stale_data_recovery_seconds": 5.0,               # <5s stale data recovery
            "selective_invalidation_efficiency": 80.0         # >80% efficiency vs full
        }

        # Violation tracking
        self.recent_violations = []
        self.max_violation_history = 1000

    def record_cache_invalidation(self, service: str, invalidation_type: str,
                                selective: bool, keys_invalidated: int,
                                duration_seconds: float, cache_patterns: dict[str, int]):
        """Record cache invalidation with SLA monitoring"""

        # Basic invalidation volume metrics
        self.metrics.cache_invalidation_volume_total.labels(
            service=service,
            invalidation_type=invalidation_type,
            selective=str(selective).lower()
        ).inc()

        # Record keys invalidated by cache type and pattern
        for cache_type, key_count in cache_patterns.items():
            self.metrics.cache_invalidation_keys_total.labels(
                service=service,
                cache_type=cache_type,
                pattern="selective" if selective else "full"
            ).inc(key_count)

        # SLA compliance check: Cache invalidation completion time
        sla_met = duration_seconds <= self.sla_thresholds["cache_invalidation_completion_seconds"]

        self.metrics.sla_cache_invalidation_completion.labels(
            service=service,
            sla_met=str(sla_met).lower()
        ).observe(duration_seconds)

        # Record SLA violation if applicable
        if not sla_met:
            violation = SLAViolation(
                violation_type="cache_invalidation_completion",
                severity="major" if duration_seconds > 45.0 else "minor",
                service=service,
                threshold_value=self.sla_thresholds["cache_invalidation_completion_seconds"],
                actual_value=duration_seconds,
                timestamp=datetime.now(),
                metadata={"invalidation_type": invalidation_type, "keys_count": keys_invalidated}
            )

            self._record_sla_violation(violation)

        logger.debug(f"Recorded cache invalidation: {service} {invalidation_type} "
                    f"({keys_invalidated} keys in {duration_seconds:.3f}s, SLA: {sla_met})")

    def record_cache_hit_miss_ratio(self, service: str, cache_type: str,
                                  hits: int, misses: int):
        """Record cache hit/miss ratios with SLA monitoring"""

        total_requests = hits + misses
        if total_requests == 0:
            return

        hit_rate = (hits / total_requests) * 100
        miss_ratio = (misses / total_requests) * 100

        # Update metrics
        self.metrics.cache_hit_rate.labels(
            service=service,
            cache_type=cache_type
        ).set(hit_rate)

        self.metrics.cache_miss_ratio.labels(
            service=service,
            cache_type=cache_type
        ).set(miss_ratio)

        # SLA compliance check: Cache hit rate
        sla_met = hit_rate >= self.sla_thresholds["cache_hit_rate_minimum"]

        if not sla_met:
            violation = SLAViolation(
                violation_type="cache_hit_rate",
                severity="major" if hit_rate < 90.0 else "minor",
                service=service,
                threshold_value=self.sla_thresholds["cache_hit_rate_minimum"],
                actual_value=hit_rate,
                timestamp=datetime.now(),
                metadata={"cache_type": cache_type, "total_requests": total_requests}
            )

            self._record_sla_violation(violation)

        logger.debug(f"Cache hit rate: {service}:{cache_type} = {hit_rate:.1f}% (SLA: {sla_met})")

    def record_selective_invalidation_efficiency(self, service: str, trigger_type: str,
                                               selective_keys: int, full_keys: int):
        """Record selective invalidation efficiency"""

        if full_keys == 0:
            efficiency = 100.0
        else:
            efficiency = max(0, (1 - selective_keys / full_keys) * 100)

        self.metrics.selective_invalidation_efficiency.labels(
            service=service,
            trigger_type=trigger_type
        ).set(efficiency)

        # SLA compliance check: Selective invalidation efficiency
        sla_met = efficiency >= self.sla_thresholds["selective_invalidation_efficiency"]

        if not sla_met:
            violation = SLAViolation(
                violation_type="selective_invalidation_efficiency",
                severity="minor",
                service=service,
                threshold_value=self.sla_thresholds["selective_invalidation_efficiency"],
                actual_value=efficiency,
                timestamp=datetime.now(),
                metadata={"trigger_type": trigger_type, "selective_keys": selective_keys, "full_keys": full_keys}
            )

            self._record_sla_violation(violation)

        logger.debug(f"Selective invalidation efficiency: {service}:{trigger_type} = {efficiency:.1f}% (SLA: {sla_met})")

    def record_cache_recovery(self, service: str, cache_type: str, recovery_type: str,
                            recovery_duration_seconds: float):
        """Record cache recovery latency with SLA monitoring"""

        self.metrics.cache_recovery_latency.labels(
            service=service,
            cache_type=cache_type,
            recovery_type=recovery_type
        ).observe(recovery_duration_seconds)

        # SLA compliance for stale data recovery
        if recovery_type == "stale_data_recovery":
            sla_met = recovery_duration_seconds <= self.sla_thresholds["stale_data_recovery_seconds"]

            if not sla_met:
                violation = SLAViolation(
                    violation_type="stale_data_recovery",
                    severity="critical" if recovery_duration_seconds > 10.0 else "major",
                    service=service,
                    threshold_value=self.sla_thresholds["stale_data_recovery_seconds"],
                    actual_value=recovery_duration_seconds,
                    timestamp=datetime.now(),
                    metadata={"cache_type": cache_type}
                )

                self._record_sla_violation(violation)

    def record_coordination_latency(self, coordination_type: str, services_count: int,
                                  latency_seconds: float):
        """Record end-to-end coordination latency with P95 SLA monitoring"""

        self.metrics.coordination_latency.labels(
            coordination_type=coordination_type,
            services_count=str(services_count)
        ).observe(latency_seconds)

        # Note: P95 SLA check would be done by Prometheus alerting rules
        # but we can track immediate violations for very high latency
        if latency_seconds > self.sla_thresholds["coordination_latency_p95_seconds"] * 5:  # 5x threshold
            violation = SLAViolation(
                violation_type="coordination_latency_extreme",
                severity="critical",
                service="session_5b_coordinator",
                threshold_value=self.sla_thresholds["coordination_latency_p95_seconds"],
                actual_value=latency_seconds,
                timestamp=datetime.now(),
                metadata={"coordination_type": coordination_type, "services_count": services_count}
            )

            self._record_sla_violation(violation)

    def record_stale_data_detection(self, service: str, data_type: str,
                                  staleness_severity: str, recovery_duration: float):
        """Record stale data detection and recovery"""

        self.metrics.stale_data_detection_total.labels(
            service=service,
            data_type=data_type,
            staleness_severity=staleness_severity
        ).inc()

        # Record recovery time
        self.record_cache_recovery(service, data_type, "stale_data_recovery", recovery_duration)

        logger.info(f"Stale data detected and recovered: {service}:{data_type} "
                   f"(severity: {staleness_severity}, recovery: {recovery_duration:.3f}s)")

    def record_cache_pattern_effectiveness(self, service: str, pattern_type: str,
                                         target_keys: int, invalidated_keys: int):
        """Record cache pattern effectiveness (precision)"""

        if target_keys == 0:
            effectiveness = 100.0
        else:
            effectiveness = min(100.0, (invalidated_keys / target_keys) * 100)

        self.metrics.cache_pattern_effectiveness.labels(
            service=service,
            pattern_type=pattern_type
        ).set(effectiveness)

        logger.debug(f"Cache pattern effectiveness: {service}:{pattern_type} = {effectiveness:.1f}%")

    def _record_sla_violation(self, violation: SLAViolation):
        """Record SLA violation with Prometheus metrics and tracking"""

        # Prometheus counter
        self.metrics.sla_violations_total.labels(
            violation_type=violation.violation_type,
            severity=violation.severity,
            service=violation.service
        ).inc()

        # Internal tracking
        self.recent_violations.append(violation)

        # Keep only recent violations
        if len(self.recent_violations) > self.max_violation_history:
            self.recent_violations.pop(0)

        # Log violation
        logger.warning(f"SLA violation: {violation.violation_type} on {violation.service} "
                      f"(severity: {violation.severity}, threshold: {violation.threshold_value}, "
                      f"actual: {violation.actual_value})")

    def get_sla_compliance_summary(self) -> dict[str, Any]:
        """Get SLA compliance summary for monitoring dashboards"""

        # Count recent violations by type and severity
        recent_time = datetime.now() - timedelta(hours=1)
        recent_violations = [v for v in self.recent_violations if v.timestamp >= recent_time]

        violations_by_type = {}
        violations_by_severity = {}

        for violation in recent_violations:
            violations_by_type[violation.violation_type] = violations_by_type.get(violation.violation_type, 0) + 1
            violations_by_severity[violation.severity] = violations_by_severity.get(violation.severity, 0) + 1

        return {
            "total_violations_last_hour": len(recent_violations),
            "violations_by_type": violations_by_type,
            "violations_by_severity": violations_by_severity,
            "sla_thresholds": self.sla_thresholds,
            "compliance_status": "degraded" if len(recent_violations) > 0 else "compliant"
        }

# Global SLA monitor instance
_session_5b_sla_monitor: Session5BSLAMonitor | None = None

def get_session_5b_sla_monitor() -> Session5BSLAMonitor:
    """Get or create Session 5B SLA monitor"""
    global _session_5b_sla_monitor

    if _session_5b_sla_monitor is None:
        _session_5b_sla_monitor = Session5BSLAMonitor()
        logger.info("Session 5B SLA Monitor initialized")

    return _session_5b_sla_monitor

# Convenience functions for quick SLA monitoring
def record_invalidation_sla(service: str, invalidation_type: str, selective: bool,
                          keys_invalidated: int, duration_seconds: float,
                          cache_patterns: dict[str, int]):
    """Quick function to record invalidation with SLA monitoring"""
    monitor = get_session_5b_sla_monitor()
    monitor.record_cache_invalidation(service, invalidation_type, selective,
                                    keys_invalidated, duration_seconds, cache_patterns)

def record_hit_miss_sla(service: str, cache_type: str, hits: int, misses: int):
    """Quick function to record hit/miss ratios with SLA monitoring"""
    monitor = get_session_5b_sla_monitor()
    monitor.record_cache_hit_miss_ratio(service, cache_type, hits, misses)

def record_coordination_sla(coordination_type: str, services_count: int, latency_seconds: float):
    """Quick function to record coordination latency with SLA monitoring"""
    monitor = get_session_5b_sla_monitor()
    monitor.record_coordination_latency(coordination_type, services_count, latency_seconds)
